"""LLM saglayici soyutlamasi — PLAN_LLM.md L0.1.

LLMProvider: protokol (runtime typing; ABC olmasa da isinstance kontrolu yapar).
LLMRequest / LLMResponse: dataclass transferleri.
FakeProvider: fixture'lardan yanit uretir — ag baglantisi yoktur.

FakeProvider anahtarlama kurali:
    - fixture_map: {(sablon_id, girdi_hash): [yanit1, yanit2, ...]}
    - Birden fazla yanitsa dizi indeksi her cagri artar (senaryolu retry).
    - Fixture bulunamazsa KeyError firlatilir — sessiz default yanit YOK.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Veri yapilari
# ---------------------------------------------------------------------------


@dataclass
class LLMRequest:
    """Saglayiciya gonderilen istek.

    Alanlar
    -------
    messages     : [{"role": "system"|"user"|"assistant", "content": str}]
    schema       : JSON Schema dict (cikti dogrulamasi icin)
    max_tokens   : maksimum cikti token sayisi
    temperature  : ornekleme sicakligi (0.0-2.0)
    role_tag     : hangi LLM rolune ait (audit icin; saglayici kullanmaz)
    template_id  : sablon kimlik kodu (audit + FakeProvider anahtari)
    """

    messages: List[Dict[str, str]]
    schema: Dict[str, Any]
    max_tokens: int = 1024
    temperature: float = 0.0
    role_tag: str = ""
    template_id: str = ""


@dataclass
class LLMResponse:
    """Saglayicidan alinan yanit.

    Alanlar
    -------
    text          : ham metin ciktisi
    usage_in      : girdi token sayisi
    usage_out     : cikti token sayisi
    latency_s     : yanit suresi (saniye)
    model_id      : kullanilan model kimlik kodu
    finish_reason : bitis nedeni ("stop", "length", "error", vb.)
    """

    text: str
    usage_in: int = 0
    usage_out: int = 0
    latency_s: float = 0.0
    model_id: str = ""
    finish_reason: str = "stop"


# ---------------------------------------------------------------------------
# Protokol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Saglayici arayuzu — hic bir saglayici bilmez; sadece bu sozu tutar."""

    def complete(self, req: LLMRequest) -> LLMResponse:
        """Istegi tamamla, LLMResponse dondur."""
        ...


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------


def _input_hash(req: LLMRequest) -> str:
    """Son user mesajinin SHA-256 hash'i (ilk 16 hex)."""
    user_texts = [m["content"] for m in req.messages if m.get("role") == "user"]
    combined = "\n".join(user_texts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# FakeProvider
# ---------------------------------------------------------------------------


class FakeProvider:
    """Testler icin deterministik sahte saglayici.

    Parametreler
    ------------
    fixture_map : {(template_id, input_hash_prefix): [yanit_str, ...]}
        input_hash_prefix: "_any_" kullanilirsa her hash icin esleme yapilir.
        Yanit listesi: ilk cagri [0], ikinci [1], ... (retry senaryosu icin).
    model_id    : dondurulen model kimlik kodu
    latency_s   : simule edilen gecikme
    """

    def __init__(
        self,
        fixture_map: Dict[tuple, List[str]],
        model_id: str = "fake-model-v1",
        latency_s: float = 0.0,
    ) -> None:
        self._fixtures = fixture_map
        self._call_counts: Dict[tuple, int] = {}
        self._model_id = model_id
        self._latency_s = latency_s

    def complete(self, req: LLMRequest) -> LLMResponse:
        """Fixture'dan yanit uretir.

        Oncelik: (template_id, exact_hash) > (template_id, "_any_") > KeyError
        """
        h = _input_hash(req)
        exact_key = (req.template_id, h)
        any_key = (req.template_id, "_any_")

        if exact_key in self._fixtures:
            key = exact_key
        elif any_key in self._fixtures:
            key = any_key
        else:
            raise KeyError(
                f"FakeProvider: fixture bulunamadi. "
                f"template_id={req.template_id!r}, input_hash={h!r}. "
                f"Mevcut anahtarlar: {list(self._fixtures.keys())}"
            )

        responses = self._fixtures[key]
        idx = self._call_counts.get(key, 0)
        if idx >= len(responses):
            idx = len(responses) - 1
        text = responses[idx]
        self._call_counts[key] = idx + 1

        return LLMResponse(
            text=text,
            usage_in=len(req.messages[0]["content"].split()) if req.messages else 0,
            usage_out=len(text.split()),
            latency_s=self._latency_s,
            model_id=self._model_id,
            finish_reason="stop",
        )

    def reset_counts(self) -> None:
        """Cagri sayaclarini sifirla (test arasindan)."""
        self._call_counts.clear()
