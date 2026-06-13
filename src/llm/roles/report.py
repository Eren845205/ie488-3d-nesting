"""Rapor yazici rol — PLAN_LLM.md Faz L1.

Pipeline sonucundan (cizelge raporu + nesting metrikleri + fiyat dokumleri)
GroundedContext kur -> kisa Turkce yonetici ozeti uret (3-6 cumle).

Sayi-topraklama kurali: BLOK modunda.
  - verify_number_grounding() basarisizsa ozet reddedilir.
  - HumanFallback donulur, kullanici uyarilir.

Girdi: ReportInput veya sozluk (is_id, n_orders, n_batches, n_warnings,
       total_revenue_usd, kaynaklar: [SourceDoc]).
Cikti: RoleResult (VALID | PARTIAL -> data, INVALID -> fallback)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import GroundedContext, SourceDoc, verify_number_grounding
from src.llm.prompts import PromptRegistry
from src.llm.provider import LLMProvider, LLMRequest
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import (
    HumanFallback,
    ValidationStatus,
    tolerant_json_extract,
    validate_against_schema,
)

logger = logging.getLogger(__name__)

# Topraklama reddi icin sentinel status
_GROUNDING_BLOCKED = "GROUNDING_BLOCKED"


@dataclass
class ReportInput:
    """Rapor rolune girdi."""

    is_id: str
    n_orders: int
    n_batches: int
    n_warnings: int
    total_revenue_usd: float
    context: GroundedContext

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_id": self.is_id,
            "n_orders": self.n_orders,
            "n_batches": self.n_batches,
            "n_warnings": self.n_warnings,
            "total_revenue_usd": self.total_revenue_usd,
            "kaynaklar": [
                {"id": doc.id, "tip": doc.tip, "icerik": doc.icerik}
                for doc in self.context.kaynaklar
            ],
        }


@dataclass
class ReportResult:
    """Rapor rolu sonucu.

    Alanlar
    -------
    role_result      : ham RoleResult (status, data, fallback, audit_ref)
    grounding_blocked: True ise sayı-topraklama BLOK modu devreye girdi
    grounding_detail : topraklama dogrulamasi detayi (ungrounded sayilar)
    """

    role_result: RoleResult
    grounding_blocked: bool = False
    grounding_detail: List[str] = field(default_factory=list)

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


class ReportRole:
    """Rapor yazici LLM rolu.

    Parametreler
    ------------
    provider   : LLMProvider ornegi
    registry   : PromptRegistry ornegi
    audit      : AuditLogger ornegi
    role_cfg   : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "report"

    def __init__(
        self,
        provider: Any,
        registry: PromptRegistry,
        audit: AuditLogger,
        role_cfg: Optional[RoleConfig] = None,
    ) -> None:
        self._base_role = LLMRole(
            role_name=self.ROLE_NAME,
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=role_cfg,
        )

    @staticmethod
    def _normalize_report_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        """kullanilan_kaynaklar icindeki dict elemanlari id string'ine indirgenir.

        Model kucuk lokal modellerde kaynak nesnesini ('id', 'tip', 'icerik' anahtarli
        dict) kopyalayabilir. Sadece 'id' anahtari tasiyan dict elemanlar string'e
        donusturulur; diger dict'ler (id'siz veya farkli yapilar) oldugu gibi birakilir
        ki gercek sema hatasi gorunur kalsin.

        Baska hicbir alana dokunulmaz.
        """
        raw = data.get("kullanilan_kaynaklar")
        if not isinstance(raw, list):
            return data
        normalized: List[Any] = []
        for item in raw:
            if isinstance(item, dict) and "id" in item:
                normalized.append(str(item["id"]))
            else:
                normalized.append(item)
        if normalized == raw:
            return data
        result = dict(data)
        result["kullanilan_kaynaklar"] = normalized
        return result

    def run(self, report_input: ReportInput) -> ReportResult:
        """Rapor uret.

        1. LLM ozet uret (normalizasyon katmani + base role).
        2. Sayi-topraklama dogrula (BLOK mod).
        3. Topraklama basarisizsa RoleResult.status=INVALID + fallback.

        Normalizasyon: sema dogrulamasindan ONCE kullanilan_kaynaklar icerisindeki
        dict elemanlar (kucuk modellerin halusinasyonu) id string'ine indirgenir.
        Bu sayede 'is not of type string' hatasi ortadan kalkar.
        """
        # Pipeline-duzey sayilari da kaynak olarak ekle (n_orders, n_batches, vb.)
        augmented_context = self._augment_context(report_input)
        augmented_input = ReportInput(
            is_id=report_input.is_id,
            n_orders=report_input.n_orders,
            n_batches=report_input.n_batches,
            n_warnings=report_input.n_warnings,
            total_revenue_usd=report_input.total_revenue_usd,
            context=augmented_context,
        )

        input_dict = augmented_input.to_dict()
        role_result = self._run_with_normalization(input_dict)

        # LLM basarisizsa (INVALID/fallback) dogrudan don
        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            return ReportResult(
                role_result=role_result,
                grounding_blocked=False,
            )

        # Sayi-topraklama kontrolu (BLOK mod) — augmented context ile
        data = role_result.data or {}
        govde = data.get("govde_md", "")
        cited_ids = data.get("kullanilan_kaynaklar", [])
        # Pipeline ozet kaynagi her zaman dahil
        cited_ids_with_summary = list(cited_ids) + ["pipeline#ozet"]
        cited_sources = [
            doc for doc in augmented_context.kaynaklar
            if doc.id in cited_ids_with_summary
        ]

        grounding_result = verify_number_grounding(govde, cited_sources)

        if not grounding_result.is_clean:
            logger.warning(
                "Rapor: sayi-topraklama ihlali — topraklanmamis sayilar: %s. "
                "Ozet REDDEDILDI (BLOK mod).",
                grounding_result.ungrounded,
            )
            blocked_fallback = HumanFallback(
                raw_text=govde,
                errors=[
                    f"Sayi-topraklama ihlali: su sayilar baglamda dogrulanamadi: "
                    f"{grounding_result.ungrounded}. "
                    "LLM ciktisi reddedildi; lutfen manuel ozet yazin."
                ],
                call_ref=role_result.audit_ref,
            )
            blocked_result = RoleResult(
                status=ValidationStatus.INVALID,
                data=None,
                fallback=blocked_fallback,
                audit_ref=role_result.audit_ref,
                attempt_count=role_result.attempt_count,
                errors=blocked_fallback.errors,
            )
            return ReportResult(
                role_result=blocked_result,
                grounding_blocked=True,
                grounding_detail=grounding_result.ungrounded,
            )

        return ReportResult(
            role_result=role_result,
            grounding_blocked=False,
        )

    def _run_with_normalization(self, input_dict: Dict[str, Any]) -> "RoleResult":
        """_base_role.run() yerine: normalizasyon katmani ile custom chain loop.

        tolerant_json_extract -> _normalize_report_payload -> validate_against_schema
        adimlarini retry dongusuyle isler; audit ve request insasi _base_role'den alir.
        """
        br = self._base_role
        tpl = br._registry.load(br._role_name)
        schema = tpl.schema
        schema_retry = br._role_cfg.schema_retry if br._role_cfg else 2
        model_id = br._role_cfg.model if br._role_cfg else "fake"
        temperature = br._role_cfg.temperature if br._role_cfg else 0.0
        max_tokens = br._role_cfg.max_tokens if br._role_cfg else 1024

        def build_request(prev_errors: List[str]):
            from src.llm.provider import LLMRequest as _Req
            few_shot = tpl.few_shot_text()
            slots: Dict[str, str] = {"few_shot": few_shot}
            try:
                system_text = tpl.render(slots)
            except Exception:
                slots["context"] = ""
                system_text = tpl.render(slots)
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
            return _Req(
                messages=messages,
                schema=schema,
                max_tokens=max_tokens,
                temperature=temperature,
                role_tag=br._role_name,
                template_id=tpl.id,
            )

        # Normalizasyon destekli chain loop
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
                logger.warning("Rapor deneme %d: JSON parse hatasi.", attempt_count)
                continue

            # Normalizasyon: kullanilan_kaynaklar dict elemanlarini id string'ine indirgir
            normalized = self._normalize_report_payload(parsed)

            vresult = validate_against_schema(normalized, schema)
            if vresult.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
                final_status = vresult.status
                final_data = vresult.data
                break

            last_errors = vresult.errors
            logger.warning(
                "Rapor deneme %d: schema hatasi: %s", attempt_count, last_errors
            )
        else:
            final_fallback = HumanFallback(
                raw_text=last_text,
                errors=last_errors,
                call_ref=br._role_name,
            )
            final_status = ValidationStatus.INVALID

        # Audit
        from src.llm.provider import LLMResponse as _Resp
        if last_resp is not None:
            audit_resp = last_resp
        else:
            audit_resp = _Resp(
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
            role=br._role_name,
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

    @staticmethod
    def _augment_context(report_input: "ReportInput") -> "GroundedContext":
        """Pipeline-duzey sayilari iceren ek SourceDoc ile context'i zenginlestirir.

        n_orders, n_batches, n_warnings, total_revenue_usd sayilari "pipeline#ozet"
        kaynaginda topraklanir. Bu sayede govde_md'deki bu sayilar dogrulama gecebilir.
        """
        from src.llm.grounding import GroundedContext

        summary_doc = SourceDoc(
            id="pipeline#ozet",
            tip="termin",
            icerik=(
                f"Siparis sayisi: {report_input.n_orders}\n"
                f"Parti sayisi: {report_input.n_batches}\n"
                f"Uyari sayisi: {report_input.n_warnings}\n"
                f"Toplam ciro: {report_input.total_revenue_usd} USD"
            ),
            uretici="demo_pipeline",
        )

        augmented = GroundedContext(
            is_id=report_input.context.is_id,
            kaynaklar=[summary_doc] + list(report_input.context.kaynaklar),
            olusturma_zamani=report_input.context.olusturma_zamani,
        )
        return augmented
