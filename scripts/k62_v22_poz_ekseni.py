# -*- coding: utf-8 -*-
"""k62_v22_poz_ekseni.py — K-62 v22: TEPE-SURUCU POZ EKSENI (envanter + n24 A/B).

v21 dersi: script-seviyesi sokum hamleleri 127.20'de tukendi; tepe suruculeri
(pyramid_with_doors / bobbin_3 / TAPER) NFV default n=8 poz menusuyle
cozuluyor. Master sette 28 poz var (K-18p AX24 ekseni; "n24 neredeyse
bedava" 2026-07-08 dersi). Uc faz:

  FAZ-1  POZ-ENVANTER (kosusuz, saniyeler): tavan tiplerinin mesh'leri 28
         master pozda dondurulur -> bbox z-boyu; ilk-8 menu min-boyu vs
         28-poz min-boyu. 8-disi pozda belirgin alcak durus varsa poz
         ekseni ACIK demektir (kosulsuz kanit).
  FAZ-2  n24 TABAN A/B: z=64.8 uclu zincir n_orientations=24 ile cozulur
         (MemErr -> n12 graceful). Ref: n8 taban 129.60.
  FAZ-3  (kosullu) n24 taban iyilestiyse tekil-relokasyon kisa zinciri
         (v20 mekanigi, max 6 deneme) + settle + A2.

Kosum: python -m scripts.detach_run k62_v22_poz_ekseni  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum.
"""
from __future__ import annotations

import gc
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
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.voxelize import rotation_matrices, N_MASTER_POSES
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v17_ripup import a2_olc
from scripts.k62_v20_relokasyon import _dokum

LOG = Path(__file__).parent / "k62_v22_poz_ekseni.log"
OUT = _ROOT / "results" / "k62_v22_poz_ekseni.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_RELOK = 6
REF = {"v20": 127.20, "n8_taban": 129.60, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
TAVAN_TIPLERI = ["pyramid_with_doors", "bobbin_3_v2", "TAPER-GAUGE-1",
                 "811791-1", "MTShoe"]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v22: tepe-surucu POZ ekseni (envanter + n24 A/B)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh0, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh0)[0])

    # ---- FAZ-1: poz-envanter (kosusuz) ---------------------------------
    log(f"[1] poz-envanter (master {N_MASTER_POSES} poz; ilk-8 = NFV menusu)")
    import trimesh as _tm
    rots = rotation_matrices(N_MASTER_POSES)
    envanter = {}
    mesh_by_name = {}
    for p in inst.parts:
        nm = getattr(p, "name", None)
        if nm in TAVAN_TIPLERI and nm not in mesh_by_name \
                and getattr(p, "stl_path", None):
            try:
                mesh_by_name[nm] = _tm.load(p.stl_path, force="mesh")
            except Exception as e:
                log(f"  uyari: {nm} mesh yuklenemedi ({e})")
    for nm in TAVAN_TIPLERI:
        m = mesh_by_name.get(nm)
        if m is None:
            log(f"  {nm:22s}: mesh bulunamadi (atla)")
            continue
        boylar = []
        for rot in rots:
            mm = m.copy()
            mm.apply_transform(rot)
            ext = mm.bounds[1] - mm.bounds[0]
            boylar.append(float(ext[2]))
        min8 = min(boylar[:8])
        min28 = min(boylar)
        arg28 = int(np.argmin(boylar))
        envanter[nm] = {"min8": round(min8, 1), "min28": round(min28, 1),
                        "poz28": arg28, "kazanc": round(min8 - min28, 1)}
        log(f"  {nm:22s}: min8={min8:6.1f}  min28={min28:6.1f}"
            f"  (poz {arg28})  kazanc={min8 - min28:5.1f}mm")

    # ---- FAZ-2: n24 taban A/B ------------------------------------------
    def coz(pinler=None, rutbeler=None, pitch=None, settle=False, n_or=None):
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
                         oncelik_adlari=(rutbeler or None),
                         n_orientations=n_or)

    n_kullanilan = 24
    res = None
    for n_dene in (24, 12):
        try:
            t1 = time.perf_counter()
            res = coz(rutbeler=UCLU, n_or=n_dene)
            n_kullanilan = n_dene
            log(f"[2] n{n_dene} taban: h={float(res.height_mm):.2f}"
                f" n={int(res.n_placed)}/{n_total}"
                f" pitch={float(res.coarse_pitch):.3f}"
                f" ({(time.perf_counter() - t1)/60:.1f}dk)"
                f"  [ref n8: 129.60]")
            break
        except MemoryError:
            log(f"[2] n{n_dene} MemoryError -> dusur")
            gc.collect()
    if res is None:
        log("[2] n24/n12 ikisi de MemErr -> dur")
        return
    h_iyi = float(res.height_mm)
    pt = float(res.coarse_pitch)

    # ---- FAZ-3: kosullu tekil-relokasyon kisa zinciri ------------------
    denemeler = []
    if int(res.n_placed) == n_total:
        denendi = set()
        for d in range(1, MAX_RELOK + 1):
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
            t1 = time.perf_counter()
            r = coz(pinler=pinler, pitch=pt, n_or=n_kullanilan)
            hr = float(r.height_mm)
            nr = int(r.n_placed)
            kabul = (nr == n_total and hr < h_iyi - 0.01)
            log(f"[3 d{d}] {hedef_p['ad']:22s} -> h={hr:.2f} n={nr}/{n_total}"
                f" ({'KABUL' if kabul else 'gecildi'})"
                f" {(time.perf_counter() - t1)/60:.1f}dk")
            denemeler.append({"d": d, "ad": hedef_p["ad"], "h": hr,
                              "n": nr, "kabul": kabul})
            if kabul:
                del res
                gc.collect()
                res, h_iyi = r, hr
                denendi.clear()
            else:
                del r
                gc.collect()

    # settle final + A2
    dokum = _dokum(res)
    dokum.sort(key=lambda k: k["ust"])
    pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
               "z_mm": q["z_mm"], "rot": q["rot"]}
              for q in dokum[1:]]
    t1 = time.perf_counter()
    try:
        rs = coz(pinler=pinler, pitch=pt, settle=True, n_or=n_kullanilan)
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
    except MemoryError:
        log("[B2] MemoryError -> settle atlandi")
        gc.collect()

    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[A2] clearance={a2['min_clearance_mm']}"
            f" kilit5={a2['kilit_5yon']} rot={a2['rot_kilit']}"
            f" sokum_planli={a2['sokum_planli']}"
            f" -> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[A2] OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {"olcum": "k62_v22_poz_ekseni",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": "A11 tek-set on-olcum (fix'li motor)",
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI, "n_orientations": n_kullanilan},
           "envanter": envanter, "denemeler": denemeler,
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
    log(f"OZET: final={h_iyi:.2f} n_or={n_kullanilan}")
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
