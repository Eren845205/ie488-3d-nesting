# -*- coding: utf-8 -*-
"""arsiv_glb_cikar.py — arsiv rehberli-sokum HTML'lerindeki gomulu GLB'yi
cikarip kalici gecmis deposuna yazar (viewer arsiv kayitlarinda da calissin).

Eren istegi 2026-08-17: Job History'de arsiv kaydina tiklayinca yerlesimin
3D goruntusu de gorunsun. Kaynak: data/otonom_gecmis/arsiv/*.html icindeki
`var __GLB_B64__ = "..."` (rehberli_sokum_template gomusu) + ayni HTML'in
VERI JSON'undaki meta (n_parca). Idempotent: detay kaydi olan kayit atlanir.
"""
import base64
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from src.runtime.otonom_gecmis import OtonomGecmisStore  # noqa: E402

GECMIS = _ROOT / "data" / "otonom_gecmis"
store = OtonomGecmisStore(GECMIS)

kayitlar = []
for ln in (GECMIS / "gecmis.jsonl").read_text(encoding="utf-8").splitlines():
    if ln.strip():
        kayitlar.append(json.loads(ln))

for k in kayitlar:
    dosya = k.get("arsiv_html")
    if not dosya:
        continue
    kid = k["id"]
    if store.detay_get(kid) is not None:
        print(f"atlandi (detay var): {k['musteri']}")
        continue
    yol = GECMIS / "arsiv" / dosya
    if not yol.exists():
        print(f"UYARI: arsiv HTML yok: {dosya}")
        continue
    html = yol.read_text(encoding="utf-8")

    m = re.search(r'var __GLB_B64__ = "([A-Za-z0-9+/=]+)"', html)
    if not m:
        print(f"UYARI: gomulu GLB bulunamadi: {dosya}")
        continue
    glb = base64.b64decode(m.group(1))

    # meta.n_parca — HTML'deki veri JSON'undan (yoksa None kalir)
    n_parca = None
    m2 = re.search(r'"n_parca"\s*:\s*(\d+)', html)
    if m2:
        n_parca = int(m2.group(1))

    store.glb_kaydet(kid, "B001", glb)
    detay = {
        "nesting_results": {"B001": {
            "height_mm": k.get("min_yukseklik_mm"),
            **({"n_parts": n_parca} if n_parca else {}),
        }},
        "pricing_results": {},
        "ranked_orders": [],
        "batches": [],
        "warnings": [],
        "elapsed_sec": 0.0,
        "glb": {"B001": True},
    }
    store.detay_kaydet(kid, detay)
    print(f"YAZILDI: {k['musteri']} — GLB {len(glb)/1e6:.1f}MB, "
          f"n_parca={n_parca}, h={k.get('min_yukseklik_mm')}")

print("BITTI")
