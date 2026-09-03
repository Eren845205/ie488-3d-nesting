# -*- coding: utf-8 -*-
"""k62_v23_mtshoe_poz.py — K-62 v23: MTShoe HEDEFLI POZ ACILIMI (cerrahi).

v22 envanteri: MTShoe min8=58.0 vs min28=22.4 (poz 24; 35.6mm durus
kazanci) — diger tavan tipleri icin poz ekseni olu. v22 n24 A/B ise
139.20 NET ZARAR (tum menuyu acmak BLB acgozlusunu bozuyor). v23 cerrahi
yol: orientation_overrides ile YALNIZ MTShoe menusune 8-disi alcak pozlar
eklenir (0..7 + aday pozlar); diger her sey n8 BIREBIR -> taban korunur,
MTShoe alcak durusa erisir.

Akis: taban (z=64.8 uclu + MTShoe-override) -> v20 tekil-relokasyon kisa
zinciri (max 8) -> settle -> A2. Ref: v20 127.20.

Kosum: python -m scripts.detach_run k62_v23_mtshoe_poz  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum. NOT: override tetigi su an AD-SABIT (MTShoe)
— mekanizma kabloya alinirsa tetik geometriklestirilir (envanter kurali:
min8-min28 > esik olan tipe otomatik poz-aciligi) + dagilimsal olcum.
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

LOG = Path(__file__).parent / "k62_v23_mtshoe_poz.log"
OUT = _ROOT / "results" / "k62_v23_mtshoe_poz.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_RELOK = 8
REF = {"v20": 127.20, "n8_taban": 129.60, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
# v22 envanteri: poz 24 = min28 durusu (22.4mm). 8'li default menu + alcak
# aday pozlar (24 ve komsu yeni-eksen pozlari 25-27; hepsi eksen-hizali R1).
MTSHOE_POZLAR = tuple(range(8)) + (24, 25, 26, 27)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v23: MTShoe hedefli poz acilimi (cerrahi override)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}"
        f" mtshoe_pozlar={MTSHOE_POZLAR}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh0, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh0)[0])
    OVR = {"MTShoe": MTSHOE_POZLAR}

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
                         oncelik_adlari=(rutbeler or None),
                         orientation_overrides=OVR)

    res = coz(rutbeler=UCLU)
    h_iyi = float(res.height_mm)
    pt = float(res.coarse_pitch)
    log(f"[taban] h={h_iyi:.2f} n={int(res.n_placed)}/{n_total}"
        f" pitch={pt:.3f}  [ref: n8 129.60 / v20 127.20]")

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
        log(f"[d{d}] {hedef_p['ad']:22s} ust={hedef_p['ust']:6.1f}"
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

    log(f"[relokasyon] SONUC: h={h_iyi:.2f} (v20 127.20 / manuel 110.41)")

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

    doc = {"olcum": "k62_v23_mtshoe_poz",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-set on-olcum; override tetigi AD-SABIT (deney) "
                    "— kabloya alinirsa geometriklestirilir + dagilimsal"),
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI,
                        "mtshoe_pozlar": list(MTSHOE_POZLAR)},
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
    log(f"OZET: final={h_iyi:.2f}")
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
