# -*- coding: utf-8 -*-
"""k62_v24_zemin_once.py — K-62 v24: ZEMIN-ONCE rutbe varyantlari.

Analiz (envanter + kalinlik 40.64 + v19 anatomi):
  * Manuel 110.41 tavani = kule dik-boyu (811793 110.8) + kanopi zarfi
    (z~69.8 + 40.64); kanopi bandimiz (64.8) ZATEN dogru — yuksek-kanopi olu.
  * 127.2 surucusu: pyramid x5 (88x88x59.3) kanopi cukuruna oturuyor
    (67.9+59.3). Tepe <=110 icin taban <=50.7 gerek = ZEMIN. Zemine ancak
    BOS zeminde girebilir (fragmentasyon sonrasi imkansiz) -> simdiye dek
    pyramid hep rutbe-1'e (kulelerden SONRA) denendi ve patladi; ONCE hic
    denenmedi.
Mekanizma: genis-footprint yukseklik-surucu tipler (pyramid + part262835 +
M18 + MTShoe sinifi) rutbe-0'a alinir (zemin-once); kuleler rutbe-1'de
delikten gecer; gerisi dolgu. 5 varyant taranir, en iyisinden tekil-
relokasyon + settle + A2.

Kosum: python -m scripts.detach_run k62_v24_zemin_once  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum; varyant adlari deney-ici (kabloya alinirsa
tetik geometriklestirilir: boy>esik VE footprint>delik -> zemin-once).
"""
from __future__ import annotations

import gc
import json
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh.transformations as tt

import scripts.eval_gate as eg
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v17_ripup import a2_olc
from scripts.k62_v20_relokasyon import _dokum

LOG = Path(__file__).parent / "k62_v24_zemin_once.log"
OUT = _ROOT / "results" / "k62_v24_zemin_once.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_RELOK = 8
REF = {"v20_v23_plato": 127.20, "manuel": 110.41}
KULELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
VARYANTLAR = [
    ("R1 pyr0-kule1",
     {"pyramid_with_doors": 0,
      "811793-1": 1, "bobbin_2_v2": 1, "bobbin_1_v2": 1}),
    ("R2 hepsi-r0",
     {"pyramid_with_doors": 0,
      "811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}),
    ("R3 genis0-kule1",
     {"pyramid_with_doors": 0, "part262835": 0,
      "M18_toShopVac_Adapter": 0, "MTShoe": 0,
      "811793-1": 1, "bobbin_2_v2": 1, "bobbin_1_v2": 1}),
    ("R4 kule0-pyr0-b3-1",
     {"pyramid_with_doors": 0, "bobbin_3_v2": 1,
      "811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}),
    ("R5 genis0-kule1-b3-2",
     {"pyramid_with_doors": 0, "part262835": 0,
      "M18_toShopVac_Adapter": 0, "MTShoe": 0,
      "811793-1": 1, "bobbin_2_v2": 1, "bobbin_1_v2": 1,
      "bobbin_3_v2": 2, "TAPER-GAUGE-1": 2}),
]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v24: ZEMIN-ONCE rutbe varyantlari")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh0, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh0)[0])

    def coz(pinler=None, rutbeler=None, pitch=None, settle=False):
        if pinler is None:
            pinler = [{"ad": p0.name, "x_mm": float(poz["dx_mm"]),
                       "y_mm": float(poz["dy_mm"]), "z_mm": Z_IYI,
                       "rot": rot_k.tolist()}]
        return solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                         plate_d_mm=eg.PLATE_STD[1],
                         fine_pitch=pitch, fine_settle=settle, seed=SEED,
                         quality="fast", clearance_mm=CLEAR_MM,
                         no_go_bounds=eg.NOGO_STD,
                         pinned_placements=pinler, pin_3d=True,
                         oncelik_adlari=(rutbeler or None))

    # ---- FAZ-A: varyant taramasi ---------------------------------------
    en_iyi = None
    faz_a = []
    for etiket, rutbeler in VARYANTLAR:
        t1 = time.perf_counter()
        r = coz(rutbeler=rutbeler)
        h = float(r.height_mm)
        n = int(r.n_placed)
        faz_a.append({"varyant": etiket, "h": h, "n": n})
        log(f"[A] {etiket:22s} -> h={h:.2f} n={n}/{n_total}"
            f" ({(time.perf_counter() - t1)/60:.1f}dk)")
        if n == n_total and (en_iyi is None or h < en_iyi[1] - 0.01):
            if en_iyi is not None:
                _, _, eski = en_iyi
                del eski
                gc.collect()
            en_iyi = (etiket, h, r)
        else:
            del r
            gc.collect()
    if en_iyi is None:
        log("[A] hicbir varyant tam cozum vermedi -> dur")
        return
    et_iyi, h_iyi, res = en_iyi
    pt = float(res.coarse_pitch)
    log(f"[A] SONUC: {et_iyi} h={h_iyi:.2f} (plato 127.20)")

    # ---- FAZ-B: tekil relokasyon ---------------------------------------
    denemeler = []
    denendi = set()
    for d in range(1, MAX_RELOK + 1):
        dokum = _dokum(res)
        dokum.sort(key=lambda k: -k["ust"])
        hedef_p = None
        for p in dokum:
            anahtar = (p["ad"], round(p["x_mm"], 1), round(p["y_mm"], 1),
                       round(p["z_mm"], 1))
            if anahtar not in denendi:
                hedef_p = p
                denendi.add(anahtar)
                break
        if hedef_p is None:
            break
        pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
                   "z_mm": q["z_mm"], "rot": q["rot"]}
                  for q in dokum if q is not hedef_p]
        t1 = time.perf_counter()
        r = coz(pinler=pinler, pitch=pt)
        hr = float(r.height_mm)
        nr = int(r.n_placed)
        kabul = (nr == n_total and hr < h_iyi - 0.01)
        log(f"[B d{d}] {hedef_p['ad']:22s} ust={hedef_p['ust']:6.1f}"
            f" -> h={hr:.2f} n={nr}/{n_total}"
            f" ({'KABUL' if kabul else 'gecildi'})"
            f" {(time.perf_counter() - t1)/60:.1f}dk")
        denemeler.append({"d": d, "ad": hedef_p["ad"], "h": hr,
                          "n": nr, "kabul": kabul})
        if kabul:
            del res
            gc.collect()
            res, h_iyi = r, hr
            denendi.clear()
        else:
            del r
            gc.collect()

    log(f"[B] SONUC: h={h_iyi:.2f} (plato 127.20 / manuel 110.41)")

    # ---- settle final + A2 ---------------------------------------------
    dokum = _dokum(res)
    dokum.sort(key=lambda k: k["ust"])
    pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
               "z_mm": q["z_mm"], "rot": q["rot"]}
              for q in dokum[1:]]
    t1 = time.perf_counter()
    rs = coz(pinler=pinler, pitch=pt, settle=True)
    hs = float(rs.height_mm)
    ns = int(rs.n_placed)
    log(f"[B2] settle'li final: h={hs:.2f} n={ns}/{n_total}"
        f" ({(time.perf_counter() - t1)/60:.1f}dk)")
    if ns == n_total and hs < h_iyi - 0.01:
        del res
        gc.collect()
        res, h_iyi = rs, hs
        log(f"[B2] KABUL: h={h_iyi:.2f}")
    else:
        del rs
        gc.collect()
        log("[B2] gecildi")

    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[A2] clearance={a2['min_clearance_mm']}"
            f" kilit5={a2['kilit_5yon']} rot={a2['rot_kilit']}"
            f" sokum_planli={a2['sokum_planli']}"
            f" -> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[A2] OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {"olcum": "k62_v24_zemin_once",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-set on-olcum; varyant rutbeleri deney-ici "
                    "(kablo tetigi: boy>esik VE footprint>delik -> "
                    "zemin-once, geometriklestirilecek)"),
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI},
           "faz_a": faz_a, "kazanan_varyant": et_iyi,
           "denemeler": denemeler,
           "final": {"height_mm": h_iyi, "a2": a2},
           "referanslar": REF}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
            log(f"kopya: {ek}")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")
    log(f"OZET: final={h_iyi:.2f} varyant={et_iyi}")
    log(f"WALL_S={time.perf_counter() - t0:.1f}"
        f"  ({(time.perf_counter() - t0) / 60:.1f} dk)")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
