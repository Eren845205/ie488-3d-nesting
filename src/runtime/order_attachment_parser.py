"""src/runtime/order_attachment_parser.py — Deterministik ek parser modulu.

Sorumluluk: mail ekindeki .xlsx / .csv dosyasini yapilandirilmis parca
listesine donusturmek. LLM KULLANILMAZ — saf deterministik.

Fonksiyon
---------
  parse_order_attachment(dosya_adi, icerik) -> List[dict]
    dosya_adi : ek dosya adi (uzanti kontrolu icin, orn. "siparis.xlsx")
    icerik    : ham bayt dizisi
    dondurur  : SCENARIO parcasiyla uyumlu dict listesi
                [{name, width_mm, depth_mm, height_mm, qty, source}, ...]
                Taninamayan format veya baslik -> bos liste + uyari log.

Esnek baslik esleme (Turkce + Ingilizce, buyuk/kucuk harf duyarsiz)
----------------------------------------------------------------------
  Ad    : ad, isim, name
  En    : en, en_mm, genislik, width, width_mm
  Boy   : boy, boy_mm, derinlik, depth, depth_mm
  Yuksek: yukseklik, yukseklik_mm, height, height_mm
  Adet  : adet, miktar, qty, quantity

Kural: LLM YOK; halusinasyon riski yok (kesintisiz kural SS6.1).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Baslik esleme tablosu (alias -> canonical)
# ---------------------------------------------------------------------------

_NAME_ALIASES = {"ad", "isim", "name", "parca_adi", "parca_ismi", "part_name"}
_WIDTH_ALIASES = {"en", "en_mm", "genislik", "width", "width_mm", "w_mm", "w"}
_DEPTH_ALIASES = {"boy", "boy_mm", "derinlik", "depth", "depth_mm", "d_mm", "d"}
_HEIGHT_ALIASES = {"yukseklik", "yukseklik_mm", "height", "height_mm", "h_mm", "h"}
_QTY_ALIASES = {"adet", "miktar", "qty", "quantity", "adet_no", "count"}

_EKSIK_BOYUT = 1.0   # mm — eksik boyut icin placeholder
MAX_ROWS = 10_000    # Fix-2: xlsx/csv satir sayisi ust siniri (zip-bomb / asiri bellek)
# Fix-1 (CRITICAL): 'adet' sutunu sinirsizdi -- bozuk/kotu niyetli ek dosyasi
# asiri buyuk adet ile pipeline'i OOM'a dusurebilirdi. bkz. src/llm/roles/parser.py
# MAX_QTY (ayni deger, ayni gerekce — endustriyel siparislerde gercekci ust sinir).
MAX_QTY = 5000


def _resolve_headers(raw_headers: List[str]) -> Dict[str, str]:
    """Ham baslik listesini canonical alanlarla esler.

    Dondurur: {canonical_field -> raw_header} sozlugu.
    Ornk: {"name": "isim", "width_mm": "en_mm", ...}
    """
    mapping: Dict[str, str] = {}
    for h in raw_headers:
        h_norm = (h or "").strip().lower().replace(" ", "_")
        if h_norm in _NAME_ALIASES and "name" not in mapping:
            mapping["name"] = h
        elif h_norm in _WIDTH_ALIASES and "width_mm" not in mapping:
            mapping["width_mm"] = h
        elif h_norm in _DEPTH_ALIASES and "depth_mm" not in mapping:
            mapping["depth_mm"] = h
        elif h_norm in _HEIGHT_ALIASES and "height_mm" not in mapping:
            mapping["height_mm"] = h
        elif h_norm in _QTY_ALIASES and "qty" not in mapping:
            mapping["qty"] = h
    return mapping


def _safe_float(val: Any, default: float = _EKSIK_BOYUT) -> float:
    """Degerden float uret; basarisiz olursa default dondur."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 1) -> int:
    """Degerden int uret; basarisiz olursa default dondur.

    Fix-1: MAX_QTY ustundeki degerler clamp'lenir (asiri buyuk adet -> OOM riski).
    """
    try:
        v = int(float(val))
    except (TypeError, ValueError):
        return default
    if v > MAX_QTY:
        logger.warning(
            "order_attachment_parser: adet asiri buyuk (%d, izin verilen ust "
            "sinir %d) — clamp'lendi.",
            v, MAX_QTY,
        )
        return MAX_QTY
    return v


def _rows_to_parts(
    rows: List[Dict[str, Any]],
    mapping: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Satir listesini SCENARIO parca dict listesine donusturur."""
    parts: List[Dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        raw_name = row.get(mapping.get("name", ""), f"parca_{i}")
        name = str(raw_name).strip() if raw_name else f"parca_{i}"
        # Fix-5: uzunluk siniri + kontrol karakterlerini ayıkla
        name = re.sub(r"[\x00-\x1f\x7f]", "", name)[:256] or f"parca_{i}"

        width_mm = _safe_float(row.get(mapping.get("width_mm", ""), _EKSIK_BOYUT))
        depth_mm = _safe_float(row.get(mapping.get("depth_mm", ""), _EKSIK_BOYUT))
        height_mm = _safe_float(row.get(mapping.get("height_mm", ""), _EKSIK_BOYUT))
        qty = _safe_int(row.get(mapping.get("qty", ""), 1))

        parts.append({
            "id": f"att_{i}",
            "name": name,
            "qty": qty,
            "source": "box",
            "width_mm": width_mm,
            "depth_mm": depth_mm,
            "height_mm": height_mm,
        })
    return parts


# ---------------------------------------------------------------------------
# Excel parse
# ---------------------------------------------------------------------------

def _parse_xlsx(icerik: bytes) -> List[Dict[str, Any]]:
    """openpyxl ile .xlsx dosyasindan parca listesi cikar.

    Bozuk dosya veya taninamayan baslik -> bos liste + uyari log.
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("order_attachment_parser: openpyxl yuklu degil — xlsx parse atlandi.")
        return []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(icerik), read_only=True, data_only=True)
        ws = wb.active
        # Fix-2: MAX_ROWS+1 satir okumak yeterli (baslik + veri); fazlasini atla
        all_rows = []
        for _row in ws.iter_rows(values_only=True):
            all_rows.append(_row)
            if len(all_rows) > MAX_ROWS + 1:
                logger.warning(
                    "order_attachment_parser: xlsx satir sayisi MAX_ROWS (%d) asildi — kesiliyor.",
                    MAX_ROWS,
                )
                break
    except Exception as exc:
        logger.warning("order_attachment_parser: xlsx acma hatasi — %s", exc)
        return []

    if not all_rows:
        logger.warning("order_attachment_parser: xlsx bos — satir yok.")
        return []

    raw_headers = [str(cell) if cell is not None else "" for cell in all_rows[0]]
    mapping = _resolve_headers(raw_headers)

    if not mapping:
        logger.warning(
            "order_attachment_parser: xlsx basliklarinda taninan alan yok — %s",
            raw_headers,
        )
        return []

    data_rows: List[Dict[str, Any]] = []
    for row in all_rows[1:]:
        if not any(cell is not None for cell in row):
            continue  # bos satir atla
        data_rows.append(
            {raw_headers[j]: (row[j] if j < len(row) else None)
             for j in range(len(raw_headers))}
        )

    return _rows_to_parts(data_rows, mapping)


# ---------------------------------------------------------------------------
# CSV parse
# ---------------------------------------------------------------------------

def _parse_csv(icerik: bytes) -> List[Dict[str, Any]]:
    """csv modulu ile .csv dosyasindan parca listesi cikar.

    Bos veya taninamayan baslik -> bos liste + uyari log.
    """
    try:
        text = icerik.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("order_attachment_parser: csv decode hatasi — %s", exc)
        return []

    if not text.strip():
        logger.warning("order_attachment_parser: csv bos icerik.")
        return []

    try:
        reader = csv.DictReader(io.StringIO(text))
        raw_headers = list(reader.fieldnames or [])
        if not raw_headers:
            logger.warning("order_attachment_parser: csv baslik satiri bos.")
            return []

        mapping = _resolve_headers(raw_headers)
        if not mapping:
            logger.warning(
                "order_attachment_parser: csv basliklarinda taninan alan yok — %s",
                raw_headers,
            )
            return []

        # Fix-2: MAX_ROWS satir siniri
        data_rows = []
        for _r in reader:
            data_rows.append(_r)
            if len(data_rows) >= MAX_ROWS:
                logger.warning(
                    "order_attachment_parser: csv satir sayisi MAX_ROWS (%d) asildi — kesiliyor.",
                    MAX_ROWS,
                )
                break
    except Exception as exc:
        logger.warning("order_attachment_parser: csv parse hatasi — %s", exc)
        return []

    return _rows_to_parts(data_rows, mapping)


# ---------------------------------------------------------------------------
# Ana API
# ---------------------------------------------------------------------------

def parse_order_attachment(
    dosya_adi: str,
    icerik: bytes,
) -> List[Dict[str, Any]]:
    """Ek dosyasini parse ederek parca listesi dondurur.

    Parametreler
    ------------
    dosya_adi : ek dosya adi — uzanti belirleme icin kullanilir
    icerik    : ham bayt dizisi

    Dondurur
    --------
    List[dict] — SCENARIO parca formatiyla uyumlu:
      [{id, name, qty, source, width_mm, depth_mm, height_mm}, ...]
    Taninamayan format veya baslik -> bos liste (istisna firlatmaz).

    LLM KULLANILMAZ — deterministik (SS6.1).
    """
    ext = (dosya_adi or "").rsplit(".", 1)[-1].lower()

    if ext in ("xlsx", "xls", "xlsm"):
        return _parse_xlsx(icerik)
    elif ext == "csv":
        return _parse_csv(icerik)
    else:
        logger.warning(
            "order_attachment_parser: bilinmeyen uzanti '.%s' — parse atlandi.", ext
        )
        return []
