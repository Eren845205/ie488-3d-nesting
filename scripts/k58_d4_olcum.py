# -*- coding: utf-8 -*-
"""k58_d4_olcum.py — A11 sifir-dokunus + K-58 R11-tavan olcumu (deneme4).

k58_p2_olcum deseninin d4 kolu (p2: 529.04 = r11-haric PASS + yeni rekor).
d4 588p: K-58 oncesi tavan-disi (150), simdi kapsamda — beklenti K-55
replay'inden ~220.7 (231.5 - r11 ~10.8); sure ~31dk solve + ~43dk R11.
HUKUM MANTIGI: fark r11 iziyle aciklanirsa sifir-dokunus PASS; r11-disi
fark = A11 alarm.
Referans: deneme4 231.5 (k51e + 2026-07-18 birebir). Sampiyon 220.69 (K-55).
Kosum: python -m scripts.detach_run k58_d4_olcum    (D:\\ie488'den)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k58_d4_olcum.log"
OUT = _ROOT / "results" / "k58_d4_olcum.json"
REF = 231.5
SAMPIYON = 220.69


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("K-58 DENEME4 OLCUMU (A11 sifir-dokunus + R11-tavan; ref 231.5)")
    t0 = time.perf_counter()
    r = evaluate_set("deneme4", 42)
    lh = r.get("legal_height_mm")
    log(f"[d4] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r.get('r11_uygulandi')}"
        f"  r11_kazanc={r.get('r11_kazanc_mm')}"
        f"  sure={r.get('duration_s')}s  invalid={r.get('invalid_reason')}")
    if lh is not None:
        log(f"KIYAS: ref {REF} -> {lh}  (fark {lh - REF:+.2f}mm;"
            f" sampiyon {SAMPIYON})")
        if r.get("r11_uygulandi"):
            log("HUKUM: r11 UYGULANDI (K-58 kaniti); fark r11-izi ile"
                " aciklanmali — sifir-dokunus r11-haric degerlendirilir")
        elif abs(lh - REF) < 0.05:
            log("HUKUM: BIREBIR + r11 kapilari gecemedi — sifir-dokunus PASS")
        else:
            log("HUKUM: ALARM — r11'siz fark (A11 sizinti arastir)")
    else:
        log(f"HUKUM: INVALID ({r.get('invalid_reason')}) — cevresel/degisiklik"
            " ayristir")
    OUT.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    log(f"toplam: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
