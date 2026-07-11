# -*- coding: utf-8 -*-
"""k43_plan1_multistart.py — K-43: plan1 coklu-restart dblf (siralama uzayi).

K-37/40 sonrasi plan1 durumu: 129.0 soft-serhli taban; tilt/Rz/NFV oldu.
Kalan ucuz kaldirac: dblf YERLESTIRME SIRASI. K-08 "largest-first" genel
optimaldi ama tek siralamadir; 112-parcali plan1'de tepe suruculeri bobbin
yigini — farkli sira bobbinleri farkli oyuklara dagitabilir.
Deney: r4_btilt kurulumu BIREBIR (soft-nogo y<=33 + n24 + bobbin tilt pozlari)
+ 6 restart: volume-desc (ref) + footprint-desc + height-desc + 3 seed'li
karistirma. En iyi < 129.0 ise kazanc; degilse siralama-uzayi da kapanir.
Sure: ~6 x 11dk + voxelize ~= 80dk.
RAM zinciri: k42_plan2_rot_derin.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k43_plan1_multistart    SAF ASCII.
"""
from __future__ import annotations
import random
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.voxelize import voxelize_part
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "k43_plan1_multistart.log"
BEKLE = Path(__file__).parent / "k42_plan2_rot_derin.log"
PLATE = (335.0, 335.0)
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))
PITCH = 1.0
MARGIN = 2
ZC = 2
CLEAR_REQ = 2.0
N_OR = 24
REF = 129.0
BOBBINLER = ("bobbin_1", "bobbin_2", "bobbin_3")
TILT_ACILAR = range(5, 90, 5)
EKSENLER = {"x": [1, 0, 0], "y": [0, 1, 0]}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bekle():
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            return
        if tur % 10 == 0:
            log(f"k42 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)


def _tilt_ekle(parts, nx, ny, kullanilan_z):
    """k37 r4_btilt ile ayni: bobbinlere esik-alti tilt pozlari ekle."""
    for p in parts:
        ad = str(getattr(p, "name", "")).lower()
        if not any(b in ad for b in BOBBINLER):
            continue
        z_esik = kullanilan_z.get(p.id, 10 ** 9)
        ok = []
        for ek, vec in EKSENLER.items():
            for ang in TILT_ACILAR:
                R = trimesh.transformations.rotation_matrix(np.deg2rad(ang), vec)
                try:
                    vp = voxelize_part(p.name, p.mesh, PITCH, rot_matrices=[R],
                                       method="slice", margin=MARGIN)
                except Exception:
                    continue
                g = vp.orientations[0].grid
                if g.shape[0] <= nx and g.shape[1] <= ny and g.shape[2] < z_esik:
                    ok.append(vp.orientations[0])
        if ok:
            p.orientations = list(p.orientations) + ok
            log(f"  {p.name[:30]}: +{len(ok)} tilt pozu (esik z={z_esik})")


def _kos(parts, n_total, etiket, order_key):
    mask = Bin3D.no_go_mask_from_bounds(NOGO_SOFT, PLATE[0], PLATE[1], PITCH)
    t = time.perf_counter()
    pls, b = dblf(parts, lambda: Bin3D(PLATE[0], PLATE[1], PITCH,
                                       z_clearance=ZC, no_go_mask=mask),
                  order_key=order_key)
    h = b.max_height_mm()
    log(f"[{etiket}] dblf: h={h:.1f}  yerlesen={len(b.placements)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    return h, b


def _dogrula_ve_kaydet(b, parts, n_total, etiket):
    pbid = {p.id: p for p in parts}
    meshes = placed_meshes(b.placements, pbid, PITCH)
    rep = min_clearance(meshes)
    acc = check_placements(b.placements, pbid)
    h = b.max_height_mm()
    legal, reason = legal_of(h, len(b.placements), n_total,
                             float(rep.min_mm), int(acc.n_locked),
                             clearance_req=CLEAR_REQ)
    log(f"[{etiket}] SONUC: h={h:.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
        f"  [SERH: soft-nogo T=12mm, hoca cevap 9]")
    if legal is not None and h < REF:
        out = _ROOT / "results" / f"plan1_multistart_{etiket}_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return legal


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-43 PLAN1 MULTI-START — dblf siralama uzayi (ref 129.0 / manuel 110.41)")
    _bekle()
    log("k42 bitti — multistart basliyor")
    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    nx, ny = int(PLATE[0] // PITCH), int(PLATE[1] // PITCH)
    t = time.perf_counter()
    parts = to_voxel_parts(inst, PITCH, n_orientations=N_OR, margin=MARGIN)
    log(f"voxelize n{N_OR}: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    # referans kosu (volume-desc) — tilt esikleri icin kullanilan poz z'leri
    h_ref, b_ref = _kos(parts, n_total, "ref_vol", None)
    pbid = {p.id: p for p in parts}
    kullanilan_z = {pl.part_id:
                    pbid[pl.part_id].orientations[pl.orientation_idx].grid.shape[2]
                    for pl in b_ref.placements}
    _tilt_ekle(parts, nx, ny, kullanilan_z)

    denemeler = [
        ("fp_desc", lambda p: (-(p.orientations[0].grid.shape[0]
                                 * p.orientations[0].grid.shape[1]),)),
        ("h_desc", lambda p: (-max(o.grid.shape[2] for o in p.orientations),)),
    ]
    for sd in (7, 13, 99):
        rng = random.Random(sd)
        jitter = {p.id: rng.random() for p in parts}
        denemeler.append((f"shuf{sd}",
                          lambda p, j=jitter: (-p.volume_voxels * (0.5 + j[p.id]),)))

    en_iyi = (h_ref, b_ref, "ref_vol")
    # tilt pozlari eklendikten sonra referans sirayi da yeniden kos (= r4_btilt esdegeri)
    for etiket, key in [("vol_tilt", None)] + denemeler:
        h, b = _kos(parts, n_total, etiket, key)
        if h < en_iyi[0]:
            en_iyi = (h, b, etiket)
    log(f"EN IYI: {en_iyi[2]} h={en_iyi[0]:.1f} (ref {REF})")
    legal = _dogrula_ve_kaydet(en_iyi[1], parts, n_total, en_iyi[2])
    log(f"HUKUM-VERISI: multistart={en_iyi[0]:.1f} ({en_iyi[2]}) | ref 129.0 "
        f"| manuel 110.41 -> "
        f"{'REKOR' if (legal is not None and en_iyi[0] < REF) else 'siralama-uzayi kapali'}")
    log("BITTI")


if __name__ == "__main__":
    main()
