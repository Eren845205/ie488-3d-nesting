# -*- coding: utf-8 -*-
"""plan3_replan_sq.py — Plan3 @335+NOGO sikistirma: kanitli kaldiraclar birlikte.

747 (default: b25, acisiz, s42) -> w90 acilar + b70 + seed taramasi (13,42,7).
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
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "plan3_replan_sq.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN3 @335+NOGO SIKISTIRMA — ref 747 (default) / Magics 593")
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    best = None
    for seed in (13, 42, 7):
        t = time.perf_counter()
        r = solve_coarse_to_fine(
            inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
            coarse_pitch=None, fine_pitch=pitch, budget=70, seed=seed,
            n_orientations=8, clearance_mm=1.0, no_go_bounds=NOGO,
            fine_angle_window=90.0, fine_angle_step=15.0, fine_angle_axes="z")
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                                 float(rep.min_mm), int(acc.n_locked))
        log(f"[s{seed}] h={float(r.height_mm):.1f}  legal="
            f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
            f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  "
            f"({(time.perf_counter() - t) / 60:.1f} dk)")
        if legal is not None and (best is None or legal < best[0]):
            best = (legal, seed, meshes)
    if best is not None:
        out = _ROOT / "results" / f"plan3_nogo335_sq_{best[0]:.1f}mm_s{best[1]}.stl"
        trimesh.util.concatenate(best[2]).export(out)
        log(f"KAZANAN s{best[1]}: {best[0]:.1f}mm  STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
