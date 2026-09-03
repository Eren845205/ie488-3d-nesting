# -*- coding: utf-8 -*-
"""k51c_baseline_kilit.py — rot-sokum katmanli sozlesmeyle baseline kilidi.

K-51b bulgusu (2026-07-15): eski sozlesmenin 5-yon kilit=0 sarti hoca
kabul kriterinden SERTTI — plan2/3 kilitleri rot-sokum denetimi gormeden
INVALID sayildi, d4 routing heightmap'ti. Eren kararlari (2026-07-15):
  (a) A2'ye rot-sokum katmani (kilit>0 -> kilit_rot_meshes yeniden yargilar;
      rot kilit=0 -> SOKUM-PLANLI legal),
  (b) d4 routing heightmap -> NFV+rot (predict rot_sokum=True),
  (c) uretim paritesi: r11="auto" + rot_kabul="auto" + dz-kaymis sahne olcumu.
Bu kosu results/eval_gate_baseline.json'u bu sozlesmeyle kilitler (A1/A8).
Kosum: python -m scripts.detach_run k51c_baseline_kilit    SAF ASCII.
"""
from __future__ import annotations
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k51c_baseline_kilit.log"


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
    print("K-51c BASELINE KILIDI — rot-sokum katmanli sozlesme "
          "(335+nogo, 2mm, NFV+rot routing, r11/rot auto, fast)")
    from scripts import eval_gate
    sys.argv = ["eval_gate", "--save-baseline",
                "--reason", "rot-sokum katmanli sozlesme kilidi (2026-07-15)"]
    try:
        eval_gate.main()
    except SystemExit as e:
        print(f"eval_gate exit kodu: {e.code}")
    print("BITTI")


if __name__ == "__main__":
    main()
