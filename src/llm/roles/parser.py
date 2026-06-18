"""Parser rolu — serbest metin/mail -> yapilandirilmis siparis JSON.

Demo'nun en yuksek-drama ani: sistem maili okuyup siparis yapilandiriyor.

Girdi  : {"mail_text": "<serbest metin>"}
Cikti  : RoleResult (VALID | PARTIAL -> data, INVALID -> fallback)

data sozlugu (parser-v1 semasi):
  musteri           : {ad, iletisim}
  termin            : {tarih, ham_ifade}
  parcalar          : [{ad, adet, boyut_mm, agirlik_kg, kaynak, guven}, ...]
  eksik_alanlar     : [str, ...]
  notlar            : str | null
  injection_suphesi : bool

Demo siparis formatina donusum (parsed_to_order):
  parser ciktisi -> SCENARIO['orders'] elemaniyla uyumlu dict.
  boyut_mm: [en, boy, yukseklik] -> en_mm, boy_mm, yukseklik_mm
  Eksik boyut -> 1.0 mm (guvensiz; eksik_alanlar listesinde gosterilir)

Kural: parser YALNIZCA veri cikarir; nesting/fiyat/cizelge
       deterministik motorlardan gelir (kesintisiz kural §6.1).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.prompts import PromptRegistry
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import HumanFallback, ValidationStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ParserResult
# ---------------------------------------------------------------------------


@dataclass
class ParserResult:
    """Parser rolu sonucu.

    Alanlar
    -------
    role_result       : ham RoleResult (status, data, fallback, audit_ref)
    order_dict        : demo SCENARIO siparisiyle uyumlu dict (basarili ise dolu)
    eksik_alanlar     : parser'in raporladigi eksik alanlar
    injection_suphesi : True ise kullanici girdisinde saldiri suptesi var
    """

    role_result: RoleResult
    order_dict: Optional[Dict[str, Any]] = None
    eksik_alanlar: Optional[List[str]] = None
    injection_suphesi: bool = False

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
# Donusturucu: parser ciktisi -> demo siparis dict'i
# ---------------------------------------------------------------------------

_BOYUT_EKSIK_DEGER = 1.0  # mm cinsinden placeholder

# Makul ust sinir: en buyuk endustriyel konteyner ~40 ft ISO = ~12192 mm ic uzunluk.
# Parcalarin hicbiri konteyneri asamayacagindan 5000 mm genis bir guvensizlik tampon.
MAX_BOYUT_MM = 5000.0


def parsed_to_order(
    data: Dict[str, Any],
    order_id: Optional[str] = None,
    priority_class: int = 2,
) -> Dict[str, Any]:
    """Parser ciktisindan demo SCENARIO siparis dict'i uret.

    Parametreler
    ------------
    data           : ParserRole.run().data (parser-v1 semasi)
    order_id       : bos ise UUID4'ten otomatik uretilir
    priority_class : varsayilan oncelik sinifi (parser eksikse kullanilir)

    Dondurur
    --------
    SCENARIO['orders'] elemaniyla uyumlu dict:
    {
      order_id, customer, deadline, priority_class,
      parts: [{id, name, qty, source, width_mm, depth_mm, height_mm}, ...]
    }

    Guvensiz donusum:
      - boyut_mm eksik/bos -> her boyut _BOYUT_EKSIK_DEGER (1.0 mm) olarak ayarlanir
      - termin.tarih None ise deadline = "" (pipeline'in kendisi uyarir)
    """
    if order_id is None:
        order_id = f"PARSED-{uuid.uuid4().hex[:8].upper()}"

    musteri = data.get("musteri") or {}
    customer = (musteri.get("ad") or "").strip() or "Bilinmiyor"

    termin = data.get("termin") or {}
    deadline = (termin.get("tarih") or "").strip()

    parcalar = data.get("parcalar") or []
    parts: List[Dict[str, Any]] = []
    eksik_alanlar_boyut: List[str] = []

    def _safe_boyut(raw_val: Any, alan_adi: str) -> float:
        """raw_val'i float'a cevirir; hata veya aralik disi -> _BOYUT_EKSIK_DEGER."""
        try:
            v = float(raw_val)
        except (ValueError, TypeError):
            logger.warning(
                "parsed_to_order: %s float'a donusturulemedi (%r) — placeholder kullanildi.",
                alan_adi, raw_val,
            )
            eksik_alanlar_boyut.append(alan_adi)
            return _BOYUT_EKSIK_DEGER
        if not (0 < v <= MAX_BOYUT_MM):
            logger.warning(
                "parsed_to_order: %s aralik disi (%.3g, beklenen 0 < boyut <= %.3g) "
                "— placeholder kullanildi.",
                alan_adi, v, MAX_BOYUT_MM,
            )
            eksik_alanlar_boyut.append(alan_adi)
            return _BOYUT_EKSIK_DEGER
        return v

    for i, p in enumerate(parcalar):
        boyut = p.get("boyut_mm") or []
        en = _safe_boyut(boyut[0], f"parcalar[{i}].boyut_mm[0]") if len(boyut) > 0 else _BOYUT_EKSIK_DEGER
        boy = _safe_boyut(boyut[1], f"parcalar[{i}].boyut_mm[1]") if len(boyut) > 1 else _BOYUT_EKSIK_DEGER
        yuk = _safe_boyut(boyut[2], f"parcalar[{i}].boyut_mm[2]") if len(boyut) > 2 else _BOYUT_EKSIK_DEGER
        parts.append({
            "id": f"parsed_{i+1}",
            "name": (p.get("ad") or f"parca_{i+1}").strip(),
            "qty": int(p.get("adet") or 1),
            "source": "box",
            "width_mm": en,
            "depth_mm": boy,
            "height_mm": yuk,
        })

    return {
        "order_id": order_id,
        "customer": customer,
        "deadline": deadline,
        "priority_class": priority_class,
        "parts": parts,
    }


# ---------------------------------------------------------------------------
# ParserRole
# ---------------------------------------------------------------------------


class ParserRole:
    """Mail/serbest metin -> yapilandirilmis siparis.

    Parametreler
    ------------
    provider  : LLMProvider ornegi
    registry  : PromptRegistry ornegi
    audit     : AuditLogger ornegi
    role_cfg  : RoleConfig (None ise varsayilanlar)
    """

    ROLE_NAME = "parser"

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

    def parse(self, mail_text: str) -> ParserResult:
        """Ham metin/mail'den siparis cikar.

        Adimlar:
          1. LLMRole.run() -> parser-v1 semasi ile yapilandirilmis JSON
          2. injection_suphesi kontrolu -> UYARI (blok degil)
          3. Basarili ise parsed_to_order() ile demo siparis dict'ine don
          4. Basarisiz (INVALID/fallback) ise HumanFallback

        Parametreler
        ------------
        mail_text : ham siparis metni (mail, WhatsApp, not, vb.)

        Dondurur
        --------
        ParserResult
        """
        input_dict = {"mail_text": mail_text}
        role_result = self._base_role.run(input_dict)

        if role_result.status == ValidationStatus.INVALID or role_result.fallback:
            logger.warning(
                "ParserRole: LLM gecerli siparis JSON'u uretemedi. "
                "audit_ref=%s", role_result.audit_ref
            )
            return ParserResult(
                role_result=role_result,
                order_dict=None,
                eksik_alanlar=None,
                injection_suphesi=False,
            )

        data = role_result.data or {}
        injection = bool(data.get("injection_suphesi", False))

        if injection:
            logger.warning(
                "ParserRole: injection_suphesi=true — kullanici girdisinde "
                "saldiri suptesi. audit_ref=%s", role_result.audit_ref
            )

        eksik = list(data.get("eksik_alanlar") or [])

        # Deadline gercekten parse edildiyse "termin.tarih" eksik_alanlar'dan cikar.
        termin = data.get("termin") or {}
        _deadline_val = (termin.get("tarih") or "").strip()
        if _deadline_val and "termin.tarih" in eksik:
            eksik = [e for e in eksik if e != "termin.tarih"]
            logger.debug(
                "ParserRole: termin.tarih dolu (%r) — eksik_alanlar'dan cikarildi.",
                _deadline_val,
            )

        if eksik:
            logger.info("ParserRole: eksik alanlar bildirdi: %s", eksik)

        order_dict = parsed_to_order(data)

        return ParserResult(
            role_result=role_result,
            order_dict=order_dict,
            eksik_alanlar=eksik,
            injection_suphesi=injection,
        )
