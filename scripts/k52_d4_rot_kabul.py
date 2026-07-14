# -*- coding: utf-8 -*-
"""k52_d4_rot_kabul.py — K-52: K-50 d4 R11-sonucunun (220.69) rot-sokum denetimi.

Gerekce (HOCA CEVABI 2026-07-14): gercek kabul kriteri yalniz yapisma +
CIKARILAMAYAN ic-ice; "zor cikan ama cikabilen" IHMAL EDILEBILIR. K-50 d4
NO-GO'su 5-yon metriginde kilit 11->12 icindi — rot-sokum (b+c) denetimi
12'yi sertifikalarsa 220.69 (manuel -%11.8) hoca-onayli cerceveye girer.
Akis: d4 replay (231.5) -> R11 v4 (ayni parametreler, ayni dz deterministik)
-> shifted mesh'lerde ROT denetimi (margin-0 @1.0 re-voxelize + rot mekanigi)
-> HUKUM. Kosum: python -m scripts.detach_run k52_d4_rot_kabul  SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from types import SimpleNamespace
from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import apply_dz, continuous_z_settle, dogrula_ve_rafine
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.voxelize import voxelize_part
from scripts.eval_gate import _load_instance
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k52_d4_rot_kabul.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
MANUEL = 250.24
CHECK_PITCH = 1.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _rot_meshes(meshes):
    """Shifted mesh'lerde rot-sokum denetimi (K-50 kilit-metrigiyle ayni
    re-voxelize tabani: margin-0 @1.0 slice; rot mekanigi R10)."""
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
                                  erode_clearance_vox=2)


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-52 D4 ROT-KABUL — K-50'nin 220.69'u hoca-kriteriyle yeniden (manuel 250.24)")
    inst = _load_instance("deneme4")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=False)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    log(f"replay: yerlesen={len(pls)}/{n_total} ({(time.perf_counter()-t)/60:.1f} dk)")

    meshes = placed_meshes(pls, parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=0.15,
                              samples_per_mesh=12000, no_go_bounds=NOGO)
    dz4, rapor4, tur4, ok4 = dogrula_ve_rafine(meshes, res.dz,
                                               samples_per_mesh=6000)
    if not ok4 or rapor4.min_mm < 2.0:
        log(f"rafine basarisiz (clear={rapor4.min_mm if rapor4 else '?'}) — NO-GO")
        log("BITTI")
        return
    shifted = apply_dz(meshes, dz4)
    h4 = max(float(m.bounds[1][2]) for m in shifted)
    log(f"R11v4: h {h0:.2f} -> {h4:.2f}  clear={rapor4.min_mm:.3f}"
        f"  ({(time.perf_counter()-t)/60:.1f} dk)  [K-50 beklentisi 220.69]")

    t = time.perf_counter()
    rot = _rot_meshes(shifted)
    log(f"ROT denetimi: kilit={rot.n_locked}/{len(shifted)}  cert={len(rot.certificates)}"
        f"  ({(time.perf_counter()-t)/60:.1f} dk)")

    kabul = (rot.n_locked == 0)
    log(f"HUKUM-VERISI: h={h4:.2f} | clear={rapor4.min_mm:.3f} | rot-kilit="
        f"{rot.n_locked} cert={len(rot.certificates)} | manuel {MANUEL} -> "
        + ("HOCA-KRITERIYLE KABUL (sokum-planli) — YENI d4 SAMPIYON ADAYI"
           if kabul else "rot'ta da kilitli -> NO-GO (gercek kenetlenme)"))
    if kabul:
        out = _ROOT / "results" / f"deneme4_r11v4_rot_{h4:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"STL: {out}")
        kaydet("deneme4", "nfv", "ham@2.0+r11v4", h4, len(pls), n_total,
               float(rapor4.min_mm), 0, None, kosu_id="K-52/rot-kabul",
               log_yolu="scripts/k52_d4_rot_kabul.log", pitch=2.0, seed=42,
               instance=inst, b_kilit=int(rot.n_locked),
               cert=len(rot.certificates),
               kilit_metrigi="rot-sokum (hoca 2026-07-14 kabul cercevesi)")
        log("telemetri v2 satiri yazildi")
    log("BITTI")


if __name__ == "__main__":
    main()
