# -*- coding: utf-8 -*-
"""webapp_suite_kosusu.py — webapp regresyon suitini detach'le kosar.

Sokum Konsolu P2-P6 template/JS degisikliklerinin regresyon kontrolu;
arka-plan pytest kosulari iki kez durduruldugu icin detach_run deseniyle
bagimsiz surecte kosulur. Sonuc: scripts/webapp_suite_kosusu.log
Kosum: python -m scripts.detach_run webapp_suite_kosusu    SAF ASCII.
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent

LOG = Path(__file__).parent / "webapp_suite_kosusu.log"


def main():
    with LOG.open("w", encoding="utf-8") as f:
        f.write("WEBAPP SUITI (P2-P6 regresyon) basladi\n")
        f.flush()
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q",
             "-k", "webapp or gecmis or sokum_konsolu or vitrin",
             "--tb=short"],
            cwd=str(_ROOT), stdout=f, stderr=subprocess.STDOUT)
        f.write(f"\nBITTI exit={p.returncode}\n")


if __name__ == "__main__":
    main()
