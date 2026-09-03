# -*- coding: utf-8 -*-
"""k59_dagilim_smoke.py — K-59: DAGILIMSAL dogrulama (smoke), A11/B1 geregi.

Eren 2026-07-19: "yeni algoritmayi baska BIR veride kosuyorsun — bu mu ML?"
HAKLI: tek-set + bir-set-daha != genelleme. B1 sozlesmesi dev verisine
SENTETIK JENERATOR AILELERINI dahil eder — bu harness K-56 zincirinin
karar-yuzeyini DAGILIM uzerinde olcer (4 sabit nokta degil):

  1. TETIK DOGRULUGU: plaka-baskin sentetik ailede (dev plaka 300-334 x
     280-325 x 20-50 + kucuk parcalar) tilt-zorunlu kapinin ateslemesi,
     bagimsiz geometrik beklentiyle (dikdortgen testi) karsilastirilir —
     sinirin IKI yanindan ornekler (fp_y ~290 esigi).
  2. KAZANC DAGILIMI: tetik atesleyen orneklerde A (kablo kapali,
     extra_rot_overrides={}) vs B (uretim kablosu otomatik) — yukseklik
     delta dagilimi (win/tie/loss; tek-ornek basari degil).
  3. YANLIS-POZITIF: kontrol ailelerinde (random_boxes, long_rods) tetik
     ASLA atesmemeli; nokta-kontrol A==B bit-ozdes.

SMOKE kapsami: hiz icin yukseklik+n_placed proxy'si (clearance/kilit tam
olcumu TAM sweep'te — A2 geregi buradaki delta goreli sinyaldir, "legal
kazanc" ilani DEGILDIR). Sozlesme: PLATE_STD 335 + NOGO_STD (HARD — mevcut
uretim). Tam sweep sakin-makine/super-bilgisayar isi.
Kosum: python -m scripts.detach_run k59_dagilim_smoke    (D:\\ie488'den)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.eval_gate as eg
from src.nesting3d.instances.format import ContainerSpec, PartSpec, NestingInstance
from src.nesting3d.instances.synthetic import long_rods, random_boxes

LOG = Path(__file__).parent / "k59_dagilim_smoke.log"
OUT = _ROOT / "results" / "k59_dagilim_smoke.json"
SEED_SOLVE = 42
CNT = ContainerSpec(width_mm=335.0, depth_mm=335.0, height_mm=None)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _plaka_baskin(seed):
    """Dev-plaka + kucuk parcalar (plan1-SINIFI, plan1 DEGIL — A11 tetik
    genellemesi). Plaka boyutu tetik sinirinin iki yanina dusecek bantta."""
    rng = random.Random(seed)
    pw = rng.uniform(300.0, 334.0)
    pd = rng.uniform(280.0, 325.0)
    ph = rng.uniform(20.0, 50.0)
    parts = [PartSpec(id="plaka", name="plaka", qty=1, source="box",
                      width_mm=pw, depth_mm=pd, height_mm=ph)]
    for i in range(rng.randint(8, 14)):
        parts.append(PartSpec(
            id=f"k{i}", name=f"k{i}", qty=1, source="box",
            width_mm=rng.uniform(15, 60), depth_mm=rng.uniform(15, 60),
            height_mm=rng.uniform(8, 40)))
    return NestingInstance(container=CNT, parts=parts), (pw, pd, ph)


def _tetik_beklenti(pw, pd):
    """Bagimsiz geometrik beklenti: dev plakanin HICBIR duz pozu no-go'lu
    plakaya sigmiyor mu? (K-56 kapisinin dikdortgen mantigi, bagimsiz
    yeniden turetim — kapinin kendisinden KOPYALANMADI ki test anlamli
    olsun). Duz pozlar: (pw,pd) ve (pd,pw)."""
    W, D = eg.PLATE_STD
    (x1, y1), (x2, y2) = eg.NOGO_STD
    def sigar(fx, fy):
        solda = fx <= x1 and fy <= D
        sagda = fx <= (W - x2) and fy <= D
        otede = fy <= (D - y2) and fx <= W
        genel = fx <= W and fy <= D
        return genel and (solda or sagda or otede)
    return not (sigar(pw, pd) or sigar(pd, pw))


def _coz(inst, ad, bastir):
    """Cozum kolu; EXCEPTION = veri (mevcut uretim bu instance'ta cokuyor
    demektir — plan1'in tarihsel k51d istisnasinin dagilimsal karsiligi)."""
    kw = {"extra_rot_overrides": {}} if bastir else {}
    t0 = time.perf_counter()
    try:
        r, _tel = eg._run_champion(ad, inst, SEED_SOLVE, **kw)
        return {"h": float(r.height_mm), "n": int(r.n_placed),
                "s": round(time.perf_counter() - t0, 1)}
    except Exception as e:
        return {"exception": f"{type(e).__name__}: {str(e)[:120]}",
                "s": round(time.perf_counter() - t0, 1)}


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-59 DAGILIMSAL SMOKE (A11/B1: sentetik aileler; sozlesme 335+HARD nogo)")
    satirlar = []

    # ---- 1+2: plaka-baskin aile (tetik + kazanc dagilimi) ----
    log("[AILE plaka-baskin] 8 ornek:")
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    for seed in range(1, 9):
        inst, (pw, pd, ph) = _plaka_baskin(seed)
        bekle = _tetik_beklenti(pw, pd)
        dec = predict_nfv_benefit(inst, family_routing=True, mode_model=_mm,
                                  rot_sokum=True, no_go_bounds=eg.NOGO_STD)
        tetik = bool(getattr(dec, "tilt_parca", None))
        dogru = tetik == bekle
        row = {"aile": "plaka_baskin", "seed": seed,
               "plaka": [round(pw, 1), round(pd, 1), round(ph, 1)],
               "tetik_beklenen": bekle, "tetik": tetik, "tetik_dogru": dogru}
        log(f"  s{seed}: plaka={pw:.0f}x{pd:.0f}x{ph:.0f}"
            f" bekle={bekle} tetik={tetik} {'OK' if dogru else 'YANLIS!'}")
        if tetik:
            a = _coz(inst, f"pb{seed}A", bastir=True)
            b = _coz(inst, f"pb{seed}B", bastir=False)
            row.update({"a": a, "b": b})
            if "h" in a and "h" in b:
                row["delta"] = round(b["h"] - a["h"], 2)
                log(f"      A(kablosuz)={a['h']:.1f} ({a['s']}s)"
                    f"  B(kablo)={b['h']:.1f} ({b['s']}s)"
                    f"  delta={b['h'] - a['h']:+.1f}mm"
                    f"  nA={a['n']} nB={b['n']}")
            elif "h" in b:
                row["sonuc"] = "A_COKER_B_COZER"
                log(f"      A EXCEPTION ({a['exception'][:70]})"
                    f"  B(kablo)={b['h']:.1f} COZUYOR — kablo=cokme-onleyici")
            elif "h" in a:
                row["sonuc"] = "B_COKER"
                log(f"      B EXCEPTION ({b['exception'][:70]})"
                    f"  A={a['h']:.1f} — ALARM: kablo bozuyor!")
            else:
                row["sonuc"] = "IKISI_COKER"
                log(f"      IKISI DE EXCEPTION (A: {a['exception'][:50]})")
        satirlar.append(row)

    # ---- 3: kontrol aileleri (yanlis-pozitif + nokta bit-ozdeslik) ----
    log("[KONTROL] random_boxes + long_rods 3'er ornek:")
    for gen, gad in [(random_boxes, "random_boxes"), (long_rods, "long_rods")]:
        for seed in (1, 2, 3):
            inst = gen(n_parts=10, container=CNT, seed=seed)
            dec = predict_nfv_benefit(inst, family_routing=True,
                                      mode_model=_mm, rot_sokum=True,
                                      no_go_bounds=eg.NOGO_STD)
            tetik = bool(getattr(dec, "tilt_parca", None))
            row = {"aile": gad, "seed": seed, "tetik": tetik,
                   "tetik_dogru": not tetik}
            log(f"  {gad} s{seed}: tetik={tetik}"
                f" {'OK' if not tetik else 'YANLIS-POZITIF!'}")
            if seed == 1 and getattr(dec, "mode", "heightmap") != "nfv":
                a = _coz(inst, f"{gad}A", bastir=True)
                b = _coz(inst, f"{gad}B", bastir=False)
                ozdes = ("h" in a and "h" in b
                         and a["h"] == b["h"] and a["n"] == b["n"])
                row.update({"a": a, "b": b, "bit_ozdes": ozdes})
                log(f"      nokta-kontrol A==B: {'OZDES' if ozdes else 'FARK!'}"
                    f" (A={a.get('h', 'EXC')} B={b.get('h', 'EXC')})")
            satirlar.append(row)

    # ---- ozet ----
    pb = [r for r in satirlar if r["aile"] == "plaka_baskin"]
    ab = [r for r in pb if "delta" in r]
    dogru_n = sum(1 for r in satirlar if r.get("tetik_dogru"))
    win = sum(1 for r in ab if r["delta"] < -0.5)
    tie = sum(1 for r in ab if abs(r["delta"]) <= 0.5)
    loss = sum(1 for r in ab if r["delta"] > 0.5)
    a_coker = sum(1 for r in pb if r.get("sonuc") == "A_COKER_B_COZER")
    b_coker = sum(1 for r in pb if r.get("sonuc") in ("B_COKER",
                                                      "IKISI_COKER"))
    ozet = {"tetik_dogrulugu": f"{dogru_n}/{len(satirlar)}",
            "ab_ornek": len(ab), "win": win, "tie": tie, "loss": loss,
            "a_coker_b_cozer": a_coker, "b_coker": b_coker,
            "delta_ort": round(sum(r["delta"] for r in ab) / len(ab), 2)
            if ab else None,
            "delta_min": min((r["delta"] for r in ab), default=None),
            "delta_max": max((r["delta"] for r in ab), default=None)}
    log(f"OZET: tetik dogrulugu {ozet['tetik_dogrulugu']}"
        f" | A/B {len(ab)} ornek: win={win} tie={tie} loss={loss}"
        f" | A-coker-B-cozer={a_coker} B-coker={b_coker}"
        f" | delta ort={ozet['delta_ort']} min={ozet['delta_min']}"
        f" max={ozet['delta_max']}")
    OUT.write_text(json.dumps({"satirlar": satirlar, "ozet": ozet,
                               "sure_dk": round((time.perf_counter() - t0) / 60,
                                                1)},
                              indent=2, default=str), encoding="utf-8")
    log(f"JSON: {OUT}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
