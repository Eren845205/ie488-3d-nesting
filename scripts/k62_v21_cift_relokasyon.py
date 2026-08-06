# -*- coding: utf-8 -*-
"""k62_v21_cift_relokasyon.py — K-62 v21: TEPE-BANDI CIFT-RELOKASYON.

v20 (tekil relokasyon) 129.60 -> 127.20 LEGAL aldi; kalan tepe 5'lisi
(3 pyramid + 2 bobbin_3) tek-parca hamleyle kirilamiyor (karsilikli
destek). v21: ayni zincir + tepe-bandi (en ust voxel bandi) parcalarindan
2'li kombinasyonlar birlikte sokulur (110 pin) — cift-parca serbestligi
BLB'ye es-zamanli yeniden-yerlestirme alani acar. Tek-tarafli kabul.

Akis: taban (z=64.8 uclu, 129.60) -> v20 tekil replay ILK KABULE dek
(d3 TAPER -> 127.20, deterministik) -> cift kombinasyon dongusu -> settle
final -> A2.

Kosum: python -m scripts.detach_run k62_v21_cift_relokasyon  (D). ASCII.
Env: K62V21_MAXCIFT (14). SERH (A11): tek-set on-olcum.
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
import traceback
from itertools import combinations
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

LOG = Path(__file__).parent / "k62_v21_cift_relokasyon.log"
OUT = _ROOT / "results" / "k62_v21_cift_relokasyon.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_TEKIL = 5                 # v20 replay guvenligi (d3'te kabul beklenir)
MAX_CIFT = int(os.environ.get("K62V21_MAXCIFT", "14"))
REF = {"v20": 127.20, "kapi_129": 129.00, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v21: tepe-bandi cift-relokasyon")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}"
        f" max_cift={MAX_CIFT}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])

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

    res = coz(rutbeler=UCLU)
    h_iyi = float(res.height_mm)
    pt = float(res.coarse_pitch)
    log(f"[taban] h={h_iyi:.2f} n={int(res.n_placed)}/{n_total}"
        f" pitch={pt:.3f}")

    # ---- v20 tekil replay (ILK kabule dek) ------------------------------
    denendi = set()
    for d in range(1, MAX_TEKIL + 1):
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
        r = coz(pinler=pinler, pitch=pt)
        hr = float(r.height_mm)
        kabul = (int(r.n_placed) == n_total and hr < h_iyi - 0.01)
        log(f"[tekil d{d}] {hedef_p['ad']:24s} -> h={hr:.2f}"
            f" ({'KABUL' if kabul else 'gecildi'})")
        if kabul:
            del res
            gc.collect()
            res, h_iyi = r, hr
            break                      # ilk kabul yeter (v20 kaniti)
        del r
        gc.collect()
    log(f"[tekil] sahne h={h_iyi:.2f}")

    # ---- cift kombinasyon dongusu --------------------------------------
    cift_kayit = []
    n_deneme = 0
    yeniden = True
    while yeniden and n_deneme < MAX_CIFT:
        yeniden = False
        dokum = _dokum(res)
        dokum.sort(key=lambda k: -k["ust"])
        tepe_esik = h_iyi - pt - 1e-6      # en ust voxel bandi
        tepe = [p for p in dokum if p["ust"] > tepe_esik]
        log(f"[cift] tepe bandi ({tepe_esik:.1f}+): {len(tepe)} parca"
            f" {sorted(set(p['ad'] for p in tepe))}")
        for a, b in combinations(range(len(tepe)), 2):
            if n_deneme >= MAX_CIFT:
                break
            n_deneme += 1
            pa, pb = tepe[a], tepe[b]
            pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
                       "z_mm": q["z_mm"], "rot": q["rot"]}
                      for q in dokum if q is not pa and q is not pb]
            t1 = time.perf_counter()
            r = coz(pinler=pinler, pitch=pt)
            hr = float(r.height_mm)
            nr = int(r.n_placed)
            kabul = (nr == n_total and hr < h_iyi - 0.01)
            log(f"[cift {n_deneme}] {pa['ad']}+{pb['ad']}"
                f" -> h={hr:.2f} n={nr}/{n_total}"
                f" ({'KABUL' if kabul else 'gecildi'})"
                f" {(time.perf_counter() - t1)/60:.1f}dk")
            cift_kayit.append({"cift": [pa["ad"], pb["ad"]], "h": hr,
                               "n": nr, "kabul": kabul})
            if kabul:
                del res
                gc.collect()
                res, h_iyi = r, hr
                yeniden = True         # sahne degisti -> tepe yeniden
                break
            del r
            gc.collect()

    log(f"[cift] SONUC: h={h_iyi:.2f} (v20 127.20 / manuel 110.41)")

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

    doc = {"olcum": "k62_v21_cift_relokasyon",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": "A11 tek-set on-olcum (fix'li motor)",
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI},
           "ciftler": cift_kayit,
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
