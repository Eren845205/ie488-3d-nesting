# -*- coding: utf-8 -*-
"""k62_v11c_secim.py — K-62 v11c: oncelik kumesi GREEDY ILERI-SECIM (SERHLI).

v11b dersi: asan-tipleri koru korune kumeye eklemek monoton DEGIL
(tur-2'de 8'li kume 165.6'ya patladi — genis/hacimli tipler onceliga
girince sira etkisi tersine donuyor). Oncelik kumesi kucuk bir ARAMA
problemi: v11c tip tek tek dener — iyilestiren TUTULUR, digeri GERI ALINIR
(greedy forward selection; aday havuzu cozumlerden dinamik beslenir).

SERHLER (A11+A2): tek-set; kilit olculmez; settle/repair pin_3d atlanir.
Kosum: python -m scripts.detach_run k62_v11c_secim  (D:\\ie488, sakin).
Env: K62V11C_Z (68) - K62V11C_MAXDENEME (12). SAF ASCII.
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
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v10_silo import _katman_telemetri, _silo_tipleri

LOG = Path(__file__).parent / "k62_v11c_secim.log"
OUT = _ROOT / "results" / "k62_v11c_secim.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
EPS = 0.01
REF = {"v11": 134.40, "v9": 139.20, "v4_kanopi": 136.50, "manuel": 110.41}
Z_MM = float(os.environ.get("K62V11C_Z", "68"))
MAX_DENEME = int(os.environ.get("K62V11C_MAXDENEME", "12"))
# BASLA="asan": kume asan-tiplerle (v11-B, bilinen iyi 134.4) BASLAR;
# ileri denemeler + GERI-cikarma turu oradan surer. Gerekce: ilk kosu
# dersi — tekil ekleme etkilesimi kaciriyor (bobbin_1 tek basina 156,
# ucluyle 134.4; kombinatorik etki).
BASLA = os.environ.get("K62V11C_BASLA", "").strip()


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v11c OLCUM: oncelik kumesi GREEDY ILERI-SECIM (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z={Z_MM}"
        f" max_deneme={MAX_DENEME}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    kalinlik = float(fiz["duz_kalinlik_mm"])
    kz2 = Z_MM + kalinlik
    pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
           "y_mm": float(poz["dy_mm"]), "z_mm": Z_MM, "rot": rot_k.tolist()}

    def coz(oncelik):
        r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                      plate_d_mm=eg.PLATE_STD[1],
                      fine_pitch=None, seed=SEED, quality="fast",
                      clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                      pinned_placements=[pin], pin_3d=True,
                      oncelik_adlari=(oncelik or None))
        return r

    denemeler = []
    kume: set = set()
    r_ref = coz(kume)
    h_ref = float(r_ref.height_mm)
    asan0 = _silo_tipleri(r_ref, p0.name, kz2)
    havuz = [ad for ad, _u in sorted(asan0.items(), key=lambda kv: -kv[1])]
    log(f"[ref] h={h_ref:.2f}  aday havuzu={havuz}")
    h_iyi = h_ref
    en_iyi_r = r_ref
    denemeler.append({"kume": [], "height_mm": h_ref, "karar": "ref"})
    if BASLA == "asan":
        kume = set(havuz)
        havuz = []
        r0 = coz(kume)
        h0 = float(r0.height_mm)
        log(f"[basla=asan] kume={sorted(kume)} -> h={h0:.2f}")
        denemeler.append({"kume": sorted(kume), "height_mm": h0,
                          "karar": "basla"})
        if int(r0.n_placed) == n_total and h0 < h_iyi - EPS:
            h_iyi = h0
            del en_iyi_r
            gc.collect()
            en_iyi_r = r0
            for a2, _u in sorted(_silo_tipleri(r0, p0.name, kz2).items(),
                                 key=lambda kv: -kv[1]):
                if a2 not in kume:
                    havuz.append(a2)
        else:
            del r0
            gc.collect()

    denendi: set = set()
    n_deneme = 0
    while havuz and n_deneme < MAX_DENEME:
        ad = havuz.pop(0)
        if ad in denendi or ad in kume:
            continue
        denendi.add(ad)
        n_deneme += 1
        aday_kume = kume | {ad}
        r = coz(aday_kume)
        h = float(r.height_mm)
        n_ok = int(r.n_placed) == n_total
        if n_ok and h < h_iyi - EPS:
            karar = "TUT"
            kume = aday_kume
            h_iyi = h
            if en_iyi_r is not None:
                del en_iyi_r
                gc.collect()
            en_iyi_r = r
            yeni_asan = _silo_tipleri(r, p0.name, kz2)
            for a2, _u in sorted(yeni_asan.items(), key=lambda kv: -kv[1]):
                if a2 not in denendi and a2 not in kume and a2 not in havuz:
                    havuz.append(a2)
        else:
            karar = "GERI-AL"
            del r
            gc.collect()
        log(f"[deneme {n_deneme}] +{ad} -> h={h:.2f} ({karar})"
            f"  kume={sorted(kume)}  h_iyi={h_iyi:.2f}")
        denemeler.append({"kume": sorted(aday_kume), "eklenen": ad,
                          "height_mm": h, "karar": karar})

    # GERI-cikarma turu: kumeden tek tek cikar, iyilesirse kalici cikar
    for ad in sorted(kume):
        if n_deneme >= MAX_DENEME:
            break
        n_deneme += 1
        aday_kume = kume - {ad}
        r = coz(aday_kume)
        h = float(r.height_mm)
        if int(r.n_placed) == n_total and h < h_iyi - EPS:
            kume = aday_kume
            h_iyi = h
            del en_iyi_r
            gc.collect()
            en_iyi_r = r
            karar = "CIKAR"
        else:
            del r
            gc.collect()
            karar = "KALSIN"
        log(f"[geri {n_deneme}] -{ad} -> h={h:.2f} ({karar})"
            f"  h_iyi={h_iyi:.2f}")
        denemeler.append({"kume": sorted(aday_kume), "cikarilan": ad,
                          "height_mm": h, "karar": karar})

    kat, ust, tepe5 = _katman_telemetri(en_iyi_r, p0.name, Z_MM, kz2)
    log(f"[en iyi] h={h_iyi:.2f}  kume={sorted(kume)}")
    log(f"[en iyi] katman={kat}")
    log(f"[en iyi] tepe5={tepe5}")
    cl_mm = None
    try:
        meshes = list(placed_meshes(en_iyi_r.placements,
                                    en_iyi_r.fine_voxel_parts,
                                    float(en_iyi_r.fine_pitch)))
        cl = min_clearance(meshes)
        cl_mm = float(cl.min_mm)
        log(f"[clearance] min={cl_mm:.3f}mm (kural >= {CLEAR_MM};"
            f" worst_pair={cl.worst_pair})")
    except Exception:
        log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")

    doc = {
        "olcum": "k62_v11c_secim", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d atlanir"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED, "z_mm": Z_MM},
        "kanopi": {"ad": p0.name, "kalinlik_mm": kalinlik, "poz": poz},
        "denemeler": denemeler,
        "en_iyi": {"kume": sorted(kume), "height_mm": h_iyi,
                   "katman": kat, "ustundeki_tipler": ust,
                   "tepe5": [list(t) for t in tepe5],
                   "min_clearance_mm": cl_mm},
        "referanslar": REF,
    }
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

    log(f"OZET: h={h_iyi:.2f} clearance={cl_mm} kume={sorted(kume)}"
        f" (v11 {REF['v11']} / manuel {REF['manuel']})")
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
