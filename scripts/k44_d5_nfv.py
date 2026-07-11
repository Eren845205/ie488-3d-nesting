# -*- coding: utf-8 -*-
"""k44_d5_nfv.py — K-44: deneme5 NFV ham + exit_guard probu (en buyuk goreli acik).

Gerekce (2026-07-11): d5 yeni-kural sampiyonu 338.4 (heightmap n24 @2mm) vs
manuel 209 = +%61.9 EN BUYUK goreli acik; NFV d5'te hic denenmedi. Anatomi:
216x ozdes ince cubuk (11x19x147) + 46 kutu (25x50x83) + 45 plakacik +
9 bending testi (37.5x59.7x150). Manuel doluluk %19 vs bizim %12.5 —
istif bosluklari bizde. K-41 recetesi: (A) ham @2.0 (kilit olc) →
(B) exit_guard @2.0 (legallesme). Kiyas REF=338.4.
RAM zinciri: k43_plan1_multistart.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k44_d5_nfv    SAF ASCII.
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
from scripts.ax24_kuyruk_335 import _load
from scripts.eval_gate import legal_of

LOG = Path(__file__).parent / "k44_d5_nfv.log"
BEKLE = Path(__file__).parent / "k43_plan1_multistart.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF = 338.4
MANUEL = 209.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bacak(inst, n_total, etiket, guard):
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=NOGO, fine_pitch=2.0,
                      exit_guard=guard)
    except Exception as e:
        log(f"[{etiket}] EXCEPTION: {type(e).__name__}: {e}")
        return None
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"[{etiket}] NFV: h={hv:.1f}  pitch={px}  yerlesen={len(pls)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=600.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"[{etiket}] (b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  "
        f"cert={len(rot.certificates)}")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"[{etiket}] SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b)="
        f"{legal_b if legal_b is not None else 'INVALID'}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    if legal_bc is not None and hv < REF:
        out = _ROOT / "results" / f"deneme5_{etiket}_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return (hv, legal_bc)


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-44 DENEME5 NFV — ham + exit_guard @2.0 (heightmap ref 338.4 / manuel 209)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k43 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k43 bitti — deneme5 NFV probu basliyor")

    inst = _load("deneme5", PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"deneme5: {n_total} parca hedef")
    ham = _bacak(inst, n_total, "nfv_ham", False)
    grd = _bacak(inst, n_total, "nfv_guard", True)
    parcalar = []
    if ham is not None:
        parcalar.append(f"ham={ham[0]:.1f}{'(legal)' if ham[1] is not None else '(INVALID)'}")
    if grd is not None:
        parcalar.append(f"guard={grd[0]:.1f}{'(legal)' if grd[1] is not None else '(INVALID)'}")
    en_iyi_legal = min((x[0] for x in (ham, grd)
                        if x is not None and x[1] is not None), default=None)
    log(f"HUKUM-VERISI: {' | '.join(parcalar) if parcalar else 'bacaklar olu'}"
        f" | heightmap 338.4 | manuel 209 -> "
        f"{'REKOR' if (en_iyi_legal is not None and en_iyi_legal < REF) else 'ref gecilemedi'}")
    log("BITTI")


if __name__ == "__main__":
    main()
