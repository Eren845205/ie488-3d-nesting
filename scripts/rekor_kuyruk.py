# -*- coding: utf-8 -*-
"""rekor_kuyruk.py — REKOR DENEMESI ONE CEKILDI (kullanici karari 2026-07-08):
  1) plan3 SIKISTIRMA @n24 (706 rekoru n8'le kirilmisti; n24 zincirde -28mm
     kazandirdi -> ayni pozlari sikistirma hattina ver; coarse drop_cache ACIK)
  2) plan2_n24  3) plan2_n8  (ax24 kuyrugunun kalan bacaklari, kos() ile)
Not: n24+fine_angle = eski None.exterior cift tetigi — fix'in saha testi.
Kosum: python -m scripts.detach_run rekor_kuyruk   SAF ASCII.
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
from scripts.ax24_kuyruk_335 import kos, log  # ayni log dosyasi -> tek monitor


def sq_n24():
    """plan3_replan_sq recetesi birebir, yalniz n_orientations=24 (+cache)."""
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    best = None
    for seed in (13, 42, 7):
        t = time.perf_counter()
        r = solve_coarse_to_fine(
            inst, plate_w_mm=335.0, plate_d_mm=335.0,
            coarse_pitch=None, fine_pitch=pitch, budget=70, seed=seed,
            n_orientations=24, clearance_mm=1.0,
            no_go_bounds=((185.1, 0.2), (215.2, 45.3)),
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
            f"({(time.perf_counter() - t) / 60:.1f} dk)  rekor_ref=706.0")
        if legal is not None and (best is None or legal < best[0]):
            best = (legal, seed, meshes)
    if best is not None:
        out = _ROOT / "results" / f"plan3_nogo335_sq_n24_{best[0]:.1f}mm_s{best[1]}.stl"
        trimesh.util.concatenate(best[2]).export(out)
        fark = best[0] - 706.0
        log(f"[sq_n24] KAZANAN s{best[1]}: {best[0]:.1f}mm ({fark:+.1f} vs 706)"
            f"  {'REKOR KIRILDI' if fark < 0 else 'rekor gecilemedi'}  STL: {out}")


def main():
    log("REKOR KUYRUGU — plan3 sq@n24 -> plan2_n24 -> plan2_n8 (cache ACIK)")
    sq_n24()
    kos("plan2", 24)
    kos("plan2", 8)
    log("BITTI")


if __name__ == "__main__":
    main()
