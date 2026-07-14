# -*- coding: utf-8 -*-
"""k51_baseline_kilit.py — Sprint-3: eval_gate v2 sozlesmesiyle ILK baseline kilidi.

v2 sozlesmesi (2026-07-14): 335x335 + yasak-bolge + 2mm kural + NFV-farkindali
sampiyon yolu (uretim DEFAULT: quality=fast) + 6000-ornek clearance.
Bu kosu results/eval_gate_baseline.json'u ILK KEZ uretir -> tune_bo'nun
exit(2) on-sarti acilir; bundan sonraki her degisiklik B2 esikleriyle bu
baseline'a kiyaslanir (A1/A8).
Kosum: python -m scripts.detach_run k51_baseline_kilit    SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k51_baseline_kilit.log"


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
    print("K-51 BASELINE KILIDI — eval_gate v2 sozlesmesi (335+nogo, 2mm, NFV-farkindali, fast)")
    from scripts import eval_gate
    sys.argv = ["eval_gate", "--save-baseline",
                "--reason", "Sprint-3 v2 sozlesmesi ilk kilit (2026-07-14)"]
    try:
        eval_gate.main()
    except SystemExit as e:
        print(f"eval_gate exit kodu: {e.code}")
    print("BITTI")


if __name__ == "__main__":
    main()
