# -*- coding: utf-8 -*-
"""k62_v10_silo.py — K-62 v10: SILO planlayici — kule-kopya x delik-atama (SERHLI).

v9 teshisi (2026-08-04): mekanizma insan-deseni kurdu (kanopi ustu 0,
41 delikten) ama tavani bobbin delik-sutunlari yapiyor (103->139; manuel
sutunlar 110'da biter) — greedy BLB kopyalari az sayida kolona yigiyor.

v10 mekanizmasi (plan 'v10 — ortak optimizasyon'):
  faz-A: v9 kosusu (kanopi 3D-pin) -> KANOPI-TEPESINI asan tipler = silo
         adaylari (COZUM-GUDUMLU tetik; veri-adi yok — v4 suclu-tasima deseni).
  faz-B: kanopi dilated-footprint DELIK maskesinde 2D greedy sutun yerlesimi;
         her silo tipi icin dusuk-katman durus (dilated grid en alcak rot),
         sutun basina L = kanopi-tepesine sigan katman; kopyalar katmanli
         3D pin olur (z = k*katman_h; gercek katman-arasi bosluk z-dilation).
  faz-C: kalan set (kanopi + silolar pinli) pin_3d ile cozulur; telemetri +
         merged clearance.

SERHLER (A11+A2): tek-set on-olcum; kilit olculmez; settle/repair pin_3d'de
atlanir; genelleme dagilimsal olcum bekler. Silo planlayici DENEY scriptinde
— GO cikarsa uretim kablosu ayri Eren-onayli seans.

Kosum: python -m scripts.detach_run k62_v10_silo  (D:\\ie488, sakin makine).
Env: K62V10_Z (kanopi z_mm, default 68) · K62V10_POZ (fizibilite poz idx, 0).
SAF ASCII stdout.
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
import trimesh
import trimesh.transformations as tt

import scripts.eval_gate as eg
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv, _nfv_clearance_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v10_silo.log"
OUT = _ROOT / "results" / "k62_v10_silo.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF = {"v9": 139.20, "v4_kanopi": 136.50, "pin_k56f": 140.21,
       "manuel": 110.41}
Z_KANOPI = float(os.environ.get("K62V10_Z", "68"))
POZ_IDX = int(os.environ.get("K62V10_POZ", "0"))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _katman_telemetri(r, kanopi_ad, kz1, kz2):
    """(katlar, ust_tipler, tepe5) — v9 telemetrisiyle ayni tanimlar."""
    pt = float(r.fine_pitch)
    katlar = {"altinda": 0, "delikten": 0, "ustunde": 0, "kanopi": 0}
    ust_tipler = {}
    tepe = []
    fvp = r.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    for pl in r.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        alt = pl.z * pt
        ust = (pl.z + o.grid.shape[2]) * pt
        ad = getattr(vp, "name", str(pl.part_id))
        tepe.append((round(ust, 1), round(alt, 1), ad))
        if ad == kanopi_ad and abs(alt - kz1) < 2 * pt:
            katlar["kanopi"] += 1
        elif ust <= kz1 + 1e-6:
            katlar["altinda"] += 1
        elif alt >= kz2 - 1e-6:
            katlar["ustunde"] += 1
            ust_tipler[ad] = ust_tipler.get(ad, 0) + 1
        else:
            katlar["delikten"] += 1
    tepe.sort(reverse=True)
    return katlar, ust_tipler, tepe[:5]


def _silo_tipleri(r, kanopi_ad, kz2):
    """COZUM-GUDUMLU tetik: tepesi kanopi-tepesini asan tipler (ad->max_ust)."""
    pt = float(r.fine_pitch)
    fvp = r.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    asanlar = {}
    for pl in r.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        ad = getattr(vp, "name", str(pl.part_id))
        if ad == kanopi_ad:
            continue
        ust = (pl.z + o.grid.shape[2]) * pt
        if ust > kz2 + pt:
            asanlar[ad] = max(asanlar.get(ad, 0.0), ust)
    return asanlar


def _dusuk_katman_rotlar(mesh):
    """Silo durus adaylari: eksenleri Z'ye getiren 3 rot, katman-h artan sirali."""
    ext = np.asarray(mesh.extents, dtype=float)
    rotlar = []
    for eksen in np.argsort(ext):  # en alcak katman once
        if eksen == 2:
            R = np.eye(4)
        elif eksen == 0:
            R = tt.rotation_matrix(np.pi / 2.0, [0.0, 1.0, 0.0])
        else:
            R = tt.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0])
        rotlar.append((float(ext[eksen]), R))
    return rotlar


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v10 SILO OLCUMU (kule-kopya x delik-atama; SERHLI)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}  z_kanopi={Z_KANOPI}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][POZ_IDX]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    kz1 = Z_KANOPI
    kz2 = Z_KANOPI + float(fiz["duz_kalinlik_mm"])
    kanopi_pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
                  "y_mm": float(poz["dy_mm"]), "z_mm": kz1,
                  "rot": rot_k.tolist()}
    log(f"kanopi: {p0.name} poz={poz} tepe={kz2:.1f}mm")

    # ---- faz-A: v9 kosusu -> silo adaylari (cozum-gudumlu) ----------------
    log("[faz-A] v9 referans kosusu (silo adaylarini cozum belirler) ...")
    rA = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0], plate_d_mm=eg.PLATE_STD[1],
                   fine_pitch=None, seed=SEED, quality="fast",
                   clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                   pinned_placements=[kanopi_pin], pin_3d=True)
    hA = float(rA.height_mm)
    pitch = float(rA.fine_pitch)
    katA, ustA, tepeA = _katman_telemetri(rA, p0.name, kz1, kz2)
    asanlar = _silo_tipleri(rA, p0.name, kz2)
    log(f"[faz-A] h={hA:.2f} pitch={pitch} katman={katA}")
    log(f"[faz-A] kanopi-tepesini asan tipler: "
        f"{ {k: round(v, 1) for k, v in asanlar.items()} }")
    del rA
    gc.collect()
    if not asanlar:
        log("[faz-A] asan tip yok -> silo gereksiz (NOOP). BITTI")
        return

    # ---- faz-B: silo planlayici ------------------------------------------
    eff_m, z_c = _nfv_clearance_voxels(CLEAR_MM, pitch, 1)
    nx, ny = int(eg.PLATE_STD[0] // pitch), int(eg.PLATE_STD[1] // pitch)
    # Delik maskesi kanopi MARGIN-0 fp'sinden (tek-tarafli dilation ilkesi,
    # _pin_hazirla ile ayni: komsu kendi marjini tasir — silo fp'si dilated).
    # Ilk tur dersi: cift-dilation delikleri ~5mm daraltip bobbinleri disari
    # atti (0/12 yatik). Solver-modelde dilated kanopi ile ortusme olabilir
    # (onyukle OR) — gercek raw-raw mesafe silo dilation'indan >= 2.4mm.
    vkan = voxelize_part(p0.name, mesh, pitch, rot_matrices=[rot_k],
                         method="slice", margin=0, z_dilate=0)
    gk = vkan.orientations[0].grid
    kix = int(round(float(poz["dx_mm"]) / pitch))
    kiy = int(round(float(poz["dy_mm"]) / pitch))
    dolu = np.zeros((nx, ny), dtype=bool)   # silo tarafindan/kanopi/no-go isgal
    fpk = gk.any(axis=2)
    x0, y0 = max(0, kix), max(0, kiy)
    x1 = min(nx, kix + fpk.shape[0]); y1 = min(ny, kiy + fpk.shape[1])
    if x1 > x0 and y1 > y0:
        dolu[x0:x1, y0:y1] |= fpk[max(0, -kix):max(0, -kix) + (x1 - x0),
                                  max(0, -kiy):max(0, -kiy) + (y1 - y0)]
    ngm = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, eg.PLATE_STD[0],
                                       eg.PLATE_STD[1], pitch)
    if ngm is not None:
        dolu |= np.asarray(ngm, dtype=bool)[:nx, :ny]
    log(f"[faz-B] grid {nx}x{ny}  kanopi+nogo isgali: {int(dolu.sum())} hucre"
        f" ({dolu.mean():.2f})")

    silo_pinleri = []
    silo_plan = []
    # EN COK ASAN tip once (ilk tur dersi: 811793 kopya-sayisiyla one gecip
    # en iyi delikleri kapti, tavani yapan bobbin_1 disarida kaldi -> 156).
    tipler = sorted(asanlar, key=lambda ad: -asanlar[ad])
    for ad in tipler:
        ps = next((p for p in inst.parts if p.name == ad), None)
        if ps is None or not getattr(ps, "stl_path", None):
            continue
        m = trimesh.load(ps.stl_path, force="mesh")
        Q = int(ps.qty)
        yerlesti = 0
        for katman_mm, R in _dusuk_katman_rotlar(m):
            if yerlesti >= Q:
                break
            # fp motor damgasiyla AYNI halo (eff_m): yatay ayrim cift-tarafli
            # dilation'la korunur (solver parcalari da dilated). Katman
            # araligi +1 hucre: slice merkez-orneklemesi yuzeyleri yarim
            # hucre tasirabilir; dikey pin-pin bosluk 2 hucle ~4.8-2.4>=2.4.
            vk = voxelize_part(ad, m, pitch, rot_matrices=[R], method="slice",
                               margin=eff_m, z_dilate=z_c)
            g = vk.orientations[0].grid
            fw, fd, gh = g.shape
            raw_h_vox = gh - z_c
            adim = gh + 1
            L = 0
            while (L * adim + raw_h_vox) * pitch <= kz2 + 1e-6:
                L += 1
            # L=1 dikey silo = solver'in zaten yapabildigi, delik alani israfi
            # (ilk tur: dik-76 tek-katman sutunlar alan yiyip net zarar verdi).
            if L < 2 or fw > nx or fd > ny:
                continue
            fp = g.any(axis=2)
            # raster tarama: dilated fp bos bolgeye (delik/dis) sigmali
            x = 0
            while x + fw <= nx and yerlesti < Q:
                y = 0
                while y + fd <= ny and yerlesti < Q:
                    pencere = dolu[x:x + fw, y:y + fd]
                    if not (pencere & fp).any():
                        adet = min(L, Q - yerlesti)
                        # KRITIK (tur-3 kok-neden): pin spec'i MARGIN-0 bbox
                        # origin'i ister; (x,y) halo'lu fp origin'i -> halo
                        # kadar iceri kaydir. Kaydirmasiz gercek pin modelden
                        # halo*pitch kayiyordu (ihlal serisi 1.92->0.58).
                        halo = eff_m
                        for k in range(adet):
                            silo_pinleri.append({
                                "ad": ad,
                                "x_mm": (x + halo) * pitch,
                                "y_mm": (y + halo) * pitch,
                                "z_mm": k * adim * pitch, "rot": R.tolist()})
                        dolu[x:x + fw, y:y + fd] |= fp
                        silo_plan.append({"ad": ad, "x": x, "y": y,
                                          "katman": adet,
                                          "katman_h_mm": round(gh * pitch, 1)})
                        yerlesti += adet
                        y += fd
                    else:
                        y += 1
                x += 1
            log(f"[faz-B] {ad}: rot katman={katman_mm:.1f}mm L={L}"
                f" -> toplam yerlesen {yerlesti}/{Q}")
        if yerlesti < Q:
            log(f"[faz-B] UYARI: {ad} icin {Q - yerlesti} kopya siloya"
                " SIGMADI (solver havuzunda kalir)")
    log(f"[faz-B] silo pin sayisi: {len(silo_pinleri)}"
        f" ({len(silo_plan)} sutun)")

    # ---- faz-C: silolu cozum ---------------------------------------------
    pins = [kanopi_pin] + silo_pinleri
    log(f"[faz-C] NFV pin_3d cozumu ({len(pins)} pin) ...")
    tc = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0], plate_d_mm=eg.PLATE_STD[1],
                  fine_pitch=pitch, seed=SEED, quality="fast",
                  clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                  pinned_placements=pins, pin_3d=True)
    sure = time.perf_counter() - tc
    kat, ust, tepe5 = _katman_telemetri(r, p0.name, kz1, kz2)
    log(f"[faz-C] h={r.height_mm:.2f}mm n={r.n_placed}/{n_total}"
        f" sure={sure / 60:.1f}dk")
    log(f"[faz-C] katman: {kat}")
    log(f"[faz-C] tepe5: {tepe5}")

    cl_mm = None
    try:
        meshes = list(placed_meshes(r.placements, r.fine_voxel_parts,
                                    float(r.fine_pitch)))
        cl = min_clearance(meshes)
        cl_mm = float(cl.min_mm)
        log(f"[clearance] min={cl_mm:.3f}mm (kural >= {CLEAR_MM};"
            f" worst_pair={cl.worst_pair} cift={cl.n_pairs_checked})")
    except Exception:
        log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")

    doc = {
        "olcum": "k62_v10_silo", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d atlanir; silo planlayici deney-scriptinde"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED},
        "kanopi": {"ad": p0.name, "z_mm": kz1, "tepe_mm": kz2,
                   "poz_idx": POZ_IDX},
        "faz_a": {"h_mm": hA, "katman": katA,
                  "asan_tipler": {k: round(v, 1) for k, v in asanlar.items()}},
        "silo_plan": silo_plan, "n_silo_pin": len(silo_pinleri),
        "faz_c": {"h_mm": float(r.height_mm), "n_placed": int(r.n_placed),
                  "n_total": n_total, "katman": kat, "ustundeki_tipler": ust,
                  "tepe5": [list(t) for t in tepe5],
                  "min_clearance_mm": cl_mm, "sure_s": round(sure, 1),
                  "fine_pitch": float(r.fine_pitch),
                  "adaptive_reason": str(r.adaptive_reason)[:300]},
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

    log(f"OZET: v10 h={r.height_mm:.2f} (v9 {REF['v9']} / v4"
        f" {REF['v4_kanopi']} / manuel {REF['manuel']})"
        f"  n={r.n_placed}/{n_total}  clearance={cl_mm}")
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
