# -*- coding: utf-8 -*-
"""k62_dagilim_smoke.py — K-62 kanopi zinciri DAGILIMSAL dogrulama (smoke).

A11 GO-ilani sartlarindan "dagilimsal tetik-dogrulugu" adimi (k59 deseni):

  1. TETIK DOGRULUGU: holey_frames ailesinde (kanopi-SINIFI, plan1 DEGIL)
     kanopi_adayi() ateslemesi, BAGIMSIZ analitik beklentiyle karsilastirilir
     (meta.tasarim'dan yeniden turetim — tetik kodundan KOPYALANMADI).
     Sinir bandi (|doluluk-0.6|<0.03, raster kalinlasmasi) ayri raporlanir.
  2. KAZANC DAGILIMI: atesleyen orneklerde A (duz solve) vs B (zincir,
     ref paylasimli) yukseklik delta dagilimi (win/tie/loss; B2 gurultu
     bandi +-%0.5). Zincir TEK-TARAFLI oldugundan loss > 0 = KOD HATASI.
  3. YANLIS-POZITIF: (a) kati-plaka STL ailesi (alan buyuk, doluluk ~1.0)
     — geometrik elenme; (b) random_boxes / long_rods (stl'siz) — yapisal
     elenme. Nokta kontrol: zincir tel.tetik=False + yalniz ref adimi.

SMOKE kapsami: yukseklik+n_placed proxy (A2 tam legalite kapi/uretim
sarmalinda). Sozlesme: PLATE 335 + NOGO_SOFT (uretim 2026-08-04).
Kosum: python -m scripts.detach_run k62_dagilim_smoke   (D:\\ie488'den)
Env: K62DS_N_TETIK (24) - K62DS_N_AB (8). SAF ASCII stdout (cp1254).
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

import scripts.eval_gate as eg
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.synthetic import (
    _cerceve_mesh,
    holey_frames,
    long_rods,
    random_boxes,
)
from src.nesting3d.kanopi_zincir import kanopi_adayi, kanopi_zinciri_coz
from src.nesting3d.nfv_solve import solve_nfv

LOG = Path(__file__).parent / "k62_dagilim_smoke.log"
OUT = _ROOT / "results" / "k62_dagilim_smoke.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
STL_DIR = Path(r"D:\ie488\tmp\holey_smoke")
SEED_SOLVE = 42
CLEAR_MM = 2.0
W, D = 335.0, 335.0
CNT = ContainerSpec(width_mm=W, depth_mm=D, height_mm=None)
N_TETIK = int(os.environ.get("K62DS_N_TETIK", "24"))
N_AB = int(os.environ.get("K62DS_N_AB", "8"))
# A/B ornekleri YOGUN kurulur (ayni cerceve tasarimi — rng sirasi cerceveyi
# parcalardan ONCE ceker; parca sayisi artinca tetik tarafi degismez).
# Gerekce (ilk kosu 2026-08-05): seyrek ornekte (10-12 parca) yukseklik
# baskisi yok -> ref = en yuksek tek parca, kazanc olculemez (7/7 tie).
AB_TOWERS = int(os.environ.get("K62DS_AB_TOWERS", "8"))
AB_FILLERS = int(os.environ.get("K62DS_AB_FILLERS", "40"))
SINIR_BANDI = 0.03      # dolulukta raster kalinlasma payi
GURULTU = 0.005         # B2 +-%0.5


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _beklenti(meta) -> bool:
    """BAGIMSIZ analitik tetik beklentisi (tasarim parametrelerinden;
    kanopi_adayi kodundan kopyalanmadi — dogruluk kiyasi anlamli olsun)."""
    ta = meta["tasarim"]
    if ta["alan_oran_analitik"] < 0.35:
        return False
    if ta["doluluk_analitik"] >= 0.6:
        return False
    fw, fd = ta["fw"], ta["fd"]
    if (D - fd) >= 33.0:          # no-go'nun ustunden dy ile kacis
        return True
    if not ta["centik"]:
        return False
    dy_max = D - fd
    for (x1, y1, x2, y2) in ta["delikler"]:
        if y1 > 1e-6:
            continue              # yalniz kenar centigi (y=0)
        if (x2 - x1) < 33.0 or (y2 - y1) < 33.0 - dy_max:
            continue
        # dx araligi bos degil mi: [max(0,185.5-x2), min(W-fw, 152.5-x1)]
        if max(0.0, 185.5 - x2) <= min(W - fw, 152.5 - x1):
            return True
    return False


def _sinirda(meta) -> bool:
    ta = meta["tasarim"]
    return abs(ta["doluluk_analitik"] - 0.6) < SINIR_BANDI


def _kati_plaka_inst(seed: int) -> NestingInstance:
    """Kontrol: kati (deliksiz) buyuk plaka STL + kutular — alan_oran
    buyuk ama doluluk ~1.0 -> tetik GEOMETRIK olarak elenmeli."""
    import random as _r
    rng = _r.Random(seed)
    fw = rng.uniform(220.0, 320.0)
    fd = rng.uniform(220.0, 300.0)
    mesh = _cerceve_mesh(fw, fd, rng.uniform(4.0, 10.0), [])
    yol = STL_DIR / f"kati_plaka_s{seed}.stl"
    mesh.export(yol)
    e = mesh.extents
    parts = [PartSpec(id="plate", name="plate", qty=1, source="stl",
                      stl_path=str(yol),
                      width_mm=round(float(e[0]), 3),
                      depth_mm=round(float(e[1]), 3),
                      height_mm=round(float(e[2]), 3))]
    for i in range(rng.randint(4, 8)):
        parts.append(PartSpec(
            id=f"k{i}", name=f"k{i}", qty=1, source="box",
            width_mm=rng.uniform(15, 55), depth_mm=rng.uniform(15, 55),
            height_mm=rng.uniform(8, 40)))
    return NestingInstance(container=CNT, parts=parts,
                           meta={"family": "kati_plaka", "seed": seed})


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 DAGILIMSAL SMOKE: tetik-dogrulugu + A/B kazanc + yanlis-pozitif")
    nogo = eg.NOGO_STD
    log(f"sozlesme: plate=({W}, {D}) nogo={nogo} clearance={CLEAR_MM}"
        f" seed={SEED_SOLVE}  n_tetik={N_TETIK} n_ab={N_AB}")
    STL_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 1) TETIK DOGRULUGU ------------------------------------------
    log("[1] tetik dogrulugu (holey_frames)")
    tetik_kayitlari = []
    uyum = uyumsuz = sinir = 0
    atesleyenler = []
    for s in range(N_TETIK):
        inst = holey_frames(stl_dir=STL_DIR, seed=s)
        bek = _beklenti(inst.meta)
        aday = kanopi_adayi(inst, W, D, nogo)
        ates = aday is not None
        ta = inst.meta["tasarim"]
        kayit = {"seed": s, "mod": inst.meta["mod"],
                 "alan_oran": ta["alan_oran_analitik"],
                 "doluluk": ta["doluluk_analitik"], "centik": ta["centik"],
                 "beklenti": bek, "ates": ates, "sinirda": _sinirda(inst.meta)}
        tetik_kayitlari.append(kayit)
        durum = "SINIR" if kayit["sinirda"] else (
            "UYUM" if bek == ates else "UYUMSUZ")
        if kayit["sinirda"]:
            sinir += 1
        elif bek == ates:
            uyum += 1
        else:
            uyumsuz += 1
        log(f"  s={s:02d} {inst.meta['mod']:5s} alan={ta['alan_oran_analitik']:.2f}"
            f" dol={ta['doluluk_analitik']:.2f} centik={int(ta['centik'])}"
            f" beklenti={int(bek)} ates={int(ates)} -> {durum}")
        if ates:
            atesleyenler.append(s)
    log(f"[1] SONUC: uyum={uyum} uyumsuz={uyumsuz} sinir-bandi={sinir}"
        f" atesleyen={len(atesleyenler)}/{N_TETIK}")

    # ---- 2) KAZANC DAGILIMI (A/B) ------------------------------------
    log(f"[2] A/B kazanc dagilimi (ilk {N_AB} atesleyen;"
        f" YOGUN varyant towers={AB_TOWERS} fillers={AB_FILLERS})")
    ab_kayitlari = []
    win = tie = loss = 0
    for s in atesleyenler[:N_AB]:
        inst = holey_frames(stl_dir=STL_DIR, seed=s,
                            n_towers=AB_TOWERS, n_fillers=AB_FILLERS)
        n_total = sum(int(p.qty) for p in inst.parts)
        tA = time.perf_counter()
        rA = solve_nfv(inst, plate_w_mm=W, plate_d_mm=D, fine_pitch=None,
                       seed=SEED_SOLVE, quality="fast",
                       clearance_mm=CLEAR_MM, no_go_bounds=nogo)
        hA = float(rA.height_mm)
        rB, tel = kanopi_zinciri_coz(
            inst, plate_w_mm=W, plate_d_mm=D, no_go_bounds=nogo,
            clearance_mm=CLEAR_MM, seed=SEED_SOLVE, ref_res=rA)
        hB = float(rB.height_mm)
        sure = time.perf_counter() - tA
        delta = hB - hA
        oran = delta / hA if hA > 0 else 0.0
        if oran < -GURULTU:
            karar = "WIN"
            win += 1
        elif oran > GURULTU:
            karar = "LOSS"       # tek-tarafli sozlesmede OLMAMALI
            loss += 1
        else:
            karar = "TIE"
            tie += 1
        ab_kayitlari.append({
            "seed": s, "hA": hA, "hB": hB, "delta": round(delta, 2),
            "nA": int(rA.n_placed), "nB": int(rB.n_placed),
            "n_total": n_total, "tetik_zincir": tel["tetik"],
            "etiket": tel.get("etiket"), "karar": karar,
            "sure_s": round(sure, 1)})
        log(f"  s={s:02d} A={hA:.2f} B={hB:.2f} delta={delta:+.2f}"
            f" ({100*oran:+.1f}%) {karar}  n={int(rB.n_placed)}/{n_total}"
            f" etiket={tel.get('etiket')} sure={sure/60:.1f}dk")
        del rA, rB
        gc.collect()
    log(f"[2] SONUC: win={win} tie={tie} loss={loss}")

    # ---- 3) YANLIS-POZITIF -------------------------------------------
    log("[3] yanlis-pozitif kontrolleri")
    yp_kayitlari = []
    yp_ihlal = 0
    kontroller = ([("kati_plaka", _kati_plaka_inst(100 + i)) for i in range(4)]
                  + [("random_boxes", random_boxes(n_parts=8, container=CNT,
                                                   seed=200 + i))
                     for i in range(2)]
                  + [("long_rods", long_rods(n_parts=6, container=CNT,
                                             seed=300 + i))
                     for i in range(2)])
    for ad, inst in kontroller:
        aday = kanopi_adayi(inst, W, D, nogo)
        ates = aday is not None
        if ates:
            yp_ihlal += 1
        yp_kayitlari.append({"aile": ad, "seed": inst.meta.get("seed"),
                             "ates": ates})
        log(f"  {ad} s={inst.meta.get('seed')}: ates={int(ates)}"
            f"{'  <<< IHLAL' if ates else ''}")
    # nokta kontrol: tetiksiz ailede zincir ref'i AYNEN dondurur
    inst_nk = _kati_plaka_inst(199)
    res_nk, tel_nk = kanopi_zinciri_coz(
        inst_nk, plate_w_mm=W, plate_d_mm=D, no_go_bounds=nogo,
        clearance_mm=CLEAR_MM, seed=SEED_SOLVE)
    nk_ok = (tel_nk["tetik"] is False and len(tel_nk["adimlar"]) == 1)
    log(f"  nokta-kontrol (kati_plaka s=199): tetik={tel_nk['tetik']}"
        f" adim={len(tel_nk['adimlar'])} -> {'OK' if nk_ok else 'IHLAL'}")
    if not nk_ok:
        yp_ihlal += 1
    log(f"[3] SONUC: ihlal={yp_ihlal}")

    ozet = {
        "tetik": {"uyum": uyum, "uyumsuz": uyumsuz, "sinir": sinir,
                  "atesleyen": len(atesleyenler), "n": N_TETIK},
        "ab": {"win": win, "tie": tie, "loss": loss},
        "yanlis_pozitif_ihlal": yp_ihlal,
    }
    doc = {
        "olcum": "k62_dagilim_smoke",
        "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "serh": ("SMOKE: yukseklik proxy; A2 tam legalite kapi/uretim "
                 "sarmalinda. Tetik-dogrulugu bagimsiz analitik beklentiyle."),
        "sozlesme": {"plate": [W, D], "nogo": nogo, "clearance_mm": CLEAR_MM,
                     "seed": SEED_SOLVE},
        "ozet": ozet,
        "tetik_kayitlari": tetik_kayitlari,
        "ab_kayitlari": ab_kayitlari,
        "yanlis_pozitif": yp_kayitlari,
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

    log(f"OZET: {json.dumps(ozet, ensure_ascii=True)}")
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
