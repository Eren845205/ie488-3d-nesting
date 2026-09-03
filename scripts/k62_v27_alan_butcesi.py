# -*- coding: utf-8 -*-
"""k62_v27_alan_butcesi.py — K-62 v27: ALAN-BUTCESI alt-siniri (A4 kosusuz teshis).

v26b EKSEN KAPANISI sonrasi kalan tek yol "kanopi-alti bandin alan-verimli
GLOBAL yeniden-istifi" (buyuk kod-gelistirme) ilan edildi. Bu script o
gelistirmeye girmeden ONCE ucuz aritmetik hukum verir (A4):

  Soru: mukemmel(e-yakin) bir yeniden-istif, verili sozlesmede (plaka 325x325,
  no-go, clearance 2mm dilated damga, kanopi z=64.8 + kalinlik) hangi tavan
  T'yi ALAN olarak mumkun kilar? 110-bandi acik mi, 127.2 yapisal mi?

  Model (iyimser taraf = ALT-SINIR; gercek cozucu bundan iyi olamaz):
    3 bolge sinifi, her biri (taban-alani, yukseklik) butcesi:
      R_full: kanopi-disi plaka + kanopi DELIK kolonlari  -> yukseklik T
      R_alt : kanopi malzemesinin alti                    -> yukseklik kz1
      R_ust : kanopi malzemesinin ustu                    -> yukseklik T-kz2
    Her kopya (tip x adet) icin 3 eksen-pozunun dilated fp/gh menusu;
    bolgede k = floor(H/gh) kat istif -> taban maliyeti = fp/k.
    Butce-farkinda greedy atama (esneklik-az + maliyet-buyuk once);
    verim carpani eta ∈ {1.0, 0.8, 0.7} ile kapasite olceklenir.

  Tetikler geometriktir (kz1, gh, dilated fp); veri-adi yalnizca olcum
  hedefi olarak gecer (A11-uyumlu). Solve YOK — dakikalar, dusuk RAM.

Kosum: python -m scripts.detach_run k62_v27_alan_butcesi  (D:\\ie488). ASCII.
SERH (A11): tek-set kosusuz teshis; hukum yalnizca "gelistirmeye deger mi"
kararina veri saglar, kazanc ilani degildir.
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
import trimesh

import scripts.eval_gate as eg
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import _nfv_clearance_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v26_atama_planner import _dusuk_katman_rotlar

LOG = Path(__file__).parent / "k62_v27_alan_butcesi.log"
OUT = _ROOT / "results" / "k62_v27_alan_butcesi.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
PT = 2.4          # analiz pitch'i (v26 coarse ile ayni)
CLEAR_MM = 2.0
KZ1 = 64.8        # kanopi tabani (sampiyon iz=27; v18 taramasi)
ETALAR = (1.0, 0.8, 0.7)
# T taramasi: voxel-kati tavan adaylari (110.4 = manuel bandi ... 129.6)
T_LISTE = (110.4, 112.8, 115.2, 117.6, 120.0, 122.4, 124.8, 127.2, 129.6)
REF = {"plato": 127.20, "manuel": 110.41}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _tip_menusu(inst, pt, eff_m, z_c, kanopi_ad, nx, ny):
    """Tip basina dilated (fp_cells, gh_v) menusu — 3 eksen pozu."""
    menu = {}
    for p in inst.parts:
        if p.name == kanopi_ad or not getattr(p, "stl_path", None):
            continue
        m = trimesh.load(p.stl_path, force="mesh")
        pozlar = []
        gorulen = set()
        for R in _dusuk_katman_rotlar(m):
            anahtar = tuple(np.round(np.asarray(R)[:3, :3].ravel(), 3))
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            vk = voxelize_part(p.name, m, pt, rot_matrices=[np.asarray(R)],
                               method="slice", margin=eff_m, z_dilate=z_c)
            g = vk.orientations[0].grid
            if g.shape[0] > nx or g.shape[1] > ny:
                continue
            pozlar.append({"fp": int(g.any(axis=2).sum()),
                           "gh_v": int(g.shape[2])})
        pozlar.sort(key=lambda q: q["gh_v"])
        menu[p.name] = {"pozlar": pozlar, "qty": int(p.qty)}
    return menu


def _kopya_opsiyonlari(pozlar, t_v, kz1_v, ust_v):
    """Bolge -> min taban-maliyeti (hucre). Bolge sigmiyorsa yok."""
    ops = {}
    for q in pozlar:
        gh, fp = q["gh_v"], q["fp"]
        for bolge, hv in (("full", t_v), ("alt", kz1_v), ("ust", ust_v)):
            if hv <= 0 or gh > hv:
                continue
            maliyet = fp / float(hv // gh)
            if bolge not in ops or maliyet < ops[bolge]:
                ops[bolge] = maliyet
    return ops


def _atama(kopyalar, kapasite):
    """Butce-farkinda greedy: esneklik-az + maliyet-buyuk once.

    kopyalar: [(ad, ops-dict)] · kapasite: {bolge: hucre}
    Doner: (yerlesen, tasan_listesi, kullanilan{bolge})
    """
    kalan = dict(kapasite)
    kullanilan = {b: 0.0 for b in kapasite}
    sirali = sorted(kopyalar,
                    key=lambda k: (len(k[1]),
                                   -min(k[1].values()) if k[1] else 0.0))
    tasan = []
    for ad, ops in sirali:
        if not ops:
            tasan.append((ad, "hicbir bolgeye sigmiyor"))
            continue
        secildi = False
        for bolge, maliyet in sorted(ops.items(), key=lambda kv: kv[1]):
            if kalan[bolge] >= maliyet:
                kalan[bolge] -= maliyet
                kullanilan[bolge] += maliyet
                secildi = True
                break
        if not secildi:
            tasan.append((ad, "butce doldu"))
    return len(sirali) - len(tasan), tasan, kullanilan


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v27: ALAN-BUTCESI alt-siniri (kosusuz A4 teshis)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} pitch={PT} kz1={KZ1}")

    inst = eg._load_instance("plan1")
    p0, mesh0, fiz = _kanopi_adayi(inst)
    kz2 = KZ1 + float(fiz["duz_kalinlik_mm"])
    nx, ny = int(eg.PLATE_STD[0] // PT), int(eg.PLATE_STD[1] // PT)
    eff_m, z_c = _nfv_clearance_voxels(CLEAR_MM, PT, 1)
    log(f"kanopi={p0.name} kalinlik={fiz['duz_kalinlik_mm']:.2f}"
        f" kz2={kz2:.2f} grid={nx}x{ny} eff_m={eff_m} z_c={z_c}")

    # ---- bolge alanlari (hucre) ----------------------------------------
    # kanopi RAW fp (margin=0: delikler dilation'la kapanmasin — v17 dersi)
    rot_k = duz_rot_matrisleri(mesh0)[0]
    vk = voxelize_part(p0.name, mesh0, PT, rot_matrices=[np.asarray(rot_k)],
                       method="slice", margin=0, z_dilate=0)
    fp_k = vk.orientations[0].grid.any(axis=2)
    bbox_c = int(fp_k.shape[0]) * int(fp_k.shape[1])
    malzeme_c = int(fp_k.sum())
    delik_c = bbox_c - malzeme_c
    plaka_c = nx * ny
    ngm = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, eg.PLATE_STD[0],
                                       eg.PLATE_STD[1], PT)
    nogo_c = int(np.asarray(ngm, dtype=bool)[:nx, :ny].sum()) \
        if ngm is not None else 0
    a_full = (plaka_c - nogo_c - bbox_c) + delik_c
    a_alt = malzeme_c
    a_ust = malzeme_c
    mm2 = PT * PT
    log(f"[ALAN] plaka={plaka_c} nogo={nogo_c} kanopi-bbox={bbox_c}"
        f" (malzeme={malzeme_c} delik={delik_c})")
    log(f"[ALAN] R_full={a_full}h ({a_full*mm2/100:.0f}cm2)"
        f" R_alt={a_alt}h ({a_alt*mm2/100:.0f}cm2)"
        f" R_ust={a_ust}h (T>kz2 ise)")

    # ---- tip menusu ----------------------------------------------------
    menu = _tip_menusu(inst, PT, eff_m, z_c, p0.name, nx, ny)
    n_kopya = sum(v["qty"] for v in menu.values())
    log(f"[MENU] {len(menu)} tip / {n_kopya} kopya (kanopi haric)")
    for ad, v in sorted(menu.items()):
        s = " | ".join(f"gh={q['gh_v']*PT:.1f} fp={q['fp']*mm2/100:.0f}cm2"
                       for q in v["pozlar"])
        log(f"[MENU] {ad:26s} x{v['qty']:<3d} {s}")

    # ---- T taramasi ----------------------------------------------------
    kz1_v = int(round(KZ1 / PT))
    kz2_v = int(round(kz2 / PT))
    tarama = []
    for t_mm in T_LISTE:
        t_v = int(round(t_mm / PT))
        ust_v = t_v - kz2_v
        kopyalar = []
        sigmayan_tip = []
        for ad, v in menu.items():
            ops = _kopya_opsiyonlari(v["pozlar"], t_v, kz1_v, ust_v)
            if not ops:
                sigmayan_tip.append(ad)
            kopyalar += [(ad, ops)] * v["qty"]
        satir = {"t_mm": t_mm, "sigmayan_tip": sigmayan_tip, "eta": {}}
        for eta in ETALAR:
            kap = {"full": a_full * eta, "alt": a_alt * eta,
                   "ust": (a_ust * eta if ust_v > 0 else 0.0)}
            yerlesen, tasan, kullanilan = _atama(kopyalar, kap)
            fizibil = (len(tasan) == 0)
            satir["eta"][str(eta)] = {
                "fizibil": fizibil, "yerlesen": yerlesen,
                "tasan": len(tasan),
                "kullanim": {b: (round(kullanilan[b] / kap[b], 2)
                                 if kap[b] > 0 else None)
                             for b in kap}}
        tarama.append(satir)
        e = satir["eta"]
        log(f"[T={t_mm:6.1f}] "
            + "  ".join(
                f"eta={k}: {'FIZIBIL' if e[k]['fizibil'] else 'TASMA'}"
                f"({e[k]['yerlesen']}/{n_kopya}"
                f" kull={e[k]['kullanim']})" for k in e)
            + (f"  SIGMAYAN-TIP={sigmayan_tip}" if sigmayan_tip else ""))

    # ---- hukum ---------------------------------------------------------
    hukum = {}
    for eta in ETALAR:
        t_min = next((s["t_mm"] for s in tarama
                      if s["eta"][str(eta)]["fizibil"]), None)
        hukum[str(eta)] = t_min
        log(f"[HUKUM] eta={eta}: alan-aritmetigi T_min ="
            f" {t_min if t_min is not None else 'YOK (129.6 dahi tasma)'}")
    log("[OKUMA] T_min <= 115 civari (gercekci eta 0.7-0.8) ise 110-bandi"
        " ALAN olarak acik -> global yeniden-istif gelistirmesi DEGER;"
        " T_min ~127 ise plato yapisaldir.")

    doc = {"olcum": "k62_v27_alan_butcesi",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-set kosusuz teshis (alt-sinir aritmetigi); "
                    "kazanc ilani degil, gelistirme-karari verisi"),
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "pitch": PT, "kz1": KZ1,
                        "kz2": round(kz2, 2)},
           "alanlar_hucre": {"plaka": plaka_c, "nogo": nogo_c,
                             "kanopi_bbox": bbox_c, "malzeme": malzeme_c,
                             "delik": delik_c, "r_full": a_full,
                             "r_alt": a_alt, "r_ust": a_ust},
           "menu": {ad: v for ad, v in menu.items()},
           "tarama": tarama, "hukum_t_min": hukum, "referanslar": REF}
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
