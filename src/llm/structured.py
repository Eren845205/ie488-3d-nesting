"""Yapilandirilmis cikti zinciri — PLAN_LLM.md L0.5.

Akis:
  LLM metin ciktisi
    -> tolerant_json_extract()   (```json blok -> ilk {...})
    -> jsonschema.validate()
    -> ValidationResult: VALID | PARTIAL | INVALID
    -> INVALID ise onar-retry (dogrulama hatalari prompt'a eklenir, max schema_retry)
    -> hala INVALID -> HumanFallback

Uc ValidationStatus:
  VALID   : sem ema tamamen gecerli
  PARTIAL : yalniz opsiyonel alanlar eksik; gerekli alanlar tam
  INVALID : gerekli alan eksik veya tip hatasi

Kural: asla sessiz gecis, asla uydurma default.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from src.llm.provider import LLMResponse as _LLMResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# jsonschema opsiyonel import
# ---------------------------------------------------------------------------
#
# Fix-3 (HIGH): jsonschema yoksa _minimal_validate SESSIZCE yalniz alan
# VARLIGINA bakar, tip/format/enum kisitlarini dogrulamaz — bu sessiz bir
# guvenlik zayiflamasidir. Boot/ilk-kullanimda GORUNUR uyari (logger.warning
# + stderr print, logging config'inden bagimsiz olarak) verilir; jsonschema
# artik requirements.txt'de listelidir.
#
# NOT (test edilebilirlik): tespit ayri bir fonksiyona (_detect_jsonschema)
# cikarildi ki testler modulu importlib.reload() ETMEDEN ImportError dalini
# dogrudan cagirabilsin — reload, bu modulden once dataclass import etmis
# diger test modullerinde isinstance() kontrollerini kirar (sinif kimligi
# degisir), bu yuzden kacinilmalidir.

_JSONSCHEMA_MISSING_WARNING = (
    "jsonschema paketi yuklu degil -- yapisal (tip/format/enum) dogrulama "
    "ZAYIFLADI: _minimal_validate yalniz zorunlu-alan VARLIGINI kontrol eder, "
    "TIP KISITLARINI dogrulamaz. Uretimde 'pip install jsonschema' ile kurun "
    "(requirements.txt icinde listelidir)."
)


def _detect_jsonschema() -> bool:
    """jsonschema import edilebilir mi kontrol eder; edilemezse GORUNUR uyari verir.

    Basarili: modul-seviyesi 'jsonschema' adini baglar, True doner.
    Basarisiz (ImportError): logger.warning + stderr print (logging config'inden
    bagimsiz garanti gorunurluk), False doner. Sessiz zayiflama YOK.
    """
    try:
        import jsonschema as _jsonschema_mod
    except ImportError:
        logger.warning(_JSONSCHEMA_MISSING_WARNING)
        print(f"[UYARI] {_JSONSCHEMA_MISSING_WARNING}", file=sys.stderr)
        return False
    globals()["jsonschema"] = _jsonschema_mod
    return True


_HAS_JSONSCHEMA = _detect_jsonschema()


def jsonschema_available() -> bool:
    """jsonschema paketinin yuklu olup olmadigini dondurur (boot-check/test icin)."""
    return _HAS_JSONSCHEMA


# ---------------------------------------------------------------------------
# ValidationStatus
# ---------------------------------------------------------------------------


class ValidationStatus(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    INVALID = "INVALID"


# ---------------------------------------------------------------------------
# HumanFallback
# ---------------------------------------------------------------------------


@dataclass
class HumanFallback:
    """Tum retry'larin basarisiz olmasi durumunda uretilen fallback nesnesi.

    Alanlar
    -------
    raw_text   : LLM'nin son ham metin ciktisi
    errors     : son dogrulama hata mesajlari
    call_ref   : audit ref (role_tag + timestamp + sequence)
    """

    raw_text: str
    errors: List[str]
    call_ref: str = ""


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """JSON dogrulama ciktisi."""

    status: ValidationStatus
    data: Optional[Dict[str, Any]]  # VALID/PARTIAL ise dolu, INVALID ise None
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# JSON cikartici
# ---------------------------------------------------------------------------


def tolerant_json_extract(text: str) -> Optional[Dict[str, Any]]:
    """LLM ciktisindan JSON objesini cikartir.

    Deneme sirasi:
    1. ```json ... ``` bloku
    2. Ilk { ... } bulgusu (agressive extract)
    3. Ham metni dogrudan json.loads
    """
    # 1. ```json blok
    block_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if block_match:
        candidate = block_match.group(1).strip()
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed

    # 2. Dengeli kume parantezi taramasi (balanced-brace scan)
    # Greedy r"\{.*\}" yerine: ilk '{' den baslayip sayacla dengeli kapanisi bul.
    # Birden fazla JSON blogu varsa her birini sirayla dener, ilk gecerlisini alir.
    for candidate in _extract_brace_candidates(text):
        parsed = _try_parse(candidate)
        if parsed is not None:
            return parsed

    # 3. Ham metin
    return _try_parse(text.strip())


def _extract_brace_candidates(text: str) -> List[str]:
    """Metindeki dengeli kume parantezi bloklarini cikartir.

    Her '{' konumundan baslayip sayacla kapanisi bulur; tum bloklari dondurur
    (ic ice ve arka arkaya yapilar icin).
    Ornek: 'abc {"a":1} xyz {"b":2}' -> ['{"a":1}', '{"b":2}']
    """
    candidates: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "{":
            depth = 0
            in_string = False
            escape_next = False
            for j in range(i, n):
                ch = text[j]
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[i : j + 1])
                        i = j + 1
                        break
            else:
                # Kapanmayan brace — geri kalan metin, daha ilerleme
                break
        else:
            i += 1
    return candidates


def _try_parse(text: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ---------------------------------------------------------------------------
# Dogrulayici
# ---------------------------------------------------------------------------


def validate_against_schema(
    data: Dict[str, Any],
    schema: Dict[str, Any],
) -> ValidationResult:
    """data'yi schema'ya gore dogrular, ValidationResult dondurur.

    PARTIAL kurali: schema'da 'required' listesi var ama data bazi opsiyonel
    alanlari tasimiyor -> PARTIAL.
    REQUIRED alan eksikse veya tip hatasi varsa -> INVALID.
    """
    if not _HAS_JSONSCHEMA:
        # jsonschema yoksa sadece required kontrol (minimal fallback)
        return _minimal_validate(data, schema)

    errors: List[str] = []
    validator = jsonschema.Draft7Validator(schema)
    for error in validator.iter_errors(data):
        errors.append(error.message)

    if not errors:
        return ValidationResult(status=ValidationStatus.VALID, data=data)

    # PARTIAL mi INVALID mi?
    required_fields = set(schema.get("required", []))
    invalid_required = any(
        _is_required_field_error(e, required_fields, schema) for e in validator.iter_errors(data)
    )
    if invalid_required:
        return ValidationResult(
            status=ValidationStatus.INVALID, data=None, errors=errors
        )
    # Yalniz opsiyonel alanlar eksik
    return ValidationResult(
        status=ValidationStatus.PARTIAL, data=data, errors=errors
    )


def _is_required_field_error(error: Any, required: set, schema: Dict) -> bool:
    """Hatanin zorunlu bir alana iliskin olup olmadigini kontrol eder.

    INVALID sayilan hata turleri:
      - required: zorunlu alan eksik
      - additionalProperties: sema disinda alan -> guvensiz, INVALID
      - tip/format/enum hatasi zorunlu bir alanda
    """
    if error.validator == "required":
        return True
    # additionalProperties ihlali her zaman INVALID (guvensiz ek alanlar)
    if error.validator == "additionalProperties":
        return True
    # tip hatasi veya format hatasi zorunlu alanlarda -> INVALID
    if error.validator in ("type", "format", "enum"):
        path = list(error.absolute_path)
        if path and str(path[0]) in required:
            return True
    return False


def _minimal_validate(
    data: Dict[str, Any], schema: Dict[str, Any]
) -> ValidationResult:
    """jsonschema yokken minimal zorunlu alan kontrolu."""
    required = schema.get("required", [])
    missing = [f for f in required if f not in data]
    if missing:
        return ValidationResult(
            status=ValidationStatus.INVALID,
            data=None,
            errors=[f"Zorunlu alan eksik: {missing}"],
        )
    return ValidationResult(status=ValidationStatus.VALID, data=data)


# ---------------------------------------------------------------------------
# Yapay-retry + fallback zinciri
# ---------------------------------------------------------------------------


@dataclass
class StructuredChainResult:
    """Zincir sonucu: basarili data VEYA fallback.

    Alanlar
    -------
    last_response : run_structured_chain tarafindan doldurulan son LLMResponse.
                    Geriye uyumlu; None olabilir (zincir hic cagri yapamadiysa).
    """

    status: ValidationStatus
    data: Optional[Dict[str, Any]]
    fallback: Optional[HumanFallback]
    attempt_count: int
    errors: List[str] = field(default_factory=list)
    last_response: Optional[Any] = field(default=None)


def run_structured_chain(
    provider: Any,
    build_request_fn: Any,
    schema: Dict[str, Any],
    max_retry: int = 2,
    call_ref: str = "",
) -> StructuredChainResult:
    """Saglayiciya istek gonder, dogrula, gerekirse yeniden dene.

    Parametreler
    ------------
    provider        : LLMProvider.complete(req) arayuzunu destekler
    build_request_fn: (errors: list[str]) -> LLMRequest
                      Ilk cagri: build_request_fn([])
                      Retry'larda: dogrulama hatalari eklenerek yeniden cagirilir
    schema          : JSON Schema (dogrulama icin)
    max_retry       : maksimum yeniden deneme sayisi
    call_ref        : audit referans kodu

    Dondurur
    --------
    StructuredChainResult — status/data/fallback/attempt_count
    """
    last_text = ""
    last_errors: List[str] = []
    last_resp: Optional[Any] = None

    for attempt in range(max_retry + 1):
        req = build_request_fn(last_errors)
        resp = provider.complete(req)
        last_resp = resp
        last_text = resp.text

        if getattr(resp, "finish_reason", "stop") == "length":
            last_errors = ["Yanıt kesildi (finish_reason=length) — max_tokens artırın veya girdi kısaltın."]
            logger.warning("Deneme %d: finish_reason=length, yanıt kesildi.", attempt + 1)
            continue

        parsed = tolerant_json_extract(last_text)
        if parsed is None:
            last_errors = [f"JSON parse hatasi: gecerli JSON objesi bulunamadi. Metin: {last_text[:200]}"]
            logger.warning("Deneme %d: JSON parse hatasi.", attempt + 1)
            continue

        result = validate_against_schema(parsed, schema)

        if result.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
            return StructuredChainResult(
                status=result.status,
                data=result.data,
                fallback=None,
                attempt_count=attempt + 1,
                errors=result.errors,
                last_response=last_resp,
            )

        last_errors = result.errors
        logger.warning(
            "Deneme %d: schema dogrulama hatasi: %s",
            attempt + 1, last_errors
        )

    # Tum retry'lar basarisiz -> HumanFallback
    fallback = HumanFallback(
        raw_text=last_text,
        errors=last_errors,
        call_ref=call_ref,
    )
    return StructuredChainResult(
        status=ValidationStatus.INVALID,
        data=None,
        fallback=fallback,
        attempt_count=max_retry + 1,
        errors=last_errors,
        last_response=last_resp,
    )
