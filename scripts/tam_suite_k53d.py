# -*- coding: utf-8 -*-
"""tam_suite_k53d.py — K-53c+d commit oncesi A9 tam suite (slow dahil).

Aile-kosullu AX24 default kablolamasi (adaptive_params + demo_pipeline +
eval_gate) uretim default'unu degistirdigi icin commit tam suite'e bloke
(Eren karari 2026-07-16). Sonuc: scripts/tam_suite_k53d.log
Kosum: python -m scripts.detach_run tam_suite_k53d    SAF ASCII.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent

LOG = Path(__file__).parent / "tam_suite_k53d.log"


def main():
    with LOG.open("w", encoding="utf-8") as f:
        f.write("A9 TAM SUITE (slow dahil) basladi — K-53c+d commit kapisi\n")
        f.flush()
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q",
             "-m", "slow or not slow", "--tb=short"],
            cwd=str(_ROOT), stdout=f, stderr=subprocess.STDOUT)
        f.write(f"\nBITTI exit={p.returncode}\n")


if __name__ == "__main__":
    main()
