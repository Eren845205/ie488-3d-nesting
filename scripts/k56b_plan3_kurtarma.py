# -*- coding: utf-8 -*-
"""k56b_plan3_kurtarma.py — plan3 seri-kurtarma + K-58 p3-kolu olcumu.

TARIHCE: 4-set kapida plan3 ortam-OOM'uyla INVALID dustu (kablo-ilgisiz;
ayni kod ayni gun 3 kez 601.92 birebir). Iki kurtarma denemesi dusuk-RAM'de
dustu. GUNCELLEME 2026-07-20: working tree artik K-58'li (R11 auto tavani
150->600) — plan3'te r11 uygulanirsa 601.92 birebir BEKLENMEZ; hukum cift:
  r11 UYGULANMADIYSA: 601.92 birebir beklenir (cevresel-kurtarma +
      sifir-dokunus kaniti).
  r11 UYGULANDIYSA: K-58 p3-kolu olcumu — fast taban 601.92'den dusus
      beklenir (~578-590; sampiyon 577.62 max-zincirdendi, p3'te AX24 payi
      yalniz ~3.4mm [K-53], rekor farki R11).
Kosum: python -m scripts.detach_run k56b_plan3_kurtarma    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k56b_plan3_kurtarma.log"
OUT = _ROOT / "results" / "k56b_plan3_kurtarma.json"
FAST_TABAN = 601.92
SAMPIYON = 577.62


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("PLAN3 KURTARMA + K-58 p3-KOLU (tek set; ref fast 601.92 /"
        " sampiyon 577.62)")
    t0 = time.perf_counter()
    r = evaluate_set("plan3", 42)
    lh = r.get("legal_height_mm")
    r11 = bool(r.get("r11_uygulandi"))
    log(f"[plan3] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r11}  r11_kazanc={r.get('r11_kazanc_mm')}"
        f"  sure={r.get('duration_s')}s  invalid={r.get('invalid_reason')}")
    if lh is None:
        log(f"HUKUM: INVALID ({r.get('invalid_reason')}) — buyuk ihtimal yine"
            " cevresel (RAM); sakin makinede tekrar")
    elif not r11:
        parite = abs(lh - FAST_TABAN) < 0.05
        log(f"HUKUM ({'BIREBIR' if parite else 'FARKLI!'}): r11 kapilari"
            f" gecemedi; beklenti 601.92 birebir ->"
            f" {'KURTARILDI + sifir-dokunus PASS' if parite else 'A11 ALARM'}")
    else:
        log(f"HUKUM: K-58 p3-kolu — fast {FAST_TABAN} -> {lh:.2f}"
            f" ({lh - FAST_TABAN:+.2f}mm; sampiyon {SAMPIYON} kiyasi:"
            f" {lh - SAMPIYON:+.2f}mm). Cevresel-kurtarma da PASS (kosu"
            " tamamlandi).")
    OUT.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    log(f"toplam: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
