# -*- coding: utf-8 -*-
"""k65_dagilim_smoke.py — K-65 tetiginin DAGILIMSAL dogrulamasi (A11/B1, k59 deseni).

Tetik: ince-plaka-dominant instance'ta DUZ YATISTA plakaya sigmayan parca
varsa heightmap yerine NFV (adaptive_params K-65). Bu harness:

  1. TETIK DOGRULUGU: 4 sentetik ailede tetik, BAGIMSIZ geometrik
     beklentiyle (flat-fit yeniden turetimi) karsilastirilir:
       A saf-ince-plaka (sigar)      -> tetik YOK, heightmap
       B plaka + ASAN cubuk karisimi -> tetik VAR, nfv
       C plaka + SIGAN cubuk karisimi-> tetik YOK, heightmap
       D random_boxes kontrol        -> ince-plaka dali disi (net-kutu)
  2. KAZANC DAGILIMI: Aile B orneklerinde A/B — ayni instance zorlanmis
     heightmap vs zorlanmis nfv(fast) yukseklik kiyasi (win/tie/loss).
     SMOKE proxy'si: nfv_quality=fast + kucuk instance (hiz); "legal kazanc"
     ilani DEGILDIR (A2 tam olcumu tam-sweep isi).
  3. YANLIS-POZITIF: tetiklenen orneklerde NFV'nin heightmap'ten belirgin
     KOTU kalmasi (delta > +%2) yanlis-pozitif sayilir.

Kosum: D:\\ie488'den  python -m scripts.detach_run k65_dagilim_smoke
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import random
import sys
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.adaptive_params import (  # noqa: E402
    predict_nfv_benefit, _duz_yatista_sigmayan_parca)
from src.nesting3d.instances.format import (  # noqa: E402
    ContainerSpec, NestingInstance, PartSpec)

LOG = Path(__file__).parent / "k65_dagilim_smoke.log"
OUT = _ROOT / "results" / "k65_dagilim_smoke.json"
PLATE = 335.0
CNT = ContainerSpec(width_mm=PLATE, depth_mm=PLATE, height_mm=None)
N_SEED = 20
N_AB = 5


def log(m=""):
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def _box(pid, w, d, h, qty=1):
    return PartSpec(id=pid, name=pid, qty=qty, source="box",
                    width_mm=w, depth_mm=d, height_mm=h)


def _aile_A(seed):
    """Saf ince-plaka (hepsi sigar)."""
    rng = random.Random(1000 + seed)
    parts = [_box(f"plk{i}", rng.uniform(40, 150), rng.uniform(40, 150),
                  rng.uniform(3, 10))
             for i in range(rng.randint(15, 25))]
    return NestingInstance(container=CNT, parts=parts)


def _aile_B(seed):
    """Ince-plaka + PLAKA-ASAN cubuk karisimi (fsm-SINIFI, fsm DEGIL)."""
    rng = random.Random(2000 + seed)
    parts = [_box(f"plk{i}", rng.uniform(30, 100), rng.uniform(30, 100),
                  rng.uniform(4, 12), qty=rng.randint(1, 3))
             for i in range(rng.randint(8, 14))]
    for j in range(rng.randint(2, 5)):
        parts.append(_box(f"cubuk{j}", rng.uniform(8, 20),
                          rng.uniform(60, 100),
                          rng.uniform(PLATE + 5, PLATE + 125),
                          qty=rng.randint(1, 4)))
    return NestingInstance(container=CNT, parts=parts)


def _aile_C(seed):
    """Ince-plaka + SIGAN cubuk karisimi (kontrol: tetik olmamali)."""
    rng = random.Random(3000 + seed)
    parts = [_box(f"plk{i}", rng.uniform(30, 100), rng.uniform(30, 100),
                  rng.uniform(4, 12), qty=rng.randint(1, 3))
             for i in range(rng.randint(8, 14))]
    for j in range(rng.randint(2, 5)):
        parts.append(_box(f"cubuk{j}", rng.uniform(8, 20),
                          rng.uniform(60, 100),
                          rng.uniform(120, PLATE - 15),
                          qty=rng.randint(1, 4)))
    return NestingInstance(container=CNT, parts=parts)


def _aile_D(seed):
    """random_boxes kontrol (net-kutu dali)."""
    from src.nesting3d.instances.synthetic import random_boxes
    return random_boxes(n_parts=random.Random(4000 + seed).randint(10, 18),
                        container=CNT, seed=4000 + seed)


def _beklenti(inst):
    """BAGIMSIZ flat-fit beklentisi (tetigin kendisinden kopyalanmadi):
    kare plaka -> asan parca <=> herhangi parcada 2. buyuk boyut > PLATE
    veya en buyuk boyut > PLATE (2. buyuk plaka icindeyse buyuk de plaka
    icinde olmali)."""
    for p in inst.parts:
        dims = sorted((float(p.width_mm), float(p.depth_mm),
                       float(p.height_mm)))
        if dims[2] > PLATE or dims[1] > PLATE:
            return True
    return False


def _karar(inst):
    return predict_nfv_benefit(inst, family_routing=True)


def _pipeline_kos(inst, mode, seed=42):
    """Zorlanmis modla run_pipeline (SMOKE: nfv_quality=fast)."""
    from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
    parts = [{"id": p.id, "name": p.name, "qty": int(p.qty), "source": "box",
              "width_mm": float(p.width_mm), "depth_mm": float(p.depth_mm),
              "height_mm": float(p.height_mm)} for p in inst.parts]
    scenario = {**RICH_SCENARIO, "seed": seed,
                "orders": [{"order_id": "K65-SMOKE", "customer": "SYN",
                            "deadline": "2026-09-01", "priority_class": 2,
                            "parts": parts}],
                "container": {"width_mm": PLATE, "depth_mm": PLATE},
                "nesting_mode": mode, "nfv_quality": "fast",
                "auto_family_routing": False}
    r = run_pipeline(scenario)
    nr = (r.get("nesting_results") or {}).get("B001") or {}
    return float(nr.get("height_mm") or 0.0), int(nr.get("n_parts") or 0)


def main() -> int:
    log("=" * 70)
    log("K-65 DAGILIMSAL SMOKE — tetik dogrulugu + A/B kazanc (k59 deseni)")
    log("=" * 70)
    t0 = time.time()
    sayimlar = {}
    hatalar = []
    kayit = {"aileler": {}, "ab": []}

    aileler = {"A_saf_plaka": (_aile_A, False, "heightmap"),
               "B_asan_karisim": (_aile_B, True, "nfv"),
               "C_sigan_karisim": (_aile_C, False, "heightmap"),
               "D_random_boxes": (_aile_D, None, None)}
    for ad, (gen, beklenen_tetik, beklenen_mod) in aileler.items():
        dogru = 0
        toplam = 0
        detay = []
        for s in range(N_SEED):
            inst = gen(s)
            dec = _karar(inst)
            tetik = "K-65" in dec.reason
            bagimsiz = _beklenti(inst)
            toplam += 1
            ok = True
            if beklenen_tetik is not None:
                # Aile-D disinda: tetik = bagimsiz beklenti = aile beklentisi
                ok = (tetik == bagimsiz == beklenen_tetik
                      and dec.mode == beklenen_mod)
            else:
                # kontrol ailesi: yalniz tetik olmamali (dal disi)
                ok = not tetik
            dogru += int(ok)
            if not ok:
                hatalar.append(f"{ad} seed={s} tetik={tetik} "
                               f"bagimsiz={bagimsiz} mod={dec.mode}")
            detay.append({"seed": s, "tetik": tetik, "mod": dec.mode})
        sayimlar[ad] = (dogru, toplam)
        kayit["aileler"][ad] = {"dogru": dogru, "toplam": toplam,
                                "detay": detay}
        log(f"{ad:16s}: {dogru}/{toplam} dogru")

    log("")
    log("A/B kazanc (Aile B, zorlanmis heightmap vs nfv-fast):")
    win = tie = loss = 0
    for s in range(N_AB):
        inst = _aile_B(s)
        try:
            hm, n1 = _pipeline_kos(inst, "heightmap")
            nf, n2 = _pipeline_kos(inst, "nfv")
        except Exception as exc:
            hatalar.append(f"AB seed={s} kosu hatasi: {exc}")
            log(f"  seed={s}: KOSU HATASI {exc}")
            continue
        delta = nf - hm
        pct = 100.0 * delta / hm if hm else 0.0
        if pct < -0.5:
            sonuc = "WIN"
            win += 1
        elif pct > 2.0:
            sonuc = "LOSS"  # yanlis-pozitif adayi
            loss += 1
        else:
            sonuc = "TIE"
            tie += 1
        kayit["ab"].append({"seed": s, "heightmap": hm, "nfv": nf,
                            "pct": round(pct, 2), "sonuc": sonuc,
                            "n_hm": n1, "n_nfv": n2})
        log(f"  seed={s}: heightmap={hm:7.1f}  nfv={nf:7.1f}  "
            f"delta={pct:+6.2f}%  {sonuc} (n={n1}/{n2})")

    log("")
    log(f"A/B: {win}W / {tie}T / {loss}L  (LOSS = yanlis-pozitif adayi)")
    basari = (all(d == t for d, t in sayimlar.values())
              and loss == 0 and not hatalar)
    kayit["ozet"] = {"sayimlar": {k: list(v) for k, v in sayimlar.items()},
                     "ab_wtl": [win, tie, loss], "hatalar": hatalar,
                     "sure_s": round(time.time() - t0, 1),
                     "tarih": str(date.today())}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(kayit, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"KAYIT: {OUT}")
    log(f"SONUC: {'PASS' if basari else 'FAIL'}  sure={time.time()-t0:.0f}s")
    return 0 if basari else 1


if __name__ == "__main__":
    sys.exit(main())
