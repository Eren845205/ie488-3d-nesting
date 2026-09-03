# -*- coding: utf-8 -*-
"""a2_p23_karantina.py — devset_plan2 + devset_plan3 etiketlerini KARANTINAYA
al (2026-08-31 cozum plani Paket C; Eren onayli plan).

Gerekce: iki satir da AC-08 (kanopi zinciri bellek bombasi) altinda olculdu —
NFV kollari olculemedi; p3 "winner=heightmap" satiri egitime girerse model
yanlis ogrenir (plan3 NFV 08-04 kaydi 607,5 LEGAL). Append-only desen
(a2_plan2_etiket_duzelt gibi): mevcut son satirin kopyasi `karantina` alaniyla
eklenir; kopru (m4_koprusu) bu satiri atlar. AC-08 fix'i sonrasi kampanya
taze satir yazinca karantina otomatik kalkar. SAF ASCII stdout.

Kosum: python -m scripts.a2_p23_karantina
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import OUT_ETIKET  # noqa: E402

SEBEP = ("AC-08 kanopi bellek bombasi altinda olculdu (NFV kollari "
         "olculemedi) - fix sonrasi yeniden olcum bekliyor (plan Paket C, "
         "2026-08-31)")


def main() -> int:
    satirlar = [json.loads(l) for l in
                OUT_ETIKET.read_text(encoding="utf-8").splitlines()
                if l.strip()]
    son = {}
    for s in satirlar:
        son[(s.get("instance_id"), s.get("scale"))] = s
    n = 0
    with OUT_ETIKET.open("a", encoding="utf-8") as fh:
        for iid in ("devset_plan2", "devset_plan3"):
            s = son.get((iid, "gercek"))
            if s is None:
                print(f"UYARI: {iid} satiri yok - atlandi")
                continue
            if s.get("karantina"):
                print(f"{iid}: zaten karantinada - atlandi")
                continue
            yeni = dict(s)
            yeni["karantina"] = SEBEP
            yeni["ts"] = time.time()
            fh.write(json.dumps(yeni, ensure_ascii=True) + "\n")
            n += 1
            print(f"{iid}: KARANTINA satiri eklendi")
    print(f"bitti: {n} satir eklendi -> {OUT_ETIKET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
