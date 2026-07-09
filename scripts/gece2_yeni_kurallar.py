# -*- coding: utf-8 -*-
"""gece2_yeni_kurallar.py — YENI-KURAL tablosunu tamamlayan gece kuyrugu
(2026-07-10; nogo x152.5-185.5 + 2mm bosluk; A2 5-yon metrigi ayri raporlanir).

Bacaklar (tek surec):
  1) deneme5 n24   (eski-kural ref 280.8)
  2) deneme4 n24   (eski-kural ref 288.5; wall_aware yolu kos() icinde)
  3) plan1 TILT    (eski-kural 135.0; MARGIN/ZC=2'ye cekildi)
  4) plan2 n24     (eski-kural 646; en uzun bacak ~2h)
plan3 zaten olculdu (heightmap 735 / NFV+guard 680 legal).
Kosum: python -m scripts.detach_run gece2_yeni_kurallar   SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.ax24_kuyruk_335 import kos, log


def main():
    log("GECE-2 YENI KURALLAR — d5 n24 -> d4 n24 -> p1 tilt -> p2 n24 (2mm+nogo-yeni)")
    kos("deneme5", 24, clearance_mm=2.0)
    kos("deneme4", 24, clearance_mm=2.0)
    try:
        from scripts.plan1_hedefli_tilt import main as tilt_main
        tilt_main()
    except Exception as e:
        log(f"[p1_tilt] EXCEPTION: {type(e).__name__}: {e}")
    kos("plan2", 24, clearance_mm=2.0)
    log("GECE2-BITTI")


if __name__ == "__main__":
    main()
