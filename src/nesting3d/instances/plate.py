"""plate.py — Plaka (konteyner taban) cozum politikasi. TEK kaynak.

Kullanici karari (2026-06-20): SABIT default plaka YOK. Algoritma her zaman
(mail, numune, dogrudan pipeline cagrisi — fark etmez) su politikayi uygular:

  * Gercek plaka acikca verilirse  -> o kullanilir (fiziksel yazici kisiti;
    parca sigmazsa nesting uyarir — gercek hayatta dogru davranis).
  * Verilmezse (None)              -> plaka eldeki PARCALARDAN otomatik turetilir.
  * Bir boyut verilip digeri None  -> verilen korunur, None olan otomatik.

Bu modul cekirdek nesting katmanindadir; build_instance_from_order (mail yolu)
ve run_pipeline (tum pipeline) ayni mantigi buradan paylasir.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple

# En buyuk parca kenarini sigdiran kare tabana guvenlik payi.
# Oransal kisim (%2) buyuk parcada olcekli kalir; ANCAK kucuk parcada %2 birkaç
# mm eder ve voxel/pitch yuvarlamasi parcayi plakadan tasirir -> "parca plakadan
# buyuk" hatasi. Bu yuzden EN AZ sabit bir taban pay (AUTO_PLATE_MIN_PAD_MM)
# uygulanir: pay = max(longest*%2, MIN_PAD). Boylece hem buyuk parcada sismez
# (gercek yazici tabanina yakin kalir) hem kucuk parcada pitch-guvenli olur.
AUTO_PLATE_MARGIN = 1.02
AUTO_PLATE_MIN_PAD_MM = 10.0
# Parca yoksa (bos instance) anlamli plaka turetilemez -> notr fallback.
EMPTY_PLATE_FALLBACK = 335.0


def auto_plate_side(part_dims: Iterable[Tuple[Optional[float], Optional[float], Optional[float]]]) -> float:
    """Parca boyutlarindan (w, d, h) otomatik kare plaka kenari (mm) turet.

    Guvenli alt sinir: en buyuk tek parca kenarini sigdiran kare. En uzun kenar
    plakaya yatay sigarsa parca her oryantasyonda yerlesebilir. Sonuca %10 pay
    eklenir. Parca yoksa EMPTY_PLATE_FALLBACK.
    """
    longest = 0.0
    for dims in part_dims:
        for v in dims:
            if v and v > longest:
                longest = float(v)
    if longest <= 0.0:
        return EMPTY_PLATE_FALLBACK
    pad = max(longest * (AUTO_PLATE_MARGIN - 1.0), AUTO_PLATE_MIN_PAD_MM)
    return round(longest + pad, 1)


def resolve_container(
    container_cfg: Optional[Dict[str, object]],
    part_dims: Iterable[Tuple[Optional[float], Optional[float], Optional[float]]],
) -> Tuple[float, float, Optional[float], bool]:
    """Plaka politikasini uygula; (width_mm, depth_mm, height_mm, plate_auto) dondur.

    container_cfg: {"width_mm", "depth_mm", "height_mm"} dict veya None.
                   width/depth None/eksikse o boyut parcalardan otomatik turetilir.
    part_dims:     otomatik turetim icin parca (w, d, h) listesi.
    plate_auto:    True ise en az bir taban boyutu otomatik turetildi.
    """
    cfg = container_cfg or {}
    w = cfg.get("width_mm")
    d = cfg.get("depth_mm")
    h = cfg.get("height_mm")

    plate_auto = w is None or d is None
    if plate_auto:
        # part_dims tek-gecislik olabilir -> listeye al (iki boyut da None ise tekrar gerekir)
        dims_list = list(part_dims)
        side = auto_plate_side(dims_list)
        if w is None:
            w = side
        if d is None:
            d = side

    return float(w), float(d), (float(h) if h is not None else None), plate_auto
