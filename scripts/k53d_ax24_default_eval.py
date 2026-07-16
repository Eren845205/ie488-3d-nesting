# -*- coding: utf-8 -*-
"""k53d_ax24_default_eval.py — aile-kosullu AX24 default'unun 4-set eval kapisi.

K-53c bulgusu (2026-07-16): d4 @ AX24 = 231.5 SOKUM-PLANLI (-%16.3 vs n=8;
K-46 max-parite; sure ilk-24'ten kisa). Kablolama: rot-sokum thin_shell
dalinda ModeDecision.nfv_quality="max" onerisi — pipeline + eval kapisi
acik override yoksa bunu kullanir (uretim paritesi). Bu kosu YENI default'la
4 seti olcer: beklenti d4 231.5 / plan2 542.5 / plan3 601.9 (ikisi thin_shell
degil, n=8 BIREBIR) / plan1 INVALID (K-54 c2f clearance-cap acik is).
4 set legal ise baseline kilitlenir (A1/A8); plan1 nedeniyle exit 4 beklenir.
Kosum: python -m scripts.detach_run k53d_ax24_default_eval    SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k53d_ax24_default_eval.log"


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
    print("K-53d — aile-kosullu AX24 default 4-set eval "
          "(335+nogo, 2mm, r11/rot auto; d4 ailesi quality=max/AX24)")
    from scripts import eval_gate
    sys.argv = ["eval_gate", "--save-baseline",
                "--reason", "aile-kosullu AX24 poz-seti default'u (K-53c GO)"]
    try:
        eval_gate.main()
    except SystemExit as e:
        print(f"eval_gate exit kodu: {e.code}")
    print("BITTI")


if __name__ == "__main__":
    main()
