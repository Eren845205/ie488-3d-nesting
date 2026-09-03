# -*- coding: utf-8 -*-
"""k62_v14_kilit.py — K-62 v14: 130.80 recetesinin KILIT (ayrilabilirlik) olcumu.

v13b final recetesi (kanopi 3D-pin z=67 + oncelik {uclu:0, TAPER-GAUGE-1:1}
+ settle pin-farkinda) deterministik yeniden cozulur; A2 legal-metrik zinciri
kosulur: (1) yerlesen==toplam, (2) min_clearance >= 2.0, (3) 5-yon kilit;
kilit>0 ise rot-sokum denetimi (A2 GUNCELLEMESI-2: rot kilit=0 ->
SOKUM-PLANLI LEGAL, butce 1200s, konservatif).

Kosum: python -m scripts.detach_run k62_v14_kilit  (D:\\ie488, sakin).
Env: K62V14_Z (67) - K62V14_ROT_BUTCE_S (1200). SAF ASCII.
SERH (A11): tek-set olcum — kilit sonucu 130.80'in legallik serhini kapatir,
GO ilani icin dagilimsal + 4-set kapi + kablo hala bekler.
"""
from __future__ import annotations

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
from src.nesting3d.continuous_settle import kilit_5yon_meshes, kilit_rot_meshes
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v14_kilit.log"
OUT = _ROOT / "results" / "k62_v14_kilit.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF_H = 130.80
Z_MM = float(os.environ.get("K62V14_Z", "67"))
ROT_BUTCE_S = float(os.environ.get("K62V14_ROT_BUTCE_S", "1200"))
RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0,
            "TAPER-GAUGE-1": 1}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v14 OLCUM: 130.80 recetesi kilit/ayrilabilirlik denetimi")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z={Z_MM}")
    log(f"recete: rutbeler={RUTBELER}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
           "y_mm": float(poz["dy_mm"]), "z_mm": Z_MM, "rot": rot_k.tolist()}

    res = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                    plate_d_mm=eg.PLATE_STD[1],
                    fine_pitch=None, seed=SEED, quality="fast",
                    clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                    pinned_placements=[pin], pin_3d=True,
                    oncelik_adlari=RUTBELER)
    h = float(res.height_mm)
    n_placed = int(res.n_placed)
    log(f"[cozum] h={h:.2f} (ref {REF_H:.2f}) n={n_placed}/{n_total}"
        f"  sure={(time.perf_counter() - t0) / 60:.1f}dk")
    if abs(h - REF_H) > 0.01:
        log(f"UYARI: yukseklik referanstan sapti ({h:.2f} != {REF_H:.2f})"
            " — determinizm kirilmis olabilir, kilit sonucu bu cozume aittir")

    meshes = list(placed_meshes(list(res.placements),
                                res.fine_voxel_parts,
                                float(res.fine_pitch)))
    log(f"[mesh] {len(meshes)} parca hazir")

    cl_mm = None
    try:
        cl = min_clearance(meshes)
        cl_mm = float(cl.min_mm)
        log(f"[clearance] min={cl_mm:.3f}mm (kural >= {CLEAR_MM};"
            f" worst_pair={cl.worst_pair})")
    except Exception:
        log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")

    t1 = time.perf_counter()
    kilit5 = kilit_5yon_meshes(meshes)
    log(f"[kilit 5-yon] n_locked={kilit5}"
        f"  sure={(time.perf_counter() - t1) / 60:.1f}dk")

    rot_kilit = None
    rot_cert = None
    sokum_planli = False
    if kilit5 > 0:
        t2 = time.perf_counter()
        try:
            rapor = kilit_rot_meshes(meshes, sure_butcesi_s=ROT_BUTCE_S)
            rot_kilit = int(rapor.n_locked)
            rot_cert = len(getattr(rapor, "certificates", {}) or {})
            sokum_planli = (rot_kilit == 0)
            log(f"[kilit rot] n_locked={rot_kilit} cert={rot_cert}"
                f"  sure={(time.perf_counter() - t2) / 60:.1f}dk")
        except Exception:
            log(f"[kilit rot] DENETIM HATASI (konservatif RED):\n"
                f"{traceback.format_exc()}")

    yerlesim_ok = (n_placed == n_total)
    clearance_ok = (cl_mm is not None and cl_mm >= CLEAR_MM)
    kilit_ok = (kilit5 == 0) or sokum_planli
    legal = yerlesim_ok and clearance_ok and kilit_ok
    if kilit5 == 0:
        kilit_kriter = "5-yon=0"
    elif sokum_planli:
        kilit_kriter = f"sokum-planli (5-yon={kilit5}, rot=0, cert={rot_cert})"
    else:
        kilit_kriter = f"KILITLI (5-yon={kilit5}, rot={rot_kilit})"
    log(f"[A2] yerlesim={'OK' if yerlesim_ok else 'IHLAL'}"
        f"  clearance={'OK' if clearance_ok else 'IHLAL'}"
        f"  kilit={kilit_kriter}")
    log(f"[A2] SONUC: {'LEGAL' if legal else 'INVALID'}  h={h:.2f}")

    doc = {
        "olcum": "k62_v14_kilit", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("A11 tek-set: kilit olcumu 130.80 legallik serhini kapatir;"
                 " GO ilani icin dagilimsal + 4-set kapi + kablo bekler"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED, "z_mm": Z_MM},
        "recete": {"rutbeler": RUTBELER, "pin": {"ad": p0.name, "z_mm": Z_MM}},
        "sonuc": {"height_mm": h, "ref_height_mm": REF_H,
                  "n_placed": n_placed, "n_total": n_total,
                  "min_clearance_mm": cl_mm,
                  "kilit_5yon": kilit5, "rot_kilit": rot_kilit,
                  "rot_cert": rot_cert, "sokum_planli": sokum_planli,
                  "legal": legal, "kilit_kriter": kilit_kriter},
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

    log(f"OZET: h={h:.2f} legal={legal} kilit={kilit_kriter}"
        f" clearance={cl_mm}")
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
