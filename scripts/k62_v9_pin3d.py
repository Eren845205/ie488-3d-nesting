# -*- coding: utf-8 -*-
"""k62_v9_pin3d.py — K-62 v9: KANOPI 3D-PIN tek-atis NFV olcumu (SERHLI).

Mekanizma (PLAN_KOK_SEBEP_VE_KISIT_V2.md 'MANUEL'E YAKLASMA YOLU' v9):
v8'in yapisal siniri 2D kolon muhruydu (pinin alti-ustu yasak -> kanopi
pin edilemiyordu). v9: pin GERCEK 3D voxelleriyle best_decode occupancy'sine
ON-YUKLENIR (nfv_solve pin_3d=True; tests/test_k62_v9_pin3d.py 13 test):
  - kanopi z~70'te 3D-pin -> cozucu kanopi ALTINDAKI gercek bosluga istifler,
  - kuleler deliklerden YUKSELIR, ustunden kanopi gecer
  = insan cozumunun (110.41) birebir mekanigi, NFV kalitesiyle.

Olcum: geometrik kanopi adayi (veri-adi YOK, A11) + fizibilite pozu ->
z adaylari taranir; her z icin TUM set (kanopi pinli) tek NFV cozumu.
En iyi z'de merged-mesh min_clearance olculur.

SERHLER (A11 + A2): tek-set on-olcum; kilit (5-yon/rot) olculmez (kanopi
en-ustte, +Z ilk sokulen — yapisal dusuk risk; tam legalite kapi asamasinda);
fine_settle/repair pin_3d'de yapisal atlanir (kuantizasyon vergisi oder);
mekanizma genellemesi k59-deseni dagilimsal olcumle (holey_frames).

Kosum: python -m scripts.detach_run k62_v9_pin3d   (D:\\ie488'den, SAKIN
makine — K-57a munhasirlik; NFV plan1 ~6-10dk/z). SAF ASCII stdout.
Env: K62V9_ZLER="70,72,68,74" (mm, virgullu) ile z adaylari ezilebilir.
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
from src.nesting3d.clearance import min_clearance
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.kanopi import duz_poz_nogo_fizibilite, duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv

LOG = Path(__file__).parent / "k62_v9_pin3d.log"
OUT = _ROOT / "results" / "k62_v9_pin3d.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
REF = {"pin_k56f": 140.21, "v4_kanopi": 136.50, "manuel": 110.41}
# Geometrik kanopi tetigi (k62_kanopi_plan1 ile ayni esikler; A11 veri-adi yok)
ALAN_ORAN_ESIK = 0.35
DOLULUK_ESIK = 0.6
_zler_env = os.environ.get("K62V9_ZLER", "").strip()
Z_ADAYLARI_MM = ([float(v) for v in _zler_env.split(",")] if _zler_env
                 else [70.0, 72.0, 68.0, 74.0])
# Acik pitch (mm): bos -> auto (suggest_nfv_pitch). Ilk olcum dersi
# (2026-08-04): auto 2.4 kaba + settle pin_3d'de atlanir -> kuantizasyon
# vergisi sonucu yedi (139.2). Ince-pitch tek-z derinlesmesi bu env ile.
_pitch_env = os.environ.get("K62V9_PITCH", "").strip()
PITCH_MM = float(_pitch_env) if _pitch_env else None
# Pin poz secimi: fizibilite pozlar[] indeksleri (virgullu). Default [0].
# Teshis 2026-08-04: tavan = bobbin sutunlarinin delik kapasitesi ->
# kanopi ofseti delik hizasini degistirir (v10 on-sinyali).
_poz_env = os.environ.get("K62V9_POZLAR", "").strip()
POZ_IDX = ([int(v) for v in _poz_env.split(",")] if _poz_env else [0])


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _kanopi_adayi(inst):
    """Geometrik tetik: duz footprint alani buyuk + delikli + no-go-fizibil."""
    pw, pd = eg.PLATE_STD
    for p in inst.parts:
        if not getattr(p, "stl_path", None):
            continue
        try:
            mesh = trimesh.load(p.stl_path, force="mesh")
        except Exception as e:
            log(f"  uyari: {p.name} mesh yuklenemedi ({e})")
            continue
        ext = sorted(float(x) for x in mesh.extents)[::-1]
        alan_oran = (ext[0] * ext[1]) / (pw * pd)
        if alan_oran < ALAN_ORAN_ESIK:
            continue
        fiz = duz_poz_nogo_fizibilite(mesh, pw, pd, eg.NOGO_STD,
                                      pitch=0.5, method="slice")
        if fiz is None or not fiz["pozlar"] or fiz["doluluk"] >= DOLULUK_ESIK:
            continue
        log(f"  kanopi adayi: {p.name} alan_oran={alan_oran:.2f}"
            f" doluluk={fiz['doluluk']:.3f} uygun={fiz['uygun_sayisi']}"
            f" kalinlik={fiz['duz_kalinlik_mm']:.2f}mm")
        return p, mesh, fiz
    return None


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v9 OLCUM: kanopi 3D-pin tek-atis NFV (SERHLI on-olcum)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED}")
    log(f"z adaylari (mm): {Z_ADAYLARI_MM}  pitch={PITCH_MM or 'auto'}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"instance: {len(inst.parts)} tip / {n_total} parca")

    aday = _kanopi_adayi(inst)
    if aday is None:
        log("FATAL: geometrik kanopi adayi yok — v9 tetiklenmez (NOOP)")
        log("BITTI")
        return
    p0, mesh, fiz = aday
    pw, pd = eg.PLATE_STD
    sonuclar = []
    kombinasyonlar = []
    for pi in POZ_IDX:
        if pi < 0 or pi >= len(fiz["pozlar"]):
            log(f"uyari: poz idx {pi} yok (kayitli {len(fiz['pozlar'])})")
            continue
        for z_mm in Z_ADAYLARI_MM:
            kombinasyonlar.append((pi, z_mm))
    for pi, z_mm in kombinasyonlar:
        poz = fiz["pozlar"][pi]
        rot_deg = float(poz["rot_deg"])
        rot = (tt.rotation_matrix(np.deg2rad(rot_deg), [0.0, 0.0, 1.0])
               @ duz_rot_matrisleri(mesh)[0])
        log(f"pin pozu[{pi}]: rot_deg={rot_deg} dx={poz['dx_mm']:.1f}"
            f" dy={poz['dy_mm']:.1f}")
        pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
               "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
               "rot": rot.tolist()}
        log(f"[z={z_mm}] NFV pin_3d cozumu basliyor ...")
        tz = time.perf_counter()
        try:
            r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd,
                          fine_pitch=PITCH_MM, seed=SEED, quality="fast",
                          clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                          pinned_placements=[pin], pin_3d=True)
        except Exception:
            log(f"[z={z_mm}] FATAL cozum hatasi:\n{traceback.format_exc()}")
            sonuclar.append({"z_mm": z_mm, "hata": traceback.format_exc(
                limit=1).strip().splitlines()[-1]})
            gc.collect()
            continue
        sure = time.perf_counter() - tz
        kayit = {
            "z_mm": z_mm, "poz_idx": pi,
            "poz": {k: float(v) for k, v in poz.items()},
            "height_mm": float(r.height_mm),
            "n_placed": int(r.n_placed), "n_total": n_total,
            "fine_pitch": float(r.fine_pitch),
            "sure_s": round(sure, 1),
            "adaptive_reason": str(r.adaptive_reason)[:300],
        }
        log(f"[z={z_mm}] h={r.height_mm:.2f}mm n={r.n_placed}/{n_total}"
            f" pitch={r.fine_pitch} sure={sure / 60:.1f}dk")
        # kanopi-goreli katman telemetrisi (A4: tavani NE yapiyor?)
        kz1 = float(z_mm)
        kz2 = kz1 + float(fiz["duz_kalinlik_mm"])
        pt = float(r.fine_pitch)
        katlar = {"altinda": 0, "delikten": 0, "ustunde": 0, "kanopi": 0}
        ust_tipler = {}
        _fvp = r.fine_voxel_parts
        _vps = (_fvp if isinstance(_fvp, dict)
                else {v.id: v for v in _fvp})
        for pl in r.placements:
            vp = _vps.get(pl.part_id)
            o = (vp.orientations[pl.orientation_idx]
                 if vp and pl.orientation_idx < len(vp.orientations) else None)
            if o is None:
                continue
            alt = pl.z * pt
            ust = (pl.z + o.grid.shape[2]) * pt   # dilation dahil, kaba
            ad = getattr(vp, "name", str(pl.part_id))
            if ad == p0.name and abs(alt - kz1) < 2 * pt:
                katlar["kanopi"] += 1
            elif ust <= kz1 + 1e-6:
                katlar["altinda"] += 1
            elif alt >= kz2 - 1e-6:
                katlar["ustunde"] += 1
                ust_tipler[ad] = ust_tipler.get(ad, 0) + 1
            else:
                katlar["delikten"] += 1
        kayit["katmanlar"] = katlar
        kayit["ustundeki_tipler"] = ust_tipler
        log(f"[z={z_mm}] katman: {katlar}")
        log(f"[z={z_mm}] kanopi-ustu tipler: {ust_tipler}")
        # tavani KIM yapiyor: en yuksek tepeli 5 yerlesim (ad, alt, ust)
        _tepe = []
        for pl in r.placements:
            vp = _vps.get(pl.part_id)
            o = (vp.orientations[pl.orientation_idx]
                 if vp and pl.orientation_idx < len(vp.orientations) else None)
            if o is None:
                continue
            _tepe.append((round((pl.z + o.grid.shape[2]) * pt, 1),
                          round(pl.z * pt, 1),
                          getattr(vp, "name", str(pl.part_id))))
        _tepe.sort(reverse=True)
        kayit["tepe5"] = [{"ust_mm": u, "alt_mm": a, "ad": ad}
                          for u, a, ad in _tepe[:5]]
        log(f"[z={z_mm}] tepe5 (ust,alt,ad): {_tepe[:5]}")
        sonuclar.append(kayit)
        # en-iyi aday clearance olcumu icin hafif durumu sakla
        kayit["_r"] = r
        # bellek: yalniz su ana kadarki EN IYI tam-yerlesimli r tutulur
        tam = [s for s in sonuclar if "_r" in s and s["n_placed"] == n_total]
        if len(tam) > 1:
            tam_sirali = sorted(tam, key=lambda s: s["height_mm"])
            for s in tam_sirali[1:]:
                del s["_r"]
        elif "_r" in kayit and kayit["n_placed"] != n_total:
            # eksik yerlesim clearance olcumune girmez
            pass
        gc.collect()

    adaylar = [s for s in sonuclar if s.get("n_placed") == n_total
               and "_r" in s]
    en_iyi = min(adaylar, key=lambda s: s["height_mm"]) if adaylar else None
    if en_iyi is not None:
        r = en_iyi.pop("_r")
        log(f"[clearance] en iyi z={en_iyi['z_mm']}"
            f" h={en_iyi['height_mm']:.2f} — merged min_clearance ...")
        try:
            meshes = list(placed_meshes(r.placements, r.fine_voxel_parts,
                                        float(r.fine_pitch)))
            cl = min_clearance(meshes)
            en_iyi["min_clearance_mm"] = float(cl.min_mm)
            log(f"[clearance] min={cl.min_mm:.3f}mm (kural >= {CLEAR_MM};"
                f" worst_pair={cl.worst_pair} cift={cl.n_pairs_checked})")
        except Exception:
            log(f"[clearance] OLCULEMEDI:\n{traceback.format_exc()}")
            en_iyi["min_clearance_mm"] = None
    for s in sonuclar:
        s.pop("_r", None)

    out = (OUT if PITCH_MM is None
           else OUT.with_name(f"k62_v9_pin3d_p{PITCH_MM}.json"))
    doc = {
        "olcum": "k62_v9_pin3d", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pitch_istek_mm": PITCH_MM,
        "serh": ("tek-set on-olcum (A11); kilit olculmedi; settle/repair "
                 "pin_3d'de atlanir; genelleme k59-deseni dagilimsal bekler"),
        "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                     "clearance_mm": CLEAR_MM, "seed": SEED},
        "kanopi": {"ad": p0.name, "doluluk": fiz["doluluk"],
                   "duz_kalinlik_mm": fiz["duz_kalinlik_mm"],
                   "poz": poz, "rot_deg": rot_deg},
        "referanslar": REF,
        "z_sonuclari": sonuclar,
        "en_iyi": ({k: v for k, v in en_iyi.items()} if en_iyi else None),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {out}")
    try:
        ek = ONEDRIVE / "results" / out.name
        if ONEDRIVE.exists() and ek.resolve() != out.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
            log(f"kopya: {ek}")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")

    if en_iyi:
        log(f"OZET: en iyi z={en_iyi['z_mm']} h={en_iyi['height_mm']:.2f}mm"
            f" (ref: v4 {REF['v4_kanopi']} / pin {REF['pin_k56f']}"
            f" / manuel {REF['manuel']})")
    else:
        log("OZET: tam-yerlesimli aday YOK (mekanizma/parametre teshisi gerek)")
    log(f"WALL_S={time.perf_counter() - t0:.1f}"
        f"  ({(time.perf_counter() - t0) / 60:.1f} dk)")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # FATAL kalkani (2026-08-04 dersi: detach stderr kaybolabiliyor)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
