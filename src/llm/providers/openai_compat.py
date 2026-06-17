"""OpenAICompatProvider — OpenAI-uyumlu API istemcisi (PLAN_LLM.md L0.2).

Ollama, vLLM ve LM Studio hepsi OpenAI /v1/chat/completions ucunu destekler;
tek istemci ucunu kapsiyorum (ayri lokal istemci YAZILMAZ — L0.2 karari).

Ozellikler:
  - base_url konfigden (orn. "http://localhost:11434")
  - api_key_env opsiyonel (Ollama'da gerekmez; vLLM'de gerekebilir)
  - Timeout + transport-retry: ustel geri cekilme, max 2 retry
  - 429'da Retry-After basligini okur
  - Testte HTTP mock ile dogrulanir; gercek servis gerekmez
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from src.llm.provider import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)

_CHAT_PATH = "/v1/chat/completions"
_MAX_RETRIES = 2
_BACKOFF_BASE = 1.0


class OpenAICompatProvider:
    """OpenAI-uyumlu /v1/chat/completions ucu icin saglayici.

    Parametreler
    ------------
    base_url    : servis kok URL'i (orn. "http://localhost:11434")
    model       : model kimlik kodu (orn. "qwen2.5:14b")
    api_key_env : opsiyonel ortam degiskeni adi; bos kalirsa anahtar gonderilmez
    timeout_s   : zaman asimi (saniye)
    http_client : test injection icin mock HTTP istemcisi
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: Optional[str] = None,
        timeout_s: float = 30.0,
        http_client: Optional[Any] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key_env = api_key_env
        self._timeout_s = timeout_s
        self._http_client = http_client  # test injection; None ise lazy-init kullanilir
        self._lazy_http_client: Optional[Any] = None  # cached httpx.Client

    def health_check(self, timeout_s: float = 5.0) -> "tuple[bool, str]":
        """Canli probe: servis ayakta mi + model yuklu mu (demo oncesi kontrol).

        `/v1/models` GET ile sorgular (Ollama + vLLM + LM Studio destekler).
        Demo'nun "LLM hazir mi" kapisi: Ollama kapaliysa veya model cekilmemisse
        demo sirasinda degil ONCEDEN yakalanir.

        Returns:
            (ok, detail) -- ok False ise detail cozum onerisi tasir.
            Hicbir exception sizdirmaz (probe asla cagriyani patlatmaz).
        """
        url = self._base_url + "/v1/models"
        try:
            client = self._get_http_client()
            resp = client.get(url, timeout=timeout_s)
            status = getattr(resp, "status_code", 0)
            if status != 200:
                return (
                    False,
                    f"Servis {self._base_url} yanit verdi ama HTTP {status}. "
                    f"Ollama saglikli mi?",
                )
            data = resp.json()
            models = [m.get("id", "") for m in data.get("data", [])]
            if self._model in models:
                return (True, f"Hazir: '{self._model}' yuklu ({self._base_url}).")
            return (
                False,
                f"Servis ayakta ama model '{self._model}' YUKLU DEGIL. "
                f"Yuklu modeller: {models[:8]}. "
                f"Cozum: `ollama pull {self._model}`",
            )
        except Exception as exc:  # noqa: BLE001 — probe asla patlamaz
            return (
                False,
                f"Servise ERISILEMIYOR ({self._base_url}): {exc}. "
                f"Ollama calisiyor mu? `ollama serve` ile baslatin.",
            )

    def complete(self, req: LLMRequest) -> LLMResponse:
        """OpenAI-uyumlu API'ye istek gonder."""
        payload = self._build_payload(req)
        headers = self._build_headers()

        t0 = time.monotonic()
        data = self._send_with_retry(payload, headers)
        latency = time.monotonic() - t0

        return self._parse_response(data, latency)

    def _build_payload(self, req: LLMRequest) -> Dict[str, Any]:
        """LLMRequest'ten OpenAI chat payload'i olustur."""
        return {
            "model": self._model,
            "messages": req.messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
        }

    def _build_headers(self) -> Dict[str, str]:
        headers = {"content-type": "application/json"}
        if self._api_key_env:
            key = os.environ.get(self._api_key_env, "")
            if key:
                headers["authorization"] = f"Bearer {key}"
        return headers

    def _send_with_retry(
        self,
        payload: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Ustel geri cekilme ile retry; 429'da Retry-After'a uy."""
        url = self._base_url + _CHAT_PATH
        client = self._get_http_client()
        last_exc: Optional[Exception] = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                resp = client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_s,
                )
                if resp.status_code == 429:
                    wait = self._retry_after(resp) or (_BACKOFF_BASE * (2 ** attempt))
                    logger.warning("OpenAI-compat 429 — %s s bekleniyor.", wait)
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
                        "OpenAICompatProvider hata (deneme %d/%d): %s — %ss bekleniyor.",
                        attempt + 1, _MAX_RETRIES + 1, exc, wait,
                    )
                    time.sleep(wait)

        detail = f" Son hata: {last_exc}" if last_exc is not None else ""
        raise RuntimeError(
            f"OpenAICompatProvider: {_MAX_RETRIES + 1} deneme sonrasi basarisiz.{detail}"
        ) from last_exc

    @staticmethod
    def _retry_after(resp: Any) -> Optional[float]:
        val = getattr(resp, "headers", {}).get("retry-after")
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _get_http_client(self) -> Any:
        if self._http_client is not None:
            return self._http_client
        # Lazy-init: ilk cagrida olusturulur, sonraki cagrilarda yeniden kullanilir
        if self._lazy_http_client is None:
            try:
                import httpx
                self._lazy_http_client = httpx.Client()
            except ImportError as exc:
                raise ImportError(
                    "OpenAICompatProvider icin 'httpx' gerekli: pip install httpx"
                ) from exc
        return self._lazy_http_client

    @staticmethod
    def _parse_response(data: Dict[str, Any], latency: float) -> LLMResponse:
        """OpenAI yanit sozlugunden LLMResponse olustur."""
        choices = data.get("choices", [])
        text = ""
        finish_reason = "stop"
        if choices:
            choice = choices[0]
            msg = choice.get("message", {})
            text = msg.get("content", "") or ""
            finish_reason = choice.get("finish_reason", "stop") or "stop"

        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            usage_in=int(usage.get("prompt_tokens", 0)),
            usage_out=int(usage.get("completion_tokens", 0)),
            latency_s=latency,
            model_id=data.get("model", ""),
            finish_reason=finish_reason,
        )
