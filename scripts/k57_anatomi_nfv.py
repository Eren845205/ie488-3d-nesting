# -*- coding: utf-8 -*-
"""k57_anatomi_nfv.py — K-57 sure-kirilim ANATOMI kosusu (3 NFV seti).

K-57d on-teshisi voxelize payini %4.6 olctu (NO-GO); kapinin ~%95'i
voxelize-DISI. Bu kosu evaluate_set'in yeni sure_kirilim telemetrisiyle
plan2/plan3/deneme4'un anatomisini cikarir: solve (NFV ham/guard decode) /
r11 / rot_kabul / clearance-6000 / 5-yon-kilit / rot-denetim kalemleri.
Ayni zamanda 542.5 / 601.9 / 231.5 replay teyidi (determinizm).

Munhasir kosu istenir (K-57a: yuk sureleri sisirir). Siralama hafiften agira.
Kosum: python -m scripts.detach_run k57_anatomi_nfv    SAF ASCII.
Cikti: scripts/k57_anatomi_nfv.log + results/k57_anatomi_nfv.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_anatomi_nfv.log"
OUT = _ROOT / "results" / "k57_anatomi_nfv.json"
SETLER = ("plan2", "plan3", "deneme4")
BEKLENEN = {"plan2": 542.5, "plan3": 601.92, "deneme4": 231.5}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("K-57 ANATOMI KOSUSU (sure-kirilim telemetrisi; 3 NFV seti)")
    rapor = {}
    t0 = time.perf_counter()
    for ad in SETLER:
        log(f"--- {ad} basladi ({time.strftime('%H:%M')}) ---")
        try:
            r = evaluate_set(ad, 42)
        except Exception as e:
            log(f"[{ad}] EXCEPTION: {type(e).__name__}: {e}")
            rapor[ad] = {"hata": f"{type(e).__name__}: {e}"}
            continue
        sk = r.get("sure_kirilim") or {}
        lh = r.get("legal_height_mm")
        bek = BEKLENEN[ad]
        parite = (lh is not None and abs(lh - bek) < 0.05)
        log(f"[{ad}] SONUC: legal={lh}  beklenen={bek}"
            f"  PARITE={'BIREBIR' if parite else 'FARKLI!'}"
            f"  toplam={r['duration_s']}s")
        log(f"[{ad}] KIRILIM: solve={sk.get('solve_s')}s"
            f" (nfv: ham={sk.get('nfv_solve_ham_s')}"
            f" guard={sk.get('nfv_solve_guard_s')}"
            f" kilit5={sk.get('nfv_kilit5_s')}"
            f" r11={sk.get('r11_s')}"
            f" rot_kabul={sk.get('rot_kabul_s')})"
            f"  clearance={sk.get('clearance_s')}s"
            f"  kilit={sk.get('kilit_s')}s  rot={sk.get('rot_s')}s")
        rapor[ad] = r
    log(f"TOPLAM: {(time.perf_counter() - t0) / 60:.1f} dk")
    OUT.write_text(json.dumps(rapor, indent=2, default=str),
                   encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
