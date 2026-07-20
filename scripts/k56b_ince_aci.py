# -*- coding: utf-8 -*-
"""k56b_ince_aci.py — K-56b(2): plan1 baseplate ince-aci x-tilt taramasi.

Baglam (YONTEM §5 K-56): K-56a kaba tarama (@5) uretim yolunu 302.8 -> 202.2
LEGAL yapti (kabul 14 poz x20-x85; y-tilt yapisal olu). Kaba poz tablosunun
kritik ipucu: z, aci kuculdukce TEKDUZE dusuyor (x20 z=135vox~137mm; x15
z=112vox~114mm AMA no-go-engelli: fp_y=292vox > 285.4vox esigi). Odul x16-x19
bandinda + @1 cozunurlukte — fp_y<=290mm saglayan EN KUCUK aci en kisa
baseplate'i verir. Hedef bandi 141-110 (eski dblf@1.0 kaniti 141.0;
manuel 110.41).

Tasarim:
  - Ince tarama: x16..x50 @1 (35 poz); filtre K-56a ile AYNI (grid'e sigar +
    no-go'suz plakaya geometrik yerlesebilir + z < yerlesebilir-default-esigi).
  - Kaba kazananlar x55..x85 @5 menuye EKLENIR -> B menusu K-56a menusunun
    USTKUMESI (eski optimum menude kalir; kume-icerme).
  - Tek B kosusu: evaluate_set("plan1", 42, extra_rot_overrides). A yeniden
    KOSULMAZ: 302.8 uc bagimsiz bit-ozdes replay'li (K-54 + k51e + K-56a);
    202.18 dun aksamki 4-set kapida da birebir — referanslar sabit alinir.

Kosum: python -m scripts.detach_run k56b_ince_aci    (D:\\ie488'den)
Cikti: scripts/k56b_ince_aci.log + results/k56b_ince_aci.json
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

from src.nesting3d.coarse_to_fine import cap_margin_to_plate, clearance_to_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.eval_gate import NOGO_STD, PLATE_STD, _load_instance, evaluate_set
from scripts.k56_plan1_uretim_tilt import (
    CLEAR_MM, HEDEF_AD, SEED, _uretim_fine_pitch, _yerlesebilir)

LOG = Path(__file__).parent / "k56b_ince_aci.log"
OUT = _ROOT / "results" / "k56b_ince_aci.json"
ACILAR_INCE = range(16, 51)          # @1 — odul bandi + K-56a kaba araligi
ACILAR_KABA = range(55, 90, 5)       # K-56a kabul edilen kaba kuyruk
REF_URETIM = 302.8                   # K-54/k51e/K-56a-A bit-ozdes replay
REF_K56A = 202.18468017578127        # K-56a B + 2026-07-18 kapi birebir
HEDEF_BANT = (141.0, 110.0)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _tarama(ad, mesh, pitch, margin, z_esik_vox, nx, ny, acilar):
    """x-tilt pozlarini filtreden gecir; (kabul_rotlar, tablo) doner."""
    ok, tablo = [], []
    for ang in acilar:
        R = trimesh.transformations.rotation_matrix(
            np.deg2rad(ang), [1, 0, 0])
        try:
            vp = voxelize_part(ad, mesh, pitch, rot_matrices=[R],
                               method="slice", margin=margin)
        except Exception as e:
            tablo.append({"poz": f"x{ang}", "durum":
                          f"voxelize HATA {type(e).__name__}"})
            log(f"    x{ang:>2}: voxelize HATA ({type(e).__name__})")
            continue
        g = vp.orientations[0].grid
        fx, fy = g.shape[0] * pitch, g.shape[1] * pitch
        sigar = g.shape[0] <= nx and g.shape[1] <= ny
        yerl = _yerlesebilir(fx, fy)
        kisa = g.shape[2] < z_esik_vox
        al = sigar and yerl and kisa
        durum = ("ALINDI" if al else
                 ("sigmiyor" if not sigar else
                  ("no-go-engelli" if not yerl else "uzun")))
        tablo.append({"poz": f"x{ang}", "fp": [g.shape[0], g.shape[1]],
                      "z": g.shape[2], "durum": durum})
        log(f"    x{ang:>2}: fp={g.shape[0]}x{g.shape[1]}"
            f" z={g.shape[2]} (~{g.shape[2] * pitch:.1f}mm)  {durum}")
        if al:
            ok.append(R)
    return ok, tablo


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56b(2) PLAN1 INCE-ACI TARAMASI (sozlesme: eval_gate v2)")
    log(f"plaka={PLATE_STD} nogo={NOGO_STD} seed={SEED}"
        f"  ref: uretim {REF_URETIM} / K-56a {REF_K56A:.2f}"
        f"  hedef bant {HEDEF_BANT}")

    inst = _load_instance("plan1")
    fine_pitch, wall = _uretim_fine_pitch(inst)
    margin, _zc = clearance_to_voxels(CLEAR_MM, fine_pitch)
    margin, _capped = cap_margin_to_plate(
        margin, fine_pitch, inst, PLATE_STD[0], PLATE_STD[1])
    nx, ny = int(PLATE_STD[0] // fine_pitch), int(PLATE_STD[1] // fine_pitch)
    log(f"uretim parametreleri: fine_pitch={fine_pitch} wall_aware={wall}"
        f" margin={margin} (capped={_capped}) grid={nx}x{ny}")

    hedef = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()]
    if not hedef:
        log("HATA: baseplate bulunamadi")
        log("BITTI")
        return
    p0 = hedef[0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])
    log(f"hedef: {p0.name}  extents={[round(float(e),1) for e in mesh.extents]}")

    # z-esigi K-56a ile ayni turetim (yerlesebilen default pozlarin min z'si)
    vp4 = voxelize_part(p0.name, mesh, fine_pitch, n_orientations=4,
                        margin=margin, method="slice")
    z_esik_vox, esik_kaynak = 10 ** 9, "yok"
    for i, o in enumerate(vp4.orientations):
        fx, fy = o.grid.shape[0] * fine_pitch, o.grid.shape[1] * fine_pitch
        if _yerlesebilir(fx, fy) and o.grid.shape[2] < z_esik_vox:
            z_esik_vox, esik_kaynak = o.grid.shape[2], f"poz{i}"
    log(f"z-esigi = {z_esik_vox} vox ({esik_kaynak};"
        f" {z_esik_vox * fine_pitch:.1f}mm)")

    log("ince tarama (x16..x50 @1):")
    rots_i, tablo_i = _tarama(p0.name, mesh, fine_pitch, margin,
                              z_esik_vox, nx, ny, ACILAR_INCE)
    log("kaba kuyruk (x55..x85 @5, K-56a kabulleri):")
    rots_k, tablo_k = _tarama(p0.name, mesh, fine_pitch, margin,
                              z_esik_vox, nx, ny, ACILAR_KABA)
    rots, tablo = rots_i + rots_k, tablo_i + tablo_k
    log(f"kabul: ince {len(rots_i)} + kaba {len(rots_k)} = {len(rots)} poz")
    if not rots:
        log("hicbir poz kabul edilmedi — beklenmedik (K-56a 14 kabul etmisti)")
        OUT.write_text(json.dumps({"b": None, "pozlar": tablo, "kabul": 0},
                                  indent=2), encoding="utf-8")
        log("BITTI")
        return

    log(f"[B] evaluate_set(plan1, extra_rot_overrides[{p0.name}]"
        f"={len(rots)} poz)...")
    res_b = evaluate_set("plan1", SEED,
                         extra_rot_overrides={p0.name: rots})
    log(f"[B] SONUC: legal={res_b['legal_height_mm']}"
        f"  h={res_b['height_mm']:.1f}  clear={res_b['min_clearance_mm']}"
        f"  kilit={res_b['n_locked']}  rot_kilit={res_b['n_locked_rot']}"
        f"  sokum_planli={res_b['sokum_planli']}"
        f"  sure={res_b['duration_s']}s"
        f"  invalid={res_b['invalid_reason']}")

    b_l = res_b["legal_height_mm"]
    if b_l is not None:
        log(f"KIYAS: uretim {REF_URETIM} -> K-56a {REF_K56A:.1f}"
            f" -> ince-aci {b_l:.1f}"
            f"  (K-56a'ya gore {b_l - REF_K56A:+.1f}mm)"
            f"  | hedef bant {HEDEF_BANT} | manuel 110.41")
    else:
        log(f"KIYAS: B INVALID ({res_b['invalid_reason']})")
    OUT.write_text(json.dumps({
        "b": res_b, "pozlar": tablo,
        "fine_pitch": fine_pitch, "margin": margin,
        "z_esik_vox": z_esik_vox,
        "kabul_ince": len(rots_i), "kabul_kaba": len(rots_k),
        "ref_uretim": REF_URETIM, "ref_k56a": REF_K56A,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
