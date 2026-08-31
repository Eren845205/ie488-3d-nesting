# -*- coding: utf-8 -*-
"""m4_kol_tek.py — TEK portfoy kolunu AYRI SURECTE kos (2026-08-30 dersi).

Neden: kampanya tek surecte kol-kol kosunca bellek birikti (plan2'de python
private 14,5 GB; nfv_fast MemoryError, nfv_max takas). Her kol taze surecte
kosar -> bellek isletim sistemine geri doner; bir kolun cokmesi kampanyayi
oldurmez. Sonuc JSON'a yazilir (ebeveyn okur); ham sidecar _kol_kos icinde.

Kullanim (ebeveyn asama2_devset_etiket cagirir; elle de kosulabilir):
  python -m scripts.m4_kol_tek --aile devset_plan2 --kol nfv_fast \\
      --seed 42 --scale gercek --clearance 2.0 --kaynak asama2:plan2 \\
      --out D:/ie488/results/m4_kollar/_tek_plan2_nfv_fast.json
SAF ASCII stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.m4_portfoy_kosu import (  # noqa: E402
    ARMS, FAMILY_BUILDERS, KAFES_ARMS, _kol_kafes, _kol_kos)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aile", required=True)
    ap.add_argument("--kol", required=True,
                    help="heightmap|nfv_fast|nfv_max|kafes|kafes_duruskoru")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", default="gercek")
    ap.add_argument("--clearance", type=float, default=2.0)
    ap.add_argument("--kaynak", default="m4_kol_tek")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    builder = FAMILY_BUILDERS.get(a.aile)
    if builder is None:
        out.write_text(json.dumps({"kol": a.kol, "hata": f"builder yok: {a.aile}"}),
                       encoding="utf-8")
        return 2
    try:
        inst = builder(a.seed, a.scale, None)
    except Exception as exc:
        out.write_text(json.dumps({"kol": a.kol,
                                   "hata": f"instance kurulamadi: {exc}"}),
                       encoding="utf-8")
        return 2

    arm_map = {ad: (mode, q) for ad, mode, q in ARMS}
    kafes_map = dict(KAFES_ARMS)
    sonuc = {"kol": a.kol, "aile": a.aile, "seed": a.seed, "scale": a.scale,
             "n_total": sum(int(p.qty) for p in inst.parts)}
    if a.kol in arm_map:
        mode, q = arm_map[a.kol]
        sonuc["sonuc"] = _kol_kos(inst, mode, q, seed=a.seed, kaynak=a.kaynak)
        sonuc["tetik"] = True
    elif a.kol in kafes_map:
        kol = _kol_kafes(inst, kafes_map[a.kol], a.clearance,
                         kaynak=a.kaynak)
        sonuc["sonuc"] = kol
        sonuc["tetik"] = kol is not None
    else:
        sonuc["hata"] = f"bilinmeyen kol: {a.kol}"
        out.write_text(json.dumps(sonuc), encoding="utf-8")
        return 2
    sonuc["wall_s"] = round(time.time() - t0, 2)
    out.write_text(json.dumps(sonuc, ensure_ascii=True), encoding="utf-8")
    print(f"[m4_kol_tek] {a.aile}/{a.kol} bitti {sonuc['wall_s']}s -> {out}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
