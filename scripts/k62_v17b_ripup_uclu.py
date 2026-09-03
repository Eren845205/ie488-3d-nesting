# -*- coding: utf-8 -*-
"""k62_v17b_ripup_uclu.py — K-62 v17b: HAM-PIN rip-up, UCLU-rutbe tabani.

v17 rip-up (dortlu rutbe, taban 134.40) tur-1 KABUL ile 132.00 LEGAL verdi
(cebe donus ACILDI — v16'da hic olmamisti). v13b fix'li en-iyi ise UCLU
rutbe tabaniyla 131.40. v17b: ayni rip-up zinciri, taban v13b kazanan
konfiginden (TAPER-GAUGE'siz uclu) — 130.80-alti bandin testi.

Kosum: python -m scripts.detach_run k62_v17b_ripup_uclu  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum (v17 ile ayni serh sinifi).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.k62_v17_ripup as v17

v17.RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
v17.LOG = Path(__file__).parent / "k62_v17b_ripup_uclu.log"
v17.OUT = _ROOT / "results" / "k62_v17b_ripup_uclu.json"
v17.REF = {"v13b_fixli_uclu": 131.40, "v13b_eski": 130.80, "manuel": 110.41}

if __name__ == "__main__":
    import traceback
    try:
        v17.main()
    except Exception:
        with v17.LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
