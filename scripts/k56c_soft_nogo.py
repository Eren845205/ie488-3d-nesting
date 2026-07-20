# -*- coding: utf-8 -*-
"""k56c_soft_nogo.py — K-56c: plan1 SOFT NO-GO olcumu (Eren onayi 2026-07-19).

Baglam: K-56b(2) ince-aci NOTR cikti (202.18 bit-ozdes); hedef bandin
kendisi (x16-x19, z 119-132mm) HARD no-go'ya engelliydi (x19 1.6mm girisle
aciliyor). Hoca cevap 9 "cok ufak girisler kabul" + K-37 kaniti (maske y-ust
45->33 = T=12mm giris seridi; r4_duz 129.0 LEGAL o maskeyle) -> Eren karari:
soft no-go sozlesmeye girsin. Bu script SERHLI ON-OLCUM yapar (sozlesme
degisikliginin kendisi = NOGO_STD guncelleme + 4-set kapi + baseline, ayri).

Iki kol (ayni seed, eval_gate v2 sozlesmesi, yalniz NOGO farkli):
  A_soft = evaluate_set(plan1) DOGAL routing — soft'ta duz baseplate
      dikdortgen-testi SINIRDA acilabilir (302.0 <= 302.0) -> tilt-zorunlu
      kapi soner; ama dilate fp (306.8) yerlesim duzeyinde sigmayabilir =
      "filtre dersi" zehirlenme riski. Ne olursa olsun OLCULUR (kapi
      davranisi = sozlesme degisikliginin gercek etkisi).
  B_soft = soft-filtreli hedefli-tilt taramasi (x5..x50 @1) + acik
      extra_rot_overrides — soft limitle (otede 302mm) yeni acilan dusuk
      acilar dahil. Beklenti: x12-x19 bandi z ~100-132mm.

Referanslar: hard-uretim 202.18 · K-37 serhli 129.0 · manuel 110.41.
Kosum: python -m scripts.detach_run k56c_soft_nogo    (D:\\ie488'den)
Cikti: scripts/k56c_soft_nogo.log + results/k56c_soft_nogo.json
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

import scripts.eval_gate as eg
from src.nesting3d.coarse_to_fine import cap_margin_to_plate, clearance_to_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k56_plan1_uretim_tilt import CLEAR_MM, HEDEF_AD, SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k56c_soft_nogo.log"
OUT = _ROOT / "results" / "k56c_soft_nogo.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))   # K-37 maskesi: y-ust 45->33
ACILAR = range(5, 51)                        # @1 — soft'ta acilan dusuk banda in
REF_HARD = 202.18468017578127
REF_K37 = 129.0
MANUEL = 110.41


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _yerlesebilir_soft(fp_x_mm, fp_y_mm):
    """K-56a dikdortgen testi, SOFT no-go sinirlariyla."""
    pw, pd = eg.PLATE_STD
    (ng_x1, ng_y1), (ng_x2, ng_y2) = NOGO_SOFT
    solda = fp_x_mm <= ng_x1 and fp_y_mm <= pd
    sagda = fp_x_mm <= (pw - ng_x2) and fp_y_mm <= pd
    otede = fp_y_mm <= (pd - ng_y2) and fp_x_mm <= pw
    return bool(solda or sagda or otede)


def _ozet(r):
    return (f"legal={r['legal_height_mm']}  h={r['height_mm']}"
            f"  clear={r['min_clearance_mm']}  kilit={r['n_locked']}"
            f"  sure={r['duration_s']}s  invalid={r['invalid_reason']}")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56c PLAN1 SOFT NO-GO ON-OLCUMU (serhli; sozlesme degisikligi ayri)")
    log(f"plaka={eg.PLATE_STD} nogo HARD={eg.NOGO_STD} -> SOFT={NOGO_SOFT}")
    log(f"ref: hard-uretim {REF_HARD:.2f} / K-37 serhli {REF_K37} /"
        f" manuel {MANUEL}")

    # ---- SOZLESME YAMASI: eval_gate.NOGO_STD call-time okunur ----
    eg.NOGO_STD = NOGO_SOFT

    # ---- A_soft: dogal routing ----
    log("[A_soft] evaluate_set(plan1) — soft no-go, dogal routing...")
    try:
        res_a = eg.evaluate_set("plan1", SEED)
        log(f"[A_soft] SONUC: {_ozet(res_a)}")
    except Exception as e:
        res_a = {"exception": f"{type(e).__name__}: {e}"}
        log(f"[A_soft] EXCEPTION: {type(e).__name__}: {e}")

    # ---- soft-filtreli tilt taramasi ----
    inst = eg._load_instance("plan1")
    fine_pitch, wall = _uretim_fine_pitch(inst)
    margin, _zc = clearance_to_voxels(CLEAR_MM, fine_pitch)
    margin, _capped = cap_margin_to_plate(
        margin, fine_pitch, inst, eg.PLATE_STD[0], eg.PLATE_STD[1])
    nx, ny = (int(eg.PLATE_STD[0] // fine_pitch),
              int(eg.PLATE_STD[1] // fine_pitch))
    log(f"uretim parametreleri: fine_pitch={fine_pitch} margin={margin}"
        f" grid={nx}x{ny}")

    p0 = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()][0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])

    vp4 = voxelize_part(p0.name, mesh, fine_pitch, n_orientations=4,
                        margin=margin, method="slice")
    z_esik_vox = 10 ** 9
    for i, o in enumerate(vp4.orientations):
        fx, fy = o.grid.shape[0] * fine_pitch, o.grid.shape[1] * fine_pitch
        log(f"  n4 poz{i}: fp={o.grid.shape[0]}x{o.grid.shape[1]}"
            f" z={o.grid.shape[2]}  soft-yerlesebilir="
            f"{_yerlesebilir_soft(fx, fy)}")
        if _yerlesebilir_soft(fx, fy) and o.grid.shape[2] < z_esik_vox:
            z_esik_vox = o.grid.shape[2]
    log(f"z-esigi = {z_esik_vox} vox ({z_esik_vox * fine_pitch:.1f}mm)")

    log("soft-filtreli tarama (x5..x50 @1):")
    rots, tablo = [], []
    for ang in ACILAR:
        R = trimesh.transformations.rotation_matrix(
            np.deg2rad(ang), [1, 0, 0])
        vp = voxelize_part(p0.name, mesh, fine_pitch, rot_matrices=[R],
                           method="slice", margin=margin)
        g = vp.orientations[0].grid
        fx, fy = g.shape[0] * fine_pitch, g.shape[1] * fine_pitch
        sigar = g.shape[0] <= nx and g.shape[1] <= ny
        yerl = _yerlesebilir_soft(fx, fy)
        kisa = g.shape[2] < z_esik_vox
        al = sigar and yerl and kisa
        durum = ("ALINDI" if al else
                 ("sigmiyor" if not sigar else
                  ("no-go-engelli" if not yerl else "uzun")))
        tablo.append({"poz": f"x{ang}", "fp": [g.shape[0], g.shape[1]],
                      "z": g.shape[2], "durum": durum})
        log(f"    x{ang:>2}: fp={g.shape[0]}x{g.shape[1]}"
            f" z={g.shape[2]} (~{g.shape[2] * fine_pitch:.1f}mm)  {durum}")
        if al:
            rots.append(R)
    log(f"kabul: {len(rots)} poz")

    # ---- B_soft: acik hedefli-tilt ----
    res_b = None
    if rots:
        log(f"[B_soft] evaluate_set(plan1, extra_rot_overrides={len(rots)}"
            f" poz)...")
        try:
            res_b = eg.evaluate_set("plan1", SEED,
                                    extra_rot_overrides={p0.name: rots})
            log(f"[B_soft] SONUC: {_ozet(res_b)}")
        except Exception as e:
            res_b = {"exception": f"{type(e).__name__}: {e}"}
            log(f"[B_soft] EXCEPTION: {type(e).__name__}: {e}")

    # ---- kiyas ----
    a_l = res_a.get("legal_height_mm") if isinstance(res_a, dict) else None
    b_l = res_b.get("legal_height_mm") if isinstance(res_b, dict) else None
    log(f"KIYAS: hard-uretim {REF_HARD:.1f} | A_soft {a_l} | B_soft {b_l}"
        f" | K-37 {REF_K37} | manuel {MANUEL}")
    OUT.write_text(json.dumps({
        "nogo_soft": NOGO_SOFT, "a_soft": res_a, "b_soft": res_b,
        "pozlar": tablo, "fine_pitch": fine_pitch, "margin": margin,
        "z_esik_vox": z_esik_vox, "kabul": len(rots),
        "ref": {"hard": REF_HARD, "k37": REF_K37, "manuel": MANUEL},
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"JSON: {OUT}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
