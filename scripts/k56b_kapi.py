# -*- coding: utf-8 -*-
"""k56b_kapi.py — K-56b hedefli-tilt kablosunun 4-SET EVAL KAPISI (A1).

eval_gate'i SIRALI kosar (baseline kiyasli). Beklenen: plan1 302.8 -> ~202
IYILESME + diger 3 set birebir -> VERDICT PASS. Munhasir kosu istenir.
Kosum: python -m scripts.detach_run k56b_kapi    SAF ASCII.
Cikti: scripts/k56b_kapi.log
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k56b_kapi.log"


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
    print("K-56b KAPI KOSUSU (hedefli-tilt kablosu; sirali, baseline kiyasli)")
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
