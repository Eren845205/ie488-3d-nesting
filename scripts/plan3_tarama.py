# -*- coding: utf-8 -*-
"""plan3_tarama.py — Plan3 SOLO legal yol konfig taramasi + kazanan STL.

Baglam (2026-07-07 gece): birlesik Plan1+3 legal 826mm = gonderilemez (makine
600mm siniri + kule etkisi) -> karar: planlar AYRI gider. Plan1 hazir (125.0
legal). Bu script Plan3'un "elden gelen en iyi legal"ini arar: budget/n_or/seed
taramasi, INVALID eleme, kazanan STL.

Kosum: python -m scripts.plan3_tarama   (~1-2 saat)  SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh  # noqa: E402

from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from src.nesting3d.instances.pitch import suggest_pitch  # noqa: E402
from scripts.eval_gate import _load_instance, legal_of  # noqa: E402

LOG = Path(__file__).parent / "plan3_tarama.log"
OUT_DIR = _ROOT / "results"
SET = "plan3"
CLEARANCE = 1.0
MAKINE_H = 600.0  # hoca 335x335x600 — tek partide asilirsa raporda kirmizi bayrak

# plate anahtari: None = otomatik; tuple = sabit plaka. P-konfigleri ayni
# musterinin Plan2'den BILINEN gercek plakasini (328.74x328.19) test eder —
# plan3 solo auto-plaka DAR -> mecburi kule hipotezi (ref 1046mm olculdu).
BASE_CONFIGS = [
    ("P_b25_n4_plate328", dict(budget=25, n_orientations=4, seed=42,
                               plate=(328.74, 328.19))),
    ("Pn8_b70_plate328", dict(budget=70, n_orientations=8, seed=42,
                              plate=(328.74, 328.19))),
    ("A_b70_n4_s42", dict(budget=70, n_orientations=4, seed=42)),
    ("B_b70_n8_s42", dict(budget=70, n_orientations=8, seed=42)),
    ("C_b150_n8_s42", dict(budget=150, n_orientations=8, seed=42)),
]
EXTRA_SEEDS = (13, 7)

# ref (b25 n4 auto-plaka) eval_gate kosusundan OLCULDU (5.2 dk):
PRE_MEASURED: list = [
    {"name": "ref_b25_n4_s42_autoplate", "budget": 25, "n_orientations": 4,
     "seed": 42, "height_mm": 1046.0, "legal_height_mm": 1046.0,
     "invalid_reason": None, "min_clearance_mm": 1.216, "n_locked": 0,
     "n_placed": 109, "pitch": 1.0, "duration_min": 5.2},
]


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _run(inst, name, budget, n_orientations, seed, n_total, plate=None):
    t = time.perf_counter()
    if plate is not None:
        pw, pd = float(plate[0]), float(plate[1])
    else:
        pw = float(inst.container.width_mm)
        pd = float(inst.container.depth_mm)
    pitch = suggest_pitch(inst, wall_aware=False)
    r = solve_coarse_to_fine(
        inst, plate_w_mm=pw, plate_d_mm=pd,
        coarse_pitch=None, fine_pitch=pitch, budget=budget, seed=seed,
        n_orientations=n_orientations, clearance_mm=CLEARANCE)
    n_placed = int(getattr(r, "n_placed", len(r.placements)))
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), n_placed, n_total,
                             float(rep.min_mm), int(acc.n_locked),
                             clearance_req=CLEARANCE)
    dt = time.perf_counter() - t
    log(f"  [{name}] h={float(r.height_mm):7.1f}mm  legal="
        f"{(f'{legal:.1f}' if legal is not None else 'INVALID(' + str(reason) + ')')}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  pitch={pitch:.3f}"
        f"  ({dt / 60:.1f} dk)"
        + ("  !! >600 MAKINE SINIRI" if float(r.height_mm) > MAKINE_H else ""))
    return {"name": name, "budget": budget, "n_orientations": n_orientations,
            "seed": seed, "plate": (list(plate) if plate else None),
            "height_mm": float(r.height_mm),
            "legal_height_mm": legal, "invalid_reason": reason,
            "min_clearance_mm": float(rep.min_mm), "n_locked": int(acc.n_locked),
            "n_placed": n_placed, "pitch": float(pitch),
            "duration_min": round(dt / 60, 1)}, r, meshes


def main():
    LOG.write_text("", encoding="utf-8")
    t_all = time.perf_counter()
    log("=" * 78)
    log(f"PLAN3 SOLO — legal yol konfig taramasi  clearance>={CLEARANCE}mm  "
        f"basladi {datetime.now().isoformat(timespec='seconds')}")
    log("=" * 78)
    inst = _load_instance(SET)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plan3: {len(inst.parts)} tip, {n_total} parca | "
        f"plaka(otomatik)={float(inst.container.width_mm):.1f}x"
        f"{float(inst.container.depth_mm):.1f}mm | makine sinir={MAKINE_H:.0f}mm")

    rows = list(PRE_MEASURED)
    for r_ in PRE_MEASURED:
        log(f"  [{r_['name']}] ONCEDEN OLCULDU: h={r_['height_mm']:.1f} "
            f"legal={r_['legal_height_mm']} clear={r_['min_clearance_mm']} "
            f"kilit={r_['n_locked']}")
    best = None
    for name, kw in BASE_CONFIGS:
        try:
            row, r, meshes = _run(inst, name, n_total=n_total, **kw)
        except Exception as e:
            log(f"  [{name}] EXCEPTION: {e} — atlandi")
            rows.append({"name": name, "invalid_reason": f"EXCEPTION: {e}"})
            continue
        rows.append(row)
        if row["legal_height_mm"] is not None and (
                best is None or row["legal_height_mm"] < best[0]):
            best = (row["legal_height_mm"], row, r, meshes)

    if best is not None:
        bk = dict(budget=best[1]["budget"],
                  n_orientations=best[1]["n_orientations"],
                  plate=best[1].get("plate"))
        for sd in EXTRA_SEEDS:
            name = f"best_{bk['budget']}_{bk['n_orientations']}_s{sd}"
            try:
                row, r, meshes = _run(inst, name, seed=sd, n_total=n_total, **bk)
            except Exception as e:
                log(f"  [{name}] EXCEPTION: {e} — atlandi")
                continue
            rows.append(row)
            if row["legal_height_mm"] is not None and row["legal_height_mm"] < best[0]:
                best = (row["legal_height_mm"], row, r, meshes)

    # PRE_MEASURED (ref) hala en iyiyse STL icin deterministik replay
    pre_best = min((r for r in PRE_MEASURED if r.get("legal_height_mm")),
                   key=lambda r: r["legal_height_mm"], default=None)
    if pre_best is not None and (best is None or pre_best["legal_height_mm"] < best[0]):
        log("")
        log(f"  yeni konfigler {pre_best['legal_height_mm']:.1f}'i gecemedi -> "
            f"STL icin {pre_best['name']} replay")
        row, r, meshes = _run(inst, pre_best["name"] + "_replay", n_total=n_total,
                              budget=pre_best["budget"],
                              n_orientations=pre_best["n_orientations"],
                              seed=pre_best["seed"])
        if row["legal_height_mm"] is not None:
            best = (row["legal_height_mm"], row, r, meshes)

    log("")
    log("-" * 78)
    if best is None:
        log("SONUC: hicbir konfig legal cikmadi. STL YAZILMADI.")
    else:
        h, row, r, meshes = best
        OUT_DIR.mkdir(exist_ok=True)
        stl_path = OUT_DIR / f"plan3_duzeltilmis_{h:.1f}mm_{row['name']}.stl"
        trimesh.util.concatenate(meshes).export(stl_path)
        log(f"KAZANAN: {row['name']}  legal_height={h:.1f}mm  "
            f"clear={row['min_clearance_mm']:.3f}  kilit=0  "
            f"yerlesen={row['n_placed']}/{n_total}"
            + ("  !! >600 MAKINE SINIRI — coklu-parti karari gerekir"
               if h > MAKINE_H else ""))
        log(f"STL: {stl_path}  ({stl_path.stat().st_size / 1e6:.1f} MB)")
    (OUT_DIR / "plan3_tarama.json").write_text(json.dumps(
        {"created": datetime.now().isoformat(timespec="seconds"),
         "clearance_req": CLEARANCE, "makine_h": MAKINE_H, "rows": rows,
         "winner": (best[1] if best else None)},
        indent=2, ensure_ascii=True), encoding="utf-8")
    log(f"tablo: {OUT_DIR / 'plan3_tarama.json'}")
    log(f"TOPLAM {(time.perf_counter() - t_all) / 60:.0f} dk")


if __name__ == "__main__":
    main()
