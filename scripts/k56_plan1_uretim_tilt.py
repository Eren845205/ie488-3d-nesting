# -*- coding: utf-8 -*-
"""k56_plan1_uretim_tilt.py — K-56a: plan1 hedefli-tilt URETIM YOLU olcumu.

Baglam (YONTEM §5 K-56): uretim yolu plan1'de 302.8 (K-54 legal) — yuksekligin
~tamami baseplate'in DIK dikilme cezasi (duz poz no-go+335'te geometrik
imkansiz; k51d/K-54 kaniti). Eski dblf@1.0 deneyi (plan1_hedefli_tilt, hard
no-go): n24 dik 260.0 -> +19 tilt pozu = 141.0 LEGAL (-%45.8). K-56a sorusu:
ayni mekanizma URETIM-ESDEGER yolda (eval_gate evaluate_set -> heightmap c2f,
335+NOGO_STD, 2mm, 5-yon+rot-sokum olcumu) ne veriyor?

A/B (ayni seed, ayni sozlesme):
  A = evaluate_set("plan1", 42)                      -> referans (302.8 replay)
  B = evaluate_set("plan1", 42, extra_rot_overrides) -> baseplate'e hedefli
      dusuk-aci tilt pozlari (x/y 5..85@5; filtre: grid'e sigar + no-go'suz
      plakaya GEOMETRIK yerlesebilir + z < en-iyi-yerlesebilir-default-poz)

Filtre dersi (2026-07-09): esik "grid'e sigan" degil "YERLESEBILEN pozun z'si"
olmali — duz poz grid'e sigar ama no-go kolonu yuzunden yerlesemez; esigi
zehirlemesin diye yerlesebilirlik dikdortgen testiyle ayrilir.

Kosum: python -m scripts.detach_run k56_plan1_uretim_tilt   (D:\\ie488'den)
Cikti: scripts/k56_plan1_uretim_tilt.log + results/k56_plan1_uretim_tilt.json
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

LOG = Path(__file__).parent / "k56_plan1_uretim_tilt.log"
OUT = _ROOT / "results" / "k56_plan1_uretim_tilt.json"
SEED = 42
HEDEF_AD = "baseplate"       # height-driver (302.7 dik dikilme cezasi)
ACILAR = range(5, 90, 5)
EKSENLER = {"x": [1, 0, 0], "y": [0, 1, 0]}
CLEAR_MM = 2.0               # WEB_MIN_CLEARANCE_MM ile ayni (uretim sozlesmesi)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _yerlesebilir(fp_x_mm, fp_y_mm):
    """No-go kolonuyla kesismeden plakada EN AZ BIR konum var mi (dikdortgen
    testi; tilt-zorunlu kapinin dersi). Kolon: x[152.5,185.5] y[0.2,45]."""
    pw, pd = PLATE_STD
    (ng_x1, ng_y1), (ng_x2, ng_y2) = NOGO_STD
    solda = fp_x_mm <= ng_x1 and fp_y_mm <= pd
    sagda = fp_x_mm <= (pw - ng_x2) and fp_y_mm <= pd
    otede = fp_y_mm <= (pd - ng_y2) and fp_x_mm <= pw
    return bool(solda or sagda or otede)


def _uretim_fine_pitch(inst):
    """eval_gate._run_champion heightmap dali ile AYNI pitch tureti."""
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.instances.pitch import suggest_pitch
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    dec = predict_nfv_benefit(inst, family_routing=True, mode_model=_mm,
                              rot_sokum=True, no_go_bounds=NOGO_STD)
    mode = getattr(dec, "mode", "heightmap")
    wall = bool(getattr(dec, "wall_aware", False))
    if mode == "nfv":
        raise RuntimeError("plan1 NFV'ye yonlendi — K-56 varsayimi bozuldu")
    return suggest_pitch(inst, wall_aware=wall), wall


def _tilt_pozlari(ad, mesh, pitch, margin, z_esik_vox, nx, ny):
    """Hedefe x/y tilt taramasi; (kabul_rotlar, tablo) doner."""
    ok, tablo = [], []
    for ek, vec in EKSENLER.items():
        for ang in ACILAR:
            R = trimesh.transformations.rotation_matrix(
                np.deg2rad(ang), vec)
            try:
                vp = voxelize_part(ad, mesh, pitch, rot_matrices=[R],
                                   method="slice", margin=margin)
            except Exception as e:
                tablo.append({"poz": f"{ek}{ang}", "durum":
                              f"voxelize HATA {type(e).__name__}"})
                log(f"    {ek}{ang:>2}: voxelize HATA ({type(e).__name__})")
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
            tablo.append({"poz": f"{ek}{ang}", "fp": [g.shape[0], g.shape[1]],
                          "z": g.shape[2], "durum": durum})
            log(f"    {ek}{ang:>2}: fp={g.shape[0]}x{g.shape[1]}"
                f" z={g.shape[2]}  {durum}")
            if al:
                ok.append(R)
    return ok, tablo


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56a PLAN1 HEDEFLI-TILT URETIM-YOLU OLCUMU (sozlesme: eval_gate v2)")
    log(f"plaka={PLATE_STD} nogo={NOGO_STD} seed={SEED}")

    # ---- A: uretim referansi (302.8 replay beklenir) ----
    log("[A] evaluate_set(plan1) — uretim default'u...")
    res_a = evaluate_set("plan1", SEED)
    log(f"[A] SONUC: legal={res_a['legal_height_mm']}"
        f"  h={res_a['height_mm']:.1f}  clear={res_a['min_clearance_mm']}"
        f"  kilit={res_a['n_locked']}  rot_kilit={res_a['n_locked_rot']}"
        f"  sure={res_a['duration_s']}s"
        f"  invalid={res_a['invalid_reason']}")

    # ---- tilt taramasi (uretim pitch/margin'iyle) ----
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
        log("HATA: baseplate bulunamadi — adlar: "
            + ", ".join(sorted({str(p.name)[:30] for p in inst.parts})))
        log("BITTI")
        return
    p0 = hedef[0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])
    log(f"hedef: {p0.name}  extents={[round(float(e),1) for e in mesh.extents]}")

    # esik: default n4 setinde YERLESEBILEN pozlarin min z'si (filtre dersi:
    # duz poz grid'e sigar ama yerlesemez — esigi zehirlemesin)
    vp4 = voxelize_part(p0.name, mesh, fine_pitch, n_orientations=4,
                        margin=margin, method="slice")
    z_esik_vox, esik_kaynak = 10 ** 9, "yok"
    for i, o in enumerate(vp4.orientations):
        fx, fy = o.grid.shape[0] * fine_pitch, o.grid.shape[1] * fine_pitch
        yerl = _yerlesebilir(fx, fy)
        log(f"  n4 poz{i}: fp={o.grid.shape[0]}x{o.grid.shape[1]}"
            f" z={o.grid.shape[2]}  yerlesebilir={yerl}")
        if yerl and o.grid.shape[2] < z_esik_vox:
            z_esik_vox, esik_kaynak = o.grid.shape[2], f"poz{i}"
    log(f"z-esigi = {z_esik_vox} vox ({esik_kaynak};"
        f" {z_esik_vox * fine_pitch:.1f}mm)")

    log("tilt taramasi (x/y 5..85 @5):")
    rots, tablo = _tilt_pozlari(p0.name, mesh, fine_pitch, margin,
                                z_esik_vox, nx, ny)
    log(f"kabul edilen tilt pozu: {len(rots)}")
    if not rots:
        log("hicbir tilt pozu kazanmadi — K-56a NO-GO (uretim pitch'inde)")
        OUT.write_text(json.dumps({"a": res_a, "b": None, "pozlar": tablo,
                                   "fine_pitch": fine_pitch,
                                   "kabul": 0}, indent=2), encoding="utf-8")
        log("BITTI")
        return

    # ---- B: ayni sozlesme + hedefli-tilt ----
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

    # ---- kiyas ----
    a_l, b_l = res_a["legal_height_mm"], res_b["legal_height_mm"]
    if a_l is not None and b_l is not None:
        log(f"KIYAS: A={a_l:.1f} -> B={b_l:.1f}  ({b_l - a_l:+.1f}mm,"
            f" %{(b_l / a_l - 1) * 100:+.1f})"
            f"  | eski-dblf@1.0 tilt 141.0 | manuel 110.41")
    else:
        log(f"KIYAS: A={a_l} B={b_l} — en az biri INVALID, hukum log'da")
    OUT.write_text(json.dumps({
        "a": res_a, "b": res_b, "pozlar": tablo,
        "fine_pitch": fine_pitch, "margin": margin,
        "z_esik_vox": z_esik_vox, "kabul": len(rots),
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
