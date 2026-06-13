"""Deterministik fiyatlama hesap motoru (PLAN_DEMO1.md 7.2).

Kullanim ornegi
---------------
    from src.pricing.schema import RuleSet
    from src.pricing.engine import PricingEngine

    rule_set = RuleSet.from_json(json_str)
    engine = PricingEngine(rule_set)
    result = engine.calculate(inputs)

    print(result.total_price)
    for line in result.breakdown:
        print(line)

Girdi
-----
inputs: dict[str, float] — alan adi -> deger (orn. {"hacim_m3": 12.5, ...})

Cikti (PricingResult)
---------------------
total_price : float — nihai fiyat
breakdown   : list[BreakdownLine] — hangi kural, hangi girdi, ara deger, katkisi

Deterministik garanti
---------------------
Ayni rule_set + ayni inputs => her zaman ayni total_price.
Motor dahili durum tutmaz; her calculate() bagimsiz calisir.
"""

from __future__ import annotations

import operator as _op
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.pricing.schema import PricingRule, RuleSet, TierEntry

# ---------------------------------------------------------------------------
# Veri yapilari
# ---------------------------------------------------------------------------


@dataclass
class BreakdownLine:
    """Tek bir kural uygulamasini aciklar."""

    rule_id: str
    rule_type: str
    rule_description: str
    input_field: Optional[str]
    input_value: Optional[float]
    intermediate_value: float
    subtotal_after: float
    note: str = ""

    def __str__(self) -> str:
        field_part = (
            f"{self.input_field}={self.input_value}" if self.input_field else "-"
        )
        return (
            f"[{self.rule_id}] {self.rule_type} | {field_part} | "
            f"ara_deger={self.intermediate_value:.4f} | "
            f"toplam_sonra={self.subtotal_after:.4f}"
            + (f" | {self.note}" if self.note else "")
        )


@dataclass
class PricingResult:
    """Hesap motoru ciktisi: nihai fiyat + tam dokum."""

    total_price: float
    breakdown: List[BreakdownLine] = field(default_factory=list)
    inputs: Dict[str, float] = field(default_factory=dict)
    rule_set_version: str = ""
    rule_set_name: str = ""


# ---------------------------------------------------------------------------
# Karsilastirma operatorleri (conditional_multiplier icin)
# ---------------------------------------------------------------------------

_OPS: Dict[str, Any] = {
    "<": _op.lt,
    "<=": _op.le,
    ">": _op.gt,
    ">=": _op.ge,
    "==": _op.eq,
    "!=": _op.ne,
}

# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------


class PricingEngine:
    """Kural setini alip deterministik fiyat hesabi yapar."""

    def __init__(self, rule_set: RuleSet) -> None:
        rule_set.validate()
        self._rule_set = rule_set

    # ------------------------------------------------------------------
    # Ana hesap
    # ------------------------------------------------------------------

    def calculate(self, inputs: Dict[str, float]) -> PricingResult:
        """inputs dict'inden fiyat dokumu uretir.

        Kurallar listede yazildigi sirada uygulanir; siranin onemi vardir
        (clamp'ler genellikle sona konur).
        """
        subtotal = 0.0
        breakdown: List[BreakdownLine] = []

        for rule in self._rule_set.rules:
            subtotal, line = self._apply_rule(rule, inputs, subtotal)
            breakdown.append(line)

        return PricingResult(
            total_price=round(subtotal, 2),
            breakdown=breakdown,
            inputs=dict(inputs),
            rule_set_version=self._rule_set.version,
            rule_set_name=self._rule_set.name,
        )

    # ------------------------------------------------------------------
    # Kural uygulayicilar
    # ------------------------------------------------------------------

    def _apply_rule(
        self,
        rule: PricingRule,
        inputs: Dict[str, float],
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        if rule.type == "unit_price":
            return self._apply_unit_price(rule, inputs, subtotal)
        if rule.type == "tier_table":
            return self._apply_tier_table(rule, inputs, subtotal)
        if rule.type == "conditional_multiplier":
            return self._apply_conditional_multiplier(rule, inputs, subtotal)
        if rule.type == "min_clamp":
            return self._apply_min_clamp(rule, subtotal)
        if rule.type == "max_clamp":
            return self._apply_max_clamp(rule, subtotal)
        raise ValueError(f"Bilinmeyen kural tipi: {rule.type!r}")

    def _apply_unit_price(
        self,
        rule: PricingRule,
        inputs: Dict[str, float],
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        input_val = _get_input(rule, inputs)
        contribution = input_val * rule.unit_price
        new_subtotal = subtotal + contribution
        line = BreakdownLine(
            rule_id=rule.id,
            rule_type=rule.type,
            rule_description=rule.description,
            input_field=rule.input_field,
            input_value=input_val,
            intermediate_value=contribution,
            subtotal_after=new_subtotal,
            note=f"{input_val} * {rule.unit_price} = {contribution:.4f}",
        )
        return new_subtotal, line

    def _apply_tier_table(
        self,
        rule: PricingRule,
        inputs: Dict[str, float],
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        input_val = _get_input(rule, inputs)
        tier_price = _lookup_tier(rule.tiers, input_val)
        new_subtotal = subtotal + tier_price
        line = BreakdownLine(
            rule_id=rule.id,
            rule_type=rule.type,
            rule_description=rule.description,
            input_field=rule.input_field,
            input_value=input_val,
            intermediate_value=tier_price,
            subtotal_after=new_subtotal,
            note=f"kademe_fiyati={tier_price}",
        )
        return new_subtotal, line

    def _apply_conditional_multiplier(
        self,
        rule: PricingRule,
        inputs: Dict[str, float],
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        if rule.condition_field not in inputs:
            raise KeyError(
                f"Kural {rule.id!r}: '{rule.condition_field}' alani inputs'ta bulunamadi. "
                f"Mevcut alanlar: {list(inputs.keys())}"
            )
        cond_val = float(inputs[rule.condition_field])
        compare_fn = _OPS[rule.operator]
        condition_met = compare_fn(cond_val, rule.threshold)
        if condition_met:
            new_subtotal = subtotal * rule.multiplier
            intermediate = subtotal * (rule.multiplier - 1.0)
            note = (
                f"{rule.condition_field}={cond_val} {rule.operator} "
                f"{rule.threshold} => carpan {rule.multiplier} uygulandı"
            )
        else:
            new_subtotal = subtotal
            intermediate = 0.0
            note = (
                f"{rule.condition_field}={cond_val} {rule.operator} "
                f"{rule.threshold} => sart saglanmadi, carpan uygulanmadi"
            )
        line = BreakdownLine(
            rule_id=rule.id,
            rule_type=rule.type,
            rule_description=rule.description,
            input_field=rule.condition_field,
            input_value=cond_val,
            intermediate_value=intermediate,
            subtotal_after=new_subtotal,
            note=note,
        )
        return new_subtotal, line

    def _apply_min_clamp(
        self,
        rule: PricingRule,
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        original = subtotal
        new_subtotal = max(subtotal, rule.min_price)
        delta = new_subtotal - original
        line = BreakdownLine(
            rule_id=rule.id,
            rule_type=rule.type,
            rule_description=rule.description,
            input_field=None,
            input_value=None,
            intermediate_value=delta,
            subtotal_after=new_subtotal,
            note=(
                f"min_price={rule.min_price}: "
                + ("tabanlandi" if delta > 0 else "etkilenmedi")
            ),
        )
        return new_subtotal, line

    def _apply_max_clamp(
        self,
        rule: PricingRule,
        subtotal: float,
    ) -> tuple[float, BreakdownLine]:
        original = subtotal
        new_subtotal = min(subtotal, rule.max_price)
        delta = new_subtotal - original
        line = BreakdownLine(
            rule_id=rule.id,
            rule_type=rule.type,
            rule_description=rule.description,
            input_field=None,
            input_value=None,
            intermediate_value=delta,
            subtotal_after=new_subtotal,
            note=(
                f"max_price={rule.max_price}: "
                + ("tavanlandi" if delta < 0 else "etkilenmedi")
            ),
        )
        return new_subtotal, line


# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------


def _get_input(rule: PricingRule, inputs: Dict[str, float]) -> float:
    if rule.input_field not in inputs:
        raise KeyError(
            f"Kural {rule.id!r}: '{rule.input_field}' alani inputs'ta bulunamadi. "
            f"Mevcut alanlar: {list(inputs.keys())}"
        )
    return float(inputs[rule.input_field])


def _lookup_tier(tiers: List[TierEntry], value: float) -> float:
    """Deger icin kademe tablosundan fiyat bulur."""
    for tier in tiers:
        if tier.up_to is None or value <= tier.up_to:
            return tier.price
    # Deger son kademeden buyukse son kademenin fiyatini dondur
    return tiers[-1].price
