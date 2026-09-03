"""LLMRole — rol baglayici (PLAN_LLM.md L0.7).

LLMRole.run(input_dict) -> RoleResult:
    1. PromptRegistry'den sablon yukle
    2. Girisin few-shot + input metnini olustur
    3. LLMRequest kur
    4. run_structured_chain() ile saglayiciya gonder
    5. AuditLogger ile kaydet
    6. RoleResult dondur

RoleResult:
    status    : ValidationStatus
    data      : dogrulanmis dict (VALID/PARTIAL) ya da None
    fallback  : HumanFallback (INVALID+retry bitti) ya da None
    audit_ref : audit JSONL kayit referansi

Her LLMRole ornegi:
    - Konfigurasyon (RoleConfig)
    - PromptRegistry
    - LLMProvider
    - AuditLogger
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.llm.audit import AuditLogger
from src.llm.config import LLMConfig, RoleConfig
from src.llm.prompts import PromptRegistry, PromptTemplate
from src.llm.provider import LLMProvider, LLMRequest, LLMResponse
from src.llm.structured import (
    HumanFallback,
    ValidationStatus,
    run_structured_chain,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RoleResult
# ---------------------------------------------------------------------------


@dataclass
class RoleResult:
    """LLMRole.run() ciktisi."""

    status: ValidationStatus
    data: Optional[Dict[str, Any]]
    fallback: Optional[HumanFallback]
    audit_ref: str
    attempt_count: int = 1
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLMRole
# ---------------------------------------------------------------------------


class LLMRole:
    """Tek bir LLM rolunun tum altyapisini bir araya getirir.

    Parametreler
    ------------
    role_name  : "parser" | "tuner" | "hypothesis" | "assistant" | "report"
    provider   : LLMProvider ornegi
    registry   : PromptRegistry ornegi
    audit      : AuditLogger ornegi
    role_cfg   : RoleConfig (konfig'dan; None ise varsayilanlar)
    """

    def __init__(
        self,
        role_name: str,
        provider: Any,
        registry: PromptRegistry,
        audit: AuditLogger,
        role_cfg: Optional[RoleConfig] = None,
    ) -> None:
        self._role_name = role_name
        self._provider = provider
        self._registry = registry
        self._audit = audit
        self._role_cfg = role_cfg

    def run(self, input_dict: Dict[str, Any]) -> RoleResult:
        """Rol calistir.

        Parametreler
        ------------
        input_dict : rol-bazli girdi (orn. {"mail_text": "...", "parts": [...]})
                     Her rol bu dict'i JSON metnine cevirir ve sablon yuvalarini doldurur.

        Dondurur
        --------
        RoleResult
        """
        tpl = self._registry.load(self._role_name)
        schema = tpl.schema
        schema_retry = self._role_cfg.schema_retry if self._role_cfg else 2
        model_id = self._role_cfg.model if self._role_cfg else "fake"
        temperature = self._role_cfg.temperature if self._role_cfg else 0.0
        max_tokens = self._role_cfg.max_tokens if self._role_cfg else 1024

        def build_request(prev_errors: List[str]) -> LLMRequest:
            """Sablon + girdi + onceki hatalar -> LLMRequest.

            H1: Sistem talimatı "system" mesajında; müşteri girdisi AYRI "user"
            mesajında <musteri_verisi>...</musteri_verisi> sarmalasıyla gönderilir.
            """
            few_shot = tpl.few_shot_text()
            slots: Dict[str, str] = {
                "few_shot": few_shot,
            }
            # context yuvasi yoksa ekleme (sablon opsiyonel)
            try:
                system_text = tpl.render(slots)
            except Exception:
                slots["context"] = ""
                system_text = tpl.render(slots)

            # H1: müşteri girdisi user mesajı olarak, <musteri_verisi> sarmalıyla
            input_text = json.dumps(input_dict, ensure_ascii=False, indent=2)
            user_content = f"<musteri_verisi>\n{input_text}\n</musteri_verisi>"

            messages = [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_content},
            ]
            if prev_errors:
                error_note = (
                    "Onceki yanit schema dogrulamasinda basarisiz oldu. Hatalar:\n"
                    + "\n".join(f"- {e}" for e in prev_errors)
                    + "\nLutfen yalnizca gecerli JSON sema ile yanit ver."
                )
                messages.append({"role": "user", "content": error_note})

            return LLMRequest(
                messages=messages,
                schema=schema,
                max_tokens=max_tokens,
                temperature=temperature,
                role_tag=self._role_name,
                template_id=tpl.id,
            )

        chain_result = run_structured_chain(
            provider=self._provider,
            build_request_fn=build_request,
            schema=schema,
            max_retry=schema_retry,
            call_ref=f"{self._role_name}",
        )

        # Son istegi olustur (audit icin son request/response)
        last_req = build_request([])

        # M4: chain_result.last_response'tan gercek usage/latency/model_id kullan.
        # None ise (zincir hic cagri yapamadiysa) minimal dummy fallback.
        from src.llm.provider import LLMResponse as _Resp
        if chain_result.last_response is not None:
            audit_resp = chain_result.last_response
        else:
            audit_resp = _Resp(
                text=(
                    json.dumps(chain_result.data, ensure_ascii=False)
                    if chain_result.data
                    else (chain_result.fallback.raw_text if chain_result.fallback else "")
                ),
                model_id=model_id,
            )

        if chain_result.fallback is not None:
            status_for_audit_str = "FALLBACK"
        elif chain_result.attempt_count > 1 and chain_result.status == ValidationStatus.VALID:
            status_for_audit_str = "RETRY"
        else:
            status_for_audit_str = chain_result.status.value

        record = self._audit.log(
            role=self._role_name,
            template_id=tpl.id,
            template_version=tpl.version,
            content_hash=tpl.content_hash,
            req=last_req,
            resp=audit_resp,
            status=status_for_audit_str,
        )

        # H2: audit_ref = record.ref (uuid4 tabanlı, benzersiz) — record.ts degil
        audit_ref = record.ref

        if chain_result.fallback:
            chain_result.fallback.call_ref = audit_ref

        return RoleResult(
            status=chain_result.status,
            data=chain_result.data,
            fallback=chain_result.fallback,
            audit_ref=audit_ref,
            attempt_count=chain_result.attempt_count,
            errors=chain_result.errors,
        )
