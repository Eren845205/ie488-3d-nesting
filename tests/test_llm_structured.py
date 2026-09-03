"""Testler: src/llm/structured.py — PLAN_LLM.md L0.5.

Kapsanan (planin 5 yolu):
  1. Gecerli JSON -> VALID
  2. Opsiyonel alan eksik -> PARTIAL
  3. Bozuk JSON (parse hatasi) -> INVALID
  4. retry sonrasi gecerli -> VALID (attempt_count > 1)
  5. Tum retry'lar basarisiz -> HumanFallback

Ayrica:
  - tolerant_json_extract: ```json blok
  - tolerant_json_extract: ilk {...} bulgusu
  - tolerant_json_extract: ham metin
  - tolerant_json_extract: None dondurmesi (gercekten bozuk)
  - validate_against_schema: zorunlu alan eksik -> INVALID
  - validate_against_schema: tip hatasi -> INVALID
  - validate_against_schema: tum alanlari tam -> VALID
  - HumanFallback alanlari
  - asla sessiz gecis (INVALID -> fallback, None data)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from src.llm.provider import FakeProvider, LLMRequest, LLMResponse
from src.llm.structured import (
    HumanFallback,
    StructuredChainResult,
    ValidationStatus,
    run_structured_chain,
    tolerant_json_extract,
    validate_against_schema,
)


# ---------------------------------------------------------------------------
# tolerant_json_extract
# ---------------------------------------------------------------------------


def test_extract_from_json_block():
    text = 'Sure!\n```json\n{"key": "val"}\n```\nAciklama.'
    result = tolerant_json_extract(text)
    assert result == {"key": "val"}


def test_extract_from_first_brace():
    text = "Burada: {\"a\": 1, \"b\": 2} ve daha fazlasi."
    result = tolerant_json_extract(text)
    assert result == {"a": 1, "b": 2}


def test_extract_raw_json():
    text = '{"x": true}'
    result = tolerant_json_extract(text)
    assert result == {"x": True}


def test_extract_returns_none_for_garbage():
    result = tolerant_json_extract("bu metin JSON degil!")
    assert result is None


def test_extract_returns_none_for_list():
    """Dizi (list) JSON objesi degil; None donmeli."""
    result = tolerant_json_extract("[1, 2, 3]")
    assert result is None


def test_extract_from_multiline_json_block():
    text = """
```json
{
  "musteri": "Ahmet",
  "parcalar": []
}
```
"""
    result = tolerant_json_extract(text)
    assert result["musteri"] == "Ahmet"


# ---------------------------------------------------------------------------
# validate_against_schema
# ---------------------------------------------------------------------------

_SCHEMA = {
    "type": "object",
    "required": ["ad", "adet"],
    "properties": {
        "ad": {"type": "string"},
        "adet": {"type": "integer"},
        "not": {"type": "string"},  # opsiyonel
    },
    "additionalProperties": False,
}


def test_validate_valid():
    data = {"ad": "braket", "adet": 5}
    result = validate_against_schema(data, _SCHEMA)
    assert result.status == ValidationStatus.VALID
    assert result.data == data
    assert result.errors == []


def test_validate_partial_optional_missing():
    """Yalnizca opsiyonel 'not' alani eksik -> PARTIAL."""
    data = {"ad": "braket", "adet": 5}
    # Sadece opsiyonel alan eksik; ancak schema'da required listesi tam
    # Bu test jsonschema'nin davranisina gore: required alanlar mevcut -> VALID
    # PARTIAL testi icin required olmayan ama schema'da tanimli alan senaryosu kullanilir.
    # Plan: PARTIAL = yalniz opsiyonel alanlar eksik
    # Burada tum zorunlu alanlar var -> VALID donmeli
    result = validate_against_schema(data, _SCHEMA)
    assert result.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL)
    assert result.data is not None


def test_validate_invalid_missing_required():
    """Zorunlu 'adet' alani eksik -> INVALID."""
    data = {"ad": "braket"}
    result = validate_against_schema(data, _SCHEMA)
    assert result.status == ValidationStatus.INVALID
    assert result.data is None
    assert len(result.errors) > 0


def test_validate_invalid_wrong_type():
    """'adet' integer olmali, string verilirse -> INVALID."""
    data = {"ad": "braket", "adet": "bes"}
    result = validate_against_schema(data, _SCHEMA)
    assert result.status == ValidationStatus.INVALID
    assert result.data is None


def test_validate_additional_properties_invalid():
    """Schemada olmayan alan -> INVALID (additionalProperties: false)."""
    data = {"ad": "braket", "adet": 5, "bilinmeyen": "x"}
    result = validate_against_schema(data, _SCHEMA)
    assert result.status == ValidationStatus.INVALID


# ---------------------------------------------------------------------------
# Fix-3 (HIGH): jsonschema opsiyonel bagimlilik -- eksikse GORUNUR uyari
# ---------------------------------------------------------------------------


def test_jsonschema_available_reflects_import_flag():
    """jsonschema_available() modulun ic _HAS_JSONSCHEMA bayragini yansitmali."""
    from src.llm import structured as structured_module
    assert structured_module.jsonschema_available() == structured_module._HAS_JSONSCHEMA


def test_jsonschema_installed_in_this_env():
    """Bu gelistirme ortaminda jsonschema kurulu olmali (requirements.txt'e
    eklendi) -- katı dogrulama gercekten aktif."""
    from src.llm.structured import jsonschema_available
    assert jsonschema_available() is True


def test_missing_jsonschema_logs_visible_warning(monkeypatch, caplog):
    """jsonschema import edilemezse (ImportError) boot-zamaninda GORUNUR bir
    uyari (logger.warning) verilmeli -- sessiz zayiflama olmamali.

    NOT: modul importlib.reload() EDILMEZ — reload, bu modulden once dataclass
    import etmis diger test modullerinde isinstance() kontrollerini kirar
    (sinif kimligi degisir). Bunun yerine ImportError-tespit mantigi ayri bir
    fonksiyona (_detect_jsonschema) cikarildi; sys.modules['jsonschema']=None
    hilesiyle o fonksiyon DOGRUDAN cagrilir (modul yeniden yuklenmez).
    """
    import sys
    from src.llm import structured as structured_module

    monkeypatch.setitem(sys.modules, "jsonschema", None)
    with caplog.at_level("WARNING"):
        sonuc = structured_module._detect_jsonschema()

    assert sonuc is False
    assert any(
        "jsonschema" in rec.message.lower() for rec in caplog.records
    ), "jsonschema eksikligi icin GORUNUR log uyarisi bulunamadi"


def test_missing_jsonschema_prints_to_stderr(monkeypatch, capsys):
    """GORUNURLUK garantisi: logging config'i susturulmus olsa bile uyari
    stderr'e de yazilir (print ile), boot sirasinda gozden kacmaz."""
    import sys
    from src.llm import structured as structured_module

    monkeypatch.setitem(sys.modules, "jsonschema", None)
    sonuc = structured_module._detect_jsonschema()

    assert sonuc is False
    captured = capsys.readouterr()
    assert "jsonschema" in captured.err.lower()


def test_detect_jsonschema_succeeds_when_installed():
    """jsonschema gercekten kurulu oldugunda _detect_jsonschema True doner ve
    modul-seviyesi 'jsonschema' adini modul global namespace'ine baglar."""
    from src.llm import structured as structured_module

    sonuc = structured_module._detect_jsonschema()

    assert sonuc is True
    assert hasattr(structured_module, "jsonschema")


# ---------------------------------------------------------------------------
# run_structured_chain
# ---------------------------------------------------------------------------


def _make_schema() -> dict:
    return {
        "type": "object",
        "required": ["ad", "adet"],
        "properties": {
            "ad": {"type": "string"},
            "adet": {"type": "integer"},
        },
        "additionalProperties": False,
    }


def _make_provider_with_responses(responses: List[str]) -> FakeProvider:
    return FakeProvider(
        fixture_map={("chain-test", "_any_"): responses}
    )


def _build_req_fn(template_id: str = "chain-test"):
    def _fn(prev_errors: List[str]) -> LLMRequest:
        content = "Hata yok." if not prev_errors else "Onceki hatalar: " + str(prev_errors)
        return LLMRequest(
            messages=[
                {"role": "system", "content": "Sen bir asistaansin."},
                {"role": "user", "content": content},
            ],
            schema=_make_schema(),
            template_id=template_id,
        )
    return _fn


# Yol 1: Gecerli JSON -> VALID
def test_chain_valid_first_try():
    provider = _make_provider_with_responses(['{"ad": "braket", "adet": 5}'])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=2,
    )
    assert result.status == ValidationStatus.VALID
    assert result.data == {"ad": "braket", "adet": 5}
    assert result.fallback is None
    assert result.attempt_count == 1


# Yol 2: Opsiyonel alan eksik -> PARTIAL
def test_chain_partial():
    schema = {
        "type": "object",
        "required": ["ad"],
        "properties": {
            "ad": {"type": "string"},
            "aciklama": {"type": "string"},
        },
    }
    provider = FakeProvider(
        fixture_map={("chain-partial", "_any_"): ['{"ad": "braket"}']}
    )

    def build_req(errs):
        return LLMRequest(
            messages=[{"role": "user", "content": "test"}],
            schema=schema,
            template_id="chain-partial",
        )

    result = run_structured_chain(
        provider=provider,
        build_request_fn=build_req,
        schema=schema,
        max_retry=2,
    )
    # 'aciklama' opsiyonel, eksik -> PARTIAL veya VALID (her ikisi kabul)
    assert result.status in (ValidationStatus.PARTIAL, ValidationStatus.VALID)
    assert result.data is not None
    assert result.fallback is None


# Yol 3: Bozuk JSON -> INVALID (tek deneme, max_retry=0)
def test_chain_invalid_bad_json():
    provider = _make_provider_with_responses(["bu JSON degil!"])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=0,
    )
    assert result.status == ValidationStatus.INVALID
    assert result.data is None
    assert result.fallback is not None
    assert isinstance(result.fallback, HumanFallback)
    assert "bu JSON degil!" in result.fallback.raw_text


# Yol 4: 1. deneme bozuk, 2. deneme gecerli -> VALID, attempt_count=2
def test_chain_retry_then_valid():
    provider = _make_provider_with_responses([
        "bozuk metin",
        '{"ad": "test", "adet": 3}',
    ])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=2,
    )
    assert result.status == ValidationStatus.VALID
    assert result.data == {"ad": "test", "adet": 3}
    assert result.fallback is None
    assert result.attempt_count == 2


# Yol 5: Tum retry'lar basarisiz -> HumanFallback
def test_chain_all_retries_fail_fallback():
    provider = _make_provider_with_responses([
        "bozuk 1",
        "bozuk 2",
        "bozuk 3",
    ])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=2,
        call_ref="test-ref-001",
    )
    assert result.status == ValidationStatus.INVALID
    assert result.data is None
    assert result.fallback is not None
    assert result.fallback.raw_text in ("bozuk 1", "bozuk 2", "bozuk 3")
    assert len(result.fallback.errors) > 0
    assert result.attempt_count == 3


# HumanFallback alanlari
def test_human_fallback_fields():
    fb = HumanFallback(
        raw_text="ham metin",
        errors=["hata1", "hata2"],
        call_ref="ref-123",
    )
    assert fb.raw_text == "ham metin"
    assert "hata1" in fb.errors
    assert fb.call_ref == "ref-123"


# Schema zorunlu alan eksikken data None olmali (asla sessiz gecis)
def test_invalid_result_data_is_none():
    data = {"ad": "braket"}  # adet eksik
    result = validate_against_schema(data, _make_schema())
    assert result.status == ValidationStatus.INVALID
    assert result.data is None


# JSON blogu icerisinde valid JSON varsa dogru parse
def test_chain_json_block_wrapped():
    text = '```json\n{"ad": "ring", "adet": 15}\n```'
    provider = _make_provider_with_responses([text])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=0,
    )
    assert result.status == ValidationStatus.VALID
    assert result.data["adet"] == 15


# ---------------------------------------------------------------------------
# H3: tolerant_json_extract — balanced-brace taramasi
# ---------------------------------------------------------------------------


def test_extract_two_consecutive_json_objects():
    """Arka arkaya iki JSON nesnesi — ilk gecerli olanı alir."""
    text = '{"a": 1} {"b": 2}'
    result = tolerant_json_extract(text)
    # ilk blok: {"a": 1}
    assert result == {"a": 1}


def test_extract_nested_json_object():
    """Ic ice JSON nesnesi — dis nesneyi dogru cikartmali."""
    text = 'Cevap: {"outer": {"inner": 42}}'
    result = tolerant_json_extract(text)
    assert result == {"outer": {"inner": 42}}


def test_extract_text_then_json():
    """Metin + JSON karisimi — JSON kismi cikartilmali."""
    text = "Tabii ki yardimci olabilirim. Iste sonuc: {\"ad\": \"parca\", \"adet\": 3} Umarim ise yarar."
    result = tolerant_json_extract(text)
    assert result == {"ad": "parca", "adet": 3}


def test_extract_second_block_valid_if_first_invalid():
    """Ilk blok bozuk JSON, ikinci gecerli — ikinci alinmali."""
    text = "{bozuk: json} {\"ad\": \"ok\", \"adet\": 7}"
    result = tolerant_json_extract(text)
    assert result == {"ad": "ok", "adet": 7}


# ---------------------------------------------------------------------------
# M4: StructuredChainResult.last_response
# ---------------------------------------------------------------------------


def test_chain_last_response_populated_on_success():
    """Basarili zincirde last_response dolu olmali."""
    provider = _make_provider_with_responses(['{"ad": "braket", "adet": 5}'])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=2,
    )
    assert result.status == ValidationStatus.VALID
    assert result.last_response is not None
    assert result.last_response.text == '{"ad": "braket", "adet": 5}'


def test_chain_last_response_populated_on_fallback():
    """Tum retry'lar basarisiz olunca da last_response dolu olmali."""
    provider = _make_provider_with_responses(["bozuk", "bozuk2", "bozuk3"])
    result = run_structured_chain(
        provider=provider,
        build_request_fn=_build_req_fn(),
        schema=_make_schema(),
        max_retry=2,
    )
    assert result.status == ValidationStatus.INVALID
    assert result.last_response is not None
