# -*- coding: utf-8 -*-
"""k62_v16d_pin_parite.py — K-62 v16d: PIN SAHNE PARITE testi.

v16c anomalileri (tepe-sokum h 134.4->158.4; alcak-sokum h 134.4->132.0
— pinli pyramid 134.4'te sabitken tepe 132 OLAMAZ) pin sahnesinin birebir
kurulmadigini soyluyor. Bu test kaniti dogrudan olcer:

  taban coz (112) -> en-alcak parca haric 111'ini pinle -> yeniden coz ->
  (1) her pin (ad, x, y, z) eski konumuyla eslesiyor mu (tolerans pitch/2)?
  (2) merged min_clearance (pinler ic ice bindiyse ~0/negatif cikar)?
  (3) yeni cozumun placements tepe-5'i (h kimden geliyor)?

Kosum: python -m scripts.detach_run k62_v16d_pin_parite  (D:\\ie488). ASCII.
"""
from __future__ import annotations

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
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v16d_pin_parite.log"
OUT = _ROOT / "results" / "k62_v16d_pin_parite.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_MM = 67.0
RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0,
            "TAPER-GAUGE-1": 1}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _dok(res):
    pt = float(res.fine_pitch)
    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    out = []
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        ad = getattr(vp, "name", str(pl.part_id))
        out.append({"ad": ad, "x": float(pl.x) * pt, "y": float(pl.y) * pt,
                    "z": float(pl.z) * pt,
                    "ust": (pl.z + o.grid.shape[2]) * pt,
                    "rot": np.asarray(o.rot_matrix, dtype=float)})
    return out, pt


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v16d: PIN SAHNE PARITE testi")
    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    pin0 = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
            "y_mm": float(poz["dy_mm"]), "z_mm": Z_MM, "rot": rot_k.tolist()}
    res = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                    plate_d_mm=eg.PLATE_STD[1],
                    fine_pitch=None, fine_settle=False, seed=SEED,
                    quality="fast", clearance_mm=CLEAR_MM,
                    no_go_bounds=eg.NOGO_STD,
                    pinned_placements=[pin0], pin_3d=True,
                    oncelik_adlari=RUTBELER)
    dok0, pt = _dok(res)
    h0 = float(res.height_mm)
    log(f"[taban] h={h0:.2f} n={len(dok0)} pitch={pt:.3f}")

    dok0.sort(key=lambda k: k["ust"])
    serbest = dok0[0]
    pinler = [{"ad": k["ad"], "x_mm": k["x"], "y_mm": k["y"],
               "z_mm": k["z"], "rot": k["rot"].tolist()}
              for k in dok0[1:]]
    log(f"[sokum] serbest: {serbest['ad']} ({serbest['x']:.1f},"
        f" {serbest['y']:.1f}, {serbest['z']:.1f}) ust={serbest['ust']:.1f}"
        f"  pin={len(pinler)}")

    r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                  plate_d_mm=eg.PLATE_STD[1],
                  fine_pitch=pt, fine_settle=False, seed=SEED,
                  quality="fast", clearance_mm=CLEAR_MM,
                  no_go_bounds=eg.NOGO_STD,
                  pinned_placements=pinler, pin_3d=True)
    dok1, pt1 = _dok(r)
    h1 = float(r.height_mm)
    log(f"[yeniden] h={h1:.2f} n={len(dok1)} pitch={pt1:.3f}")
    tepe5 = sorted(dok1, key=lambda k: -k["ust"])[:5]
    for k in tepe5:
        log(f"  tepe: {k['ad']:24s} alt={k['z']:6.1f} ust={k['ust']:6.1f}")

    # pin eslesmesi: eski pin konumlarinin her biri yeni dokumde var mi
    tol = pt + 1e-6
    yeni_havuz = list(dok1)
    eslesen = 0
    kayanlar = []
    for p in dok0[1:]:
        bulundu = None
        for i, q in enumerate(yeni_havuz):
            if (q["ad"] == p["ad"] and abs(q["x"] - p["x"]) <= tol
                    and abs(q["y"] - p["y"]) <= tol
                    and abs(q["z"] - p["z"]) <= tol):
                bulundu = i
                break
        if bulundu is not None:
            eslesen += 1
            yeni_havuz.pop(bulundu)
        else:
            kayanlar.append(p)
    log(f"[parite] pin={len(pinler)} eslesen={eslesen}"
        f" KAYAN={len(kayanlar)}")
    for p in kayanlar[:10]:
        log(f"  kayan: {p['ad']:24s} eski=({p['x']:.1f}, {p['y']:.1f},"
            f" {p['z']:.1f}) ust={p['ust']:.1f}")

    cl_mm = None
    try:
        meshes = list(placed_meshes(list(r.placements), r.fine_voxel_parts,
                                    float(r.fine_pitch)))
        cl = min_clearance(meshes)
        cl_mm = float(cl.min_mm)
        log(f"[clearance] min={cl_mm:.3f}mm (ic-ice binme sinyali: ~0/neg)")
    except Exception:
        log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")

    doc = {"olcum": "k62_v16d_pin_parite",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "taban_h": h0, "yeniden_h": h1, "pitch": pt,
           "n_pin": len(pinler), "eslesen": eslesen,
           "kayan": [{k2: (round(v, 2) if isinstance(v, float) else v)
                      for k2, v in p.items() if k2 != "rot"}
                     for p in kayanlar],
           "tepe5": [{k2: (round(v, 2) if isinstance(v, float) else v)
                      for k2, v in k.items() if k2 != "rot"}
                     for k in tepe5],
           "min_clearance_mm": cl_mm}
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
    log(f"WALL_S={time.perf_counter() - t0:.1f}")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
