# -*- coding: utf-8 -*-
"""k46_d4_nfv.py — K-46: deneme4 NFV ham + exit_guard probu (INVALID'i kapatma).

Gerekce (2026-07-12): d4'un GECERLI 2mm sayisi YOK — eski 288.0 etiketi 1mm
kablosuyla kosulmustu (gercek clearance 0.859, yeni kural INVALID). K-27'nin
"d4 NFV yolu kapali (413/588 kilit)" hukmu HAM NFV icindi; exit_guard'li
(kilit-ONLEYICI) recete d4'te HIC denenmedi — K-41/44 bu recetenin iki ailede
kilidi sifirladigini kanitladi. d4 riski: 62 ASY cani ic-ice gecmek ister,
guard vergisi buyuk cikabilir (p3'te +66 gibi) — olcmeden bilinmez.
Bacaklar: (A) ham @2.0 (kilit olc; beklenti yuksek kilit) → (B) exit_guard
@2.0 (kilitsiz legallesme denemesi). Kiyas: manuel 250.24 (2mm-legal ref YOK).
Kosum: python -m scripts.detach_run k46_d4_nfv    SAF ASCII.
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

LOG = Path(__file__).parent / "k46_d4_nfv.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
MANUEL = 250.24


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
    rep = min_clearance(meshes, samples_per_mesh=6000)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"[{etiket}] SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}(6000 ornek)  "
        f"legal(b)={legal_b if legal_b is not None else 'INVALID'}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    if legal_bc is not None:
        out = _ROOT / "results" / f"deneme4_{etiket}_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return (hv, legal_bc)


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-46 DENEME4 NFV — ham + exit_guard @2.0 (2mm-legal ref YOK / manuel 250.24)")
    inst = _load_instance("deneme4")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"deneme4: {n_total} parca hedef")
    ham = _bacak(inst, n_total, "nfv_ham", False)
    grd = _bacak(inst, n_total, "nfv_guard", True)
    parcalar = []
    for ad, x in (("ham", ham), ("guard", grd)):
        if x is not None:
            parcalar.append(f"{ad}={x[0]:.1f}{'(legal)' if x[1] is not None else '(INVALID)'}")
    en_iyi = min((x[0] for x in (ham, grd)
                  if x is not None and x[1] is not None), default=None)
    log(f"HUKUM-VERISI: {' | '.join(parcalar) if parcalar else 'bacaklar olu'}"
        f" | manuel 250.24 -> "
        f"{'ILK 2mm-LEGAL d4 SAYISI' if en_iyi is not None else 'legal sayi HALA yok'}")
    log("BITTI")


if __name__ == "__main__":
    main()
