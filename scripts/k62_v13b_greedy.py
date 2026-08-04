# -*- coding: utf-8 -*-
"""k62_v13b_greedy.py — K-62 v13b: rutbe-1 katmanina GREEDY tekil ekleme.

v13 dersi: rutbe-1'e TOPLU ekleme patlar (158.4); TEKIL ekleme kazandirir
(uclu+TAPER=130.80, uclu+pyramid notr). v13b: rutbe-0 = kule uclusu sabit;
adaylar rutbe-1'e TEK TEK denenir — iyilestiren TUTULUR (birikimli),
digerleri GERI ALINIR; yeni asan tipler aday havuzuna eklenir.

Kosum: python -m scripts.detach_run k62_v13b_greedy  (D:\\ie488, sakin).
Env: K62V13B_Z (67) - K62V13B_MAXDENEME (10). SAF ASCII.
SERHLER (A11+A2): tek-set; kilit olculmez; settle pin-farkinda CALISIR.
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

LOG = Path(__file__).parent / "k62_v13b_greedy.log"
OUT = _ROOT / "results" / "k62_v13b_greedy.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
EPS = 0.01
REF = {"v13_tekil_taper": 130.80, "v12b": 132.00, "manuel": 110.41}
Z_MM = float(os.environ.get("K62V13B_Z", "67"))
MAX_DENEME = int(os.environ.get("K62V13B_MAXDENEME", "10"))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v13b OLCUM: rutbe-1 greedy tekil ekleme (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z={Z_MM}")

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

    def coz(rutbeler):
        return solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                         plate_d_mm=eg.PLATE_STD[1],
                         fine_pitch=None, seed=SEED, quality="fast",
                         clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                         pinned_placements=[pin], pin_3d=True,
                         oncelik_adlari=(rutbeler or None))

    # rutbe-0 kumesi COZUM-GUDUMLU (onceliksiz referansin asan tipleri)
    r0 = coz(None)
    kume0 = set(_silo_tipleri(r0, p0.name, kz2))
    log(f"[ref] h={float(r0.height_mm):.2f}  rutbe-0={sorted(kume0)}")
    del r0
    gc.collect()

    rutbeler = {ad: 0 for ad in kume0}
    r1 = coz(rutbeler)
    h_iyi = float(r1.height_mm)
    asan1 = _silo_tipleri(r1, p0.name, kz2)
    havuz = [ad for ad, _u in sorted(asan1.items(), key=lambda kv: -kv[1])
             if ad not in rutbeler]
    log(f"[taban] h={h_iyi:.2f}  aday havuzu={havuz}")
    en_iyi_r = r1
    denemeler = [{"rutbeler": dict(rutbeler), "height_mm": h_iyi,
                  "karar": "taban"}]

    denendi: set = set()
    n = 0
    while havuz and n < MAX_DENEME:
        ad = havuz.pop(0)
        if ad in denendi or ad in rutbeler:
            continue
        denendi.add(ad)
        n += 1
        aday = dict(rutbeler)
        aday[ad] = 1
        r = coz(aday)
        h = float(r.height_mm)
        if int(r.n_placed) == n_total and h < h_iyi - EPS:
            karar = "TUT"
            rutbeler = aday
            h_iyi = h
            del en_iyi_r
            gc.collect()
            en_iyi_r = r
            for a2, _u in sorted(_silo_tipleri(r, p0.name, kz2).items(),
                                 key=lambda kv: -kv[1]):
                if a2 not in denendi and a2 not in rutbeler and a2 not in havuz:
                    havuz.append(a2)
        else:
            karar = "GERI-AL"
            del r
            gc.collect()
        log(f"[deneme {n}] +{ad}@r1 -> h={h:.2f} ({karar})"
            f"  h_iyi={h_iyi:.2f}  rutbe-1={[k for k, v in rutbeler.items() if v == 1]}")
        denemeler.append({"rutbeler": aday, "eklenen": ad,
                          "height_mm": h, "karar": karar})

    kat, ust, tepe5 = _katman_telemetri(en_iyi_r, p0.name, Z_MM, kz2)
    log(f"[en iyi] h={h_iyi:.2f}  rutbeler={rutbeler}")
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
        "olcum": "k62_v13b_greedy", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle "
                 "pin-farkinda calisir; repair atlanir"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED, "z_mm": Z_MM},
        "kanopi": {"ad": p0.name, "kalinlik_mm": kalinlik, "poz": poz},
        "denemeler": denemeler,
        "en_iyi": {"rutbeler": rutbeler, "height_mm": h_iyi, "katman": kat,
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

    log(f"OZET: h={h_iyi:.2f} clearance={cl_mm}"
        f" (tekil-taper {REF['v13_tekil_taper']} / manuel {REF['manuel']})")
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
