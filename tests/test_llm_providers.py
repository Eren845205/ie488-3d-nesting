"""Testler: src/llm/providers/ — PLAN_LLM.md L0.2.

AnthropicProvider:
  - api_key eksik -> EnvironmentError
  - Basarili istek: mock HTTP -> LLMResponse
  - 429 + Retry-After -> bekleme + retry
  - Transport hatasi -> retry + RuntimeError
  - _build_payload: system mesaji ayrilmasi
  - _parse_response: content blok parse

OpenAICompatProvider:
  - Basarili istek: mock HTTP -> LLMResponse
  - 429 -> retry
  - Transport hatasi -> RuntimeError
  - api_key_env bos ise authorization header yok
  - api_key_env dolu ise bearer header var
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.llm.provider import LLMRequest, LLMResponse
from src.llm.providers.anthropic_provider import AnthropicProvider
from src.llm.providers.openai_compat import OpenAICompatProvider


# ---------------------------------------------------------------------------
# Mock HTTP istemci yardimcisi
# ---------------------------------------------------------------------------


class MockResponse:
    """requests/httpx yanit taklitcisi."""

    def __init__(
        self,
        status_code: int = 200,
        body: Dict[str, Any] = None,
        headers: Dict[str, str] = None,
    ):
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}

    def json(self) -> Dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockHttpClient:
    """Tek yanit veya yanit listesi donduren mock HTTP istemcisi."""

    def __init__(self, responses: List[MockResponse]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def post(self, url: str, **kwargs: Any) -> MockResponse:
        resp = self._responses[self._idx]
        if self._idx < len(self._responses) - 1:
            self._idx += 1
        return resp


def _anthropic_ok_body(text: str = "merhaba") -> Dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "model": "claude-haiku-20240307",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def _openai_ok_body(text: str = "merhaba") -> Dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "model": "qwen2.5:14b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 80, "completion_tokens": 15},
    }


def _make_req(template_id: str = "t1") -> LLMRequest:
    return LLMRequest(
        messages=[
            {"role": "system", "content": "Sen bir asistaansin."},
            {"role": "user", "content": "siparis ver"},
        ],
        schema={"type": "object"},
        template_id=template_id,
    )


# ---------------------------------------------------------------------------
# AnthropicProvider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    def test_missing_api_key_raises_env_error(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
        )
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            provider.complete(_make_req())

    def test_successful_request(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
        mock_client = MockHttpClient([MockResponse(200, _anthropic_ok_body("cevap"))])
        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
            http_client=mock_client,
        )
        resp = provider.complete(_make_req())
        assert resp.text == "cevap"
        assert resp.usage_in == 100
        assert resp.usage_out == 20
        assert resp.model_id == "claude-haiku-20240307"
        assert resp.finish_reason == "end_turn"

    def test_build_payload_separates_system(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
        )
        req = LLMRequest(
            messages=[
                {"role": "system", "content": "sistem talimati"},
                {"role": "user", "content": "kullanici sorusu"},
            ],
            schema={},
        )
        payload = provider._build_payload(req)
        assert payload["system"] == "sistem talimati"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_429_triggers_retry(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        responses = [
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(200, _anthropic_ok_body("retry yanit")),
        ]
        mock_client = MockHttpClient(responses)
        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
            http_client=mock_client,
        )
        with patch("time.sleep"):  # gercek bekleme yapma
            resp = provider.complete(_make_req())
        assert resp.text == "retry yanit"

    def test_transport_error_retries_then_raises(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")

        class FailClient:
            def post(self, *args, **kwargs):
                raise ConnectionError("ag hatasi")

        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
            http_client=FailClient(),
        )
        with patch("time.sleep"):
            with pytest.raises(RuntimeError, match="basarisiz"):
                provider.complete(_make_req())

    def test_parse_response_multiple_content_blocks(self, monkeypatch):
        body = {
            "id": "msg_x",
            "model": "claude-haiku-20240307",
            "content": [
                {"type": "text", "text": "birinci "},
                {"type": "text", "text": "ikinci"},
            ],
            "stop_reason": "stop",
            "usage": {"input_tokens": 5, "output_tokens": 3},
        }
        resp = AnthropicProvider._parse_response(body, 0.5)
        assert resp.text == "birinci ikinci"

    def test_retry_after_parses_float(self):
        class FakeResp:
            headers = {"retry-after": "2.5"}
        assert AnthropicProvider._retry_after(FakeResp()) == 2.5

    def test_retry_after_none_when_missing(self):
        class FakeResp:
            headers = {}
        assert AnthropicProvider._retry_after(FakeResp()) is None


# ---------------------------------------------------------------------------
# OpenAICompatProvider
# ---------------------------------------------------------------------------


class TestOpenAICompatProvider:
    def test_successful_request(self):
        mock_client = MockHttpClient([MockResponse(200, _openai_ok_body("yerel cevap"))])
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen2.5:14b",
            http_client=mock_client,
        )
        resp = provider.complete(_make_req())
        assert resp.text == "yerel cevap"
        assert resp.usage_in == 80
        assert resp.usage_out == 15
        assert resp.finish_reason == "stop"

    def test_no_api_key_env_no_auth_header(self):
        """api_key_env belirtilmemisse authorization header olmamali."""
        captured: Dict[str, Any] = {}

        class CapturingClient:
            def post(self, url, **kwargs):
                captured.update(kwargs)
                return MockResponse(200, _openai_ok_body("ok"))

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen",
            http_client=CapturingClient(),
        )
        provider.complete(_make_req())
        assert "authorization" not in captured.get("headers", {})

    def test_api_key_env_adds_bearer_header(self, monkeypatch):
        monkeypatch.setenv("LOCAL_API_KEY", "secret-token")
        captured: Dict[str, Any] = {}

        class CapturingClient:
            def post(self, url, **kwargs):
                captured.update(kwargs)
                return MockResponse(200, _openai_ok_body("ok"))

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen",
            api_key_env="LOCAL_API_KEY",
            http_client=CapturingClient(),
        )
        provider.complete(_make_req())
        assert captured["headers"].get("authorization") == "Bearer secret-token"

    def test_429_triggers_retry(self):
        responses = [
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(200, _openai_ok_body("retry ok")),
        ]
        mock_client = MockHttpClient(responses)
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen",
            http_client=mock_client,
        )
        with patch("time.sleep"):
            resp = provider.complete(_make_req())
        assert resp.text == "retry ok"

    def test_transport_error_retries_then_raises(self):
        class AlwaysFail:
            def post(self, *args, **kwargs):
                raise ConnectionError("network")

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen",
            http_client=AlwaysFail(),
        )
        with patch("time.sleep"):
            with pytest.raises(RuntimeError, match="basarisiz"):
                provider.complete(_make_req())

    def test_base_url_trailing_slash_stripped(self):
        """base_url sonundaki / chat path'e eklenmemeli."""
        captured: Dict[str, str] = {}

        class CapturingClient:
            def post(self, url, **kwargs):
                captured["url"] = url
                return MockResponse(200, _openai_ok_body("ok"))

        provider = OpenAICompatProvider(
            base_url="http://localhost:11434/",
            model="qwen",
            http_client=CapturingClient(),
        )
        provider.complete(_make_req())
        assert captured["url"] == "http://localhost:11434/v1/chat/completions"

    def test_parse_response_empty_choices(self):
        body = {"choices": [], "usage": {}, "model": "qwen"}
        resp = OpenAICompatProvider._parse_response(body, 0.0)
        assert resp.text == ""
        assert resp.finish_reason == "stop"


# ---------------------------------------------------------------------------
# M2: Hep-429 senaryosunda hata mesaji 429 bilgisini icermeli
# ---------------------------------------------------------------------------


class TestAllRetries429:
    def test_anthropic_all_429_error_mentions_429(self, monkeypatch):
        """AnthropicProvider: tum denemeler 429 ise RuntimeError mesaji 429 icermeli."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
        always_429 = MockHttpClient([
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(429, {}, {"retry-after": "0"}),
        ])
        provider = AnthropicProvider(
            api_key_env="ANTHROPIC_API_KEY",
            model="claude-haiku-20240307",
            http_client=always_429,
        )
        with patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                provider.complete(_make_req())
        assert "429" in str(exc_info.value)

    def test_openai_all_429_error_mentions_429(self):
        """OpenAICompatProvider: tum denemeler 429 ise RuntimeError mesaji 429 icermeli."""
        always_429 = MockHttpClient([
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(429, {}, {"retry-after": "0"}),
            MockResponse(429, {}, {"retry-after": "0"}),
        ])
        provider = OpenAICompatProvider(
            base_url="http://localhost:11434",
            model="qwen",
            http_client=always_429,
        )
        with patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                provider.complete(_make_req())
        assert "429" in str(exc_info.value)
