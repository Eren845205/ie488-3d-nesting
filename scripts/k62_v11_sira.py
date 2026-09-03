# -*- coding: utf-8 -*-
"""k62_v11_sira.py — K-62 v11: COZUM-ICI KULE-ONCELIGI olcumu (SERHLI).

v10 dersi: statik delik-tahsisi BLB esnekliginden kotu (4 tur NO-GO).
v11 ayni hedefe cozum-ICINDEN gider: pin yalniz KANOPI (v9 semantigi);
kule tipleri (faz-A cozum-gudumlu) decode SIRASINDA one alinir
(nfv_solve oncelik_adlari -> parallel_decode _sira_anahtari, opt-in).
Insan deseni: once kuleleri dik (taban+delik kolonlarini kuleler alir),
sonra kisa parcalarla arayi doldur.

Olcum: z-taramasi (kanopi z) x oncelik-varyanti:
  A) oncelik yok (v9 referans, ayni kosuda yeniden)
  B) asan-tipler oncelikli
  C) asan + tum bobbin ailesi oncelikli (asanlarin kardesleri de kule)
En iyide merged clearance. Telemetri: katman + tepe5.

SERHLER (A11+A2): tek-set; kilit olculmez; settle/repair pin_3d atlanir.
Kosum: python -m scripts.detach_run k62_v11_sira  (D:\\ie488, sakin makine).
Env: K62V11_ZLER (default "68,70"). SAF ASCII stdout.
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

LOG = Path(__file__).parent / "k62_v11_sira.log"
OUT = _ROOT / "results" / "k62_v11_sira.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF = {"v9": 139.20, "v4_kanopi": 136.50, "manuel": 110.41}
_z_env = os.environ.get("K62V11_ZLER", "").strip()
Z_LER = [float(v) for v in _z_env.split(",")] if _z_env else [68.0, 70.0]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v11 OLCUM: cozum-ici kule-onceligi (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z'ler={Z_LER}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    kalinlik = float(fiz["duz_kalinlik_mm"])

    def coz(z_mm, oncelik, etiket):
        pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
               "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
               "rot": rot_k.tolist()}
        t1 = time.perf_counter()
        r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                      plate_d_mm=eg.PLATE_STD[1],
                      fine_pitch=None, seed=SEED, quality="fast",
                      clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                      pinned_placements=[pin], pin_3d=True,
                      oncelik_adlari=oncelik)
        kat, ust, tepe5 = _katman_telemetri(r, p0.name, z_mm, z_mm + kalinlik)
        log(f"[{etiket} z={z_mm}] h={r.height_mm:.2f} n={r.n_placed}/{n_total}"
            f" sure={(time.perf_counter() - t1) / 60:.1f}dk")
        log(f"[{etiket} z={z_mm}] katman={kat}")
        log(f"[{etiket} z={z_mm}] tepe5={tepe5}")
        return r, {"etiket": etiket, "z_mm": z_mm,
                   "oncelik": sorted(oncelik) if oncelik else None,
                   "height_mm": float(r.height_mm),
                   "n_placed": int(r.n_placed),
                   "fine_pitch": float(r.fine_pitch),
                   "katman": kat, "ustundeki_tipler": ust,
                   "tepe5": [list(t) for t in tepe5]}

    # faz-A: referans (oncelik yok) + asan tipler
    rA, kayitA = coz(Z_LER[0], None, "A-ref")
    asanlar = _silo_tipleri(rA, p0.name, Z_LER[0] + kalinlik)
    log(f"asan tipler: { {k: round(v, 1) for k, v in asanlar.items()} }")
    del rA
    gc.collect()

    onc_B = set(asanlar)
    # C: asanlarin "ailesi" — ayni govde adini tasiyan kardes tipler de kule
    govdeler = {ad.split("_")[0] for ad in asanlar}
    onc_C = {p.name for p in inst.parts
             if p.name != p0.name and p.name.split("_")[0] in govdeler}
    log(f"oncelik B={sorted(onc_B)}")
    log(f"oncelik C={sorted(onc_C)}")

    sonuclar = [kayitA]
    en_iyi = (kayitA, None)  # (kayit, r) — clearance icin r sakla
    for z_mm in Z_LER:
        for etiket, onc in (("B-asan", onc_B), ("C-aile", onc_C)):
            r, kayit = coz(z_mm, onc, etiket)
            sonuclar.append(kayit)
            if (kayit["n_placed"] == n_total
                    and kayit["height_mm"] < en_iyi[0]["height_mm"]):
                if en_iyi[1] is not None:
                    del en_iyi
                    gc.collect()
                en_iyi = (kayit, r)
            else:
                del r
                gc.collect()

    kayit, r = en_iyi
    if r is not None:
        log(f"[clearance] en iyi {kayit['etiket']} z={kayit['z_mm']}"
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
        "olcum": "k62_v11_sira", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d atlanir"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED},
        "kanopi": {"ad": p0.name, "kalinlik_mm": kalinlik, "poz": poz},
        "sonuclar": sonuclar,
        "en_iyi": kayit,
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

    log(f"OZET: en iyi {kayit['etiket']} z={kayit['z_mm']}"
        f" h={kayit['height_mm']:.2f}"
        f" (v9 {REF['v9']} / v4 {REF['v4_kanopi']} / manuel {REF['manuel']})")
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
