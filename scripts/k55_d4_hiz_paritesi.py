# -*- coding: utf-8 -*-
"""k55_d4_hiz_paritesi.py — K-55: R11 hizlandirmasinin d4 uretim-olcegi kaniti.

K-52 akisinin BIREBIR tekrari (ayni parametreler, ayni seed): d4 replay
(quality=max) -> continuous_z_settle(12000) + dogrula_ve_rafine(6000) ->
rot denetimi. Yeni kod (K-55: query workers=6 + distance_upper_bound
budamasi) BIT-OZDES sonuc vermek ZORUNDA: K-52 referanslari h4=220.69 /
clear=2.006 / rot kilit=0. Olculen sey SURE: K-52'de settle+rafine 393dk
(dogal CPU-yuk oynakligiyla) — hedef ~1 saat siniri (mikro-bench 4.6x).
Kosum: python -m scripts.detach_run k55_d4_hiz_paritesi    SAF ASCII.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from types import SimpleNamespace
from src.nesting3d.continuous_settle import (DEFAULT_WORKERS, apply_dz,
                                             continuous_z_settle,
                                             dogrula_ve_rafine)
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.voxelize import voxelize_part
from scripts.eval_gate import _load_instance

LOG = Path(__file__).parent / "k55_d4_hiz_paritesi.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
CHECK_PITCH = 1.0
# K-52 referanslari (scripts/k52_d4_rot_kabul.log): parite HEDEFI
REF_H4 = 220.69
REF_CLEAR = 2.006
REF_SETTLE_DK = 393.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _rot_meshes(meshes):
    parts = {}
    pls = []
    for i, m in enumerate(meshes):
        pid = f"m{i}"
        parts[pid] = voxelize_part(pid, m, CHECK_PITCH, n_orientations=1,
                                   margin=0, z_dilate=0,
                                   rot_matrices=[np.eye(4)], method="slice")
        org = m.bounds[0]
        pls.append(SimpleNamespace(part_id=pid, orientation_idx=0,
                                   x=int(round(org[0] / CHECK_PITCH)),
                                   y=int(round(org[1] / CHECK_PITCH)),
                                   z=int(round(org[2] / CHECK_PITCH))))
    return check_separability_rot(pls, parts, max_grid_vox=800,
                                  sure_butcesi_s=1200.0,
                                  erode_clearance_vox=(2, 2))


def main():
    LOG.write_text("", encoding="utf-8")
    log(f"K-55 D4 HIZ PARITESI — K-52 akisi yeni kodla (workers={DEFAULT_WORKERS};"
        f" referans: h4={REF_H4} clear={REF_CLEAR} settle {REF_SETTLE_DK:.0f}dk)")
    inst = _load_instance("deneme4")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=False)
    px = float(r.fine_pitch)
    pls = list(r.placements)
    log(f"replay: yerlesen={len(pls)}/{n_total} ({(time.perf_counter()-t)/60:.1f} dk)")

    meshes = placed_meshes(pls, r.fine_voxel_parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=0.15,
                              samples_per_mesh=12000, no_go_bounds=NOGO)
    t_settle = (time.perf_counter() - t) / 60
    log(f"settle: h {h0:.2f} -> {res.height_mm:.2f}  ({t_settle:.1f} dk; "
        f"K-52'de bu asama+rafine {REF_SETTLE_DK:.0f}dk)")
    t = time.perf_counter()
    dz4, rapor4, tur4, ok4 = dogrula_ve_rafine(meshes, res.dz,
                                               samples_per_mesh=6000)
    t_rafine = (time.perf_counter() - t) / 60
    if not ok4 or rapor4 is None or rapor4.min_mm < 2.0:
        log(f"rafine basarisiz (clear={rapor4.min_mm if rapor4 else '?'}) — "
            f"PARITE KIRILDI, ARASTIR")
        log("BITTI")
        return
    shifted = apply_dz(meshes, dz4)
    h4 = max(float(m.bounds[1][2]) for m in shifted)
    toplam_dk = t_settle + t_rafine
    log(f"R11v4: h {h0:.2f} -> {h4:.2f}  clear={rapor4.min_mm:.3f}  tur={tur4}"
        f"  (settle {t_settle:.1f} + rafine {t_rafine:.1f} = {toplam_dk:.1f} dk)")
    h_ok = abs(h4 - REF_H4) < 0.05
    c_ok = abs(float(rapor4.min_mm) - REF_CLEAR) < 0.005
    log(f"PARITE: h4 {'OK' if h_ok else 'FARKLI!'} (ref {REF_H4})  "
        f"clear {'OK' if c_ok else 'FARKLI!'} (ref {REF_CLEAR})  "
        f"hizlanma ~{REF_SETTLE_DK / max(toplam_dk, 0.1):.1f}x")

    t = time.perf_counter()
    rot = _rot_meshes(shifted)
    log(f"ROT denetimi: kilit={rot.n_locked}/{len(shifted)} "
        f"cert={len(rot.certificates)}  ({(time.perf_counter()-t)/60:.1f} dk)")
    log(f"HUKUM: " + ("PARITE TAM + rot kilit 0 -> K-55 GO"
                      if (h_ok and c_ok and rot.n_locked == 0)
                      else "sapma var -> olcumu YONTEM'e sapmayla isle"))
    log("BITTI")


if __name__ == "__main__":
    main()
