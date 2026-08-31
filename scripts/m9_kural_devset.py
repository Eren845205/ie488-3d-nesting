# -*- coding: utf-8 -*-
"""m9_kural_devset.py — M9-fix-1: dev-set instance'lari icin GERCEK uretim
KURALININ kararlarini uret ve `results/regret_raporu.json`'a devset anahtari
ile ekle (2026-08-31; ASAMA2_KAPI_RAPORU §3 artefakti: kural_map'te devset
anahtari yoktu -> RuleAdapter heightmap-default'a dustu, KURAL satiri sahte).

Karar baglami ETIKET KOSULLARIYLA AYNI: no-go/pin YOK, mode_model YOK
(saf kural; model katkisi zaten ayri adaylarda olculuyor), rot_sokum=True
(uretim dunyasi, Eren 2026-07-15). Arm adi esleme (m4_koprusu ile ayni):
mode=heightmap -> "heightmap"; mode=nfv & quality=max -> "nfv_max";
mode=nfv (fast/None) -> "nfv_kalite".

Kosum: python -m scripts.m9_kural_devset   SAF ASCII stdout.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import FAMILY_BUILDERS  # noqa: E402
from src.nesting3d.adaptive_params import predict_nfv_benefit  # noqa: E402

RR = _ROOT / "results" / "regret_raporu.json"
SETLER = ("plan1", "plan2", "plan3", "deneme4", "deneme5")


def _arm_adi(dec) -> str:
    if getattr(dec, "mode", "heightmap") != "nfv":
        return "heightmap"
    q = getattr(dec, "nfv_quality", None) or "fast"
    return "nfv_max" if q == "max" else "nfv_kalite"


def main() -> int:
    rj = json.loads(RR.read_text(encoding="utf-8"))
    setler = rj.setdefault("setler", {})
    for s in SETLER:
        aile = f"devset_{s}"
        uid = f"{aile}@gercek"
        t0 = time.time()
        inst = FAMILY_BUILDERS[aile](42, "gercek", None)
        dec = predict_nfv_benefit(inst, family_routing=True, mode_model=None,
                                  rot_sokum=True, no_go_bounds=None)
        arm = _arm_adi(dec)
        setler[uid] = {
            "kural_arm": arm,
            "kural_mode": getattr(dec, "mode", None),
            "kural_quality": getattr(dec, "nfv_quality", None),
            "kural_gerekce": str(getattr(dec, "reason", ""))[:200],
            "kaynak": "m9_kural_devset 2026-08-31 (etiket-kosullari: "
                      "no-go yok, model yok, rot_sokum=True)",
        }
        print(f"{uid:26s} kural_arm={arm:12s} "
              f"({time.time()-t0:.0f}s; gerekce: "
              f"{str(getattr(dec, 'reason', ''))[:80]})")
    RR.write_text(json.dumps(rj, indent=1, ensure_ascii=True),
                  encoding="utf-8")
    print(f"regret_raporu.json guncellendi ({len(setler)} anahtar)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
