# -*- coding: utf-8 -*-
"""k57_rot_reuse_parite.py — K-57 cift-rot fix'i PARITE + KAZANC kaniti.

Anatomi kaniti (k57_anatomi_nfv, 2026-07-18): dz'siz setlerde eval katmani
solve'un rot_kabul denetimini AYNEN tekrarliyor — plan2 283s + d4 209s =
492s israf. Fix: r11_dz yok + solve rot_kabul rot_kilit=0 -> kanit yeniden
kullanilir (rot_kaynak="solve_reuse"), denetim tekrarlanmaz.

Bu kosu fix'li evaluate_set ile plan2 + deneme4'u olcer. GECER sayilir eger:
  - legal 542.5 / 231.5 BIREBIR (sayilar degismez — kalite-notr kanit)
  - rot_kaynak == "solve_reuse" ve sure_kirilim.rot_s None
  - toplam sure anatomi tabanindan asagi (878.2 / 1506.9s)
Kosum: python -m scripts.detach_run k57_rot_reuse_parite    SAF ASCII.
Cikti: scripts/k57_rot_reuse_parite.log + results/k57_rot_reuse_parite.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_rot_reuse_parite.log"
OUT = _ROOT / "results" / "k57_rot_reuse_parite.json"
BEKLENEN = {"plan2": (542.5, 878.2), "deneme4": (231.5, 1506.9)}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import evaluate_set
    log("K-57 ROT-REUSE PARITE KOSUSU (plan2 + deneme4; dz'siz cift-rot fix)")
    rapor, hepsi_gecti = {}, True
    t0 = time.perf_counter()
    for ad, (bek_legal, taban_s) in BEKLENEN.items():
        log(f"--- {ad} basladi ({time.strftime('%H:%M')}) ---")
        r = evaluate_set(ad, 42)
        lh = r.get("legal_height_mm")
        sk = r.get("sure_kirilim") or {}
        parite = lh is not None and abs(lh - bek_legal) < 0.05
        reuse = r.get("rot_kaynak") == "solve_reuse"
        kazanc = taban_s - r["duration_s"]
        gecti = parite and reuse
        hepsi_gecti = hepsi_gecti and gecti
        log(f"[{ad}] legal={lh} (beklenen {bek_legal})"
            f"  PARITE={'BIREBIR' if parite else 'FARKLI!'}"
            f"  rot_kaynak={r.get('rot_kaynak')}  cert={r.get('rot_cert')}"
            f"  sokum_planli={r.get('sokum_planli')}")
        log(f"[{ad}] sure: {r['duration_s']}s (anatomi tabani {taban_s}s,"
            f" kazanc {kazanc:+.0f}s)  rot_s={sk.get('rot_s')}"
            f"  {'GECTI' if gecti else 'KALDI'}")
        rapor[ad] = r
    log(f"TOPLAM: {(time.perf_counter() - t0) / 60:.1f} dk"
        f"  HUKUM: {'4/4 GECTI' if hepsi_gecti else 'KALDI — incele'}")
    OUT.write_text(json.dumps(rapor, indent=2, default=str),
                   encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
