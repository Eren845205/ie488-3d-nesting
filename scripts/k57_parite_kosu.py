# -*- coding: utf-8 -*-
"""k57_parite_kosu.py — K-57b set-paralel kapinin PARITE + WALL olcumu.

eval_gate --parallel 2 kosar; amac: 4/4 set baseline'la BIT-OZDES mi (surec-
izolasyon parite tezi) + gercek duvar-saati (sirali ~88dk'ya kiyas). OOM olursa
seri-kurtarma devreye girer (kod icinde). k51_baseline_kilit.py deseni: ince
sarmalayici; DETACH ile hayatta kalir (run_in_background PowerShell tur sinirinda
oluyordu — feedback-store-python-proses-adi dersi).

Kosum: python -m scripts.detach_run k57_parite_kosu   SAF ASCII.
Cikti: bu dosyanin yanindaki k57_parite_kosu.log + %TEMP%/detach_k57_parite_kosu.*
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_parite_kosu.log"


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
    # K-57c: FFT_BUDGET_MB env (opsiyonel) verilirse cocuklara cap gecer ->
    # dilimleme (H-17 bit-ozdes) -> OOM'suz gercek paralellik. Yoksa K-57b
    # ciplak paralel (bugunku parite kosusu). Ornek:
    #   NFV_FFT_BUDGET_MB=350 python -m scripts.detach_run k57_parite_kosu
    import os
    cap = os.environ.get("NFV_FFT_BUDGET_MB")
    argv = ["eval_gate", "--parallel", "2"]
    if cap:
        argv += ["--fft-budget-mb", cap]
        # runner kendi ortamindaki env'i cocuklara MIRAS BIRAKMASIN (cocuk
        # cap'i --fft-budget-mb'den alsin; aksi halde runner-NFV de kisitli
        # kosardi — burada solve yok ama netlik icin temizle).
        os.environ.pop("NFV_FFT_BUDGET_MB", None)
    print(f"K-57 PARITE + WALL OLCUMU — eval_gate {' '.join(argv[1:])} (4 set)")
    t0 = time.perf_counter()
    from scripts import eval_gate
    sys.argv = argv
    kod = 0
    try:
        eval_gate.main()
    except SystemExit as e:
        kod = int(e.code) if e.code is not None else 0
    wall = time.perf_counter() - t0
    print(f"WALL_S={wall:.1f}  ({wall/60:.1f} dk)  eval_gate_exit={kod}")
    print("BITTI")


if __name__ == "__main__":
    main()
