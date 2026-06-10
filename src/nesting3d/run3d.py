"""run3d.py — CLI for the 3D voxel nesting pipeline (PLAN_3D.md §3, §5).

Examples:
  python -m src.nesting3d.run3d                            # default scenario, DBLF + SA
  python -m src.nesting3d.run3d --scenario all --export-stl
  python -m src.nesting3d.run3d --algo dblf --scenario stress

Outputs (results/):
  nesting3d_<scenario>.png           final layout render
  sa3d_convergence_<scenario>.png    SA convergence (when SA runs)
  nesting3d_result_<scenario>.stl    combined STL scene (--export-stl)
  summary_3d.csv / summary_3d.md     metric table for the run
"""

import argparse
import csv
import time
from pathlib import Path

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.export_stl import export_scene
from src.nesting3d.models import SCENARIOS, model_set
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.visualize3d import render_convergence, render_layout
from src.nesting3d.voxelize import expand_quantities

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="3D voxel nesting (PLAN_3D.md)")
    p.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="default")
    p.add_argument("--algo", choices=["dblf", "sa"], default="sa",
                   help="sa = DBLF baseline + SA improvement (default)")
    p.add_argument("--pitch", type=float, default=220.0 / 64)
    p.add_argument("--plate", type=float, default=220.0, help="kare taban kenarı (mm)")
    p.add_argument("--rotations", type=int, default=4, choices=[1, 2, 3, 4])
    p.add_argument("--margin", type=int, default=0,
                   help="parça arası boşluk (voxel, dilation)")
    p.add_argument("--voxel-method", choices=["subdivide", "slice"],
                   default="subdivide",
                   help="slice = yüksek yüz sayılı gerçek STL'ler için hızlı "
                        "ve hacim-doğru yol (numune senaryosunda önerilir)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--iters", type=int, default=1000)
    p.add_argument("--export-stl", action="store_true")
    p.add_argument("--out", type=Path, default=RESULTS_DIR)
    return p.parse_args(argv)


def run_scenario(scenario: str, args) -> list[dict]:
    """Run one scenario; returns summary rows (dicts)."""
    parts = expand_quantities(
        model_set(scenario), args.pitch,
        n_orientations=args.rotations, margin=args.margin,
        method=args.voxel_method,
    )
    bin_factory = lambda: Bin3D(args.plate, args.plate, args.pitch)
    parts_by_id = {p.id: p for p in parts}
    rows = []

    print(f"\n=== Senaryo: {scenario} — {len(parts)} parça "
          f"(taban {args.plate:.0f}x{args.plate:.0f} mm, pitch {args.pitch:.2f}) ===")

    t0 = time.perf_counter()
    base_placements, base_bin = dblf(parts, bin_factory)
    dblf_ms = (time.perf_counter() - t0) * 1000
    print(f"DBLF baseline : yükseklik {base_bin.max_height_mm():6.1f} mm  "
          f"density {base_bin.packing_density():.3f}  ({dblf_ms:.0f} ms)")
    rows.append({
        "scenario": scenario, "algo": "dblf", "parts": len(parts),
        "height_mm": round(base_bin.max_height_mm(), 2),
        "density": round(base_bin.packing_density(), 4),
        "time_s": round(dblf_ms / 1000, 2), "iters": 0,
    })
    placements, bin3d, suffix = base_placements, base_bin, "dblf"

    if args.algo == "sa":
        t0 = time.perf_counter()
        res = simulated_annealing_3d(
            parts, bin_factory, seed=args.seed, iterations=args.iters,
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
        })
        placements, bin3d, suffix = res.placements, res.bin3d, "sa"
        render_convergence(
            res.history, res.baseline_height_mm,
            args.out / f"sa3d_convergence_{scenario}.png",
            title=f"SA yakınsama — {scenario} ({len(parts)} parça)",
        )

    layout_png = render_layout(
        placements, parts_by_id, bin3d,
        args.out / f"nesting3d_{scenario}.png",
        title=f"3D nesting [{suffix.upper()}] — {scenario}: {len(placements)} parça, "
              f"yükseklik {bin3d.max_height_mm():.1f} mm",
    )
    print(f"Görsel        : {layout_png}")

    if args.export_stl:
        stl = export_scene(
            placements, parts_by_id, args.pitch,
            args.out / f"nesting3d_result_{scenario}.stl",
        )
        print(f"STL           : {stl}")
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
        f.write("| senaryo | algo | parça | yükseklik (mm) | density | süre (s) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in rows:
            f.write(f"| {r['scenario']} | {r['algo'].upper()} | {r['parts']} "
                    f"| {r['height_mm']} | {r['density']} | {r['time_s']} |\n")
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
