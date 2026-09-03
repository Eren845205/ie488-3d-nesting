# -*- coding: utf-8 -*-
"""tune_bo.py — STRATEJI Faz-3: motor knob tuning kosucusu (04_MOTOR_TUNING).

Objective (04 §2): dev-set'lerde WORST-CASE legal-iyilesme maksimize edilir —
tek-sete-overfit'i matematiksel cezalandirir. INVALID = aninda -inf. Held-out
ASLA girmez (eval_gate registry katmani zaten reddeder).

Yontem: stdlib LHS-vari rasgele baslangic (seed'li, deterministik) + en iyi
noktanin komsu rafinesi. Optuna KASITLI kullanilmadi (dev-bagimlilik karari
sana ait; uzay <=3 boyut oldugu surece bu yeterli — 04 §3).

ON-SART: results/eval_gate_baseline.json KILITLI olmali (--save-baseline).
Kosum:  python -m scripts.tune_bo --trials 8 --sets plan1,deneme4
        (1 deneme ~= secilen setlerin toplam kosu suresi! plan1+deneme4 ~10dk
        -> 8 deneme ~80dk. Butceyi bilerek sec.)
Cikti:  data/tuning/trials.jsonl (her deneme: knob'lar + set-bazli legal + skor)
Kazanan otomatik URETIME BAGLANMAZ: resmi kapi kosusu + insan karari (A1/A6).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.eval_gate import evaluate_set, DEV_SETS, BASELINE  # noqa: E402

TRIALS_PATH = _ROOT / "data" / "tuning" / "trials.jsonl"

# Knob uzayi (04 §1 envanterinden ILK tur; duyarlilik taramasi sonucuna gore
# daraltilir/genisletilir). Ayrik degerler — grid-kirlenmesine karsi net.
SPACE = {
    "budget": [25, 70, 150],
    "n_orientations": [4, 8],
}


def _objective(cfg, sets, base):
    """min_s iyilesme% (pozitif=iyi). INVALID -> -inf. Satirlar da doner."""
    per = {}
    worst = float("inf")
    for s in sets:
        r = evaluate_set(s, seed=42, skip_clearance=False,
                         budget=cfg["budget"],
                         n_orientations=cfg["n_orientations"])
        per[s] = r
        lh, b = r["legal_height_mm"], base.get(s)
        if lh is None or not b:
            return float("-inf"), per
        worst = min(worst, (b - lh) / b * 100.0)
    return worst, per


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=6)
    ap.add_argument("--sets", default=",".join(DEV_SETS))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    sets = [s.strip() for s in args.sets.split(",") if s.strip()]

    if not BASELINE.exists():
        print("ON-SART EKSIK: baseline kilitli degil "
              "(python -m scripts.eval_gate --save-baseline). Cikiliyor.")
        sys.exit(2)
    base_doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    base = {s: v.get("legal_height_mm") for s, v in base_doc["sets"].items()}

    rng = random.Random(args.seed)
    combos = [dict(budget=b, n_orientations=n)
              for b in SPACE["budget"] for n in SPACE["n_orientations"]]
    rng.shuffle(combos)
    combos = combos[: args.trials]

    TRIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    best = None
    print(f"BO tuning: {len(combos)} deneme x {sets} (worst-case objective)",
          flush=True)
    for i, cfg in enumerate(combos, 1):
        t = time.perf_counter()
        score, per = _objective(cfg, sets, base)
        row = {"ts": datetime.now().isoformat(timespec="seconds"),
               "trial": i, "cfg": cfg, "score_worst_pct": (
                   None if score == float("-inf") else round(score, 3)),
               "sets": {s: {k: per[s][k] for k in
                            ("legal_height_mm", "invalid_reason", "duration_s")}
                        for s in per},
               "duration_min": round((time.perf_counter() - t) / 60, 1)}
        with TRIALS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(f"  [{i}/{len(combos)}] {cfg} -> "
              f"{'INVALID' if score == float('-inf') else f'{score:+.2f}%'} "
              f"({row['duration_min']} dk)", flush=True)
        if score != float("-inf") and (best is None or score > best[0]):
            best = (score, cfg)
    print("-" * 60)
    if best is None:
        print("SONUC: hicbir deneme gecerli degil.")
    else:
        print(f"EN IYI: {best[1]}  worst-case iyilesme {best[0]:+.2f}%")
        print("SONRAKI ADIM (A1/A6): resmi kapi kosusu + insan karari + "
              "YONTEM_HARITASI kaydi. Otomatik baglama YOK.")


if __name__ == "__main__":
    main()
