"""Fiyatlama kural seti normalizasyon semasi (PLAN_DEMO1.md 7.1).

Desteklenen kural tipleri
-------------------------
unit_price     : birim * birim_fiyat = ara_tutar
                 Parametreler: input_field (str), unit_price (float)

tier_table     : girdi araliklar tablosuna gore kademeli fiyat
                 Parametreler: input_field (str), tiers listesi
                 Her tier: {"up_to": float|null, "price": float}
                 up_to=null => son kademe (sinirsiz)

conditional_multiplier : baska bir alanin degeri sartini saglarsa carpan uygular
                         Parametreler: condition_field (str), operator (str),
                         threshold (float), multiplier (float)

min_clamp      : toplam fiyatin altina dusmesini engeller
                 Parametreler: min_price (float)

max_clamp      : toplam fiyatin ustune cikmesini engeller
                 Parametreler: max_price (float)

Girdi alanlari
--------------
Standart alanlar: hacim_m3, agirlik_kg, konteyner_sayisi, doluluk_oran, mesafe_km
Alan listesi genisleyebilir — motor alan-agnostiktir.

JSON yapisi
-----------
{
  "version": "1.0",
  "name": "Ornek kural seti",
  "rules": [
    {
      "id": "r1",
      "type": "unit_price",
      "input_field": "hacim_m3",
      "unit_price": 500.0,
      "description": "Hacim bazi birim fiyat"
    },
    ...
  ]
}
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Sabitleri (desteklenen kural tipleri)
# ---------------------------------------------------------------------------

RULE_TYPES = frozenset(
    {
        "unit_price",
        "tier_table",
        "conditional_multiplier",
        "min_clamp",
        "max_clamp",
    }
)

STANDARD_INPUT_FIELDS = frozenset(
    {
        "hacim_m3",
        "agirlik_kg",
        "konteyner_sayisi",
        "doluluk_oran",
        "mesafe_km",
    }
)


# ---------------------------------------------------------------------------
# Kural dataclass'lari
# ---------------------------------------------------------------------------


@dataclass
class TierEntry:
    """Tek bir kademe tablosu satirini temsil eder."""

    price: float
    up_to: Optional[float] = None  # None => sinirsiz (son kademe)

    def to_dict(self) -> Dict[str, Any]:
        return {"up_to": self.up_to, "price": self.price}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TierEntry":
        return cls(price=float(d["price"]), up_to=d.get("up_to"))


@dataclass
class PricingRule:
    """Tek bir fiyatlama kuralini temsil eder."""

    id: str
    type: str
    description: str = ""

    # unit_price parametreleri
    input_field: Optional[str] = None
    unit_price: Optional[float] = None

    # tier_table parametreleri
    tiers: List[TierEntry] = field(default_factory=list)

    # conditional_multiplier parametreleri
    condition_field: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    multiplier: Optional[float] = None

    # min_clamp / max_clamp parametreleri
    min_price: Optional[float] = None
    max_price: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "description": self.description,
        }
        if self.input_field is not None:
            d["input_field"] = self.input_field
        if self.unit_price is not None:
            d["unit_price"] = self.unit_price
        if self.tiers:
            d["tiers"] = [t.to_dict() for t in self.tiers]
        if self.condition_field is not None:
            d["condition_field"] = self.condition_field
        if self.operator is not None:
            d["operator"] = self.operator
        if self.threshold is not None:
            d["threshold"] = self.threshold
        if self.multiplier is not None:
            d["multiplier"] = self.multiplier
        if self.min_price is not None:
            d["min_price"] = self.min_price
        if self.max_price is not None:
            d["max_price"] = self.max_price
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PricingRule":
        tiers = [TierEntry.from_dict(t) for t in d.get("tiers", [])]
        return cls(
            id=d["id"],
            type=d["type"],
            description=d.get("description", ""),
            input_field=d.get("input_field"),
            unit_price=d.get("unit_price"),
            tiers=tiers,
            condition_field=d.get("condition_field"),
            operator=d.get("operator"),
            threshold=d.get("threshold"),
            multiplier=d.get("multiplier"),
            min_price=d.get("min_price"),
            max_price=d.get("max_price"),
        )


@dataclass
class RuleSet:
    """Musteriye ozel fiyatlama kural setini temsil eder.

    Her musteriyi farkli JSON dosyasinda saklanir; kodda sabit deger yoktur.
    """

    version: str
    name: str
    rules: List[PricingRule] = field(default_factory=list)

    # ---------------------------------------------------------------------------
    # Dogrulama
    # ---------------------------------------------------------------------------

    def validate(self) -> None:
        """Kural setinin gecerliligi dogrular. Hata varsa ValueError firlatir."""
        if not self.version:
            raise ValueError("version alani bos olamaz")
        if not self.name:
            raise ValueError("name alani bos olamaz")
        seen_ids: set = set()
        for rule in self.rules:
            if not rule.id:
                raise ValueError("Kural id bos olamaz")
            if rule.id in seen_ids:
                raise ValueError(f"Tekrar kural id: {rule.id!r}")
            seen_ids.add(rule.id)
            if rule.type not in RULE_TYPES:
                raise ValueError(
                    f"Gecersiz kural tipi {rule.type!r}. "
                    f"Gecerli tipler: {sorted(RULE_TYPES)}"
                )
            _validate_rule_params(rule)

    # ---------------------------------------------------------------------------
    # JSON round-trip
    # ---------------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "rules": [r.to_dict() for r in self.rules],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RuleSet":
        rules = [PricingRule.from_dict(r) for r in d.get("rules", [])]
        return cls(version=d["version"], name=d["name"], rules=rules)

    @classmethod
    def from_json(cls, text: str) -> "RuleSet":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_file(cls, path: str) -> "RuleSet":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


# ---------------------------------------------------------------------------
# Yardimci dogrulayicilar
# ---------------------------------------------------------------------------


def _validate_rule_params(rule: PricingRule) -> None:
    if rule.type == "unit_price":
        _require(rule, "input_field", "unit_price")
        if rule.unit_price < 0:
            raise ValueError(f"Kural {rule.id!r}: unit_price negatif olamaz")

    elif rule.type == "tier_table":
        _require(rule, "input_field")
        if not rule.tiers:
            raise ValueError(f"Kural {rule.id!r}: tier_table bos tiers olamaz")
        _validate_tiers(rule.id, rule.tiers)

    elif rule.type == "conditional_multiplier":
        _require(rule, "condition_field", "operator", "threshold", "multiplier")
        valid_ops = {"<", "<=", ">", ">=", "==", "!="}
        if rule.operator not in valid_ops:
            raise ValueError(
                f"Kural {rule.id!r}: gecersiz operator {rule.operator!r}. "
                f"Gecerliler: {sorted(valid_ops)}"
            )
        if rule.multiplier <= 0:
            raise ValueError(f"Kural {rule.id!r}: multiplier pozitif olmali")

    elif rule.type == "min_clamp":
        _require(rule, "min_price")
        if rule.min_price < 0:
            raise ValueError(f"Kural {rule.id!r}: min_price negatif olamaz")

    elif rule.type == "max_clamp":
        _require(rule, "max_price")
        if rule.max_price < 0:
            raise ValueError(f"Kural {rule.id!r}: max_price negatif olamaz")


def _require(rule: PricingRule, *fields: str) -> None:
    for f in fields:
        if getattr(rule, f) is None:
            raise ValueError(
                f"Kural {rule.id!r} ({rule.type}): '{f}' alani zorunlu"
            )


def _validate_tiers(rule_id: str, tiers: List[TierEntry]) -> None:
    """Kademelerin tutarli oldugunu dogrular (son kademe haric up_to mevcut,
    up_to degerleri kesin monoton artan olmali, ozdes up_to yasak)."""
    prev_up_to: Optional[float] = None
    for i, tier in enumerate(tiers[:-1]):
        if tier.up_to is None:
            raise ValueError(
                f"Kural {rule_id!r}: sadece son kademenin up_to=null olmasi gerekir "
                f"(kademe {i} up_to=null ama son kademe degil)"
            )
        if prev_up_to is not None:
            if tier.up_to <= prev_up_to:
                raise ValueError(
                    f"Kural {rule_id!r}: kademeler kesin artan up_to siralamasinda olmali; "
                    f"kademe {i} up_to={tier.up_to} <= onceki up_to={prev_up_to}"
                )
        prev_up_to = tier.up_to
