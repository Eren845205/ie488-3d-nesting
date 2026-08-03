# -*- coding: utf-8 -*-
"""k56g_kapi.py — K-56g duz-pinleme kablosunun 4-SET EVAL KAPISI (A1).

K-56g sozlesme-KAPILI: `no_go_soft` ILAN edilmedikce olu kod. Bu kapi
kosusu ilani URETIM CONFIG'INE DOKUNMADAN env ile yapar
(PLATE_NOGO_SOFT; resolve_no_go_soft env-fallback — test_k56g_duz_pin
sozlesmesi). Beklenen: plan1 duz-pin zinciriyle IYILESME (~140 bandi),
p2/p3/d4 SIFIR-DOKUNUS birebir (tilt-zorunlu parca yalniz p1'de) ->
VERDICT PASS. PASS sonrasi plate.local.json'a kalici `no_go_soft` ilani
+ baseline yenileme AYRI EREN ONAYI ister (sozlesme degisikligi sinifi).

Munhasir kosu (K-57a): sakin makine, RAM-agir es-kosu yok.
Kosum: python -m scripts.detach_run k56g_kapi    SAF ASCII.
Cikti: scripts/k56g_kapi.log
"""
from __future__ import annotations
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k56g_kapi.log"
NOGO_SOFT_ENV = "152.5,0.2,185.5,33.0"  # K-56c Eren-onayli soft sozlesme


class _Tee:
    def __init__(self, o):
        self._o = o
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
    sys.stdout = _Tee(sys.stdout)
    sys.stderr = _Tee(sys.stderr)
    t0 = time.perf_counter()
    os.environ["PLATE_NOGO_SOFT"] = NOGO_SOFT_ENV  # import ONCESI sart
    print("K-56g KAPI KOSUSU (duz-pin kablosu; soft no-go ENV-ilanli,"
          " uretim config DOKUNULMADI)")
    print(f"PLATE_NOGO_SOFT={NOGO_SOFT_ENV}")
    sys.argv = ["eval_gate"]
    from scripts import eval_gate
    try:
        rc = eval_gate.main()
    except SystemExit as e:
        rc = int(e.code or 0)
    print(f"WALL_S={time.perf_counter() - t0:.1f}"
          f"  ({(time.perf_counter() - t0) / 60:.1f} dk)  eval_gate_exit={rc}")
    print("BITTI")


if __name__ == "__main__":
    main()
