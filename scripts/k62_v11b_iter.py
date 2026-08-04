# -*- coding: utf-8 -*-
"""k62_v11b_iter.py — K-62 v11b: ITERATIF kule-onceligi (SERHLI).

v11 bulgusu: asan-tip onceligi 139.2 -> 134.4 (v4 136.5 GECILDI); yeni
tavani baska tipler yapti (pyramid_with_doors, TAPER-GAUGE). v11b dogal
devami: her turda kanopi-tepesini asan tipler oncelik kumesine EKLENIR,
yeniden cozulur; yeni asan cikmayana / iyilesme durana dek (max tur env).

Kayit: her turun h/katman/tepe5 + kume; en iyide merged clearance.
SERHLER (A11+A2): tek-set; kilit olculmez; settle/repair pin_3d atlanir.
Kosum: python -m scripts.detach_run k62_v11b_iter  (D:\\ie488, sakin).
Env: K62V11B_Z (default 68) - K62V11B_MAXTUR (default 5). SAF ASCII.
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

LOG = Path(__file__).parent / "k62_v11b_iter.log"
OUT = _ROOT / "results" / "k62_v11b_iter.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF = {"v11": 134.40, "v9": 139.20, "v4_kanopi": 136.50, "manuel": 110.41}
Z_MM = float(os.environ.get("K62V11B_Z", "68"))
MAX_TUR = int(os.environ.get("K62V11B_MAXTUR", "5"))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v11b OLCUM: ITERATIF kule-onceligi (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z={Z_MM} max_tur={MAX_TUR}")

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

    oncelik = set()
    turlar = []
    en_iyi = None   # (kayit, r)
    for tur in range(MAX_TUR + 1):   # tur 0 = onceliksiz referans
        t1 = time.perf_counter()
        r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                      plate_d_mm=eg.PLATE_STD[1],
                      fine_pitch=None, seed=SEED, quality="fast",
                      clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                      pinned_placements=[pin], pin_3d=True,
                      oncelik_adlari=(oncelik or None))
        kat, ust, tepe5 = _katman_telemetri(r, p0.name, Z_MM, kz2)
        asan = _silo_tipleri(r, p0.name, kz2)
        kayit = {"tur": tur, "oncelik": sorted(oncelik),
                 "height_mm": float(r.height_mm),
                 "n_placed": int(r.n_placed),
                 "fine_pitch": float(r.fine_pitch), "katman": kat,
                 "ustundeki_tipler": ust, "tepe5": [list(t) for t in tepe5],
                 "asan": {k: round(v, 1) for k, v in asan.items()}}
        turlar.append(kayit)
        log(f"[tur {tur}] h={r.height_mm:.2f} n={r.n_placed}/{n_total}"
            f" oncelik={len(oncelik)} sure={(time.perf_counter() - t1) / 60:.1f}dk")
        log(f"[tur {tur}] katman={kat}  asan={kayit['asan']}")
        if (kayit["n_placed"] == n_total
                and (en_iyi is None
                     or kayit["height_mm"] < en_iyi[0]["height_mm"])):
            if en_iyi is not None:
                gc.collect()
            en_iyi = (kayit, r)
        else:
            del r
            gc.collect()
        yeni = set(asan) - oncelik
        if not yeni:
            log(f"[tur {tur}] yeni asan tip yok -> yakinsadi")
            break
        oncelik |= yeni
        log(f"[tur {tur}] kumeye eklendi: {sorted(yeni)}")

    kayit, r = en_iyi if en_iyi else (turlar[-1], None)
    if r is not None:
        log(f"[clearance] en iyi tur {kayit['tur']}"
            f" h={kayit['height_mm']:.2f} ...")
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
        "olcum": "k62_v11b_iter", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d atlanir"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED, "z_mm": Z_MM},
        "kanopi": {"ad": p0.name, "kalinlik_mm": kalinlik, "poz": poz},
        "turlar": turlar, "en_iyi": kayit, "referanslar": REF,
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

    log(f"OZET: en iyi tur {kayit['tur']} h={kayit['height_mm']:.2f}"
        f" clearance={kayit.get('min_clearance_mm')}"
        f" (v11 {REF['v11']} / v4 {REF['v4_kanopi']} / manuel {REF['manuel']})")
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
