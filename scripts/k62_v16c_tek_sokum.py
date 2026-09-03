# -*- coding: utf-8 -*-
"""k62_v16c_tek_sokum.py — K-62 v16c AYIRT EDICI TESHIS: tek-parca sokumu.

v16/v16b rip-up NO-GO'sunun kok nedenini ayirt eder: sokulen parcalar ESKI
(bos) pozlarina bile donemiyor (donebilseler h ayni kalirdi; 138/136.8
cikti). Iki hipotez:
  (a) PIN-DILATION SEMANTIGI: pin occupancy'ye dilation'li damgalaniyor +
      aday parca da dilation'li test ediliyor -> cift bosluk sarti ->
      parca kendi eski cebine "carpisma" goruyor.
  (b) BBOX-FEASIBILITY: dar cepler bbox testinde reddediliyor.

Deney: settle'siz taban coz (134.40 @2.4) -> EN TEPEDEKI TEK placement'i
sok -> kalan 111'i pinle -> yeniden coz. Olcum:
  - h ayni kalirsa: donme MUMKUN -> (a) ve (b) zayif, NO-GO kombinatoryal.
  - h yukselirse + yeni poz != eski poz: parca cebe giremiyor -> (a)/(b)
    kaniti; eski poz hucresinin pin-occ durumu loglanir (dolu ise (a) KESIN).

Kosum: python -m scripts.detach_run k62_v16c_tek_sokum  (D:\\ie488). ASCII.
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
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v16c_tek_sokum.log"
OUT = _ROOT / "results" / "k62_v16c_tek_sokum.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_MM = 67.0
# SEC="tepe" (default) en-yuksek parcayi soker; "alcak" en-alcak tepeliyi
# soker (tepeye etkisi SIFIR olmali -> h firlarsa PIN-CEVIRI hatasi kesin:
# v16c-tepe kosusunda h 134.4->158.4 anomalisi, sokulen parca ust=132'de).
SEC = os.environ.get("K62V16C_SEC", "tepe").strip()
RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0,
            "TAPER-GAUGE-1": 1}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v16c TESHIS: tek-parca sokumu (eski pozuna donebiliyor mu?)")
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
    h0 = float(res.height_mm)
    pt = float(res.fine_pitch)
    log(f"[taban] h={h0:.2f} n={int(res.n_placed)}/{n_total} pitch={pt:.3f}")

    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    kayitlar = []
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        ad = getattr(vp, "name", str(pl.part_id))
        ust = (pl.z + o.grid.shape[2]) * pt
        kayitlar.append((ust, ad, pl, o))
    kayitlar.sort(key=lambda k: k[0])
    secilen = kayitlar[-1] if SEC == "tepe" else kayitlar[0]
    pinler = []
    for ust_i, ad_i, pl_i, o_i in kayitlar:
        if (ust_i, ad_i, pl_i, o_i) is secilen or pl_i is secilen[2]:
            continue
        rot_i = np.asarray(o_i.rot_matrix, dtype=float)
        pinler.append({"ad": ad_i, "x_mm": float(pl_i.x) * pt,
                       "y_mm": float(pl_i.y) * pt,
                       "z_mm": float(pl_i.z) * pt, "rot": rot_i.tolist()})
    ust, ad, pl, o = secilen
    eski = {"ad": ad, "x": float(pl.x) * pt, "y": float(pl.y) * pt,
            "z": float(pl.z) * pt, "ust": round(ust, 1)}
    log(f"[sokum] sec={SEC} parca: {ad} eski poz=({eski['x']:.1f},"
        f" {eski['y']:.1f}, {eski['z']:.1f}) ust={eski['ust']}")
    log(f"[sokum] pin={len(pinler)} (kalan herkes)")

    r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                  plate_d_mm=eg.PLATE_STD[1],
                  fine_pitch=pt, fine_settle=False, seed=SEED,
                  quality="fast", clearance_mm=CLEAR_MM,
                  no_go_bounds=eg.NOGO_STD,
                  pinned_placements=pinler, pin_3d=True)
    h1 = float(r.height_mm)
    log(f"[yeniden] h={h1:.2f} n={int(r.n_placed)}/{n_total}"
        f" (taban {h0:.2f})")
    fvp1 = r.fine_voxel_parts
    vps1 = fvp1 if isinstance(fvp1, dict) else {v.id: v for v in fvp1}
    yeni = None
    pin_adlari_sayac = {}
    for q in pinler:
        pin_adlari_sayac[q["ad"]] = pin_adlari_sayac.get(q["ad"], 0) + 1
    kalan = dict(pin_adlari_sayac)
    for pl1 in r.placements:
        vp1 = vps1.get(pl1.part_id)
        o1 = (vp1.orientations[pl1.orientation_idx]
              if vp1 and pl1.orientation_idx < len(vp1.orientations) else None)
        if o1 is None:
            continue
        a1 = getattr(vp1, "name", str(pl1.part_id))
        # pin kopyalarini tuket; artakalan ayni-adli placement sokulen parca
        if kalan.get(a1, 0) > 0:
            kalan[a1] -= 1
            continue
        if a1 == ad:
            yeni = {"x": float(pl1.x) * float(r.fine_pitch),
                    "y": float(pl1.y) * float(r.fine_pitch),
                    "z": float(pl1.z) * float(r.fine_pitch),
                    "ust": round((pl1.z + o1.grid.shape[2])
                                 * float(r.fine_pitch), 1)}
    log(f"[yeniden] sokulen parca yeni poz: {yeni}")
    ayni_poz = (yeni is not None
                and abs(yeni["x"] - eski["x"]) < pt + 1e-6
                and abs(yeni["y"] - eski["y"]) < pt + 1e-6
                and abs(yeni["z"] - eski["z"]) < pt + 1e-6)
    if abs(h1 - h0) < 1e-6 and ayni_poz:
        okuma = "DONEBILIYOR — NO-GO kombinatoryal (coklu-sokum sirasi)"
    elif abs(h1 - h0) < 1e-6:
        okuma = "h ayni ama poz farkli — es-yukseklik alternatifi buldu"
    else:
        okuma = ("DONEMIYOR — pin-dilation semantigi / bbox-feasibility "
                 "kaniti (h yukseldi)")
    log(f"[okuma] {okuma}")

    doc = {"olcum": "k62_v16c_tek_sokum",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "taban_h": h0, "yeniden_h": h1, "pitch": pt,
           "sokulen": eski, "yeni_poz": yeni, "ayni_poz": ayni_poz,
           "okuma": okuma}
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
