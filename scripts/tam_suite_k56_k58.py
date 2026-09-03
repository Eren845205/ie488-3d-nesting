# -*- coding: utf-8 -*-
"""tam_suite_k56_k58.py — K-56b/c/f + K-58 + K-59 commit oncesi A9 tam suite.

Genis yuzey: coarse_to_fine (pinned_placements) + eval_gate (pin passthrough
+ if/elif fix) + nfv_solve (R11 tavan 150->600) + demo_pipeline yorumlari +
targeted_tilt kablosu + test guncellemeleri (rot_kabul tasarim-pinleri,
eval_gate fake imzasi). Commit tam suite'e bloke (A9 bayat-mock tuzagi).
Sonuc: scripts/tam_suite_k56_k58.log
Kosum: python -m scripts.detach_run tam_suite_k56_k58    SAF ASCII.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent

LOG = Path(__file__).parent / "tam_suite_k56_k58.log"


def main():
    with LOG.open("w", encoding="utf-8") as f:
        f.write("A9 TAM SUITE (slow dahil) basladi — K-56/K-58/K-59 commit kapisi\n")
        f.flush()
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q",
             "-m", "slow or not slow", "--tb=short"],
            cwd=str(_ROOT), stdout=f, stderr=subprocess.STDOUT)
        f.write(f"\nBITTI exit={p.returncode}\n")


if __name__ == "__main__":
    main()
