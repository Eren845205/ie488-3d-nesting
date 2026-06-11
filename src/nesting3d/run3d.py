"""run3d.py — CLI for the 3D voxel nesting pipeline (PLAN_3D.md §3, §5).

Examples:
  python -m src.nesting3d.run3d                            # default scenario, DBLF + SA
  python -m src.nesting3d.run3d --scenario all --export-stl
  python -m src.nesting3d.run3d --algo dblf --scenario stress
  python -m src.nesting3d.run3d --scenario numune --export-stl --check-clearance
      # numune default'ları: taban 335x335, pitch 2.5, margin 1 (>=1mm boşluk),
      # slice voxelization, z limiti 600 mm (hoca makinesi, 2026-06-11)

Outputs (results/):
  nesting3d_<scenario>.png           final layout render
  sa3d_convergence_<scenario>.png    SA convergence (when SA runs)
  nesting3d_result_<scenario>.stl    combined STL scene (--export-stl)
  summary_3d.csv / summary_3d.md     metric table for the run
"""

import argparse
import csv
import json
import time
from pathlib import Path

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.clearance import min_clearance
from src.nesting3d.dblf import dblf, plates_first_key, tower_order_key
from src.nesting3d.export_stl import export_scene, placed_meshes
from src.nesting3d.models import (NUMUNE_ORIENTATIONS,
                                  NUMUNE_ORIENTATIONS_HYBRID,
                                  NUMUNE_ORIENTATIONS_TILT, NUMUNE_PLATES,
                                  SCENARIOS, model_set)
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.visualize3d import render_convergence, render_layout
from src.nesting3d.voxelize import expand_quantities

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"

# Senaryo-bazlı default'lar.  numune = hoca makinesi (2026-06-11 feedback):
# taban 335x335 mm, max z 600 mm, parça arası min 1 mm (margin dilation),
# yüksek yüz sayılı gerçek STL'lerde slice voxelization.
SCENARIO_DEFAULTS = {
    "numune": {"plate": 335.0, "pitch": 2.5, "margin": 1,
               "voxel_method": "slice"},
}
BASE_DEFAULTS = {"plate": 220.0, "pitch": 220.0 / 64, "margin": 0,
                 "voxel_method": "subdivide"}
MAX_Z_MM = 600.0


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="3D voxel nesting (PLAN_3D.md)")
    p.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="default")
    p.add_argument("--algo", choices=["dblf", "sa"], default="sa",
                   help="sa = DBLF baseline + SA improvement (default)")
    p.add_argument("--pitch", type=float, default=None,
                   help=f"voxel kenarı mm (default {BASE_DEFAULTS['pitch']:.2f}, "
                        "numune senaryosunda 2.5)")
    p.add_argument("--plate", type=float, default=None,
                   help="kare taban kenarı mm (default 220, numune 335)")
    p.add_argument("--rotations", type=int, default=4,
                   choices=[1, 2, 3, 4, 6, 8],
                   help="poz sayısı; 5+ = 180°/270° + ters çevirme "
                        "(plaka geçişmesi için, toz yataklı üretim)")
    p.add_argument("--margin", type=int, default=None,
                   help="parça arası boşluk (voxel, dilation; numune default 1 "
                        "= garantili >=1 mm gerçek mesafe)")
    p.add_argument("--voxel-method", choices=["subdivide", "slice"],
                   default=None,
                   help="slice = yüksek yüz sayılı gerçek STL'ler için hızlı "
                        "ve hacim-doğru yol (numune default'u)")
    p.add_argument("--max-z", type=float, default=MAX_Z_MM,
                   help="makine z limiti mm — aşılırsa uyarı + z_ok=False")
    p.add_argument("--check-clearance", action="store_true",
                   help="devoxelize edilmiş orijinal mesh'lerde parça arası "
                        "min mesafeyi ölç ve raporla")
    p.add_argument("--start", choices=["volume", "plates-first", "tower"],
                   default="volume",
                   help="DBLF başlangıç sırası: volume = hacim-azalan; "
                        "plates-first = plakalar önce + aynı tip ardışık; "
                        "tower = DP-optimal çapraz-tip plaka istif sırası "
                        "(geçişme matrisinden, numune ≤170 denemesi)")
    p.add_argument("--orient", choices=["flat", "hybrid", "tilt"],
                   default="flat",
                   help="numune plaka poz kısıtı: flat = tüm plakalar yatık; "
                        "hybrid = kısa plakalara (n3/n6) dik de serbest; "
                        "tilt = hibrit + eğik 'ekmek rafı' pozları "
                        "(20-35°, <=170 denemesi)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--iters", type=int, default=1000)
    p.add_argument("--export-stl", action="store_true")
    p.add_argument("--out", type=Path, default=RESULTS_DIR)
    return p.parse_args(argv)


def resolve_params(args, scenario: str) -> dict:
    """CLI'da verilmeyen parametreleri senaryo default'larından çöz."""
    d = {**BASE_DEFAULTS, **SCENARIO_DEFAULTS.get(scenario, {})}
    return {
        "plate": args.plate if args.plate is not None else d["plate"],
        "pitch": args.pitch if args.pitch is not None else d["pitch"],
        "margin": args.margin if args.margin is not None else d["margin"],
        "voxel_method": (args.voxel_method if args.voxel_method is not None
                         else d["voxel_method"]),
    }


def run_scenario(scenario: str, args) -> list[dict]:
    """Run one scenario; returns summary rows (dicts)."""
    prm = resolve_params(args, scenario)
    pitch, plate = prm["pitch"], prm["plate"]
    parts = expand_quantities(
        model_set(scenario), pitch,
        n_orientations=args.rotations, margin=prm["margin"],
        method=prm["voxel_method"],
        orientation_overrides=(
            {"flat": NUMUNE_ORIENTATIONS,
             "hybrid": NUMUNE_ORIENTATIONS_HYBRID,
             "tilt": NUMUNE_ORIENTATIONS_TILT}[args.orient]
            if scenario == "numune" else None),
    )
    # margin: yatay boşluk grid dilation'da, dikey boşluk z_clearance'ta
    bin_factory = lambda: Bin3D(plate, plate, pitch,
                                z_clearance=prm["margin"])
    parts_by_id = {p.id: p for p in parts}
    rows = []

    print(f"\n=== Senaryo: {scenario} — {len(parts)} parça "
          f"(taban {plate:.0f}x{plate:.0f} mm, pitch {pitch:.2f}, "
          f"margin {prm['margin']} voxel, max z {args.max_z:.0f} mm) ===")

    if args.start == "plates-first":
        order_key = plates_first_key(NUMUNE_PLATES)
    elif args.start == "tower":
        order_key = tower_order_key(parts, NUMUNE_PLATES, bin_factory)
    else:
        order_key = None

    t0 = time.perf_counter()
    base_placements, base_bin = dblf(parts, bin_factory, order_key=order_key)
    dblf_ms = (time.perf_counter() - t0) * 1000
    print(f"DBLF baseline : yükseklik {base_bin.max_height_mm():6.1f} mm  "
          f"density {base_bin.packing_density():.3f}  ({dblf_ms:.0f} ms)")
    rows.append({
        "scenario": scenario, "algo": "dblf", "parts": len(parts),
        "height_mm": round(base_bin.max_height_mm(), 2),
        "density": round(base_bin.packing_density(), 4),
        "time_s": round(dblf_ms / 1000, 2), "iters": 0,
        "z_ok": base_bin.max_height_mm() <= args.max_z,
    })
    placements, bin3d, suffix = base_placements, base_bin, "dblf"

    if args.algo == "sa":
        t0 = time.perf_counter()
        res = simulated_annealing_3d(
            parts, bin_factory, seed=args.seed, iterations=args.iters,
            order_key=order_key,
        )
        sa_s = time.perf_counter() - t0
        gain = res.baseline_height_mm - res.best_height_mm
        print(f"SA ({args.iters} iter): yükseklik {res.best_height_mm:6.1f} mm  "
              f"density {res.best_density:.3f}  ({sa_s:.0f} s)  "
              f"kazanç {gain:+.1f} mm")
        rows.append({
            "scenario": scenario, "algo": "sa", "parts": len(parts),
            "height_mm": round(res.best_height_mm, 2),
            "density": round(res.best_density, 4),
            "time_s": round(sa_s, 2), "iters": args.iters,
            "z_ok": res.best_height_mm <= args.max_z,
        })
        placements, bin3d, suffix = res.placements, res.bin3d, "sa"
        render_convergence(
            res.history, res.baseline_height_mm,
            args.out / f"sa3d_convergence_{scenario}.png",
            title=f"SA yakınsama — {scenario} ({len(parts)} parça)",
        )

    if bin3d.max_height_mm() > args.max_z:
        print(f"UYARI         : yükseklik {bin3d.max_height_mm():.1f} mm "
              f"> z limiti {args.max_z:.0f} mm — yerleşim makineye SIĞMAZ")

    layout_png = render_layout(
        placements, parts_by_id, bin3d,
        args.out / f"nesting3d_{scenario}.png",
        title=f"3D nesting [{suffix.upper()}] — {scenario}: {len(placements)} parça, "
              f"yükseklik {bin3d.max_height_mm():.1f} mm",
    )
    print(f"Görsel        : {layout_png}")

    if args.export_stl:
        stl = export_scene(
            placements, parts_by_id, pitch,
            args.out / f"nesting3d_result_{scenario}.stl",
        )
        print(f"STL           : {stl}")

    if args.check_clearance:
        t0 = time.perf_counter()
        meshes = placed_meshes(placements, parts_by_id, pitch)
        rep = min_clearance(meshes)
        dt = time.perf_counter() - t0
        verdict = "OK (>=1 mm)" if rep.ok(1.0) else "İHLAL (<1 mm)"
        pair = ""
        if rep.worst_pair is not None:
            i, j = rep.worst_pair
            pair = f"  en yakın çift: {placements[i].part_id} <-> {placements[j].part_id}"
        print(f"Clearance     : min {rep.min_mm:.2f} mm — {verdict} "
              f"({rep.n_pairs_checked} çift, {dt:.0f} s){pair}")
        args.out.mkdir(parents=True, exist_ok=True)
        with open(args.out / f"clearance_{scenario}.json", "w",
                  encoding="utf-8") as f:
            json.dump({
                "scenario": scenario, "algo": suffix,
                "min_mm": rep.min_mm if rep.min_mm != float("inf") else None,
                "threshold_mm": 1.0, "ok": rep.ok(1.0),
                "pairs_checked": rep.n_pairs_checked,
                "samples_per_mesh": rep.samples_per_mesh,
            }, f, ensure_ascii=False, indent=2)
    return rows


def _write_summary(rows: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "summary_3d.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    md_path = out_dir / "summary_3d.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 3D Nesting — Sonuç Tablosu\n\n")
        f.write("| senaryo | algo | parça | yükseklik (mm) | density | süre (s) "
                "| z<=600 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in rows:
            z_ok = "✓" if r.get("z_ok", True) else "✗ AŞIM"
            f.write(f"| {r['scenario']} | {r['algo'].upper()} | {r['parts']} "
                    f"| {r['height_mm']} | {r['density']} | {r['time_s']} "
                    f"| {z_ok} |\n")
    print(f"\nÖzet tablo    : {md_path}")


def main(argv=None) -> None:
    args = _parse_args(argv)
    scenarios = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    rows = []
    for sc in scenarios:
        rows.extend(run_scenario(sc, args))
    _write_summary(rows, args.out)


if __name__ == "__main__":
    main()
