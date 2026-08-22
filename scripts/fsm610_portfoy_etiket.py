# -*- coding: utf-8 -*-
"""fsm610_portfoy_etiket.py — fsm610 GERCEK siparisinin karsi-olgusal
portfoy etiketi (KARAR-1 terfi + "kafes de ogretilsin", Eren 2026-08-21).

M4 deseninin fsm610 ozel-kosusu: uretim kollari (heightmap / nfv_fast /
nfv_max) + tetikli kafes kollari (kafes / kafes_duruskoru) ayni A2
metrigiyle kosulur, etiket `results/m4_portfoy_etiket.jsonl`'a APPEND
edilir (aile=fsm610_gercek, scale=gercek). Egitime giris m4_koprusu
uzerinden (registry rol=dev; kafes kollari kafes_dahil=True ile).

UYARI: agir kosu (~2-3 saat; nfv_max tek basina ~40dk) — MUNHASIR koser
(K-57a + 2026-08-21 ust-uste-bindirme yasagi). SAF ASCII stdout.
Kosum: D:\\ie488'den `python -m scripts.detach_run fsm610_portfoy_etiket`.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import (  # noqa: E402
    ARMS, KAFES_ARMS, OUT_ETIKET, _f_fsm610_gercek, _kol_kafes, _kol_kos,
    etiket_hesapla)


def log(m: str = "") -> None:
    print(m, flush=True)


def main() -> int:
    from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
    clearance_req = float(WEB_MIN_CLEARANCE_MM)
    log("=" * 70)
    log("FSM610 PORTFOY ETIKETI — gercek siparis (KARAR-1 terfi 2026-08-21)")
    log(f"kollar={[a[0] for a in ARMS]} + tetikli {[a[0] for a in KAFES_ARMS]}"
        f"  clearance_req={clearance_req}mm")
    log("NOT: etiket uretimi — kazanc ilani DEGILDIR (A11).")
    log("=" * 70)
    t0 = time.time()
    inst = _f_fsm610_gercek(42, "gercek", None)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"instance kuruldu: {n_total} parca")

    arms = {}
    for ad, mode, q in ARMS:
        log(f"kol {ad} basliyor ...")
        kol = _kol_kos(inst, mode, q, seed=42, kaynak="fsm610_etiket")
        arms[ad] = kol
        log(f"  {ad}: h={kol.get('height_mm')} cl={kol.get('min_clearance_mm')}"
            f" kilit5={kol.get('n_locked_5dir')} sure={kol.get('wall_s')}s"
            + (f" HATA={kol['hata']}" if kol.get("hata") else ""))
    for ad, durus in KAFES_ARMS:
        log(f"kol {ad} basliyor (tetikli) ...")
        kol = _kol_kafes(inst, durus, clearance_req)
        if kol is None:
            log(f"  {ad}: tetik atesLEMEDI — kol eklenmedi")
            continue
        arms[ad] = kol
        log(f"  {ad}: h={kol.get('height_mm')} cl={kol.get('min_clearance_mm')}"
            f" kilit5={kol.get('n_locked_5dir')} sure={kol.get('wall_s')}s"
            + (f" HATA={kol['hata']}" if kol.get("hata") else ""))

    et = etiket_hesapla(arms, clearance_req)
    satir = {"ts": time.time(), "instance_id": "fsm610",
             "aile": "fsm610_gercek", "seed": 42, "scale": "gercek",
             "n_total": n_total, "clearance_req_mm": clearance_req,
             "arms": arms, **et}
    OUT_ETIKET.parent.mkdir(exist_ok=True)
    with OUT_ETIKET.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(satir, ensure_ascii=False) + "\n")
    log(f"ETIKET YAZILDI: winner={et['winner_mode']} n_legal={et['n_legal']}"
        f" -> {OUT_ETIKET}")
    log(f"BITTI ({(time.time()-t0)/60:.1f} dk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
