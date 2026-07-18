# -*- coding: utf-8 -*-
"""k57_fastlen_kapi.py — fastlen URETIM KANITI (A1 kapisi): 3 NFV seti.

fastlen decode_gpu default'u ACILDI (orneklem A/B: -%49.9, h+placements
birebir). A1 geregi uretim sayilarinin TAM kapida birebir kaldigi kanitlanir:
evaluate_set(plan2/plan3/deneme4) -> legal 542.5 / 601.92 / 231.5 BIREBIR
beklenir + sure kazanci raporlanir (rot-reuse fix'li tabanlar: 678 / 1477 /
1113s). plan1 heightmap (decode'suz) — etkilenmez, kosulmaz.

Kosum: python -m scripts.detach_run k57_fastlen_kapi    SAF ASCII.
Cikti: scripts/k57_fastlen_kapi.log + results/k57_fastlen_kapi.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_fastlen_kapi.log"
OUT = _ROOT / "results" / "k57_fastlen_kapi.json"
BEKLENEN = {"plan2": (542.5, 678.1), "plan3": (601.92, 1477.4),
            "deneme4": (231.5, 1113.3)}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("K-57 FASTLEN KAPI KANITI (3 NFV seti; rot-reuse'lu tabanlara karsi)")
    rapor, hepsi = {}, True
    t0 = time.perf_counter()
    for ad, (bek, taban) in BEKLENEN.items():
        log(f"--- {ad} ({time.strftime('%H:%M')}) ---")
        r = evaluate_set(ad, 42)
        lh = r.get("legal_height_mm")
        parite = lh is not None and abs(lh - bek) < 0.05
        hepsi = hepsi and parite
        sk = r.get("sure_kirilim") or {}
        log(f"[{ad}] legal={lh} (beklenen {bek})"
            f"  PARITE={'BIREBIR' if parite else 'FARKLI!'}"
            f"  sure={r['duration_s']}s (taban {taban}s,"
            f" {taban - r['duration_s']:+.0f}s)"
            f"  solve={sk.get('solve_s')}s strateji={sk.get('decode_strateji')}")
        rapor[ad] = r
    log(f"TOPLAM: {(time.perf_counter() - t0) / 60:.1f} dk"
        f"  HUKUM: {'PARITE 3/3 + kazanc' if hepsi else 'KALDI — incele'}")
    OUT.write_text(json.dumps(rapor, indent=2, default=str), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
