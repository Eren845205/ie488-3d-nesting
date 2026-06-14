"""Aciklayici rol — sistem kararlarini sade Turkce aciklar.

Girdi: ExplainerInput
    karar_tipi   : "algoritma" | "fiyat" | "oncelik"
    sistem_ciktisi: deterministik motor ciktisi (nesting sonucu, fiyat dokumleri,
                    oncelik kuyruklari). Tum rakamlar buradan gelir.

Cikti: ExplainerResult
    aciklama_md       : sade Turkce aciklama metni (2-5 cumle, markdown)
    karar_tipi        : aciklanan karar kategorisi (girdiden yansitilir)
    kullanilan_girdiler: aciklamada atif yapilan girdi alanlari
    topraklama_uyarisi: True ise aciklamada girdide olmayan rakam/sebep uretildi

Topraklama kurali:
    UYARI modunda (asistan gibi) — blok DEGIL.
    LLM kendi topraklama_uyarisi alanini doldurur (prompt kurali).
    Ek olarak: verify_number_grounding() ile sistem ciktisindaki sayilara
    gore aciklama_md kontrol edilir; uyusmazsa number_flag=True.

Kural: LLM ACIKLAR, HESAPLAMAZ.
    Yeni aritmetik, oran, toplam uretmez. Girdideki rakamlari anlamlandirir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import (
    GroundedContext,
    SourceDoc,
    verify_number_grounding,
)
from src.llm.prompts import PromptRegistry
from src.llm.provider import LLMRequest, LLMResponse
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import (
    HumanFallback,
    ValidationStatus,
    tolerant_json_extract,
    validate_against_schema,
)

logger = logging.getLogger(__name__)

KararTipi = Literal["algoritma", "fiyat", "oncelik"]


# ---------------------------------------------------------------------------
# ExplainerInput
# ---------------------------------------------------------------------------


@dataclass
class ExplainerInput:
    """Aciklayici rolune girdi.

    Alanlar
    -------
    karar_tipi     : aciklanacak karar kategorisi
    sistem_ciktisi : deterministik motor ciktisi (dict); rakamlar buradan
    """

    karar_tipi: KararTipi
    sistem_ciktisi: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "karar_tipi": self.karar_tipi,
            "sistem_ciktisi": self.sistem_ciktisi,
        }

    def to_source_doc(self) -> SourceDoc:
        """Topraklama dogrulamasi icin sistem_ciktisi -> SourceDoc."""
        icerik = json.dumps(self.sistem_ciktisi, ensure_ascii=False, indent=2)
        return SourceDoc(
            id="sistem_ciktisi#input",
            tip="termin",
            icerik=icerik,
            uretici="explainer.input",
        )


# ---------------------------------------------------------------------------
# ExplainerResult
# ---------------------------------------------------------------------------


@dataclass
class ExplainerResult:
    """Aciklayici rolu sonucu.

    Alanlar
    -------
    role_result        : ham RoleResult (status, data, fallback, audit_ref)
    number_flag        : True ise aciklama_md'de sistem ciktisinda olmayan
                         rakam uretildi (sayi-topraklama UYARI)
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
# ExplainerRole
# ---------------------------------------------------------------------------


class ExplainerRole:
    """Sistem karar aciklayici LLM rolu.

    Parametreler
    ------------
    provider   : LLMProvider ornegi
    registry   : PromptRegistry ornegi
    audit      : AuditLogger ornegi
    role_cfg   : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "explainer"

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

    def explain(self, explainer_input: ExplainerInput) -> ExplainerResult:
        """Sistem kararini acikla.

        Adimlar:
        1. Girdi dict olustur ve LLM chain loop calistir.
        2. LLM basarisizsa dogrudan fallback don.
        3. Sayi-topraklama: aciklama_md'deki sayilari sistem_ciktisi'ndaki
           sayilarla karsilastir (UYARI modu — blok degil).
        4. ExplainerResult dondur.
        """
        input_dict = explainer_input.to_dict()
        role_result = self._run_chain(input_dict)

        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            return ExplainerResult(role_result=role_result)

        data = role_result.data or {}
        aciklama_md = data.get("aciklama_md", "")

        source_doc = explainer_input.to_source_doc()
        grounding = verify_number_grounding(aciklama_md, [source_doc])
        number_flag = not grounding.is_clean

        if number_flag:
            logger.warning(
                "Aciklayici sayi-topraklama UYARI: sistem ciktisinda bulunmayan "
                "sayilar aciklamada kullanildi: %s",
                grounding.ungrounded,
            )

        return ExplainerResult(
            role_result=role_result,
            number_flag=number_flag,
            ungrounded_numbers=grounding.ungrounded,
        )

    def _run_chain(self, input_dict: Dict[str, Any]) -> RoleResult:
        """Structured chain loop — base role modeli izler.

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
                f"<sistem_ciktisi>\n{input_text}\n</sistem_ciktisi>"
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

            parsed = tolerant_json_extract(last_text)
            if parsed is None:
                last_errors = [
                    f"JSON parse hatasi: gecerli JSON objesi bulunamadi. "
                    f"Metin: {last_text[:200]}"
                ]
                logger.warning(
                    "Aciklayici deneme %d: JSON parse hatasi.", attempt_count
                )
                continue

            vresult = validate_against_schema(parsed, schema)
            if vresult.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
                final_status = vresult.status
                final_data = vresult.data
                break

            last_errors = vresult.errors
            logger.warning(
                "Aciklayici deneme %d: schema hatasi: %s",
                attempt_count,
                last_errors,
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
