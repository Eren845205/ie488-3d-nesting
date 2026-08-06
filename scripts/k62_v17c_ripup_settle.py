# -*- coding: utf-8 -*-
"""k62_v17c_ripup_settle.py — K-62 v17c: HAM-PIN rip-up, UCLU rutbe + SETTLE.

v17 (dortlu, snap'siz): 134.40 -> 132.00 LEGAL (tur-1 KABUL — cebe donus
ACILDI). v17b (uclu, snap'siz): 132.00 sabit nokta. v13b fix'li en-iyi
131.40 ise SETTLE'LI. v17c: uclu rutbe + fine_settle ACIK (taban = v13b
131.40 birebir) + rip-up turlari settle'li — 130.80-alti bandin testi.

Pin snap riski: settle pitch'i kucuk (coarse/4) -> pin mm-koordinat snap'i
<= pitch/8 mm; v17 harness'i koordinati voxel_origin'den raw-bbox'a cevirir
(pitch-bagimsiz, kendinden-dogrulamali).

Kosum: python -m scripts.detach_run k62_v17c_ripup_settle  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum (v17 serh sinifi).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.k62_v17_ripup as v17

v17.RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
v17.SNAPSIZ = False          # settle ACIK (v13b davranisi)
v17.LOG = Path(__file__).parent / "k62_v17c_ripup_settle.log"
v17.OUT = _ROOT / "results" / "k62_v17c_ripup_settle.json"
v17.REF = {"v13b_fixli_uclu_settle": 131.40, "v13b_eski": 130.80,
           "v17_ripup": 132.00, "manuel": 110.41}

if __name__ == "__main__":
    import traceback
    try:
        v17.main()
    except Exception:
        with v17.LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
