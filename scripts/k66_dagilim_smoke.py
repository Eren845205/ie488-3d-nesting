# -*- coding: utf-8 -*-
"""k66_dagilim_smoke.py — K-66-d kafes dekodunun DAGILIMSAL kapisi (k59 deseni).

Uc olcum (RUNBOOK P-3.5-6; MK-03 tek-set serhinin kaldirilma adimi):
  1. TETIK DOGRULUGU: tetikli aile (mass_plate_rod_mix) tetiklenmeli;
     kontrol aileleri (random_boxes, thin_plates) TETIKLENMEMELI
     (bagimsiz beklenti: tekrar-kitle payi + asan-parca varligi).
  2. A/B KAZANC DAGILIMI: seed-basina kafes-dekod vs pinsiz-NFV (ayni
     pitch/seed/kalite), YALNIZ A2-legal sonuclar kiyaslanir (5-yon).
  3. YANLIS-POZITIF: tetiklenen ornekte kafes belirgin KOTU (delta>+%2)
     ise yanlis-pozitif adayi.

Kosum: D:\\ie488'den python -m scripts.detach_run k66_dagilim_smoke
Env: K66D_SEEDS (12) / K66D_QTY (120) / K66D_PITCH (2.4) / K66D_QUALITY (fast)
SAF ASCII stdout. A11: dagilimsal kanit adimi — kapi karari icin veri;
uretim kablosu karari Eren'de.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.format import ContainerSpec  # noqa: E402
from scripts.k66_d_kafes_dekod import (  # noqa: E402
    asan_mi, eksen_rot_bul, kafes_plani, pin_listesi)

LOG = Path(__file__).parent / "k66_dagilim_smoke.log"
# K66D_OUT: cikti yolunu degistirir (v2-A/B gibi yan kosular resmi kapi
# kanitinin ustune YAZMASIN diye; default eski yol birebir).
OUT = Path(os.environ.get("K66D_OUT") or
           (_ROOT / "results" / "k66_dagilim_smoke.json"))
PLATE = 335.0
CLEAR = 2.0
KITLE_PAY = 0.5


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def _siniflandir(inst):
    """k66_d main() ile ayni tetik mantigi (tekrar-kitle + asan)."""
    modeller = {}
    for p in inst.parts:
        mm = modeller.setdefault(p.name, {"qty": 0, "dims": (
            float(p.width_mm), float(p.depth_mm), float(p.height_mm))})
        mm["qty"] += int(p.qty)
    n_total = sum(m["qty"] for m in modeller.values())
    asanlar = {ad: m for ad, m in modeller.items()
               if asan_mi(m["dims"], PLATE, PLATE, CLEAR)}
    esik = max(20, int(0.05 * n_total))
    tekrarlar = {ad: m for ad, m in modeller.items()
                 if m["qty"] >= esik and ad not in asanlar}
    tetik = (bool(tekrarlar) and bool(asanlar)
             and sum(m["qty"] for m in tekrarlar.values())
             >= KITLE_PAY * n_total)
    return modeller, asanlar, tekrarlar, n_total, tetik


def _bagimsiz_beklenti(inst):
    """Tetik kodundan BAGIMSIZ beklenti: herhangi parca iki buyuk boyutla
    plakaya sigmiyor MU + en yuksek adetli sigan model toplam adedin
    yarisini gecıyor MU (dogrudan parca listesinden)."""
    from collections import Counter
    asan_var = False
    sayim = Counter()
    for p in inst.parts:
        d = sorted((float(p.width_mm), float(p.depth_mm), float(p.height_mm)))
        if d[1] + CLEAR > PLATE or d[2] + CLEAR > PLATE:
            asan_var = True
        else:
            sayim[p.name] += int(p.qty)
    n_total = sum(int(p.qty) for p in inst.parts)
    return asan_var and sum(sayim.values()) >= 0.5 * n_total


def _kafes_coz(inst, pitch, quality, seed):
    """k66_d main() cozum yolunun harness kopyasi (deney; kablo degil)."""
    import trimesh
    from src.nesting3d.nfv_solve import solve_nfv
    modeller, asanlar, tekrarlar, n_total, tetik = _siniflandir(inst)
    if not tetik:
        return None
    kitle_ad = max(tekrarlar, key=lambda a: tekrarlar[a]["qty"])
    n_rod = sum(m["qty"] for m in asanlar.values())
    slot = tuple(max(sorted(m["dims"])[i] for m in asanlar.values())
                 for i in range(3))
    plan = kafes_plani(slot, n_rod, modeller[kitle_ad]["dims"],
                       modeller[kitle_ad]["qty"], PLATE, PLATE, CLEAR,
                       pitch=pitch,
                       skor_v2=os.environ.get("K66D_PLAN_V2") == "1")
    if not plan.get("uygun"):
        return {"hata": f"plan kurulamadi: {plan.get('sebep')}"}
    ornek = {}
    for p in inst.parts:
        if p.name in (set(asanlar) | {kitle_ad}) and p.name not in ornek:
            if getattr(p, "stl_path", None):
                ornek[p.name] = tuple(
                    trimesh.load(str(p.stl_path), force="mesh").extents)
            else:
                ornek[p.name] = (float(p.width_mm), float(p.depth_mm),
                                 float(p.height_mm))
    rod = plan["rod"]
    dar_x = abs(rod["w"] - slot[0]) < abs(rod["w"] - slot[1])
    rod_pinler = []
    for ad in sorted(asanlar):
        m0, m1, m2 = sorted(asanlar[ad]["dims"])
        hedef = (m0, m1, m2) if dar_x else (m1, m0, m2)
        rrot = eksen_rot_bul(ornek[ad], hedef)
        if rrot is None:
            return {"hata": f"rot bulunamadi: {ad}"}
        rod_pinler.extend([(ad, rrot)] * asanlar[ad]["qty"])
    kitle_rot = eksen_rot_bul(ornek[kitle_ad], tuple(plan["cell"]))
    if kitle_rot is None:
        return {"hata": "rot bulunamadi: kitle"}
    pins = pin_listesi(plan, rod_pinler, kitle_ad, kitle_rot, CLEAR)
    res = solve_nfv(inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
                    fine_pitch=pitch, seed=seed, quality=quality,
                    clearance_mm=CLEAR, pinned_placements=pins, pin_3d=True)
    return {"res": res, "n_total": n_total}


def _pinsiz_coz(inst, pitch, quality, seed):
    from src.nesting3d.nfv_solve import solve_nfv
    n_total = sum(int(p.qty) for p in inst.parts)
    res = solve_nfv(inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
                    fine_pitch=pitch, seed=seed, quality=quality,
                    clearance_mm=CLEAR)
    return {"res": res, "n_total": n_total}


def _a2(res_d):
    from scripts.k62_v17_ripup import a2_olc
    a2 = a2_olc(res_d["res"], res_d["n_total"])
    return {"h": float(res_d["res"].height_mm),
            "n": int(res_d["res"].n_placed), "n_total": res_d["n_total"],
            "clearance": a2["min_clearance_mm"],
            "kilit5": a2["kilit_5yon"], "legal": bool(a2["legal"])}


def main() -> int:
    seeds = int(os.environ.get("K66D_SEEDS", "12"))
    qty = int(os.environ.get("K66D_QTY", "120"))
    pitch = float(os.environ.get("K66D_PITCH", "2.4"))
    quality = os.environ.get("K66D_QUALITY", "fast")
    log("=" * 70)
    log("K-66-d DAGILIMSAL SMOKE (k59 deseni) — tetik + A/B + yanlis-pozitif")
    log(f"seeds={seeds} qty={qty} pitch={pitch} quality={quality} "
        f"plate={PLATE} clear={CLEAR}")
    log("=" * 70)
    t0 = time.time()
    from src.nesting3d.instances.synthetic import (
        mass_plate_rod_mix, random_boxes, thin_plates)
    cnt = ContainerSpec(width_mm=PLATE, depth_mm=PLATE, height_mm=None)

    # 1) TETIK DOGRULUGU
    hatalar = []
    dogru = 0
    for s in range(seeds):
        inst = mass_plate_rod_mix(container=cnt, seed=s, qty_per_plate=qty)
        _, _, _, _, tetik = _siniflandir(inst)
        ok = tetik and _bagimsiz_beklenti(inst)
        dogru += int(ok)
        if not ok:
            hatalar.append(f"tetikli-aile seed={s} tetik={tetik}")
    n_kontrol = 0
    kontrol_dogru = 0
    for gen, ad in ((random_boxes, "random_boxes"), (thin_plates, "thin_plates")):
        for s in range(min(seeds, 6)):
            inst = (gen(n_parts=16, container=cnt, seed=s) if ad == "random_boxes"
                    else gen(n_parts=20, container=cnt, seed=s))
            _, _, _, _, tetik = _siniflandir(inst)
            n_kontrol += 1
            kontrol_dogru += int(not tetik)
            if tetik:
                hatalar.append(f"kontrol {ad} seed={s} YANLIS TETIK")
    log(f"[tetik] tetikli-aile {dogru}/{seeds} | kontrol "
        f"{kontrol_dogru}/{n_kontrol}")

    # 2) A/B kazanc + 3) yanlis-pozitif
    win = tie = loss = 0
    ab = []
    for s in range(seeds):
        inst = mass_plate_rod_mix(container=cnt, seed=s, qty_per_plate=qty)
        try:
            k = _kafes_coz(inst, pitch, quality, 42)
            if k is None or "hata" in (k or {}):
                hatalar.append(f"AB seed={s} kafes: {(k or {}).get('hata', 'tetik-yok')}")
                continue
            ka = _a2(k)
            p = _pinsiz_coz(inst, pitch, quality, 42)
            pa = _a2(p)
        except Exception as exc:
            hatalar.append(f"AB seed={s} kosu hatasi: {exc}")
            log(f"  seed={s}: KOSU HATASI {exc}")
            continue
        satir = {"seed": s, "kafes": ka, "pinsiz": pa}
        if not ka["legal"] or not pa["legal"]:
            satir["sonuc"] = ("KAFES-INVALID" if not ka["legal"]
                              else "PINSIZ-INVALID")
            if not ka["legal"]:
                loss += 1  # kafes legal uretemiyorsa yanlis-pozitif adayi
        else:
            delta_pct = 100.0 * (ka["h"] - pa["h"]) / pa["h"]
            satir["delta_pct"] = round(delta_pct, 2)
            if delta_pct < -0.5:
                satir["sonuc"] = "WIN"; win += 1
            elif delta_pct > 2.0:
                satir["sonuc"] = "LOSS"; loss += 1
            else:
                satir["sonuc"] = "TIE"; tie += 1
        ab.append(satir)
        log(f"  seed={s}: kafes={ka['h']:7.1f}({'L' if ka['legal'] else 'X'})"
            f"  pinsiz={pa['h']:7.1f}({'L' if pa['legal'] else 'X'})"
            f"  {satir.get('delta_pct', '')} {satir['sonuc']}")

    log("")
    log(f"A/B: {win}W / {tie}T / {loss}L  (LOSS = yanlis-pozitif adayi)")
    basari = (dogru == seeds and kontrol_dogru == n_kontrol
              and loss == 0 and not hatalar)
    doc = {"tarih": str(date.today()),
           "ayarlar": {"seeds": seeds, "qty": qty, "pitch": pitch,
                       "quality": quality},
           "tetik": {"tetikli": [dogru, seeds],
                     "kontrol": [kontrol_dogru, n_kontrol]},
           "ab": ab, "wtl": [win, tie, loss], "hatalar": hatalar,
           "sure_s": round(time.time() - t0, 1),
           "a11_not": "dagilimsal kanit adimi; kablo karari Eren'de"}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"KAYIT: {OUT}")
    log(f"SONUC: {'PASS' if basari else 'FAIL'}  "
        f"sure={(time.time() - t0)/60:.1f}dk")
    log("BITTI")
    return 0 if basari else 1


if __name__ == "__main__":
    sys.exit(main())
