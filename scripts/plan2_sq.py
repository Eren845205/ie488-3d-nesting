# -*- coding: utf-8 -*-
"""plan2_sq.py — PLAN2 SIKISTIRMA @335+NOGO (plan3'u 747->685 yapan recete,
plan2'ye ILK uygulama; 2026-07-09 'plan2'de cok fark var').

Recete: budget=70 + n24 + fine_angle z-acilari (w90/15) + coklu seed +
coarse drop_cache. plan2 @0.5 pitch -> seed basina sure uzun olabilir;
2 seed (13, 42). Kiyas: zincir n24 = 646 / Magics 492.39.

RAM zinciri: plan2_nfv_nogo.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run plan2_sq   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.pitch import suggest_pitch
from scripts.eval_gate import legal_of
from scripts.ax24_kuyruk_335 import _load

LOG = Path(__file__).parent / "plan2_sq.log"
BEKLE = Path(__file__).parent / "plan2_nfv_nogo.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN2 SIKISTIRMA @335+NOGO — ref zincir 646 / Magics 492.39")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"plan2 NFV probu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — sikistirma basliyor")

    inst = _load("plan2", PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    best = None
    for seed in (13, 42):
        t = time.perf_counter()
        r = solve_coarse_to_fine(
            inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
            coarse_pitch=None, fine_pitch=pitch, budget=70, seed=seed,
            n_orientations=24, clearance_mm=1.0, no_go_bounds=NOGO,
            fine_angle_window=90.0, fine_angle_step=15.0, fine_angle_axes="z",
            drop_cache=True)
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                                 float(rep.min_mm), int(acc.n_locked))
        log(f"[sq_n24_s{seed}] h={float(r.height_mm):.1f}  legal="
            f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
            f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  "
            f"({(time.perf_counter() - t) / 60:.1f} dk)  ref=646.0")
        if legal is not None and (best is None or legal < best[0]):
            best = (legal, seed, meshes)
    if best is not None:
        out = _ROOT / "results" / f"plan2_nogo335_sq_n24_{best[0]:.1f}mm_s{best[1]}.stl"
        trimesh.util.concatenate(best[2]).export(out)
        fark = best[0] - 646.0
        log(f"KAZANAN s{best[1]}: {best[0]:.1f}mm ({fark:+.1f} vs 646)"
            f"  Magics'e +%{(best[0] / 492.39 - 1) * 100:.1f}  STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
