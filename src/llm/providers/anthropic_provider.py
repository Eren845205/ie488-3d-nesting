"""AnthropicProvider — Anthropic Messages API istemcisi (PLAN_LLM.md L0.2).

Ozellikler:
  - api_key_env: ortam degiskeninden API anahtari (koda gomulu anahtar YASAK).
  - Timeout + transport-retry: ustel geri cekilme, max 2 retry.
  - 429 durumunda Retry-After basligini okur, bekler.
  - Testte HTTP mock kullanilir; gercek anahtar gerekmez.

Bagimlilik: stdlib + httpx (optional; yoksa ImportError acik).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from src.llm.provider import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_RETRIES = 2
_BACKOFF_BASE = 1.0  # saniye


class AnthropicProvider:
    """Anthropic Messages API saglayicisi.

    Parametreler
    ------------
    api_key_env : API anahtarinin tutuldugu ortam degiskeni adi
    model       : Anthropic model kimlik kodu (orn. "claude-haiku-20240307")
    timeout_s   : istek zaman asimi (saniye)
    http_client : opsiyonel — test injection icin mock HTTP istemcisi
    """

    def __init__(
        self,
        api_key_env: str,
        model: str,
        timeout_s: float = 30.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self._api_key_env = api_key_env
        self._model = model
        self._timeout_s = timeout_s
        self._http_client = http_client  # None ise httpx kullanilir

    def complete(self, req: LLMRequest) -> LLMResponse:
        """Anthropic Messages API'sine istek gonder, LLMResponse dondur."""
        api_key = os.environ.get(self._api_key_env, "")
        if not api_key:
            raise EnvironmentError(
                f"AnthropicProvider: {self._api_key_env!r} ortam degiskeni bos. "
                "API anahtari koda gomulmez."
            )

        payload = self._build_payload(req)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        t0 = time.monotonic()
        response_data = self._send_with_retry(payload, headers)
        latency = time.monotonic() - t0

        return self._parse_response(response_data, latency)

    def _build_payload(self, req: LLMRequest) -> Dict[str, Any]:
        """LLMRequest'ten Anthropic Messages API payload'i olustur."""
        system_msgs = [m["content"] for m in req.messages if m["role"] == "system"]
        user_msgs = [m for m in req.messages if m["role"] != "system"]

        payload: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "messages": user_msgs,
        }
        if system_msgs:
            payload["system"] = "\n\n".join(system_msgs)
        return payload

    def _send_with_retry(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Ustel geri cekilme ile retry; 429'da Retry-After'a uy."""
        client = self._get_http_client()
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = client.post(
                    _ANTHROPIC_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_s,
                )
                if resp.status_code == 429:
                    wait = self._retry_after(resp) or (_BACKOFF_BASE * (2 ** attempt))
                    logger.warning("Anthropic 429 — %s s bekleniyor.", wait)
                    last_exc = RuntimeError(
                        f"429 rate-limit, attempt {attempt + 1}"
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    logger.warning(
                        "AnthropicProvider hata (deneme %d/%d): %s — %ss bekleniyor.",
                        attempt + 1, _MAX_RETRIES + 1, exc, wait,
                    )
                    time.sleep(wait)

        detail = f" Son hata: {last_exc}" if last_exc is not None else ""
        raise RuntimeError(
            f"AnthropicProvider: {_MAX_RETRIES + 1} deneme sonrasi basarisiz.{detail}"
        ) from last_exc

    @staticmethod
    def _retry_after(resp: Any) -> Optional[float]:
        """Retry-After basligini float saniyeye cevirir."""
        val = getattr(resp, "headers", {}).get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _get_http_client(self) -> Any:
        """Test injection veya gercek httpx."""
        if self._http_client is not None:
            return self._http_client
        try:
            import httpx
            return httpx.Client()
        except ImportError as exc:
            raise ImportError(
                "AnthropicProvider icin 'httpx' gerekli: pip install httpx"
            ) from exc

    @staticmethod
    def _parse_response(data: Dict[str, Any], latency: float) -> LLMResponse:
        """Anthropic yanit sozlugunden LLMResponse olustur."""
        content_blocks = data.get("content", [])
        text = ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")

        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            usage_in=int(usage.get("input_tokens", 0)),
            usage_out=int(usage.get("output_tokens", 0)),
            latency_s=latency,
            model_id=data.get("model", ""),
            finish_reason=data.get("stop_reason", "stop"),
        )
