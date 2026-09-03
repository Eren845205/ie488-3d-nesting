# -*- coding: utf-8 -*-
"""k42_plan2_rot_derin.py — K-42: plan2 ham 532.0'i DERIN R10 ile legallestirme.

K-39b/K-41 durumu: ham NFV @2.0 = 532.0 (clear 2.002) ama (b+c) 29 kilit
INVALID; guard'li 544.5 CIFT-LEGAL sampiyon. Aradaki 12.5mm = rot-sokumun
DEFAULT butcesiyle (Z90/X30/Y30, lift 0-3, 480s) cozemedigi 29 kilit.
Hipotez: hoca (c) kriteri "donderek cikarma" acisiz sinir koymuyor —
genis merdiven (Z180/X60/Y60) + lift 0-6 + 2400s butce kilitleri acabilir.
GO ise: plan2 = 532.0 (b+c)-LEGAL YENI SAMPIYON (−12.5).
NFV deterministik (K-36 kaniti) → ayni 532.0 layout yeniden uretimle gelir.
Kosum: python -m scripts.detach_run k42_plan2_rot_derin    SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.clearance import min_clearance
from src.nesting3d.coarse_to_fine import clearance_to_voxels
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "k42_plan2_rot_derin.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF_GUARD = 544.5
MAX_ACI_DERIN = {"Z": 180.0, "X": 60.0, "Y": 60.0}
LIFTS_DERIN = (0, 1, 2, 3, 4, 5, 6)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-42 PLAN2 ROT-DERIN — ham 532.0 legallestirme (guard ref 544.5 / manuel 492.39)")
    inst = _load_instance("plan2")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=NOGO, fine_pitch=2.0)
    except Exception as e:
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        log("BITTI")
        return
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"NFV: h={hv:.1f}  pitch={px}  yerlesen={len(pls)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)  [beklenen 532.0]")
    ec = clearance_to_voxels(2.0, px)
    t = time.perf_counter()
    rot_def = check_separability_rot(pls, parts, max_grid_vox=800,
                                     sure_butcesi_s=480.0, erode_clearance_vox=ec)
    log(f"rot DEFAULT: kilit={rot_def.n_locked}  cert={len(rot_def.certificates)}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)  [beklenen 29]")
    t = time.perf_counter()
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 max_aci=MAX_ACI_DERIN, lifts=LIFTS_DERIN,
                                 sure_butcesi_s=2400.0, erode_clearance_vox=ec)
    log(f"rot DERIN (Z180/X60/Y60, lift0-6, 2400s): kilit={rot.n_locked}"
        f"  cert={len(rot.certificates)}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  (b) kilit={r5.n_locked}"
        f"  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    log(f"HUKUM-VERISI: rot-derin={hv:.1f} kilit {rot_def.n_locked}->{rot.n_locked}"
        f" | guard 544.5 | manuel 492.39 -> "
        f"{'YENI SAMPIYON' if (legal_bc is not None and hv < REF_GUARD) else 'guard sampiyon kalir'}")
    if legal_bc is not None and hv < REF_GUARD:
        out = _ROOT / "results" / f"plan2_nfv_rotderin_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
