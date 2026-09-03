"""intent_router.py -- Deterministik niyet-yonlendirici (saf fonksiyon, LLM YOK).

Soru metnindeki anahtar kelimeler -> rol secimi.

Kural tablosu:
  - "ozet|rapor|teklif|yonetici"            -> report
  - "neden|nicin|hangi algoritma|nasil secil|
     fiyat nereden|oncelik neden|nasil belirl|
     nasil hesap|nasil karar"               -> explainer
        - "algoritma|yontem|nasil secil"       -> karar_tipi=algoritma
        - "fiyat|ucret|maliyet"                -> karar_tipi=fiyat
        - "oncelik|sira|hangi once"            -> karar_tipi=oncelik
        - varsayilan                           -> karar_tipi=algoritma
  - eslesme yok                              -> assistant (default)

Explainer tetikleyicileri yalnizca belgelenmis spesifik desenlerle eslenir;
"nasil X" catch-all kullanilmaz (MED-3: asiri genis esleme onceden kaldirildi).

Bu modul:
  - Saf fonksiyon: yan etki yok, import harici bagimliligi yok.
  - LLM cagirisi yapmaz.
  - §6.1: Yeni matematik / karar uretmez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

RolAdi = Literal["report", "explainer", "assistant"]
KararTipi = Literal["algoritma", "fiyat", "oncelik"]


@dataclass(frozen=True)
class Intent:
    """Niyet-yonlendirici sonucu.

    Alanlar
    -------
    rol        : secilen LLM rolu
    karar_tipi : explainer rolunde aciklanacak karar kategorisi (diger rollerde None)
    """

    rol: RolAdi
    karar_tipi: Optional[KararTipi] = None


# ---------------------------------------------------------------------------
# Anahtar kelime setleri
# ---------------------------------------------------------------------------

_REPORT_PATTERNS = re.compile(
    r"\b(ozet|ozetle|rapor|teklif|yonetici)\b",
    re.IGNORECASE | re.UNICODE,
)

_EXPLAINER_TRIGGER_PATTERNS = re.compile(
    # Trailing \b omitted: multi-token stems like "nasil secil(di)" need prefix match.
    r"\b(neden|nicin|nasil\s+secil|hangi\s+algoritma|fiyat\s+nereden|"
    r"oncelik\s+neden|nasil\s+belirl|nasil\s+hesap|nasil\s+karar)",
    re.IGNORECASE | re.UNICODE,
)

_KARAR_ALGORITMA = re.compile(
    r"\b(algoritma|yontem|nasil\s+secil|hangi\s+cozuc)\b",
    re.IGNORECASE | re.UNICODE,
)

_KARAR_FIYAT = re.compile(
    r"\b(fiyat|ucret|maliyet|fiyatlandirma|nereden\s+geldi)\b",
    re.IGNORECASE | re.UNICODE,
)

_KARAR_ONCELIK = re.compile(
    r"\b(oncelik|sira|once|hangi\s+once|neden\s+once)\b",
    re.IGNORECASE | re.UNICODE,
)


def route_intent(soru: str) -> Intent:
    """Soru metnini analiz ederek uygun rol ve karar_tipi'ni belirler.

    Bu saf fonksiyon LLM cagirisi yapmaz. Deterministik anahtar kelime
    eslestirimesiyle calisir.

    Parametreler
    ------------
    soru : Operatorun girdigi serbest soru metni

    Donus
    -----
    Intent(rol, karar_tipi)
    """
    metin = (soru or "").strip()

    # 1. Oncelik: rapor/ozet anahtar kelimeleri
    if _REPORT_PATTERNS.search(metin):
        return Intent(rol="report", karar_tipi=None)

    # 2. Aciklayici tetikleyiciler
    if _EXPLAINER_TRIGGER_PATTERNS.search(metin):
        karar_tipi = _infer_karar_tipi(metin)
        return Intent(rol="explainer", karar_tipi=karar_tipi)

    # 3. Varsayilan: genel asistan
    return Intent(rol="assistant", karar_tipi=None)


def _infer_karar_tipi(metin: str) -> KararTipi:
    """Aciklayici modunda hangi karar tipinin soruldugunu cozumler."""
    if _KARAR_FIYAT.search(metin):
        return "fiyat"
    if _KARAR_ONCELIK.search(metin):
        return "oncelik"
    # Varsayilan: algoritma
    return "algoritma"
