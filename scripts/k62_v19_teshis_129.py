# -*- coding: utf-8 -*-
"""k62_v19_teshis_129.py — K-62 v19: 129.00 sahnesinin doluluk anatomisi.

v15 teshisinin (130.80 icin) fix'li-motor 129.00 sahnesine tekrari
(A4 olc-once: v18b sira-perturbasyonu sabit noktayi kiramadiysa siradaki
mekanizmayi VERI secsin — kanopi-alti bos mu, delik kapasitesi mi, tavan
yapisal mi?). Fark: Z=64.8 (iz=27 kazanani) + UCLU rutbe (TAPER'siz).

Kosum: python -m scripts.detach_run k62_v19_teshis_129  (D:\\ie488). ASCII.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scripts.k62_v15_teshis as v15

v15.Z_MM = 64.8
v15.RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
v15.LOG = Path(__file__).parent / "k62_v19_teshis_129.log"
v15.OUT = _ROOT / "results" / "k62_v19_teshis_129.json"

if __name__ == "__main__":
    import traceback
    try:
        v15.main()
    except Exception:
        with v15.LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
