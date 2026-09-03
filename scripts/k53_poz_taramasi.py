# -*- coding: utf-8 -*-
"""k53_poz_taramasi.py — K-53a/b: fast'i max'a yaklastirma poz taramasi.

Eren yonu (2026-07-15): "fastleri gelistirelim, olmadi max'i opsiyon sunariz".
Teshis: quality yalniz poz sayisini kontrol eder (fast=8, max=AX24); ucurum
poz-duyarli ailelerde (plan3 +%4.2, d4 +%19). Bu tarama fast butcesiyle
n_orientations {12,16,24} olcer -> kazanc/sure egrisi. Ucuz->pahali sira:
once d4 (koso kisa, ucurum buyuk), sonra plan3 (n=8'de 96dk — pahali).

Sonuclar ADIM ADIM loglanir (results/k53_poz_taramasi.json'a da yazilir);
istenirse plan3 blogu beklenmeden durdurulabilir. Baseline'a DOKUNMAZ
(A8 — yalniz olcum; kazanan konfig ayri eval_gate kosusuyla kapiya girer).
Kosum: python -m scripts.detach_run k53_poz_taramasi    SAF ASCII.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import datetime
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k53_poz_taramasi.log"
OUT = _ROOT / "results" / "k53_poz_taramasi.json"

# (set, n_orientations) — ucuz->pahali; n=8 referanslari k51c/k51d'den bilinir
TARAMA = [
    ("deneme4", 12),
    ("deneme4", 16),
    ("deneme4", 24),
    ("plan3", 12),
    ("plan3", 16),
]


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
    print("K-53 POZ TARAMASI — fast butcesi + n_orientations {12,16,24}")
    print(f"sira: {TARAMA}")
    from scripts.eval_gate import evaluate_set
    sonuclar = []
    for set_adi, n_or in TARAMA:
        print(f"[{set_adi} n={n_or}] kosuyor...", flush=True)
        t0 = time.perf_counter()
        try:
            r = evaluate_set(set_adi, seed=42, n_orientations=n_or)
        except Exception as e:
            r = {"legal_height_mm": None, "invalid_reason": f"EXCEPTION: {e}"}
        r = dict(r)
        r["set"] = set_adi
        r["n_orientations"] = n_or
        r["tarama_sure_s"] = round(time.perf_counter() - t0, 1)
        sonuclar.append(r)
        lh = r.get("legal_height_mm")
        lh_s = (f"{lh:.1f}mm" if lh is not None
                else f"INVALID({r.get('invalid_reason')})")
        print(f"[{set_adi} n={n_or}] legal={lh_s}  "
              f"kilit={r.get('n_locked')}  rot={r.get('n_locked_rot')}  "
              f"sokum_planli={r.get('sokum_planli')}  "
              f"({r['tarama_sure_s']}s)", flush=True)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "schema": 1, "created": datetime.now().isoformat(timespec="seconds"),
            "referans": "n=8 degerleri k51c/k51d loglarinda",
            "sonuclar": sonuclar,
        }, indent=2, ensure_ascii=True), encoding="utf-8")
    print("BITTI")


if __name__ == "__main__":
    main()
