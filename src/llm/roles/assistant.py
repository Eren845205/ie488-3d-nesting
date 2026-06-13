"""Asistan rol — PLAN_LLM.md Faz L3.

(soru, GroundedContext) -> topraklanmis Turkce yanit.

3 kural (APP_YOL_HARITASI.md sek. 6.6):
  1. TOPRAKLAMA — yalniz sistem ciktilarindan konusur; kaynak gosterir.
  2. HESAPLAMAZ, ACIKLAR — yeni aritmetik uretmez.
  3. ONERIP UYGULAMAZ — aksiyonlar yalniz oneri listesinde.

Sema dogrulayici kurallari (kod, prompt degil):
  - ret=false ise alintilar bos OLAMAZ -> INVALID.
  - Her kaynak_id baglam kaynaklari icerisinde olmali -> UYARI (yumusak).
  - Sayi-topraklama: UYARI + bayrak (asistanda blok DEGiL).

Conversation: son 6 tur verbatim (tarihsel; baglam her soru aninda yeniden kurulur).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import GroundedContext, SourceDoc, verify_number_grounding
from src.llm.prompts import PromptRegistry
from src.llm.provider import LLMProvider, LLMRequest, LLMResponse
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import (
    HumanFallback,
    ValidationStatus,
    validate_against_schema,
    tolerant_json_extract,
)

logger = logging.getLogger(__name__)

_MAX_HISTORY_TURNS = 6


# ---------------------------------------------------------------------------
# Conversation geçmisi
# ---------------------------------------------------------------------------


@dataclass
class ConversationTurn:
    """Tek bir soru-cevap turu."""

    soru: str
    cevap_md: str


@dataclass
class Conversation:
    """Son MAX_HISTORY_TURNS turu saklar.

    Kural: gecmis ASLA olgu kaynaklari olarak sunulmaz; yalniz baglam
    saglayici (ne soruldu, ne cevaplandi) bilgisi. GroundedContext her soru
    aninda yeniden kurulur.
    """

    turns: List[ConversationTurn] = field(default_factory=list)
    max_turns: int = _MAX_HISTORY_TURNS

    def add(self, soru: str, cevap_md: str) -> None:
        self.turns.append(ConversationTurn(soru=soru, cevap_md=cevap_md))
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def to_history_text(self) -> str:
        """Gecmis turlari okunabilir metin olarak dondurur."""
        if not self.turns:
            return ""
        lines = ["## Onceki Soru-Cevaplar (baglam degil, gecmis kayit)"]
        for i, turn in enumerate(self.turns, start=1):
            lines.append(f"**Soru {i}:** {turn.soru}")
            lines.append(f"**Cevap {i}:** {turn.cevap_md}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AssistantResult
# ---------------------------------------------------------------------------


@dataclass
class AssistantResult:
    """Asistan rolu sonucu.

    Alanlar
    -------
    role_result          : ham RoleResult
    number_flag          : True ise sayi-topraklama UYARI bayragi
    ungrounded_numbers   : topraklanamayan sayilar listesi
    unknown_citation_ids : baglam disindaki kaynak_id'ler (yumusak uyari)
    """

    role_result: RoleResult
    number_flag: bool = False
    ungrounded_numbers: List[str] = field(default_factory=list)
    unknown_citation_ids: List[str] = field(default_factory=list)

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
# AssistantRole
# ---------------------------------------------------------------------------


class AssistantRole:
    """Asistan LLM rolu.

    Parametreler
    ------------
    provider    : LLMProvider ornegi
    registry    : PromptRegistry ornegi
    audit       : AuditLogger ornegi
    role_cfg    : RoleConfig (None ise varsayilanlar)
    conversation: paylasilan Conversation (opsiyonel; None ise yeni)
    """

    ROLE_NAME = "assistant"

    def __init__(
        self,
        provider: Any,
        registry: PromptRegistry,
        audit: AuditLogger,
        role_cfg: Optional[RoleConfig] = None,
        conversation: Optional[Conversation] = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._audit = audit
        self._role_cfg = role_cfg
        self._conversation = conversation or Conversation()

        # base role — sema dogrulamasi + audit + retry burada
        self._base_role = LLMRole(
            role_name=self.ROLE_NAME,
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=role_cfg,
        )

    @property
    def conversation(self) -> Conversation:
        return self._conversation

    @staticmethod
    def _normalize_assistant_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        """alintilar listesindeki kaynak_id degerlerini string'e normalize eder.

        Model kucuk lokal modellerde kaynak_id yerine tam kaynak nesnesini
        ({'id': ..., 'tip': ..., 'icerik': ...}) kopyalayabilir.
        'id' anahtari tasiyan dict ise o id string'ine indirgenir;
        diger yapilar (id'siz dict, vs.) oldugu gibi birakilir.

        Sadece alintilar[].kaynak_id alanina dokunulur; baska hicbir alana dokunulmaz.
        """
        raw = data.get("alintilar")
        if not isinstance(raw, list):
            return data
        changed = False
        normalized: List[Any] = []
        for item in raw:
            if isinstance(item, dict):
                kaynak_id = item.get("kaynak_id")
                if isinstance(kaynak_id, dict) and "id" in kaynak_id:
                    item = dict(item)
                    item["kaynak_id"] = str(kaynak_id["id"])
                    changed = True
            normalized.append(item)
        if not changed:
            return data
        result = dict(data)
        result["alintilar"] = normalized
        return result

    def _run_with_normalization(self, input_dict: Dict[str, Any]) -> "RoleResult":
        """_base_role.run() yerine: alintilar normalizasyonu ile custom chain loop."""
        from src.llm.provider import LLMRequest as _Req, LLMResponse as _Resp

        br = self._base_role
        tpl = br._registry.load(br._role_name)
        schema = tpl.schema
        schema_retry = br._role_cfg.schema_retry if br._role_cfg else 2
        model_id = br._role_cfg.model if br._role_cfg else "fake"
        temperature = br._role_cfg.temperature if br._role_cfg else 0.0
        max_tokens = br._role_cfg.max_tokens if br._role_cfg else 1024

        def build_request(prev_errors: List[str]):
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
                logger.warning("Asistan deneme %d: JSON parse hatasi.", attempt_count)
                continue

            normalized = self._normalize_assistant_payload(parsed)

            vresult = validate_against_schema(normalized, schema)
            if vresult.status in (ValidationStatus.VALID, ValidationStatus.PARTIAL):
                final_status = vresult.status
                final_data = vresult.data
                break

            last_errors = vresult.errors
            logger.warning(
                "Asistan deneme %d: schema hatasi: %s", attempt_count, last_errors
            )
        else:
            final_fallback = HumanFallback(
                raw_text=last_text,
                errors=last_errors,
                call_ref=br._role_name,
            )
            final_status = ValidationStatus.INVALID

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

    def ask(self, soru: str, context: GroundedContext) -> AssistantResult:
        """Kullanicinin sorusunu baglam icerisinde cevapla.

        Adimlar:
        1. Girdi dict kur (soru + baglam + gecmis).
        2. LLMRole.run() ile yanit al (schema + retry).
        3. Alinti zorunluluğu kontrolu (ret=false ise alintilar dolu olmali).
        4. Kaynak_id baglam kontrolu (yumusak uyari).
        5. Sayi-topraklama (UYARI+bayrak; blok degil).
        6. Basarili yaniti conversation'a ekle.
        """
        input_dict = self._build_input(soru, context)
        role_result = self._run_with_normalization(input_dict)

        # LLM basarisiz
        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            return AssistantResult(role_result=role_result)

        data = role_result.data or {}

        # Alinti zorunluluğu: ret=false ise alintilar bos olamaz
        ret_flag = data.get("ret", False)
        alintilar = data.get("alintilar", [])

        if not ret_flag and not alintilar:
            logger.warning(
                "Asistan: ret=false ama alintilar bos — INVALID (alinti zorunlulugu)."
            )
            empty_citation_fallback = HumanFallback(
                raw_text=json.dumps(data, ensure_ascii=False),
                errors=["Schema kurali ihlali: ret=false oldugunda alintilar bos olamaz."],
                call_ref=role_result.audit_ref,
            )
            invalid_result = RoleResult(
                status=ValidationStatus.INVALID,
                data=None,
                fallback=empty_citation_fallback,
                audit_ref=role_result.audit_ref,
                attempt_count=role_result.attempt_count,
                errors=empty_citation_fallback.errors,
            )
            return AssistantResult(role_result=invalid_result)

        # Kaynak_id baglam kontrolu (yumusak — UYARI, blok degil)
        context_ids = set(context.kaynak_ids())
        unknown_ids = [
            a.get("kaynak_id", "")
            for a in alintilar
            if a.get("kaynak_id", "") not in context_ids
        ]
        if unknown_ids:
            logger.warning(
                "Asistan: kaynak_id'ler baglamda yok (yumusak uyari): %s", unknown_ids
            )

        # Sayi-topraklama (UYARI + bayrak; blok degil)
        cevap_md = data.get("cevap_md", "")
        cited_ids = [a.get("kaynak_id", "") for a in alintilar]
        cited_sources = [
            doc for doc in context.kaynaklar
            if doc.id in cited_ids
        ]
        grounding = verify_number_grounding(cevap_md, cited_sources)
        number_flag = not grounding.is_clean
        if number_flag:
            logger.warning(
                "Asistan sayi-topraklama UYARI: topraklanamayan sayilar %s",
                grounding.ungrounded,
            )

        # Basarili yanit -> conversation'a ekle
        if not ret_flag:
            self._conversation.add(soru=soru, cevap_md=cevap_md)

        return AssistantResult(
            role_result=role_result,
            number_flag=number_flag,
            ungrounded_numbers=grounding.ungrounded,
            unknown_citation_ids=unknown_ids,
        )

    # ------------------------------------------------------------------
    # Yardimci
    # ------------------------------------------------------------------

    def _build_input(self, soru: str, context: GroundedContext) -> Dict[str, Any]:
        """LLMRole.run() icin girdi dict'i olusturur."""
        return {
            "soru": soru,
            "baglam_kaynaklari": context.kaynak_ids(),
            "baglam_metni": context.to_context_text(),
            "gecmis": self._conversation.to_history_text(),
        }
