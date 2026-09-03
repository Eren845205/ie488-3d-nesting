# -*- coding: utf-8 -*-
"""k53c_ax24_d4.py — K-53c: d4 ailesine AX24 poz seti olcumu (Eren karari (a)).

K-53 hukmu (2026-07-16): poz kaldiraci yalniz d4-ailesinde; "kac poz" degil
"HANGI pozlar" — d4 AX24-max ham 231.5 (K-46) < ilk-24 250.0. Bu olcum ayni
eval_gate sozlesmesiyle (335+nogo+2mm+rot-kabul) d4'u n_orientations="ax24"
(= quality=max poz seti, 24 eksen-hizali egiksiz) ile kosar. Referanslar:
n=8 276.5 (k51c/k51d) · ilk-24 250.0 (K-53) · sampiyon 220.69 (max+R11, K-52).
GO esigi: legal < 250.0 (ilk-24'u gecmeli); beklenti ~231.5 + rot-sokum.

Baseline'a DOKUNMAZ (A8 — yalniz olcum; PASS ise uretim default'una
aile-kosullu kablolama AYRI is + 4-set eval kapisi).
Kosum: python -m scripts.detach_run k53c_ax24_d4    SAF ASCII.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k53c_ax24_d4.log"
OUT = _ROOT / "results" / "k53c_ax24_d4.json"


class _TeeLog:
    def __init__(self, orijinal):
        self._o = orijinal
        self._f = LOG.open("a", encoding="utf-8")

    def write(self, m):
        self._o.write(m)
        self._f.write(m)
        self._f.flush()

    def flush(self):
        self._o.flush()
        self._f.flush()


def main():
    LOG.write_text("", encoding="utf-8")
    sys.stdout = _TeeLog(sys.stdout)
    print("K-53c — deneme4 @ AX24 poz seti (eval_gate sozlesmesi, seed=42)")
    print("referans: n=8 276.5 / ilk-24 250.0 / sampiyon 220.69 (max+R11)")
    from scripts.eval_gate import evaluate_set
    t0 = time.perf_counter()
    try:
        r = evaluate_set("deneme4", seed=42, n_orientations="ax24")
    except Exception as e:
        r = {"legal_height_mm": None, "invalid_reason": f"EXCEPTION: {e}"}
    r = dict(r)
    r["set"] = "deneme4"
    r["poz_seti"] = "ax24"
    r["tarama_sure_s"] = round(time.perf_counter() - t0, 1)
    lh = r.get("legal_height_mm")
    lh_s = (f"{lh:.1f}mm" if lh is not None
            else f"INVALID({r.get('invalid_reason')})")
    print(f"[deneme4 ax24] legal={lh_s}  kilit={r.get('n_locked')}  "
          f"rot={r.get('n_locked_rot')}  sokum_planli={r.get('sokum_planli')}  "
          f"({r['tarama_sure_s']}s)", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema": 1, "created": datetime.now().isoformat(timespec="seconds"),
        "referans": "n=8 276.5 (k51c/d) · ilk-24 250.0 (K-53) · 220.69 (K-52)",
        "sonuclar": [r],
    }, indent=2, ensure_ascii=True), encoding="utf-8")
    print("BITTI")


if __name__ == "__main__":
    main()
