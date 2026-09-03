"""Watcher narrasyon rolu — deterministik bulgulari sade Turkce'ye cevirir.

Girdi: WatcherNarrationInput[Finding listesi]
Cikti: WatcherResult{anlatim_md, kapsanan_bulgular, topraklama_uyarisi}

Kurallar:
  - LLM KARAR VERMEZ: severity/karar deterministik denetciden gelir.
  - Topraklama UYARI modunda (blok degil): bulgu sayilari anlatimda
    gecmiyorsa number_flag=True, ama status INVALID olmaz.
  - Bos bulgu listesi -> LLM cagrisi yapilmaz, None donus.
  - Retry/fallback: explainer.py ile ayni mantik.

Şablon: prompts/watcher/ (meta.json, system.md, schema.json, examples/)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import SourceDoc, verify_number_grounding
from src.llm.prompts import PromptRegistry
from src.llm.provider import LLMRequest, LLMResponse
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import (
    HumanFallback,
    ValidationStatus,
    tolerant_json_extract,
    validate_against_schema,
)
from src.watcher.checks import Finding

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WatcherNarrationInput
# ---------------------------------------------------------------------------


@dataclass
class WatcherNarrationInput:
    """Watcher anlatim rolune girdi.

    Alanlar
    -------
    findings : deterministik denetciden gelen Finding listesi
    """

    findings: List[Finding]

    def to_dict(self) -> Dict[str, Any]:
        """Finding listesini LLM icin JSON-serializeable dict'e donustur."""
        return {
            "bulgular": [
                {
                    "asama": f.asama,
                    "kod": f.kod,
                    "severity": f.severity,
                    "baslik": f.baslik,
                    "ham_detay": f.ham_detay,
                }
                for f in self.findings
            ]
        }

    def to_source_doc(self) -> SourceDoc:
        """Topraklama dogrulamasi icin Finding listesi -> SourceDoc.

        Bulgu metrikerindeki sayilar kaynak icerigine eklenir;
        anlatimda bu sayilarin disinda bir sayi kullanilirsa uyari verilir.
        """
        satirlar = []
        for f in self.findings:
            satirlar.append(f"Bulgu: {f.kod} ({f.severity})")
            satirlar.append(f"Baslik: {f.baslik}")
            satirlar.append(f"Detay: {f.ham_detay}")
            # metrik sayilarini da ekle (topraklama dogrulamasi icin)
            for k, v in f.metrik.items():
                if isinstance(v, (int, float)):
                    satirlar.append(f"{k}={v}")
        return SourceDoc(
            id="watcher#bulgular",
            tip="telemetri",
            icerik="\n".join(satirlar),
            uretici="watcher.checks",
        )


# ---------------------------------------------------------------------------
# WatcherResult
# ---------------------------------------------------------------------------


@dataclass
class WatcherResult:
    """Watcher anlatim rolu sonucu.

    Alanlar
    -------
    role_result        : ham RoleResult (status, data, fallback, audit_ref)
    number_flag        : True ise anlatimda bulgu kaynaginda olmayan sayi uretildi
    ungrounded_numbers : topraklanamayan sayilar listesi
    """

    role_result: RoleResult
    number_flag: bool = False
    ungrounded_numbers: List[str] = field(default_factory=list)

    @property
    def status(self) -> ValidationStatus:
        return self.role_result.status

    @property
    def data(self) -> Optional[Dict[str, Any]]:
        return self.role_result.data

    @property
    def fallback(self) -> Optional[HumanFallback]:
        return self.role_result.fallback

    @property
    def audit_ref(self) -> str:
        return self.role_result.audit_ref


# ---------------------------------------------------------------------------
# WatcherRole
# ---------------------------------------------------------------------------


class WatcherRole:
    """Watcher bulgu anlatim LLM rolu.

    Parametreler
    ------------
    provider   : LLMProvider ornegi
    registry   : PromptRegistry ornegi
    audit      : AuditLogger ornegi
    role_cfg   : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "watcher"

    def __init__(
        self,
        provider: Any,
        registry: PromptRegistry,
        audit: AuditLogger,
        role_cfg: Optional[RoleConfig] = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._audit = audit
        self._role_cfg = role_cfg
        self._base_role = LLMRole(
            role_name=self.ROLE_NAME,
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=role_cfg,
        )

    def narrate(self, findings: List[Finding]) -> Optional[WatcherResult]:
        """Finding listesini sade Turkce anlatima donustur.

        Adimlar:
        1. Bos finding listesi -> LLM cagrisi yapilmaz; None donus.
        2. Finding listesini dict'e donustur; LLM chain loop calistir.
        3. LLM basarisizsa dogrudan fallback (WatcherResult INVALID).
        4. Sayi-topraklama UYARI modu: anlatim_md'deki sayilari
           bulgu ham_detay ve metrik sayilariyla karsilastir.
        5. WatcherResult dondur.
        """
        if not findings:
            # LLM cagrisi yok; tam anlamli None donus
            return None

        narration_input = WatcherNarrationInput(findings=findings)
        input_dict = narration_input.to_dict()
        role_result = self._run_chain(input_dict)

        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            return WatcherResult(role_result=role_result)

        data = role_result.data or {}
        anlatim_md = data.get("anlatim_md", "")

        source_doc = narration_input.to_source_doc()
        grounding = verify_number_grounding(anlatim_md, [source_doc])
        number_flag = not grounding.is_clean

        if number_flag:
            logger.warning(
                "Watcher sayi-topraklama UYARI: bulgu kaynaginda bulunmayan "
                "sayilar anlatimda kullanildi: %s",
                grounding.ungrounded,
            )

        return WatcherResult(
            role_result=role_result,
            number_flag=number_flag,
            ungrounded_numbers=grounding.ungrounded,
        )

    def _run_chain(self, input_dict: Dict[str, Any]) -> RoleResult:
        """Structured chain loop — explainer.py deseniyle ayni.

        tolerant_json_extract -> validate_against_schema -> retry.
        AuditLogger ile kaydet.
        """
        br = self._base_role
        tpl = br._registry.load(br._role_name)
        schema = tpl.schema
        schema_retry = br._role_cfg.schema_retry if br._role_cfg else 2
        model_id = br._role_cfg.model if br._role_cfg else "fake"
        temperature = br._role_cfg.temperature if br._role_cfg else 0.0
        max_tokens = br._role_cfg.max_tokens if br._role_cfg else 1024

        def build_request(prev_errors: List[str]) -> LLMRequest:
            few_shot = tpl.few_shot_text()
            slots: Dict[str, str] = {"few_shot": few_shot}
            try:
                system_text = tpl.render(slots)
            except Exception:
                slots["context"] = ""
                system_text = tpl.render(slots)
            input_text = json.dumps(input_dict, ensure_ascii=False, indent=2)
            user_content = (
                f"<bulgular>\n{input_text}\n</bulgular>"
            )
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
                role_tag=self.ROLE_NAME,
                template_id=tpl.id,
            )

        last_text = ""
        last_errors: List[str] = []
        last_resp = None
        final_status = ValidationStatus.INVALID
        final_data = None
        final_fallback = None
        attempt_count = 0

        for attempt in range(schema_retry + 1):
            attempt_count = attempt + 1
            req = build_request(last_errors)
            resp = br._provider.complete(req)
            last_resp = resp
            last_text = resp.text

            if getattr(resp, "finish_reason", "stop") == "length":
                last_errors = ["Yanit kesildi (finish_reason=length)."]
                logger.warning(
                    "Watcher deneme %d: finish_reason=length.", attempt_count
                )
                continue

            parsed = tolerant_json_extract(last_text)
            if parsed is None:
                last_errors = [
                    f"JSON parse hatasi: gecerli JSON objesi bulunamadi. "
                    f"Metin: {last_text[:200]}"
                ]
                logger.warning("Watcher deneme %d: JSON parse hatasi.", attempt_count)
                continue

            vresult = validate_against_schema(parsed, schema)
            if vresult.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
                final_status = vresult.status
                final_data = vresult.data
                break

            last_errors = vresult.errors
            logger.warning(
                "Watcher deneme %d: schema hatasi: %s",
                attempt_count, last_errors,
            )
        else:
            final_fallback = HumanFallback(
                raw_text=last_text,
                errors=last_errors,
                call_ref=self.ROLE_NAME,
            )
            final_status = ValidationStatus.INVALID

        if last_resp is not None:
            audit_resp = last_resp
        else:
            audit_resp = LLMResponse(
                text=(
                    json.dumps(final_data, ensure_ascii=False)
                    if final_data
                    else (final_fallback.raw_text if final_fallback else "")
                ),
                model_id=model_id,
            )

        if final_fallback is not None:
            status_for_audit = "FALLBACK"
        elif attempt_count > 1 and final_status == ValidationStatus.VALID:
            status_for_audit = "RETRY"
        else:
            status_for_audit = final_status.value

        record = br._audit.log(
            role=self.ROLE_NAME,
            template_id=tpl.id,
            template_version=tpl.version,
            content_hash=tpl.content_hash,
            req=build_request([]),
            resp=audit_resp,
            status=status_for_audit,
        )
        audit_ref = record.ref
        if final_fallback is not None:
            final_fallback.call_ref = audit_ref

        return RoleResult(
            status=final_status,
            data=final_data,
            fallback=final_fallback,
            audit_ref=audit_ref,
            attempt_count=attempt_count,
            errors=last_errors,
        )
