"""Testler: src/llm/provider.py — PLAN_LLM.md L0.1.

Kapsanan:
  - LLMRequest / LLMResponse dataclass round-trip
  - LLMProvider protokol kontrolu
  - FakeProvider: dogru fixture eslemesi
  - FakeProvider: exact-key onceligi
  - FakeProvider: "_any_" joker eslemesi
  - FakeProvider: senaryolu dizi (retry senaryosu: [bozuk, gecerli])
  - FakeProvider: fixture yoksa KeyError (sessiz default YOK)
  - FakeProvider.reset_counts() calismasi
  - _input_hash deterministik
"""

from __future__ import annotations

import pytest

from src.llm.provider import (
    FakeProvider,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    _input_hash,
)


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------


def _make_req(
    template_id: str = "t1",
    user_content: str = "merhaba",
    role_tag: str = "parser",
) -> LLMRequest:
    return LLMRequest(
        messages=[
            {"role": "system", "content": "Sen bir asistaansin."},
            {"role": "user", "content": user_content},
        ],
        schema={"type": "object"},
        max_tokens=512,
        temperature=0.0,
        role_tag=role_tag,
        template_id=template_id,
    )


# ---------------------------------------------------------------------------
# LLMRequest / LLMResponse
# ---------------------------------------------------------------------------


def test_llm_request_defaults():
    req = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        schema={},
    )
    assert req.max_tokens == 1024
    assert req.temperature == 0.0
    assert req.role_tag == ""
    assert req.template_id == ""


def test_llm_response_defaults():
    resp = LLMResponse(text="merhaba")
    assert resp.usage_in == 0
    assert resp.usage_out == 0
    assert resp.latency_s == 0.0
    assert resp.model_id == ""
    assert resp.finish_reason == "stop"


def test_llm_response_fields():
    resp = LLMResponse(
        text="sonuc",
        usage_in=100,
        usage_out=50,
        latency_s=1.5,
        model_id="claude-haiku",
        finish_reason="length",
    )
    assert resp.text == "sonuc"
    assert resp.usage_in == 100
    assert resp.latency_s == 1.5
    assert resp.finish_reason == "length"


# ---------------------------------------------------------------------------
# LLMProvider protokol
# ---------------------------------------------------------------------------


def test_fake_provider_implements_protocol():
    fp = FakeProvider(fixture_map={})
    assert isinstance(fp, LLMProvider)


# ---------------------------------------------------------------------------
# _input_hash deterministik
# ---------------------------------------------------------------------------


def test_input_hash_deterministic():
    req = _make_req(user_content="test input")
    h1 = _input_hash(req)
    h2 = _input_hash(req)
    assert h1 == h2
    assert len(h1) == 16


def test_input_hash_differs_for_different_input():
    req1 = _make_req(user_content="input A")
    req2 = _make_req(user_content="input B")
    assert _input_hash(req1) != _input_hash(req2)


# ---------------------------------------------------------------------------
# FakeProvider: dogru esleme
# ---------------------------------------------------------------------------


def test_fake_provider_exact_key_match():
    req = _make_req(template_id="parser-v1", user_content="siparis")
    h = _input_hash(req)
    fp = FakeProvider(
        fixture_map={
            ("parser-v1", h): ['{"musteri": null, "parcalar": [], "eksik_alanlar": [], "injection_suphesi": false}']
        }
    )
    resp = fp.complete(req)
    assert "musteri" in resp.text


def test_fake_provider_any_key_match():
    req = _make_req(template_id="parser-v1", user_content="farkli metin")
    fp = FakeProvider(
        fixture_map={
            ("parser-v1", "_any_"): ['{"status": "ok"}']
        }
    )
    resp = fp.complete(req)
    assert resp.text == '{"status": "ok"}'


def test_fake_provider_exact_beats_any():
    req = _make_req(template_id="t1", user_content="secme")
    h = _input_hash(req)
    fp = FakeProvider(
        fixture_map={
            ("t1", h): ["exact yanit"],
            ("t1", "_any_"): ["joker yanit"],
        }
    )
    resp = fp.complete(req)
    assert resp.text == "exact yanit"


# ---------------------------------------------------------------------------
# FakeProvider: KeyError — sessiz default YOK
# ---------------------------------------------------------------------------


def test_fake_provider_missing_fixture_raises_key_error():
    req = _make_req(template_id="bilinmeyen", user_content="test")
    fp = FakeProvider(fixture_map={})
    with pytest.raises(KeyError, match="FakeProvider"):
        fp.complete(req)


def test_fake_provider_wrong_template_id_raises():
    req = _make_req(template_id="t2")
    fp = FakeProvider(fixture_map={("t1", "_any_"): ["yanit"]})
    with pytest.raises(KeyError):
        fp.complete(req)


# ---------------------------------------------------------------------------
# FakeProvider: senaryolu dizi (retry)
# ---------------------------------------------------------------------------


def test_fake_provider_sequential_responses():
    req = _make_req(template_id="retry-test")
    fp = FakeProvider(
        fixture_map={
            ("retry-test", "_any_"): [
                "bozuk metin (1. deneme)",
                '{"id": 1}',   # 2. deneme gecerli
            ]
        }
    )
    resp1 = fp.complete(req)
    resp2 = fp.complete(req)
    assert "bozuk" in resp1.text
    assert '"id": 1' in resp2.text


def test_fake_provider_last_response_repeated_after_exhaustion():
    req = _make_req(template_id="exhaust-test")
    fp = FakeProvider(
        fixture_map={
            ("exhaust-test", "_any_"): ["yanit-A", "yanit-B"]
        }
    )
    r1 = fp.complete(req)
    r2 = fp.complete(req)
    r3 = fp.complete(req)  # liste bitti; son eleman tekrarlanmali
    assert r1.text == "yanit-A"
    assert r2.text == "yanit-B"
    assert r3.text == "yanit-B"


# ---------------------------------------------------------------------------
# FakeProvider: reset_counts
# ---------------------------------------------------------------------------


def test_fake_provider_reset_counts():
    req = _make_req(template_id="reset-test")
    fp = FakeProvider(
        fixture_map={
            ("reset-test", "_any_"): ["ilk", "ikinci"]
        }
    )
    fp.complete(req)  # ilk
    fp.complete(req)  # ikinci
    fp.reset_counts()
    resp = fp.complete(req)
    assert resp.text == "ilk"


# ---------------------------------------------------------------------------
# FakeProvider: model_id ve latency
# ---------------------------------------------------------------------------


def test_fake_provider_model_id():
    req = _make_req(template_id="model-test")
    fp = FakeProvider(
        fixture_map={("model-test", "_any_"): ["ok"]},
        model_id="test-model-v9",
    )
    resp = fp.complete(req)
    assert resp.model_id == "test-model-v9"


def test_fake_provider_finish_reason_stop():
    req = _make_req(template_id="fr-test")
    fp = FakeProvider(fixture_map={("fr-test", "_any_"): ["yanit"]})
    resp = fp.complete(req)
    assert resp.finish_reason == "stop"
