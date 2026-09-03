# -*- coding: utf-8 -*-
"""detach_run.py — repo scriptini AYRIK surec olarak baslat (izin-dostu).

GUVENLIK: yalniz `scripts.` altindaki modul adlarini kabul eder (keyfi komut
CALISTIRMAZ) — izin sistemindeki `python -m scripts.*` kuralina sigar; boylece
Start-Process bilesikleri (onay prompt'u tetikleyen) gereksizlesir.

Kullanim: python -m scripts.detach_run plan3_acili_prob
Cikti stdout/stderr: <repo>/logs/detach_<modul>_<zaman>.out|.err (KALICI —
2026-08-30 dersi: Temp'teki 08-22 kampanya loglari kayboldu; logs/ gitignore'da,
D:/ie488 uzerinde kalir; ayrica %TEMP%/detach_<modul>.out|.err son-kosu kopyasi)
"""
import datetime
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
    logs = _ROOT / "logs"
    logs.mkdir(exist_ok=True)
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = logs / f"detach_{mod}_{zaman}.out"
    err = logs / f"detach_{mod}_{zaman}.err"
    # geri-uyum: eski Temp yolu son-kosu isaretcisi (yol metni) olarak kalir
    try:
        (Path(tempfile.gettempdir()) / f"detach_{mod}.out").write_text(
            f"KALICI LOG: {out}" + chr(10), encoding="ascii")
    except OSError:
        pass
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    p = subprocess.Popen(
        [sys.executable, "-m", f"scripts.{mod}"], cwd=str(_ROOT),
        stdout=out.open("w"), stderr=err.open("w"),
        creationflags=flags if os.name == "nt" else 0)
    print(f"DETACHED pid={p.pid}  modul=scripts.{mod}  out={out}  err={err}")


if __name__ == "__main__":
    main()
