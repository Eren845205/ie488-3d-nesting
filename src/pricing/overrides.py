"""Iki seviyeli override (PLAN_DEMO1.md 7.3).

Seviye (a) — Kural duzeyi override
    Mevcut kural setindeki bir parametreyi degistirerek YENi versiyon yaratir.
    Orijinal kural seti ASLA degistirilmez — immutable. Yeni RuleSet nesnesi doner.

Seviye (b) — Teklif duzeyi override
    Hesaplanmis bir teklifin nihai fiyatini elle eger. Orijinal hesap silinmez;
    egilmis + gerekce + zaman damgasi ayri saklanir.

Her iki seviyede de iz kaydi (audit trail) tutulur.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.pricing.schema import PricingRule, RuleSet


# ---------------------------------------------------------------------------
# Yardimci zaman damgasi
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Seviye (a): Kural duzeyi override
# ---------------------------------------------------------------------------


@dataclass
class RuleOverrideRecord:
    """Kural parametresi degisikligini belgeler."""

    original_rule_set_version: str
    new_rule_set_version: str
    rule_id: str
    changed_params: Dict[str, Any]  # {param_adi: {"before": x, "after": y}}
    reason: str
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_rule_set_version": self.original_rule_set_version,
            "new_rule_set_version": self.new_rule_set_version,
            "rule_id": self.rule_id,
            "changed_params": self.changed_params,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


def override_rule_param(
    rule_set: RuleSet,
    rule_id: str,
    param: str,
    new_value: Any,
    reason: str,
    new_version: str,
    log_path: Optional[str] = None,
) -> tuple[RuleSet, RuleOverrideRecord]:
    """Kural setindeki tek bir parametreyi degistirerek yeni versiyon uretir.

    Parametreler
    ------------
    rule_set    : Degistirilecek orijinal kural seti (immutable — kopyalanir)
    rule_id     : Hedef kuralin id'si
    param       : Degistirilecek alan adi (ornek: "unit_price", "min_price")
    new_value   : Yeni deger
    reason      : Degisiklik gerekce metni (iz kaydi icin)
    new_version : Yeni kural seti versiyon etiketi
    log_path    : Verilirse override kaydi bu JSONL dosyasina otomatik yazilir
                  (varsayilan None = eski davranis, log yazilmaz)

    Donus
    -----
    (yeni_rule_set, override_kaydi) demeti
    """
    if new_version == rule_set.version:
        raise ValueError(
            f"new_version mevcut versiyonla ayni: {new_version!r}. "
            "Override her zaman farkli bir versiyon etiketi gerektirir."
        )
    old_rule_set = rule_set
    new_rule_set = copy.deepcopy(old_rule_set)
    new_rule_set.version = new_version

    target: Optional[PricingRule] = None
    for r in new_rule_set.rules:
        if r.id == rule_id:
            target = r
            break
    if target is None:
        raise KeyError(f"Kural bulunamadi: {rule_id!r}")

    old_value = getattr(target, param, None)
    setattr(target, param, new_value)
    new_rule_set.validate()

    record = RuleOverrideRecord(
        original_rule_set_version=old_rule_set.version,
        new_rule_set_version=new_version,
        rule_id=rule_id,
        changed_params={param: {"before": old_value, "after": new_value}},
        reason=reason,
    )
    if log_path is not None:
        # Gecikmeli import: versioning -> overrides circular bagimliligini önler
        from src.pricing.versioning import append_rule_override_record  # noqa: PLC0415
        append_rule_override_record(log_path, record)
    return new_rule_set, record


# ---------------------------------------------------------------------------
# Seviye (b): Teklif duzeyi override
# ---------------------------------------------------------------------------


@dataclass
class QuoteOverrideRecord:
    """Tek bir teklifin fiyatinin elle egildigini belgeler."""

    quote_id: str
    original_price: float
    overridden_price: float
    reason: str
    operator: str  # eger eden kullanicinin adi / kimligi
    timestamp: str = field(default_factory=_now_iso)

    # Orijinal hesap dokumu (asla silinmez; referans icin saklanir)
    original_breakdown_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "quote_id": self.quote_id,
            "original_price": self.original_price,
            "overridden_price": self.overridden_price,
            "reason": self.reason,
            "operator": self.operator,
            "timestamp": self.timestamp,
            "original_breakdown_summary": self.original_breakdown_summary,
        }


@dataclass
class OverriddenQuote:
    """Orijinal hesap + teklif duzeyi egilmis fiyati birlikte tutar."""

    quote_id: str
    original_price: float
    final_price: float  # egilmis; override yoksa original ile esit
    override_record: Optional[QuoteOverrideRecord] = None
    breakdown_lines: List[str] = field(default_factory=list)

    @property
    def was_overridden(self) -> bool:
        return self.override_record is not None


def apply_quote_override(
    quote_id: str,
    original_price: float,
    overridden_price: float,
    reason: str,
    operator: str,
    breakdown_lines: Optional[List[str]] = None,
) -> OverriddenQuote:
    """Tek teklif fiyatini elle eger; orijinal bilgiler korunur.

    Parametreler
    ------------
    quote_id         : Teklifin benzersiz kimligi
    original_price   : Motorun hesapladigi fiyat
    overridden_price : Operatorun elle koydugu fiyat
    reason           : Degisiklik gerekce metni
    operator         : Eger eden kullanici adi / id
    breakdown_lines  : Orijinal hesap dokumunun str listesi (opsiyonel, saklanir)

    Donus
    -----
    OverriddenQuote — orijinal + egilmis fiyati ve kaydi birlikte tasir
    """
    summary = "\n".join(breakdown_lines or [])
    record = QuoteOverrideRecord(
        quote_id=quote_id,
        original_price=original_price,
        overridden_price=overridden_price,
        reason=reason,
        operator=operator,
        original_breakdown_summary=summary,
    )
    return OverriddenQuote(
        quote_id=quote_id,
        original_price=original_price,
        final_price=overridden_price,
        override_record=record,
        breakdown_lines=list(breakdown_lines or []),
    )


# ---------------------------------------------------------------------------
# Override gecmisi yonetimi (bellekte; kalici iz icin versioning.py kullanin)
# ---------------------------------------------------------------------------


class OverrideLog:
    """Bellekteki kural ve teklif override kayitlarini yonetir.

    Kalici iz icin versioning.py append_quote_record() fonksiyonu kullanilir.
    Bu sinif test / baglam icinde gerekli oldugunda yaratilir.
    """

    def __init__(self) -> None:
        self._rule_overrides: List[RuleOverrideRecord] = []
        self._quote_overrides: List[QuoteOverrideRecord] = []

    def record_rule_override(self, record: RuleOverrideRecord) -> None:
        self._rule_overrides.append(record)

    def record_quote_override(self, record: QuoteOverrideRecord) -> None:
        self._quote_overrides.append(record)

    def rule_overrides(self) -> List[RuleOverrideRecord]:
        return list(self._rule_overrides)

    def quote_overrides(self) -> List[QuoteOverrideRecord]:
        return list(self._quote_overrides)

    def quote_override_for(self, quote_id: str) -> Optional[QuoteOverrideRecord]:
        for rec in reversed(self._quote_overrides):
            if rec.quote_id == quote_id:
                return rec
        return None
