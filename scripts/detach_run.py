# -*- coding: utf-8 -*-
"""detach_run.py — repo scriptini AYRIK surec olarak baslat (izin-dostu).

GUVENLIK: yalniz `scripts.` altindaki modul adlarini kabul eder (keyfi komut
CALISTIRMAZ) — izin sistemindeki `python -m scripts.*` kuralina sigar; boylece
Start-Process bilesikleri (onay prompt'u tetikleyen) gereksizlesir.

Kullanim: python -m scripts.detach_run plan3_acili_prob
Cikti stdout/stderr: %TEMP%/detach_<modul>.out|.err
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) != 2 or not sys.argv[1].replace("_", "").isalnum():
        print("kullanim: python -m scripts.detach_run <scripts_modul_adi>")
        sys.exit(2)
    mod = sys.argv[1]
    if not (_ROOT / "scripts" / f"{mod}.py").exists():
        print(f"HATA: scripts/{mod}.py yok — yalniz repo scriptleri calistirilir")
        sys.exit(2)
    out = Path(tempfile.gettempdir()) / f"detach_{mod}.out"
    err = Path(tempfile.gettempdir()) / f"detach_{mod}.err"
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    p = subprocess.Popen(
        [sys.executable, "-m", f"scripts.{mod}"], cwd=str(_ROOT),
        stdout=out.open("w"), stderr=err.open("w"),
        creationflags=flags if os.name == "nt" else 0)
    print(f"DETACHED pid={p.pid}  modul=scripts.{mod}  out={out}")


if __name__ == "__main__":
    main()
