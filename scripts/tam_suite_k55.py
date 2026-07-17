# -*- coding: utf-8 -*-
"""tam_suite_k55.py — K-55 + plaka-izolasyon commit oncesi A9 tam suite.

K-55 hizlandirmasi (continuous_settle + clearance workers/budama) genis
yuzeyli (min_clearance her legalite kapisinda) ve app.py plate_root
enjeksiyonu webapp yuzeyine dokunuyor — commit tam suite'e bloke
(2026-07-16 "tam suite -> commit" deseni). Sonuc: scripts/tam_suite_k55.log
Kosum: python -m scripts.detach_run tam_suite_k55    SAF ASCII.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent

LOG = Path(__file__).parent / "tam_suite_k55.log"


def main():
    with LOG.open("w", encoding="utf-8") as f:
        f.write("A9 TAM SUITE (slow dahil) basladi — K-55 + plaka-izolasyon commit kapisi\n")
        f.flush()
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q",
             "-m", "slow or not slow", "--tb=short"],
            cwd=str(_ROOT), stdout=f, stderr=subprocess.STDOUT)
        f.write(f"\nBITTI exit={p.returncode}\n")


if __name__ == "__main__":
    main()
