# -*- coding: utf-8 -*-
"""a2_plan2_etiket_duzelt.py — plan2 etiket satirini DUZELTILMIS kollarla
yeniden yaz (append-only; kopru son satiri alir). 2026-08-30 tek-seferlik:

- heightmap: bugunku ham sidecar'dan (708,5 / cl 0,001 INVALID — dogru).
- nfv_fast / nfv_max: BEKCI iptali (AC-08 kanopi bellek bombasi) — hata kolu.
- kafes / kafes_duruskoru: rot-sokum hukumlu TAZE olcumden
  (_tek_devset_plan2_<kol>.json).

Kosum: D:\\ie488'den `python -m scripts.a2_plan2_etiket_duzelt`. SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import OUT_ETIKET, SIDECAR_DIR, etiket_hesapla


def _sidecar_kol(ad_prefix: str) -> dict:
    aday = sorted(SIDECAR_DIR.glob(f"{ad_prefix}_*.json"))
    d = json.loads(aday[-1].read_text(encoding="utf-8"))
    kol = dict(d["kol_ozet"])
    kol["sidecar"] = str(aday[-1])
    return kol


def _tek_kol(kol_adi: str) -> dict | None:
    yol = SIDECAR_DIR / f"_tek_devset_plan2_{kol_adi}.json"
    d = json.loads(yol.read_text(encoding="utf-8"))
    if not d.get("tetik", True):
        return None
    return d.get("sonuc")


def main() -> int:
    arms = {}
    arms["heightmap"] = _sidecar_kol("asama2_plan2_heightmap")
    arms["nfv_fast"] = {
        "hata": ("BEKCI: private 14.9GB > 12.0GB (takas) - kol iptal, 1380s"
                 " [AC-08 kanopi bellek bombasi]")}
    arms["nfv_max"] = {
        "hata": ("BEKCI: private 14.1GB > 12.0GB (takas) - kol iptal, 4740s"
                 " [AC-08 kanopi bellek bombasi]")}
    for k in ("kafes", "kafes_duruskoru"):
        kol = _tek_kol(k)
        if kol is not None:
            arms[k] = kol
    et = etiket_hesapla(arms, 2.0)
    inst = json.loads(  # n_total icin bugunku plan2 satiri
        [s for s in OUT_ETIKET.read_text(encoding="utf-8").splitlines()
         if '"devset_plan2"' in s][-1])
    satir = {"ts": time.time(), "instance_id": "devset_plan2",
             "aile": "devset_plan2", "seed": 42, "scale": "gercek",
             "n_total": inst["n_total"], "clearance_req_mm": 2.0,
             "duzeltme": "2026-08-30 kafes rot-sokum hukmu (P-4.3)",
             "arms": arms, **et}
    with OUT_ETIKET.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(satir, ensure_ascii=True) + "\n")
    print(f"DUZELTILMIS plan2 etiketi: winner={et['winner_mode']} "
          f"n_legal={et['n_legal']} regret={et['regret_mm']}")
    print(f"invalid={et['invalid_reasons']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
