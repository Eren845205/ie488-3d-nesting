# -*- coding: utf-8 -*-
"""k62_v12_mikro.py — K-62 v12: kume-sabit MIKRO TARAMA (z x seed) (SERHLI).

v11c sonucu: oncelik kumesi {811793-1, bobbin_1_v2, bobbin_2_v2} lokal
optimum (134.40 @ z=68, seed 42). v12 ayni kumeyle iki ucuz ekseni tarar:
  1) kanopi z mikro-sweep (64..69; 70+ kotu olculdu),
  2) en iyi z'de seed cesitlemesi (BLB/oryantasyon orneklemesi degisir;
     hoca 'her kosuda farkli dizilim' istegiyle uyumlu altyapi sinyali).
En iyide merged clearance + katman telemetrisi.

SERHLER (A11+A2): tek-set; kilit olculmez; settle/repair pin_3d atlanir.
Kosum: python -m scripts.detach_run k62_v12_mikro  (D:\\ie488, sakin).
Env: K62V12_ZLER ("64,66,67,68,69") - K62V12_SEEDLER ("42,7,101,2026").
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

LOG = Path(__file__).parent / "k62_v12_mikro.log"
OUT = _ROOT / "results" / "k62_v12_mikro.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
CLEAR_MM = 2.0
REF = {"v11": 134.40, "manuel": 110.41}
_z = os.environ.get("K62V12_ZLER", "").strip()
Z_LER = [float(v) for v in _z.split(",")] if _z else [64.0, 66.0, 67.0,
                                                     68.0, 69.0]
_s = os.environ.get("K62V12_SEEDLER", "").strip()
SEEDLER = [int(v) for v in _s.split(",")] if _s else [42, 7, 101, 2026]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v12 OLCUM: kume-sabit mikro tarama (z x seed) (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM}  z'ler={Z_LER} seedler={SEEDLER}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    kalinlik = float(fiz["duz_kalinlik_mm"])

    # v11c lokal-optimum kumesi COZUM-GUDUMLU yeniden turetilir (A11:
    # veri-adi gomulmez): onceliksiz referanstan kanopi-tepe asan tipler.
    r0 = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0], plate_d_mm=eg.PLATE_STD[1],
                   fine_pitch=None, seed=SEEDLER[0], quality="fast",
                   clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                   pinned_placements=[{
                       "ad": p0.name, "x_mm": float(poz["dx_mm"]),
                       "y_mm": float(poz["dy_mm"]), "z_mm": Z_LER[-1] if 68.0 not in Z_LER else 68.0,
                       "rot": rot_k.tolist()}], pin_3d=True)
    kume = set(_silo_tipleri(r0, p0.name,
                             (68.0 if 68.0 in Z_LER else Z_LER[-1]) + kalinlik))
    log(f"oncelik kumesi (cozum-gudumlu): {sorted(kume)}")
    del r0
    gc.collect()

    def coz(z_mm, seed):
        pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
               "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
               "rot": rot_k.tolist()}
        r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                      plate_d_mm=eg.PLATE_STD[1],
                      fine_pitch=None, seed=seed, quality="fast",
                      clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                      pinned_placements=[pin], pin_3d=True,
                      oncelik_adlari=kume)
        return r

    sonuclar = []
    en_iyi = None   # (kayit, r)

    def kaydet(z_mm, seed, r):
        nonlocal en_iyi
        kayit = {"z_mm": z_mm, "seed": seed,
                 "height_mm": float(r.height_mm),
                 "n_placed": int(r.n_placed)}
        log(f"[z={z_mm} seed={seed}] h={r.height_mm:.2f}"
            f" n={r.n_placed}/{n_total}")
        sonuclar.append(kayit)
        if (kayit["n_placed"] == n_total
                and (en_iyi is None
                     or kayit["height_mm"] < en_iyi[0]["height_mm"])):
            if en_iyi is not None:
                gc.collect()
            en_iyi = (kayit, r)
        else:
            del r
            gc.collect()

    for z_mm in Z_LER:
        kaydet(z_mm, SEEDLER[0], coz(z_mm, SEEDLER[0]))
    z_iyi = en_iyi[0]["z_mm"] if en_iyi else Z_LER[0]
    log(f"[z-sweep] en iyi z={z_iyi} h={en_iyi[0]['height_mm']:.2f}")
    for seed in SEEDLER[1:]:
        kaydet(z_iyi, seed, coz(z_iyi, seed))

    kayit, r = en_iyi
    kat, ust, tepe5 = _katman_telemetri(r, p0.name, kayit["z_mm"],
                                        kayit["z_mm"] + kalinlik)
    kayit["katman"] = kat
    kayit["tepe5"] = [list(t) for t in tepe5]
    log(f"[en iyi] z={kayit['z_mm']} seed={kayit['seed']}"
        f" h={kayit['height_mm']:.2f}")
    log(f"[en iyi] katman={kat}")
    log(f"[en iyi] tepe5={tepe5}")
    try:
        meshes = list(placed_meshes(r.placements, r.fine_voxel_parts,
                                    float(r.fine_pitch)))
        cl = min_clearance(meshes)
        kayit["min_clearance_mm"] = float(cl.min_mm)
        log(f"[clearance] min={cl.min_mm:.3f}mm (kural >= {CLEAR_MM};"
            f" worst_pair={cl.worst_pair})")
    except Exception:
        log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")

    doc = {
        "olcum": "k62_v12_mikro", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d atlanir"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM},
        "kanopi": {"ad": p0.name, "kalinlik_mm": kalinlik, "poz": poz},
        "oncelik_kumesi": sorted(kume),
        "sonuclar": sonuclar, "en_iyi": kayit, "referanslar": REF,
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

    log(f"OZET: en iyi z={kayit['z_mm']} seed={kayit['seed']}"
        f" h={kayit['height_mm']:.2f} clearance={kayit.get('min_clearance_mm')}"
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
