"""runtime/quantity_text_parser.py — Mail govdesinden parca-adet eslemesi.

Hocanin gercek maili su formatta gelir (her satir bir parca):

    Merhabalar Hocam,

    Plan1

    ENG-500053_L-Bracket 22 adet
    811793-1 20 adet
    TAPER-GAUGE-1 10 adet
    ...
    baseplate_v2 1 adet

    Iyi calismalar,
    Saygilarimla.

Her parca satiri:  <parca_adi> <sayi> adet
Parca adi = ZIP icindeki <ad>.stl dosyasinin uzantisiz adi (birebir).
Selamlama / baslik / imza satirlari (adet icermeyen) ATLANIR.

Tasarim: DETERMINISTIK birincil yol (regex). Bu format cok duzenli oldugundan
LLM gerekmez -- LLM yalniz format bozulursa fallback olarak dusunulur (ayri
katman; bu modul saf deterministik + yan etkisiz). Determinizm: ayni metin ->
ayni dict.
"""

from __future__ import annotations

import logging
import re
from typing import Dict

logger = logging.getLogger(__name__)

# Satir: "<ad> <sayi> adet"  — ad bosluk icerebilir (non-greedy), sayi tam,
# "adet" kelimesi zorunlu (TR siparis dili). Sonrasi serbest (nokta vs).
_QTY_LINE = re.compile(r"^(?P<ad>.+?)\s+(?P<adet>\d+)\s*adet\b", re.IGNORECASE)

# Fix-1 (CRITICAL): mail govdesinde "<ad> 999999999 adet" gibi sinirsiz bir
# sayi pipeline'i OOM'a dusurebilirdi. bkz. src/llm/roles/parser.py MAX_QTY
# (ayni deger, ayni gerekce).
MAX_QTY = 5000


def parse_quantities(text: str) -> Dict[str, int]:
    """Mail govdesinden {parca_adi: adet} eslemesi cikar.

    Args:
        text: Mail govdesi (duz metin).

    Returns:
        Ekleme sirasini koruyan dict {parca_adi: adet}. Adet iceren satir yoksa
        bos dict. Ayni ad birden cok satirda gecerse adetler TOPLANIR (ayni
        parca iki satirda boluunmus olabilir).
    """
    result: Dict[str, int] = {}
    for line in text.splitlines():
        m = _QTY_LINE.match(line.strip())
        if not m:
            continue
        ad = m.group("ad").strip()
        adet = int(m.group("adet"))
        if not ad or adet <= 0:
            continue
        if adet > MAX_QTY:
            logger.warning(
                "quantity_text_parser: '%s' adeti asiri buyuk (%d, izin verilen "
                "ust sinir %d) — clamp'lendi.",
                ad, adet, MAX_QTY,
            )
            adet = MAX_QTY
        result[ad] = result.get(ad, 0) + adet
    return result
