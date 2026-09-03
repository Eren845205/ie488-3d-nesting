# -*- coding: utf-8 -*-
"""k38_pitch175.py — K-38: plan3 NFV fine_pitch=1.75 (grid butcesi siniri).

K-36 kaniti: pitch 2.5->2.0 = 618.1->598.5 ((b) VE (b+c) kilit 0 — cift-legal
REKOR; manuel 593'e +5.5mm). Grid butcesi 34M; 1.75'te ~33.5M = SINIRDA sigar.
Beklenti: 593 ALTI mumkun. Tek bacak: s42 @1.75 + 5-yon + R10.
RAM zinciri: k37_r4_softnogo.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k38_pitch175    SAF ASCII.
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

LOG = Path(__file__).parent / "k38_pitch175.log"
BEKLE = Path(__file__).parent / "k37_r4_softnogo.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF = 598.5


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-38 PITCH-175 — plan3 NFV @1.75 (ref 598.5 cift-legal / manuel 593)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k37 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k37 bitti — pitch 1.75 bacagi basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=NOGO, fine_pitch=1.75)
    except Exception as e:
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        log("BITTI")
        return
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"NFV: h={hv:.1f}  pitch={px}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=240.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"(b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  "
        f"cert={len(rot.certificates)}")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b)="
        f"{legal_b if legal_b is not None else 'INVALID'}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    log(f"HUKUM-VERISI: p1.75={hv:.1f} | ref 598.5 | manuel 593 -> "
        f"{'REKOR' if (legal_bc is not None and hv < REF) else 'ref gecilemedi'}"
        f"{' + 593 ALTI!' if (legal_bc is not None and hv < 593.0) else ''}")
    if legal_bc is not None and hv < REF:
        out = _ROOT / "results" / f"plan3_nfv_derin_p175_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
