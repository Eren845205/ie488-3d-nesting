"""Teklif yazici rol — musteri-yanit mail taslagi.

Girdi: TeklifInput
    musteri_adi     : musteri tam adi / hitap
    parca_ozeti     : [{"ad": str, "adet": int}, ...] parca listesi
    toplam_fiyat_usd: deterministik fiyat motoru ciktisi (float)
    termin_ifadesi  : serbest metin termin tahmini (str)
    context         : GroundedContext (kaynak ID'leri icin)

Cikti: TeklifResult
    role_result     : ham RoleResult (status, data, fallback, audit_ref)
    number_flag     : True ise mail_govde_md'de bağlam-disi sayi uretildi (UYARI)
    ungrounded_numbers: topraklanamayan sayilar listesi

Topraklama kurali: UYARI modunda (blok DEGIL).
    number_flag=True olsa bile status VALID kalir, fallback None'dir.
    Kucuk modelin baglamda olmayan sayi yazmasini engeller degil, isaretler.

Kural: LLM YAZAR, HESAPLAMAZ.
    Fiyat, adet ve termin girdiden aynen aktarilir; LLM yalnizca kibar mail kurar.
    Ic muhendislik terimleri (nesting yogunlugu, algoritma, voxel, seed) musteriye
    YAZILMAZ — prompt kurali + topraklama denetimi ile desteklenir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------------------
# TeklifInput
# ---------------------------------------------------------------------------


@dataclass
class TeklifInput:
    """Teklif rolune girdi.

    Alanlar
    -------
    musteri_adi      : musteri tam adi / hitap (orn. "Sayin Ahmet Yilmaz")
    parca_ozeti      : [{"ad": str, "adet": int}] liste
    toplam_fiyat_usd : deterministik fiyat motoru ciktisi
    termin_ifadesi   : serbest metin termin (orn. "5 is gunu")
    context          : GroundedContext (mevcut kaynak ID'leri)
    """

    musteri_adi: str
    parca_ozeti: List[Dict[str, Any]]
    toplam_fiyat_usd: float
    termin_ifadesi: str
    context: GroundedContext

    def _build_summary_doc(self) -> SourceDoc:
        """Teklif ozet SourceDoc — topraklama dogrulamasi icin sayilari topraklar."""
        parca_satirlar = []
        adet_degerleri = []
        for p in self.parca_ozeti:
            ad = p.get("ad", "")
            adet = p.get("adet", "")
            parca_satirlar.append(f"{ad} x{adet}")
            adet_degerleri.append(str(adet))
        parca_str = "; ".join(parca_satirlar) if parca_satirlar else "belirtilmedi"
        # adetler: say?lar? \b-uyumlu (word-boundary) sekilde tutan ek sat?r;
        # "x10" formatinda 10 regex ile yakalanamaz ama "adetler: 10" satirinda yakalanir.
        adetler_str = ", ".join(adet_degerleri) if adet_degerleri else ""

        icerik = (
            f"musteri: {self.musteri_adi}\n"
            f"parcalar: {parca_str}\n"
            + (f"adetler: {adetler_str}\n" if adetler_str else "")
            + f"fiyat: {self.toplam_fiyat_usd} USD\n"
            f"termin: {self.termin_ifadesi}"
        )
        return SourceDoc(
            id="teklif#ozet",
            tip="termin",
            icerik=icerik,
            uretici="teklif.input",
        )

    def augmented_context(self) -> GroundedContext:
        """Context'e teklif#ozet SourceDoc'u ekleyerek geri dondurur."""
        summary_doc = self._build_summary_doc()
        return GroundedContext(
            is_id=self.context.is_id,
            kaynaklar=[summary_doc] + list(self.context.kaynaklar),
            olusturma_zamani=self.context.olusturma_zamani,
        )

    def to_dict(self) -> Dict[str, Any]:
        """LLM girdisi icin serializeable dict.

        Augmented context kaynaklarini da dahil eder.
        """
        aug_ctx = self.augmented_context()
        return {
            "musteri_adi": self.musteri_adi,
            "parcalar": self.parca_ozeti,
            "toplam_fiyat_usd": self.toplam_fiyat_usd,
            "termin_ifadesi": self.termin_ifadesi,
            "kaynaklar": [
                {"id": doc.id, "tip": doc.tip, "icerik": doc.icerik}
                for doc in aug_ctx.kaynaklar
            ],
        }


# ---------------------------------------------------------------------------
# TeklifResult
# ---------------------------------------------------------------------------


@dataclass
class TeklifResult:
    """Teklif rolu sonucu.

    Alanlar
    -------
    role_result        : ham RoleResult (status, data, fallback, audit_ref)
    number_flag        : True ise mail_govde_md'de bağlam-disi sayi uretildi
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
# TeklifRole
# ---------------------------------------------------------------------------


class TeklifRole:
    """Musteri-yanit mail taslagi LLM rolu.

    Parametreler
    ------------
    provider   : LLMProvider ornegi
    registry   : PromptRegistry ornegi
    audit      : AuditLogger ornegi
    role_cfg   : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "teklif"

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

    def draft(self, teklif_input: TeklifInput) -> TeklifResult:
        """Mail taslagi uret.

        Adimlar:
        1. Girdi dict olustur (augmented context dahil) ve LLM chain loop calistir.
        2. LLM basarisizsa (INVALID/fallback) dogrudan TeklifResult don.
        3. kullanilan_kaynaklar normalizasyonu (dict -> id string).
        4. VALID/PARTIAL: mail_govde_md al; teklif#ozet her zaman eklenir.
        5. Sayi-topraklama UYARI modu: verify_number_grounding().
           number_flag=True olsa bile status VALID, fallback None (BLOK DEGIL).
        6. TeklifResult dondur.
        """
        aug_ctx = teklif_input.augmented_context()
        input_dict = teklif_input.to_dict()
        role_result = self._run_chain(input_dict)

        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            return TeklifResult(role_result=role_result)

        # Normalizasyon: kullanilan_kaynaklar icindeki dict -> id string
        data = role_result.data or {}
        data = self._normalize_payload(data)

        mail_govde_md = data.get("mail_govde_md", "")

        # Cited sources: kesisim + her zaman teklif#ozet
        cited_ids = data.get("kullanilan_kaynaklar", [])
        cited_ids_with_ozet = list(cited_ids)
        if "teklif#ozet" not in cited_ids_with_ozet:
            cited_ids_with_ozet.append("teklif#ozet")

        cited_sources = [
            doc for doc in aug_ctx.kaynaklar
            if doc.id in cited_ids_with_ozet
        ]

        grounding = verify_number_grounding(mail_govde_md, cited_sources)
        number_flag = not grounding.is_clean

        if number_flag:
            logger.warning(
                "Teklif sayi-topraklama UYARI (blok degil): "
                "mail_govde_md icinde baglamda bulunmayan sayilar: %s",
                grounding.ungrounded,
            )

        # UYARI modu: status degistirme, fallback set etme
        return TeklifResult(
            role_result=role_result,
            number_flag=number_flag,
            ungrounded_numbers=grounding.ungrounded,
        )

    @staticmethod
    def _normalize_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        """kullanilan_kaynaklar icindeki dict elemanlari id string'ine indirgenir.

        report._normalize_report_payload deseni — kucuk model halusinasyonu icin.
        """
        raw = data.get("kullanilan_kaynaklar")
        if not isinstance(raw, list):
            return data
        normalized = []
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

    def _run_chain(self, input_dict: Dict[str, Any]) -> RoleResult:
        """Structured chain loop — explainer/watcher deseniyle ayni.

        tolerant_json_extract -> _normalize_payload -> validate_against_schema -> retry.
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
            user_content = f"<teklif_verisi>\n{input_text}\n</teklif_verisi>"
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
                last_errors = [
                    "Yanit kesildi (finish_reason=length) — max_tokens artirin."
                ]
                logger.warning(
                    "Teklif deneme %d: finish_reason=length, yanit kesildi.",
                    attempt_count,
                )
                continue

            parsed = tolerant_json_extract(last_text)
            if parsed is None:
                last_errors = [
                    f"JSON parse hatasi: gecerli JSON objesi bulunamadi. "
                    f"Metin: {last_text[:200]}"
                ]
                logger.warning(
                    "Teklif deneme %d: JSON parse hatasi.", attempt_count
                )
                continue

            # Normalizasyon: validate oncesi
            normalized = self._normalize_payload(parsed)
            vresult = validate_against_schema(normalized, schema)
            if vresult.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
                final_status = vresult.status
                final_data = vresult.data
                break

            last_errors = vresult.errors
            logger.warning(
                "Teklif deneme %d: schema hatasi: %s",
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
