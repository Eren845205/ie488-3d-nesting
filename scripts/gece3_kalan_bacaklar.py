# -*- coding: utf-8 -*-
"""gece3_kalan_bacaklar.py — GECE-2 OOM kazasinin kalan bacaklari (2026-07-09).

GECE-2 olumu: d4 STL teshis scripti (278MB split, 3.3GB) tilt kosusuyla
CAKISTI -> sistem RAM tukendi -> p1_tilt MemoryError + p2_n24 dogumda oldu.
RAM dersi (tek agir surec) BIR KEZ DAHA: bu kuyruk teshis bittikten sonra,
tek basina baslatilir.

Bacaklar:
  1) plan1 TILT  (baseline 260.0 @2mm OLCULDU-gecerli; tilt tarama+kosu OLMEDEN
     kesildi — deterministik, bastan)
  2) plan2 n24   (yeni kural 2mm; eski-kural ref 646/122dk)
Etiketleme: legal_of(clearance_req=2.0) KABLOLU (bu oturum fix'i).
Kosum: python -m scripts.detach_run gece3_kalan_bacaklar   SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.ax24_kuyruk_335 import kos, log


def main():
    log("GECE-3 KALAN BACAKLAR — p1 tilt -> p2 n24 (2mm+nogo-yeni; gece2 OOM devami)")
    try:
        from scripts.plan1_hedefli_tilt import main as tilt_main
        tilt_main()
    except Exception as e:
        log(f"[p1_tilt] EXCEPTION: {type(e).__name__}: {e}")
    kos("plan2", 24, clearance_mm=2.0)
    log("GECE3-BITTI")


if __name__ == "__main__":
    main()
