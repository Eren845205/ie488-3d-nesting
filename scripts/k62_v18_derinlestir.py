# -*- coding: utf-8 -*-
"""k62_v18_derinlestir.py — K-62 v18: 129.00-ALTI DERINLESTIRME ZINCIRI.

Kapi otomatik zinciri (fix'li motor) 129.00 LEGAL buldu (z=65.3 -> iz=27).
Sabit-nokta analizi iki acilmamis ekseni gosteriyor:

  FAZ-A  z-VOXEL taramasi: z=65.3 ve z=67 aslinda iz=27/28'e snap oluyor;
         iz 26..29 (62.4 / 64.8 / 67.2 / 69.6 mm @2.4) hic sistematik
         taranmadi. Uclu oncelik sabit; en iyi taban secilir.
  FAZ-B  KADEMELI rip-up + SIRA perturbasyonu: rip-up sabit-noktasinin
         nedeni BLB'nin deterministik hacim-azalan sirasi. Her kademede
         (hedef = h_iyi - pitch) sokulenlere 4 sira varyanti denenir:
         V0 default (hacim-azalan) / V1 en-UZUN-once / V2 en-KISA-once /
         V3 kule-tipleri-once. Tek-tarafli: iyilesen tutulur, kademe iner.
  FAZ-C  kazanana A2 tam legalite (clearance + 5-yon kilit + gerek rot).

Kosum: python -m scripts.detach_run k62_v18_derinlestir  (D:\\ie488). ASCII.
Env: K62V18_MAXKADEME (4). SERH (A11): tek-set on-olcum.
"""
from __future__ import annotations

import gc
import json
import os
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
from scripts.k62_v17_ripup import _pinler_ve_sokulenler, a2_olc

LOG = Path(__file__).parent / "k62_v18_derinlestir.log"
OUT = _ROOT / "results" / "k62_v18_derinlestir.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_LISTE = [62.4, 64.8, 67.2, 69.6]          # iz 26..29 @2.4
MAX_KADEME = int(os.environ.get("K62V18_MAXKADEME", "4"))
REF = {"kapi_otomatik": 129.00, "v17c": 131.40, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
KULE_TIPLERI = ("811793-1", "bobbin_1_v2", "bobbin_2_v2", "bobbin_3_v2",
                "pyramid_with_doors", "TAPER-GAUGE-1")


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v18: 129.00-alti derinlestirme (z-voxel + kademeli rip-up)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])

    def coz(z_mm, pinler=None, rutbeler=None, pitch=None, settle=False):
        if pinler is None:
            pinler = [{"ad": p0.name, "x_mm": float(poz["dx_mm"]),
                       "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
                       "rot": rot_k.tolist()}]
        return solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                         plate_d_mm=eg.PLATE_STD[1],
                         fine_pitch=pitch, fine_settle=settle, seed=SEED,
                         quality="fast", clearance_mm=CLEAR_MM,
                         no_go_bounds=eg.NOGO_STD,
                         pinned_placements=pinler, pin_3d=True,
                         oncelik_adlari=(rutbeler or None))

    # ---- FAZ-A: z-voxel taramasi (uclu oncelik) -------------------------
    log("[A] z-voxel taramasi (iz 26..29, uclu oncelik)")
    en_iyi = None
    faz_a = []
    for z in Z_LISTE:
        t1 = time.perf_counter()
        r = coz(z, rutbeler=UCLU)
        h = float(r.height_mm)
        n = int(r.n_placed)
        faz_a.append({"z": z, "h": h, "n": n,
                      "sure_s": round(time.perf_counter() - t1, 1)})
        log(f"  z={z:5.1f} -> h={h:.2f} n={n}/{n_total}"
            f" ({(time.perf_counter() - t1)/60:.1f}dk)")
        if n == n_total and (en_iyi is None or h < en_iyi[1] - 0.01):
            if en_iyi is not None:
                del en_iyi
                gc.collect()
            en_iyi = (z, h, r)
        else:
            del r
            gc.collect()
    if en_iyi is None:
        log("FAZ-A hic tam cozum vermedi -> dur")
        return
    z_iyi, h_iyi, res = en_iyi
    pt = float(res.coarse_pitch)
    log(f"[A] SONUC: z={z_iyi} h={h_iyi:.2f} pitch={pt:.3f}")

    # ---- FAZ-B: kademeli rip-up + sira perturbasyonu --------------------
    log("[B] kademeli rip-up (4 sira varyanti / kademe)")

    def sira_varyantlari(sokulen):
        """[(etiket, rutbeler|None)] — sokulen tip adlarina gore."""
        # sokulen: [(ad, alt, ust)] -> tip yuksekligi = ust-alt (max kopya)
        boy = {}
        for ad, alt, ust in sokulen:
            boy[ad] = max(boy.get(ad, 0.0), float(ust) - float(alt))
        uzun = sorted(boy, key=lambda a: -boy[a])
        v1 = {a: i for i, a in enumerate(uzun)}                 # uzun once
        v2 = {a: i for i, a in enumerate(reversed(uzun))}       # kisa once
        v3 = {a: (0 if a in KULE_TIPLERI else 1) for a in boy}  # kule once
        return [("V0-default", None), ("V1-uzun", v1),
                ("V2-kisa", v2), ("V3-kule", v3)]

    kademeler = []
    son_kabul = None                      # (pinler, rutbeler) — settle'li tekrar icin
    for k in range(1, MAX_KADEME + 1):
        hedef = h_iyi - pt
        pinler, sokulen = _pinler_ve_sokulenler(res, hedef)
        if not sokulen:
            log(f"[B k{k}] hedef={hedef:.1f}: sokulecek yok -> dur")
            break
        tipler = {}
        for ad, _a, _u in sokulen:
            tipler[ad] = tipler.get(ad, 0) + 1
        log(f"[B k{k}] hedef={hedef:.1f} pin={len(pinler)}"
            f" sokulen={len(sokulen)} {tipler}")
        kabul_var = False
        for etiket, rutbeler in sira_varyantlari(sokulen):
            t1 = time.perf_counter()
            r = coz(None, pinler=pinler, rutbeler=rutbeler, pitch=pt)
            hr = float(r.height_mm)
            nr = int(r.n_placed)
            kabul = (nr == n_total and hr < h_iyi - 0.01)
            log(f"  {etiket:10s} h={hr:.2f} n={nr}/{n_total}"
                f" ({'KABUL' if kabul else 'gecildi'})"
                f" {(time.perf_counter() - t1)/60:.1f}dk")
            kademeler.append({"kademe": k, "varyant": etiket, "hedef": hedef,
                              "h": hr, "n": nr, "kabul": kabul})
            if kabul:
                del res
                gc.collect()
                res, h_iyi = r, hr
                son_kabul = (pinler, rutbeler)
                kabul_var = True
                break            # kademe kazandi -> yeni tabandan devam
            del r
            gc.collect()
        if not kabul_var:
            log(f"[B k{k}] hicbir varyant iyilestirmedi -> dur")
            break

    log(f"[B] SONUC: h={h_iyi:.2f} (kapi 129.00 / manuel 110.41)")

    # ---- FAZ-B2: kazanan kombinasyonun SETTLE'LI tekrari (tek kosu) -----
    # (kademe kabulu yoksa faz-A kazanani z ile; settle kuantizasyon
    #  geri-alimi v13b/v17c'de ~0.6mm getirmisti — tek-tarafli kabul.)
    t1 = time.perf_counter()
    if son_kabul is not None:
        rs = coz(None, pinler=son_kabul[0], rutbeler=son_kabul[1],
                 pitch=pt, settle=True)
    else:
        rs = coz(z_iyi, rutbeler=UCLU, settle=True)
    hs = float(rs.height_mm)
    ns = int(rs.n_placed)
    log(f"[B2] settle'li tekrar: h={hs:.2f} n={ns}/{n_total}"
        f" ({(time.perf_counter() - t1)/60:.1f}dk)")
    if ns == n_total and hs < h_iyi - 0.01:
        del res
        gc.collect()
        res, h_iyi = rs, hs
        log(f"[B2] KABUL: h={h_iyi:.2f}")
    else:
        del rs
        gc.collect()
        log("[B2] gecildi (settle iyilestirmedi)")

    # ---- FAZ-C: A2 tam legalite ----------------------------------------
    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[C] A2: clearance={a2['min_clearance_mm']}"
            f" kilit5={a2['kilit_5yon']} rot={a2['rot_kilit']}"
            f" sokum_planli={a2['sokum_planli']}"
            f" -> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[C] A2 OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {"olcum": "k62_v18_derinlestir",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": "A11 tek-set on-olcum (fix'li motor)",
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED},
           "faz_a": faz_a, "z_iyi": z_iyi, "kademeler": kademeler,
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
    log(f"OZET: final={h_iyi:.2f} z={z_iyi}")
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
