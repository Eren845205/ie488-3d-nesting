# -*- coding: utf-8 -*-
"""eval_baseline_kosu.py — DEV-SET EVAL KAPISI + BASELINE DONDURMA (Kademe 4;
kullanici karari 2026-07-09: 'anayasadan beri yapilan HER gelisme bu testten
gecsin'). ANAYASA A1/A8: bugunku sampiyonlar eval_gate'in KENDI formatiyla
olculur ve baseline yazilir -> bundan sonraki HER degisiklik bu kapiyla
kiyaslanir (regresyon kapisi = genellemeyi koruyan mekanizma).

RAM zinciri: heldout_n24_final.log BITTI olana kadar bekler; sonra
`python -m scripts.eval_gate --save-baseline` (dev setler: plan1/2/3+deneme4,
uretim zinciri) alt-surec olarak kosulur. SAF ASCII.
"""
from __future__ import annotations
import subprocess, sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "eval_baseline_kosu.log"
BEKLE = Path(__file__).parent / "heldout_n24_final.log"


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("EVAL KAPISI dev-baseline dondurma (A1/A8; Kademe 4)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"held-out final bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — eval_gate --save-baseline basliyor (dev setler)")
    p = subprocess.run(
        [sys.executable, "-m", "scripts.eval_gate", "--save-baseline"],
        cwd=str(_ROOT), capture_output=True, text=True)
    for satir in (p.stdout or "").splitlines():
        log(satir)
    if p.returncode != 0:
        log("STDERR-KUYRUK: " + "\n".join((p.stderr or "").splitlines()[-15:]))
        log(f"EVAL GATE HATA (rc={p.returncode})")
    log("BITTI")


if __name__ == "__main__":
    main()
