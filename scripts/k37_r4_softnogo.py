# -*- coding: utf-8 -*-
"""k37_r4_softnogo.py — K-37 / R4-probu: plan1 SOFT NO-GO (baseplate-girisi).

Teshis (2026-07-10): 141 = yapisal; kok neden HARD no-go.
  - baseplate duz bbox 330x302x41 — duz poz her konumda no-go'nun y<=45
    seridine ~12mm girer (335-302=33 pay < 45) -> hard maske duz pozu
    IMKANSIZ kiliyor -> egik baseplate taban yiyor -> bobbin 4 kat (~144).
  - Magics 110.41 = 41 (DUZ baseplate) + 2 kat bobbin (~2x36) — duz yatirma
    no-go'ya 12mm'lik kose girisiyle.
  - HOCA CEVABI 9 (2026-07-09): "yasak bolgeye Plan1'deki baseplate ornegi
    GIBI cok ufak girisler kabul edilebilir" -> bu SPESIFIK giris onayli.
Deney: maske y-ust siniri 45.0 -> 33.0 kirpilir (T=12mm giris seridi; yalniz
baseplate degil TUM parcalara acilir — SERH: rapor bunu tasir, uretim
default'u degismez). Bacaklar:
  A) r4_duz      : kirpilmis maske, n24 menu (tilt POZSUZ — duz poz artik legal)
  B) r4_btilt    : + bobbin_1/2/3'e ara-aci tilt taramasi (esik=A'nin z'si)
Kiyas: hard-nogo tilt sampiyonu 141.0 / manuel 110.41. Beklenti ~110-125.

RAM zinciri: k36_derin_arama.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k37_r4_softnogo    SAF ASCII.
"""
from __future__ import annotations
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

LOG = Path(__file__).parent / "k37_r4_softnogo.log"
BEKLE = Path(__file__).parent / "k36_derin_arama.log"
PLATE = (335.0, 335.0)
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))   # y-ust 45->33: T=12mm giris seridi
PITCH = 1.0
MARGIN = 2
ZC = 2
CLEAR_REQ = 2.0
N_OR = 24
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
            log(f"k36 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)


def _tilt_pozlari(p, nx, ny, z_esik):
    ok = []
    for ek, vec in EKSENLER.items():
        for ang in TILT_ACILAR:
            R = trimesh.transformations.rotation_matrix(np.deg2rad(ang), vec)
            try:
                vp = voxelize_part(p.name, p.mesh, PITCH, rot_matrices=[R],
                                   method="slice", margin=MARGIN)
            except Exception as e:
                log(f"    {ek}{ang:>2}: voxelize HATA ({type(e).__name__})")
                continue
            g = vp.orientations[0].grid
            sigar = g.shape[0] <= nx and g.shape[1] <= ny
            kisa = g.shape[2] < z_esik
            if sigar and kisa:
                log(f"    {ek}{ang:>2}: fp={g.shape[0]}x{g.shape[1]} z={g.shape[2]}  ALINDI")
                ok.append(vp.orientations[0])
    return ok


def _kos(parts, n_total, etiket):
    mask = Bin3D.no_go_mask_from_bounds(NOGO_SOFT, PLATE[0], PLATE[1], PITCH)
    t = time.perf_counter()
    _, b = dblf(parts, lambda: Bin3D(PLATE[0], PLATE[1], PITCH,
                                     z_clearance=ZC, no_go_mask=mask))
    h = b.max_height_mm()
    log(f"[{etiket}] dblf: h={h:.1f}  yerlesen={len(b.placements)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    if h > 10000:
        log(f"[{etiket}] IMKANSIZ (sentinel)")
        return None, None
    pbid = {p.id: p for p in parts}
    meshes = placed_meshes(b.placements, pbid, PITCH)
    rep = min_clearance(meshes)
    acc = check_placements(b.placements, pbid)
    legal, reason = legal_of(h, len(b.placements), n_total,
                             float(rep.min_mm), int(acc.n_locked),
                             clearance_req=CLEAR_REQ)
    log(f"[{etiket}] SONUC: h={h:.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  "
        f"[SERH: soft-nogo T=12mm, hoca cevap 9 kapsaminda]")
    tops = sorted(((pl.z + pbid[pl.part_id].orientations[pl.orientation_idx]
                    .grid.shape[2]) * PITCH,
                   str(getattr(pbid[pl.part_id], "name", pl.part_id)))
                  for pl in b.placements)[::-1]
    log(f"[{etiket}] height-driver ilk5: "
        + " | ".join(f"{h_:.0f}:{a[:24]}" for h_, a in tops[:5]))
    if legal is not None:
        out = _ROOT / "results" / f"plan1_softnogo_{etiket}_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return legal, b


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-37 / R4 SOFT-NOGO — plan1 (hard-nogo sampiyonu 141.0 / manuel 110.41)")
    _bekle()
    log("k36 bitti — soft-nogo probu basliyor")
    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    nx, ny = int(PLATE[0] // PITCH), int(PLATE[1] // PITCH)
    t = time.perf_counter()
    parts = to_voxel_parts(inst, PITCH, n_orientations=N_OR, margin=MARGIN)
    log(f"voxelize n{N_OR}: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    # A) duz baseplate serbest — tiltsiz temiz kosu
    h_duz, b_duz = _kos(parts, n_total, "r4_duz")
    if b_duz is None:
        return

    # B) + bobbin ara-aci tilt (esik = A cozumunun kullandigi poz z'si)
    pbid = {p.id: p for p in parts}
    kullanilan_z = {}
    for pl in b_duz.placements:
        kullanilan_z[pl.part_id] = \
            pbid[pl.part_id].orientations[pl.orientation_idx].grid.shape[2]
    for p in parts:
        ad = str(getattr(p, "name", "")).lower()
        if any(b in ad for b in BOBBINLER):
            z_esik = kullanilan_z.get(p.id, 10 ** 9)
            yeni = _tilt_pozlari(p, nx, ny, z_esik)
            if yeni:
                p.orientations = list(p.orientations) + yeni
                log(f"  {p.name[:30]}: +{len(yeni)} tilt pozu (esik z={z_esik})")
    h_bt, _ = _kos(parts, n_total, "r4_btilt")

    if h_duz is not None:
        log(f"KIYAS: hard-tilt 141.0 -> soft-duz {h_duz:.1f}"
            + (f" -> +btilt {h_bt:.1f}" if h_bt is not None else "")
            + f"  manuel 110.41'e: +%{((h_bt or h_duz) / 110.41 - 1) * 100:.1f}")
    log("BITTI")


if __name__ == "__main__":
    main()
