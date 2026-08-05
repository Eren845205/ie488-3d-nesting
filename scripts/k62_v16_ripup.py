# -*- coding: utf-8 -*-
"""k62_v16_ripup.py — K-62 v16: RIP-UP & RE-SOLVE (tavan sokumu + sabit-sahne
yeniden cozumu). v15 teshisinin dogrudan saldirisi.

v15 kaniti (results/k62_v15_teshis.json): 130.80'de kanopi-alti %65 BOS
(4881cm3), 110+ tavan yuku yalnizca 569cm3 (17 parca) — problem kapasite
degil KOMBINATORYAL (BLB 17 parcayi yukarida birakmis).

Mekanizma (motor degisikligi YOK — v9 pin_3d altyapisi):
  tur k: cozumdeki ust > hedef parcalar SOKULUR; kalanlar pin listesi
  olarak verilir (ad + mm koord + orientation.rot_matrix — pinler
  id-tuketimli dusuldugunden cozucu YALNIZ sokulenleri yeniden yerlestirir,
  sonuc yine tam 112-parca cozumu). Iyilesme varsa tur k+1 daha dusuk
  hedefle tekrar. TEK-TARAFLI: kotulesen tur GERI ALINIR.

Kosum: python -m scripts.detach_run k62_v16_ripup  (D:\\ie488, sakin).
Env: K62V16_HEDEF (111) - K62V16_MAXTUR (3). SAF ASCII.
SERH (A11): tek-set on-olcum; kilit/clearance final turda olculur;
GO cikarsa mekanizma kanopi_zincir kablosuna 5. adim olarak genellenir
(dagilimsal + kapi ayri).
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
from src.nesting3d.continuous_settle import kilit_5yon_meshes, kilit_rot_meshes
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v16_ripup.log"
OUT = _ROOT / "results" / "k62_v16_ripup.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_MM = float(os.environ.get("K62V16_Z", "67"))
HEDEF0 = float(os.environ.get("K62V16_HEDEF", "111"))
MAX_TUR = int(os.environ.get("K62V16_MAXTUR", "3"))
# Kaba-pitch on-sinyal modu (RAM krizi dersi 2026-08-05: 95-pin voxelize
# @0.6 pitch ~80dk/tur; auto ise bol RAM'de 0.3 secip tur-1'de 6.19GiB
# occupancy istedi -> MemErr). DEFAULT 1.2 SABIT (env detach_run'a
# gecmiyor); "auto" yazilirsa None.
_pitch_env = os.environ.get("K62V16_PITCH", "1.2").strip()
PITCH_MM = None if _pitch_env == "auto" else float(_pitch_env)
# v16b SNAP'SIZ mod (tur-1 GERI-AL 138.0 sonrasi tek-degisken deneyi):
# settle KAPALI + tur cozumu tabanin coarse grid'inde -> pin snap = 0.
# (v16 kaba kosuda pinler 1.2 gridine +-0.6mm kaydi — delik-hizasi bozulmus
# olabilir.) K62V16_SNAPSIZ=1 script-ici default degil; dosyada sabitlenir.
SNAPSIZ = os.environ.get("K62V16_SNAPSIZ", "1").strip() == "1"
REF = {"v13b": 130.80, "manuel": 110.41}
RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0,
            "TAPER-GAUGE-1": 1}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _pinler_ve_sokulenler(res, hedef_mm):
    """Cozumden pin listesi (ust <= hedef) + sokulen sayaci cikar."""
    pt = float(res.fine_pitch)
    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    pinler = []
    sokulen = []
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        ad = getattr(vp, "name", str(pl.part_id))
        ust = (pl.z + o.grid.shape[2]) * pt
        if ust <= hedef_mm + 1e-6:
            rot = np.asarray(o.rot_matrix, dtype=float)
            pinler.append({"ad": ad, "x_mm": float(pl.x) * pt,
                           "y_mm": float(pl.y) * pt,
                           "z_mm": float(pl.z) * pt,
                           "rot": rot.tolist()})
        else:
            sokulen.append((ad, round(float(pl.z) * pt, 1), round(ust, 1)))
    return pinler, sokulen


def a2_olc(res, n_total):
    meshes = list(placed_meshes(list(res.placements), res.fine_voxel_parts,
                                float(res.fine_pitch)))
    cl = min_clearance(meshes)
    cl_mm = float(cl.min_mm)
    kilit5 = kilit_5yon_meshes(meshes)
    rot_kilit = rot_cert = None
    sokum_planli = False
    if kilit5 > 0:
        rapor = kilit_rot_meshes(meshes, sure_butcesi_s=1200.0)
        rot_kilit = int(rapor.n_locked)
        rot_cert = len(getattr(rapor, "certificates", {}) or {})
        sokum_planli = (rot_kilit == 0)
    legal = (int(res.n_placed) == n_total and cl_mm >= CLEAR_MM
             and (kilit5 == 0 or sokum_planli))
    return {"min_clearance_mm": round(cl_mm, 3), "kilit_5yon": kilit5,
            "rot_kilit": rot_kilit, "rot_cert": rot_cert,
            "sokum_planli": sokum_planli, "legal": legal}


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v16 OLCUM: rip-up & re-solve (SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_MM}"
        f" hedef0={HEDEF0} max_tur={MAX_TUR}")

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
                    fine_pitch=(None if SNAPSIZ else PITCH_MM),
                    fine_settle=(not SNAPSIZ), seed=SEED, quality="fast",
                    clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                    pinned_placements=[pin0], pin_3d=True,
                    oncelik_adlari=RUTBELER)
    h = float(res.height_mm)
    pt = float(res.fine_pitch)
    log(f"[taban] h={h:.2f} n={int(res.n_placed)}/{n_total} pitch={pt:.3f}"
        f" snapsiz={int(SNAPSIZ)}")

    turlar = []
    hedef = HEDEF0
    for tur in range(1, MAX_TUR + 1):
        pinler, sokulen = _pinler_ve_sokulenler(res, hedef)
        if not sokulen:
            log(f"[tur {tur}] hedef={hedef:.1f}: sokulecek parca yok -> dur")
            break
        tipler = {}
        for ad, _a, _u in sokulen:
            tipler[ad] = tipler.get(ad, 0) + 1
        log(f"[tur {tur}] hedef={hedef:.1f}  pin={len(pinler)}"
            f"  sokulen={len(sokulen)} {tipler}")
        t1 = time.perf_counter()
        # DIKKAT: res.fine_pitch SETTLE pitch'idir (coarse/4) — onu coarse
        # olarak geri beslemek 0.3-coarse patlamasi yapti (MemErr dersi).
        # Tur cozumu SABIT kaba pitch'te; pin mm-koordinatlari pitch-bagimsiz
        # (snap payi <= pitch/2 — on-sinyalde kabul, ince finalde kucuk).
        r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                      plate_d_mm=eg.PLATE_STD[1],
                      fine_pitch=(pt if SNAPSIZ else PITCH_MM),
                      fine_settle=(not SNAPSIZ), seed=SEED, quality="fast",
                      clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                      pinned_placements=pinler, pin_3d=True)
        hr = float(r.height_mm)
        nr = int(r.n_placed)
        sure = time.perf_counter() - t1
        kabul = (nr == n_total and hr < h - 0.01)
        log(f"[tur {tur}] h={hr:.2f} n={nr}/{n_total}"
            f" ({'KABUL' if kabul else 'GERI-AL'}) sure={sure/60:.1f}dk")
        turlar.append({"tur": tur, "hedef": hedef, "n_pin": len(pinler),
                       "n_sokulen": len(sokulen), "sokulen_tipler": tipler,
                       "h": hr, "n": nr, "kabul": kabul,
                       "sure_s": round(sure, 1)})
        if kabul:
            del res
            gc.collect()
            res, h = r, hr
            # sonraki tur hedefi: yeni tavani sok (h'nin hemen alti);
            # manuel bandinin altina inmeye zorlamayiz
            hedef = max(REF["manuel"] - 0.01, min(hedef, h - 2 * pt))
        else:
            del r
            gc.collect()
            break

    log(f"[final] h={h:.2f} (v13b {REF['v13b']} / manuel {REF['manuel']})")
    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[A2] clearance={a2['min_clearance_mm']} kilit5={a2['kilit_5yon']}"
            f" rot={a2['rot_kilit']} sokum_planli={a2['sokum_planli']}"
            f" -> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[A2] OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {
        "olcum": "k62_v16_ripup", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("A11 tek-set on-olcum; GO ise kanopi_zincir kablosuna "
                 "5. adim + dagilimsal + kapi"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED, "z_mm": Z_MM,
                     "hedef0": HEDEF0},
        "taban_h": REF["v13b"], "turlar": turlar,
        "final": {"height_mm": h, "a2": a2},
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
    log(f"OZET: final={h:.2f} tur={len(turlar)}")
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
