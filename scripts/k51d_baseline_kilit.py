# -*- coding: utf-8 -*-
"""k51d_baseline_kilit.py — tilt-zorunlu kapili routing ile baseline kilidi.

K-51c bulgusu (2026-07-15): rot-sokum katmani plan2 (542.5) / plan3 (601.9) /
deneme4 (276.5) uclusunu SOKUM-PLANLI LEGAL yapti; tek bloker plan1'in eski
routing'iydi (kural NFV'ye yolluyordu; baseplate 330x302 duz pozda no-go'lu
plakaya SIGMAZ — geometrik kesin). Bu kosu tilt-zorunlu fizibilite kapisiyla
(predict_nfv_benefit no_go_bounds) plan1'i heightmap-fast'ten olcer; 4 set
legal ise results/eval_gate_baseline.json ILK KEZ kilitlenir (A1/A8).
Kosum: python -m scripts.detach_run k51d_baseline_kilit    SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k51d_baseline_kilit.log"


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
    print("K-51d BASELINE KILIDI — rot-sokum katmani + tilt-zorunlu kapi "
          "(335+nogo, 2mm, plan1->heightmap, r11/rot auto, fast)")
    from scripts import eval_gate
    sys.argv = ["eval_gate", "--save-baseline",
                "--reason", "tilt-zorunlu kapili sozlesme kilidi (2026-07-15)"]
    try:
        eval_gate.main()
    except SystemExit as e:
        print(f"eval_gate exit kodu: {e.code}")
    print("BITTI")


if __name__ == "__main__":
    main()
