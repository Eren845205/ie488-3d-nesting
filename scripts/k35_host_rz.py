# -*- coding: utf-8 -*-
"""k35_host_rz.py — K-35 / R3: host parcaya SUREKLI Rz aday pozlari (plan1).

Fotograf dersi (STRATEJI/06 §2): Magics'in baseplate'i CAPRAZ duruyor —
eksen-hizali n24 menude de tek-eksen tilt taramasinda da boyle poz YOK.
R3 v1 mekanizmasi: hedefe (baseplate) BILESIK pozlar uretilir:
  Rz(phi) * R{x|y}(theta)   (azimut x tilt; phi=0 hali = mevcut tilt menusu)
+ saf Rz(phi) duz pozlar (buyuk cerceve muhtemelen sigmaz — filtre eler, log gorunur).

Esik dersi (2026-07-09): poz filtresi "cozumun FIILEN kullandigi pozun z'si"
ile; k35'te esik <= (esit KABUL — ayni yukseklikte daha kompakt ayak-izi
no-go etrafinda daha iyi yerlesebilir; kisa-sartini tilt zaten sagladi).

A/B: A = mevcut sampiyon reçetesi (tilt menusu, 141.0 beklenir) ->
     B = ayni menu + Rz kombinasyonlari. Ayni pitch/clearance/no-go.
Kiyas: p1 baseline 260 / tilt 141 / Magics-manuel 110.41; hedef ~116-126.

Kosum: python -m scripts.detach_run k35_host_rz  (sistem bosken; tek-surec).
SAF ASCII.
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

LOG = Path(__file__).parent / "k35_host_rz.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
PITCH = 1.0
MARGIN = 2
ZC = 2
CLEAR_REQ = 2.0
N_OR = 24
HEDEF_AD = "baseplate"
TILT_ACILAR = range(5, 90, 5)          # mevcut tilt taramasi (A menusu)
RZ_ACILAR = (10, 20, 30, 40, 50, 60, 70, 80)   # azimut taramasi (B eki)
KOMBO_TILT = (10, 20, 30, 40, 50, 60, 70, 80)  # kombo tilt bacagi
EKSENLER = {"x": [1, 0, 0], "y": [0, 1, 0]}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _vox_poz(p, R, ad, nx, ny, z_esik, esit_kabul):
    """Tek rotasyon matrisini voxelize et; sigma/z filtresinden gecirse
    Orientation dondur, gecmezse None (nedeni logla)."""
    try:
        vp = voxelize_part(p.name, p.mesh, PITCH, rot_matrices=[R],
                           method="slice", margin=MARGIN)
    except Exception as e:
        log(f"    {ad}: voxelize HATA ({type(e).__name__})")
        return None
    g = vp.orientations[0].grid
    sigar = g.shape[0] <= nx and g.shape[1] <= ny
    kisa = (g.shape[2] <= z_esik) if esit_kabul else (g.shape[2] < z_esik)
    log(f"    {ad}: fp={g.shape[0]}x{g.shape[1]} z={g.shape[2]}"
        f"  {'ALINDI' if (sigar and kisa) else ('sigmiyor' if not sigar else 'uzun')}")
    return vp.orientations[0] if (sigar and kisa) else None


def _tilt_menusu(p, nx, ny, z_esik):
    """A menusu: plan1_hedefli_tilt'in birebir tilt pozlari (esik strict <)."""
    ok = []
    for ek, vec in EKSENLER.items():
        for ang in TILT_ACILAR:
            R = trimesh.transformations.rotation_matrix(np.deg2rad(ang), vec)
            o = _vox_poz(p, R, f"{ek}{ang:>2}", nx, ny, z_esik, esit_kabul=False)
            if o is not None:
                ok.append(o)
    return ok


def _rz_menusu(p, nx, ny, z_esik):
    """B eki: saf Rz duzler + Rz*Rtilt kombolari (esik <=, esit kabul)."""
    ok = []
    z = [0, 0, 1]
    for phi in RZ_ACILAR:
        Rz = trimesh.transformations.rotation_matrix(np.deg2rad(phi), z)
        o = _vox_poz(p, Rz, f"z{phi:>2} duz", nx, ny, z_esik, esit_kabul=True)
        if o is not None:
            ok.append(o)
        for ek, vec in EKSENLER.items():
            for th in KOMBO_TILT:
                Rt = trimesh.transformations.rotation_matrix(np.deg2rad(th), vec)
                o = _vox_poz(p, Rz @ Rt, f"z{phi:>2}*{ek}{th:>2}",
                             nx, ny, z_esik, esit_kabul=True)
                if o is not None:
                    ok.append(o)
    return ok


def _kos(parts, n_total, etiket):
    mask = Bin3D.no_go_mask_from_bounds(NOGO, PLATE[0], PLATE[1], PITCH)
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
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}")
    tops = sorted(((pl.z + pbid[pl.part_id].orientations[pl.orientation_idx]
                    .grid.shape[2]) * PITCH,
                   str(getattr(pbid[pl.part_id], "name", pl.part_id)))
                  for pl in b.placements)[::-1]
    log(f"[{etiket}] height-driver ilk5: "
        + " | ".join(f"{h_:.0f}:{a[:24]}" for h_, a in tops[:5]))
    if legal is not None:
        out = _ROOT / "results" / f"plan1_nogo335_hostrz_{etiket}_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return legal, b


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-35 / R3 HOST-RZ — plan1 @335+NOGO (tilt sampiyonu 141.0 / manuel 110.41)")
    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    nx, ny = int(PLATE[0] // PITCH), int(PLATE[1] // PITCH)
    t = time.perf_counter()
    parts = to_voxel_parts(inst, PITCH, n_orientations=N_OR, margin=MARGIN)
    log(f"voxelize n{N_OR}: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    hedefler = [p for p in parts if HEDEF_AD in str(getattr(p, "name", "")).lower()]
    if not hedefler:
        log(f"HATA: '{HEDEF_AD}' isimli parca yok")
        return

    # esik icin dik baseline (tilt dersi: cozumun kullandigi pozun z'si)
    h_dik, b_dik = _kos(parts, n_total, "dik_n24")
    if b_dik is None:
        return
    kullanilan_z = {}
    pbid = {p.id: p for p in parts}
    for pl in b_dik.placements:
        kullanilan_z[pl.part_id] = \
            pbid[pl.part_id].orientations[pl.orientation_idx].grid.shape[2]

    # A) tilt menusu (sampiyon recete — 141.0 beklenir)
    for p in hedefler:
        z_esik = kullanilan_z.get(p.id, 10 ** 9)
        log(f"hedef: {p.name[:40]}  dik-cozum-poz-z={z_esik}vox — tilt taramasi:")
        yeni = _tilt_menusu(p, nx, ny, z_esik)
        p.orientations = list(p.orientations) + yeni
        log(f"  +{len(yeni)} tilt pozu")
    h_tilt, b_tilt = _kos(parts, n_total, "tilt_n24")

    # B) esik guncelle: TILT cozumunun kullandigi z (daha siki hedef) -> Rz eki
    if b_tilt is not None:
        for pl in b_tilt.placements:
            kullanilan_z[pl.part_id] = \
                pbid[pl.part_id].orientations[pl.orientation_idx].grid.shape[2]
    for p in hedefler:
        z_esik = kullanilan_z.get(p.id, 10 ** 9)
        log(f"hedef: {p.name[:40]}  tilt-cozum-poz-z={z_esik}vox — Rz taramasi:")
        yeni = _rz_menusu(p, nx, ny, z_esik)
        p.orientations = list(p.orientations) + yeni
        log(f"  +{len(yeni)} Rz/kombo pozu")
    h_rz, _ = _kos(parts, n_total, "hostrz_n24")

    if h_tilt is not None and h_rz is not None:
        log(f"KIYAS: tilt={h_tilt:.1f} -> hostrz={h_rz:.1f}"
            f"  ({h_rz - h_tilt:+.1f}mm)  manuel 110.41'e: "
            f"+%{(h_rz / 110.41 - 1) * 100:.1f}")
    log("BITTI")


if __name__ == "__main__":
    main()
