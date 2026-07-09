# -*- coding: utf-8 -*-
"""plan1_hedefli_tilt.py — HEDEFLI-TILT prototipi (Kademe 2 no.1, 2026-07-08):
height-driver parcaya x/y TILT taramasi (Plan1 baseplate @335+NOGO).

Teshis (ax24 n24 height-driver): kulenin tepesi BASEPLATE (260mm; sonraki parca
147). Duz yatirma IMKANSIZ — no-go kolonu tam-yukseklik ve 330.2mm ayak izi 335
plakada her duz pozisyonda kolonla kesisir (+-4.8mm pay). Magics egik basiyor =
zorunluluk. Mekanizma: baseplate'e Rx/Ry tilt pozlari uretilir (5..85 derece,
adim 5), grid'e siganlar ve z-uzantisi dik-durustan kucuk olanlar poz listesine
EKLENIR (orijinaller kalir — dblf en iyisini secer). A/B: ayni kosuda tilt'siz
baseline + tilt'li kosum, ayni pitch/clearance/no-go.

Kosum: python -u -m scripts.plan1_hedefli_tilt   (C:\\dev\\ie488'den; kuyruk
bittikten SONRA — tek surec RAM kurali). SAF ASCII.
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

LOG = Path(__file__).parent / "plan1_hedefli_tilt.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
PITCH = 1.0
MARGIN = 1          # clearance_to_voxels(1.0, 1.0) = (1,1)
ZC = 1
N_OR = 24           # ax24 kesfi: n24 neredeyse bedava, p1 n24=260 baseline
HEDEF_AD = "baseplate"   # height-driver (ax24 dokumu: baseplate_v2 tek basina 260)
ACILAR = range(5, 90, 5)
EKSENLER = {"x": [1, 0, 0], "y": [0, 1, 0]}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def parts_by_id(parts):
    return {p.id: p for p in parts}


def _tilt_pozlari(p, nx, ny, z_esik_vox):
    """Hedef parcaya Rx/Ry tilt pozlari uret; grid'e sigan VE z-uzantisi
    esikten kucuk olanlari dondur. Log: poz tablosu."""
    ok = []
    for ek, vec in EKSENLER.items():
        for ang in ACILAR:
            R = trimesh.transformations.rotation_matrix(np.deg2rad(ang), vec)
            try:
                vp = voxelize_part(p.name, p.mesh, PITCH, rot_matrices=[R],
                                   method="slice", margin=MARGIN)
            except Exception as e:
                log(f"    {ek}{ang:>2}: voxelize HATA ({type(e).__name__})")
                continue
            g = vp.orientations[0].grid
            sigar = g.shape[0] <= nx and g.shape[1] <= ny
            kisa = g.shape[2] < z_esik_vox
            log(f"    {ek}{ang:>2}: fp={g.shape[0]}x{g.shape[1]} z={g.shape[2]}"
                f"  {'ALINDI' if (sigar and kisa) else ('sigmiyor' if not sigar else 'uzun')}")
            if sigar and kisa:
                ok.append(vp.orientations[0])
    return ok


def _kos(parts, n_total, etiket):
    """Doner: (legal, bin) — bin, hedefin FIILEN kullandigi pozu okumak icin
    (2026-07-09 filtre dersi: grid'e sigan ama no-go yuzunden YERLESEMEYEN
    duz poz z-esigini zehirledi; esik = cozumun kullandigi pozun z'si olmali)."""
    mask = Bin3D.no_go_mask_from_bounds(NOGO, PLATE[0], PLATE[1], PITCH)
    t = time.perf_counter()
    _, b = dblf(parts, lambda: Bin3D(PLATE[0], PLATE[1], PITCH,
                                     z_clearance=ZC, no_go_mask=mask))
    h = b.max_height_mm()
    log(f"[{etiket}] dblf: h={h:.1f}  yerlesen={len(b.placements)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    if h > 10000:
        log(f"[{etiket}] IMKANSIZ (sentinel)")
        return None
    pbid = {p.id: p for p in parts}
    meshes = placed_meshes(b.placements, pbid, PITCH)
    rep = min_clearance(meshes)
    acc = check_placements(b.placements, pbid)
    legal, reason = legal_of(h, len(b.placements), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"[{etiket}] SONUC: h={h:.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}")
    # height-driver ilk-5 (tilt'in kuleyi gercekten kirdigini gor)
    tops = sorted(((pl.z + pbid[pl.part_id].orientations[pl.orientation_idx]
                    .grid.shape[2]) * PITCH,
                   str(getattr(pbid[pl.part_id], "name", pl.part_id)))
                  for pl in b.placements)[::-1]
    log(f"[{etiket}] height-driver ilk5: "
        + " | ".join(f"{h_:.0f}:{a[:24]}" for h_, a in tops[:5]))
    if legal is not None:
        out = _ROOT / "results" / f"plan1_nogo335_tilt_{etiket}_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return legal, b


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN1 HEDEFLI-TILT — 335+NOGO (n24 dik baseline 260 / Magics 110.41)")
    # RAM zinciri (2026-07-09): plan3 NFV probu bitene kadar bekle (tek surec
    # kurali; o da d4 probunu, o da ax24 kuyrugunu bekliyor).
    bekle = Path(__file__).parent / "plan3_nfv_probu.log"
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     bekle.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if bekle.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"plan3 NFV probu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — tilt kosusu basliyor")
    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    nx, ny = int(PLATE[0] // PITCH), int(PLATE[1] // PITCH)
    t = time.perf_counter()
    parts = to_voxel_parts(inst, PITCH, n_orientations=N_OR, margin=MARGIN)
    log(f"voxelize n{N_OR}: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    hedefler = [p for p in parts if HEDEF_AD in str(getattr(p, "name", "")).lower()]
    if not hedefler:
        log(f"HATA: '{HEDEF_AD}' isimli parca yok — adlar: "
            + ", ".join(sorted({str(getattr(p, 'name', '?'))[:30] for p in parts})))
        return
    # A) baseline: tilt'siz (ayni script, ayni parametreler — temiz A/B)
    h_base, b_base = _kos(parts, n_total, "baseline_n24")

    # B) tilt: esik = cozumun hedef icin FIILEN kullandigi pozun z'si
    # (onceki kosu dersi: "grid'e sigan" duz poz no-go yuzunden yerlesemiyor
    # ama min-z esigini 41'e cekip TUM tilt pozlarini elemisti -> 260=260)
    kullanilan_z = {}
    for pl in b_base.placements:
        kullanilan_z[pl.part_id] = \
            parts_by_id(parts)[pl.part_id].orientations[pl.orientation_idx].grid.shape[2]
    for p in hedefler:
        z_esik = kullanilan_z.get(p.id, 10 ** 9)
        log(f"hedef: {p.name[:40]}  cozumde-kullanilan-poz-z={z_esik}vox — tilt taramasi:")
        yeni = _tilt_pozlari(p, nx, ny, z_esik)
        if yeni:
            p.orientations = list(p.orientations) + yeni
            log(f"  +{len(yeni)} tilt pozu eklendi (orijinaller korundu)")
        else:
            log("  hicbir tilt pozu kazanmadi — tilt bu parcada NO-GO")
    h_tilt, _ = _kos(parts, n_total, "tilt_n24")

    if h_base is not None and h_tilt is not None:
        log(f"KIYAS: baseline={h_base:.1f} -> tilt={h_tilt:.1f}"
            f"  ({h_tilt - h_base:+.1f}mm, %{(h_tilt / h_base - 1) * 100:+.1f})"
            f"  Magics=110.41 -> tilt/Magics=+%{(h_tilt / 110.41 - 1) * 100:.1f}")
    log("BITTI")


if __name__ == "__main__":
    main()
