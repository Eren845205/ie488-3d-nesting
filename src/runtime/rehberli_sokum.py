"""rehberli_sokum.py — Cevrimdisi, tek-dosya "Rehberli Sokum" HTML paketleyici.

build_rehberli_sokum_html(data, glb_bytes) sablonu
(src/webapp/static/rehberli_sokum_template.html) icindeki yer tutuculari
doldurur ve tek bir self-contained HTML string dondurur:
    - operator verisi (adim listesi, kimlik, sipariş ozeti) JSON gomulur,
    - GLB sahnesi base64 gomulur,
    - three.js + GLTFLoader + OrbitControls (repo icindeki ES module
      kaynaklari) base64 + data: URI import-map ile gomulur (CDN YOK,
      yeni bagimlilik YOK).

Sonuc dosya file:// altinda internet/kurulum GEREKMEDEN acilir; hoca
cift tiklayip acar, gozat-hazir olur. Motor koduna (src/nesting3d/)
BAGIMLILIK yok — bu modul yalniz sunum/paketleme katmanidir.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict

_STATIC_DIR = Path(__file__).resolve().parent.parent / "webapp" / "static"
_TEMPLATE_PATH = _STATIC_DIR / "rehberli_sokum_template.html"

_PLACEHOLDER_VERI = "__VERI_JSON__"
_PLACEHOLDER_GLB = "__GLB_BASE64__"
_PLACEHOLDER_THREE = "__THREE_JS_B64__"
_PLACEHOLDER_GLTFLOADER = "__GLTFLOADER_JS_B64__"
_PLACEHOLDER_ORBITCONTROLS = "__ORBITCONTROLS_JS_B64__"
# 2026-07-26 saha hatasi: GLTFLoader './utils/BufferGeometryUtils.js' goreli
# importu blob tabaninda cozulemez ("base scheme isn't hierarchical") — o da
# gomulur ve sablonda blob URL'e yeniden yazilir.
_PLACEHOLDER_BGU = "__BUFFERGEOMUTILS_JS_B64__"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def build_rehberli_sokum_html(data: Dict[str, Any], glb_bytes: bytes) -> str:
    """Rehberli-sokum sablonunu doldurup tam HTML string dondurur.

    data: bkz. modul docstring / gorev sozlesmesi ("meta", "siparisler",
    "adimlar", "kilitli"). glb_bytes: build_result_scene ile uretilen
    GLB sahnesi (ham bytes).
    """
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    three_js = (_STATIC_DIR / "three.min.js").read_bytes()
    gltf_js = (_STATIC_DIR / "GLTFLoader.js").read_bytes()
    orbit_js = (_STATIC_DIR / "OrbitControls.js").read_bytes()
    bgu_js = (_STATIC_DIR / "utils" / "BufferGeometryUtils.js").read_bytes()

    # </script> enjeksiyonuna karsi guvenli hale getir — veri gomulu bir
    # <script type="application/json"> etiketi icinde yasar; HTML ayristirici
    # type'a bakmaksizin "</script" dizisinde etiketi kapatir.
    veri_json = json.dumps(data, ensure_ascii=False).replace("</script", "<\\/script")

    html = template
    html = html.replace(_PLACEHOLDER_VERI, veri_json)
    html = html.replace(_PLACEHOLDER_GLB, _b64(glb_bytes))
    html = html.replace(_PLACEHOLDER_THREE, _b64(three_js))
    html = html.replace(_PLACEHOLDER_GLTFLOADER, _b64(gltf_js))
    html = html.replace(_PLACEHOLDER_ORBITCONTROLS, _b64(orbit_js))
    html = html.replace(_PLACEHOLDER_BGU, _b64(bgu_js))
    return html
