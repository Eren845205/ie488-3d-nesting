# -*- coding: utf-8 -*-
"""k47a_d5_pitch1.py — K-47a: deneme5 NFV @pitch=1.0 (H-17 dilimli-FFT kapisi).

Gerekce (2026-07-12): K-38 dersi — 2mm kuralinda TAM pitch'ler yalniz 2.0 (1vox)
ve 1.0 (2vox); pitch 1.0 pozisyon kuantizasyonunu yariya indirir (parca basina
ort. pitch/2 z-vergisi geri gelir). Onceden MemErr'di: fftconvolve tam-boy f64
tamponu (K-39/39b). H-17 eksen-adaptif dilimli konvolusyon (CPU+GPU) bunu acti
(tests/test_h17_fft_chunk.py 14 yesil).
Recete K-41/44: ONCE ham; (b+c) kilit>0 CIKARSA guard bacagi (kosullu — K-44'te
guard gereksiz +20.5 vergiydi, ders islenmis).
REF (sampiyon @2.0): 223.5 CIFT-LEGAL ham. MANUEL 209.
Kosum: python -m scripts.detach_run k47a_d5_pitch1    SAF ASCII.
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

LOG = Path(__file__).parent / "k47a_d5_pitch1.log"
BEKLE = Path(__file__).parent / "k47c_d4_cert_dump.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
PITCH = 1.0
REF = 223.5     # d5 sampiyonu (K-44 ham @2.0)
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
                      no_go_bounds=NOGO, fine_pitch=PITCH,
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
        out = _ROOT / "results" / f"deneme5_p1_{etiket}_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return (hv, legal_bc, int(rot.n_locked))


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-47a DENEME5 NFV @1.0 — H-17 dilimli-FFT kapisi (ref 223.5 / manuel 209)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k47c bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k47c bitti — deneme5 @1.0 basliyor")
    inst = _load("deneme5", PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"deneme5: {n_total} parca hedef  pitch={PITCH}")
    ham = _bacak(inst, n_total, "ham", False)
    grd = None
    if ham is not None and ham[2] > 0:
        log(f"ham (b+c) kilit={ham[2]} > 0 -> guard bacagi kosuluyor (K-41/44 recetesi)")
        grd = _bacak(inst, n_total, "guard", True)
    elif ham is not None:
        log("ham kilitsiz -> guard bacagi GEREKSIZ (K-44 dersi, vergi odenmez)")
    parcalar = []
    for ad, x in (("ham", ham), ("guard", grd)):
        if x is not None:
            parcalar.append(f"{ad}={x[0]:.1f}{'(legal)' if x[1] is not None else '(INVALID)'}")
    en_iyi = min((x[0] for x in (ham, grd) if x is not None and x[1] is not None),
                 default=None)
    log(f"HUKUM-VERISI: {' | '.join(parcalar) if parcalar else 'bacaklar olu'}"
        f" | ref@2.0 223.5 | manuel 209 -> "
        f"{'REKOR' if (en_iyi is not None and en_iyi < REF) else 'ref gecilemedi'}")
    log("BITTI")


if __name__ == "__main__":
    main()
