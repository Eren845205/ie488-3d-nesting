# -*- coding: utf-8 -*-
"""k58_p2_olcum.py — A11 sifir-dokunus kaniti + K-58 R11-tavan olcumu (plan2).

AMAC (Eren 2026-07-19 "overfit sorunu — bahsini gormek istiyorum"): bugunun
plan1-derinlesmesi (K-56c/d/e/f) working tree'de dururken plan2'nin uretim
yolu OLCULUR:
  (1) SIFIR-DOKUNUS: K-56 zinciri plan2'ye dokunmuyor olmali — tek beklenen
      fark K-58 (R11 auto tavani 150->600; plan2 226p artik kapsamda).
  (2) K-58 OLCUMU: r11 uygulanirsa beklenen kazanc kucuk (K-50: p2 bandi
      ~+0.8mm) — 542.5 -> ~541.5-542.5 arasi legal.
HUKUM MANTIGI: |sonuc - 542.5| kucuk ve tel r11 iziyle aciklanabilir ->
sifir-dokunus PASS + K-58 p2-kolu olculmus olur. r11-disi fark -> ALARM
(bugunku degisikliklerden biri plan2'ye sizmis demektir; A11 ihlali).

Referans: plan2 542.5 — 4 bagimsiz kosuda birebir (k51c/d/e + 2026-07-18).
Kosum: python -m scripts.detach_run k58_p2_olcum    (D:\\ie488'den)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k58_p2_olcum.log"
OUT = _ROOT / "results" / "k58_p2_olcum.json"
REF = 542.5


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("K-58 PLAN2 OLCUMU (A11 sifir-dokunus + R11-tavan; ref 542.5 x4)")
    t0 = time.perf_counter()
    r = evaluate_set("plan2", 42)
    lh = r.get("legal_height_mm")
    r11 = (r.get("sure_kirilim") or {}).get("r11_s")
    log(f"[plan2] legal={lh}  clear={r.get('min_clearance_mm')}"
        f"  kilit={r.get('n_locked')}  rot_kilit={r.get('n_locked_rot')}"
        f"  r11_uygulandi={r.get('r11_uygulandi')}"
        f"  r11_kazanc={r.get('r11_kazanc_mm')}  r11_s={r11}"
        f"  sure={r.get('duration_s')}s  invalid={r.get('invalid_reason')}")
    if lh is not None:
        fark = lh - REF
        log(f"KIYAS: ref {REF} -> {lh}  (fark {fark:+.2f}mm)")
        if abs(fark) < 0.05 and not r.get("r11_uygulandi"):
            log("HUKUM: BIREBIR + r11 uygulanmadi — sifir-dokunus PASS,"
                " K-58 p2'de kapilari gecemedi (tek-tarafli, sonuc korunur)")
        elif r.get("r11_uygulandi"):
            log("HUKUM: r11 UYGULANDI (K-58 tavan kalkti kaniti);"
                f" fark {fark:+.2f}mm r11-izi ile aciklanmali"
                " — sifir-dokunus r11-haric PASS")
        else:
            log("HUKUM: ALARM — r11'siz fark var; bugunku degisiklik sizintisi"
                " arastirilmali (A11)")
    else:
        log(f"HUKUM: INVALID ({r.get('invalid_reason')}) — cevresel mi"
            " degisiklik mi ayristirilmali")
    OUT.write_text(json.dumps(r, indent=2, default=str), encoding="utf-8")
    log(f"toplam: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
