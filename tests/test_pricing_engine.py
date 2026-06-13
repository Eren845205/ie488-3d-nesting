"""TDD testleri — src/pricing/engine.py (PLAN_DEMO1.md 7.2).

Kapsam: deterministik hesap, tam dokum, her kural tipi, hata durumlari.
"""

import pytest

from src.pricing.schema import PricingRule, RuleSet, TierEntry
from src.pricing.engine import BreakdownLine, PricingEngine, PricingResult


# ---------------------------------------------------------------------------
# Fikstür yardimcilari
# ---------------------------------------------------------------------------


def _make_engine(*rules: PricingRule, version: str = "1.0", name: str = "test") -> PricingEngine:
    rs = RuleSet(version=version, name=name, rules=list(rules))
    return PricingEngine(rs)


def _unit_price_rule(
    rule_id: str = "r1",
    field: str = "hacim_m3",
    price: float = 500.0,
) -> PricingRule:
    return PricingRule(id=rule_id, type="unit_price", input_field=field, unit_price=price)


def _tier_rule(
    rule_id: str = "rt",
    field: str = "mesafe_km",
    tiers=None,
) -> PricingRule:
    if tiers is None:
        tiers = [
            TierEntry(price=200.0, up_to=100.0),
            TierEntry(price=400.0, up_to=500.0),
            TierEntry(price=700.0, up_to=None),
        ]
    return PricingRule(id=rule_id, type="tier_table", input_field=field, tiers=tiers)


# ---------------------------------------------------------------------------
# Temel hesap — unit_price
# ---------------------------------------------------------------------------


def test_unit_price_basic_calculation():
    engine = _make_engine(_unit_price_rule(price=500.0))
    result = engine.calculate({"hacim_m3": 10.0})
    assert result.total_price == pytest.approx(5000.0)


def test_unit_price_zero_input():
    engine = _make_engine(_unit_price_rule(price=500.0))
    result = engine.calculate({"hacim_m3": 0.0})
    assert result.total_price == pytest.approx(0.0)


def test_unit_price_fractional():
    engine = _make_engine(_unit_price_rule(price=100.0))
    result = engine.calculate({"hacim_m3": 3.5})
    assert result.total_price == pytest.approx(350.0)


# ---------------------------------------------------------------------------
# Deterministik garanti
# ---------------------------------------------------------------------------


def test_same_inputs_same_price_unit_price():
    engine = _make_engine(_unit_price_rule())
    r1 = engine.calculate({"hacim_m3": 7.0})
    r2 = engine.calculate({"hacim_m3": 7.0})
    assert r1.total_price == r2.total_price


def test_same_inputs_same_price_complex_rule_set():
    rs = RuleSet(
        version="1.0",
        name="complex",
        rules=[
            _unit_price_rule("r1", "hacim_m3", 500.0),
            _tier_rule("r2"),
            PricingRule(
                id="r3",
                type="conditional_multiplier",
                condition_field="mesafe_km",
                operator=">",
                threshold=1000.0,
                multiplier=1.2,
            ),
            PricingRule(id="r4", type="min_clamp", min_price=300.0),
        ],
    )
    engine = PricingEngine(rs)
    inputs = {"hacim_m3": 5.0, "mesafe_km": 250.0}
    prices = [engine.calculate(inputs).total_price for _ in range(5)]
    assert len(set(prices)) == 1  # hepsi esit


# ---------------------------------------------------------------------------
# Tier table
# ---------------------------------------------------------------------------


def test_tier_table_first_tier():
    engine = _make_engine(_tier_rule())
    result = engine.calculate({"mesafe_km": 50.0})
    assert result.total_price == pytest.approx(200.0)


def test_tier_table_boundary_first_tier():
    engine = _make_engine(_tier_rule())
    result = engine.calculate({"mesafe_km": 100.0})
    assert result.total_price == pytest.approx(200.0)


def test_tier_table_second_tier():
    engine = _make_engine(_tier_rule())
    result = engine.calculate({"mesafe_km": 300.0})
    assert result.total_price == pytest.approx(400.0)


def test_tier_table_last_unlimited_tier():
    engine = _make_engine(_tier_rule())
    result = engine.calculate({"mesafe_km": 9999.0})
    assert result.total_price == pytest.approx(700.0)


# ---------------------------------------------------------------------------
# Conditional multiplier
# ---------------------------------------------------------------------------


def test_conditional_multiplier_condition_met():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 1000.0),
        PricingRule(
            id="r2",
            type="conditional_multiplier",
            condition_field="mesafe_km",
            operator=">",
            threshold=500.0,
            multiplier=1.5,
        ),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 10.0, "mesafe_km": 600.0})
    # 10 * 1000 = 10000; * 1.5 = 15000
    assert result.total_price == pytest.approx(15000.0)


def test_conditional_multiplier_condition_not_met():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 1000.0),
        PricingRule(
            id="r2",
            type="conditional_multiplier",
            condition_field="mesafe_km",
            operator=">",
            threshold=500.0,
            multiplier=1.5,
        ),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 10.0, "mesafe_km": 100.0})
    # Sart saglanmadi; carpan uygulanmaz => 10000
    assert result.total_price == pytest.approx(10000.0)


def test_conditional_multiplier_equal_operator():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 100.0),
        PricingRule(
            id="r2",
            type="conditional_multiplier",
            condition_field="konteyner_sayisi",
            operator="==",
            threshold=3.0,
            multiplier=2.0,
        ),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 5.0, "konteyner_sayisi": 3.0})
    assert result.total_price == pytest.approx(1000.0)  # 500 * 2


def test_conditional_multiplier_missing_condition_field_raises():
    """Kosul alani inputs'ta yoksa KeyError firlatiyor olmali — sessiz 0.0 degil."""
    rules = [
        _unit_price_rule("r1", "hacim_m3", 100.0),
        PricingRule(
            id="r2",
            type="conditional_multiplier",
            condition_field="mesafe_km",
            operator=">",
            threshold=0.0,
            multiplier=2.0,
        ),
    ]
    engine = _make_engine(*rules)
    # mesafe_km eksik => KeyError firlatiyor olmali
    with pytest.raises(KeyError, match="mesafe_km"):
        engine.calculate({"hacim_m3": 5.0})


# ---------------------------------------------------------------------------
# Min/max clamp
# ---------------------------------------------------------------------------


def test_min_clamp_raises_below_min():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 10.0),
        PricingRule(id="r2", type="min_clamp", min_price=1000.0),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 5.0})
    # 5 * 10 = 50 < 1000 => 1000
    assert result.total_price == pytest.approx(1000.0)


def test_min_clamp_no_effect_above_min():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 500.0),
        PricingRule(id="r2", type="min_clamp", min_price=100.0),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 5.0})
    assert result.total_price == pytest.approx(2500.0)


def test_max_clamp_caps_above_max():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 10000.0),
        PricingRule(id="r2", type="max_clamp", max_price=5000.0),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 10.0})
    # 100000 > 5000 => 5000
    assert result.total_price == pytest.approx(5000.0)


def test_max_clamp_no_effect_below_max():
    rules = [
        _unit_price_rule("r1", "hacim_m3", 100.0),
        PricingRule(id="r2", type="max_clamp", max_price=50000.0),
    ]
    engine = _make_engine(*rules)
    result = engine.calculate({"hacim_m3": 5.0})
    assert result.total_price == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# Dokum (breakdown) — izlenebilirlik
# ---------------------------------------------------------------------------


def test_breakdown_has_one_line_per_rule():
    engine = _make_engine(
        _unit_price_rule("r1"),
        PricingRule(id="r2", type="min_clamp", min_price=1.0),
    )
    result = engine.calculate({"hacim_m3": 5.0})
    assert len(result.breakdown) == 2


def test_breakdown_line_contains_rule_id():
    engine = _make_engine(_unit_price_rule("my_rule"))
    result = engine.calculate({"hacim_m3": 3.0})
    assert result.breakdown[0].rule_id == "my_rule"


def test_breakdown_line_subtotal_matches_final():
    engine = _make_engine(_unit_price_rule("r1", price=200.0))
    result = engine.calculate({"hacim_m3": 4.0})
    assert result.breakdown[-1].subtotal_after == pytest.approx(result.total_price)


def test_breakdown_str_is_informative():
    engine = _make_engine(_unit_price_rule("r1", price=100.0))
    result = engine.calculate({"hacim_m3": 3.0})
    line_str = str(result.breakdown[0])
    assert "r1" in line_str
    assert "unit_price" in line_str
    assert "hacim_m3" in line_str


def test_breakdown_input_field_and_value_stored():
    engine = _make_engine(_unit_price_rule("r1", "agirlik_kg", 50.0))
    result = engine.calculate({"agirlik_kg": 20.0})
    line = result.breakdown[0]
    assert line.input_field == "agirlik_kg"
    assert line.input_value == pytest.approx(20.0)


def test_breakdown_intermediate_value_correct_unit_price():
    engine = _make_engine(_unit_price_rule("r1", "hacim_m3", 300.0))
    result = engine.calculate({"hacim_m3": 7.0})
    # intermediate_value = girdi * birim_fiyat = 7 * 300 = 2100
    assert result.breakdown[0].intermediate_value == pytest.approx(2100.0)


# ---------------------------------------------------------------------------
# Coklu kural kombinasyonu — ornegi
# ---------------------------------------------------------------------------


def test_combined_rule_set_example():
    """Ornek: hacim birim fiyat + mesafe kademe + uzak zammi + min kelepce."""
    rs = RuleSet(
        version="1.0",
        name="ornek",
        rules=[
            _unit_price_rule("r1", "hacim_m3", 500.0),
            _tier_rule("r2", "mesafe_km"),
            PricingRule(
                id="r3",
                type="conditional_multiplier",
                condition_field="mesafe_km",
                operator=">",
                threshold=1000.0,
                multiplier=1.2,
            ),
            PricingRule(id="r4", type="min_clamp", min_price=300.0),
            PricingRule(id="r5", type="max_clamp", max_price=50000.0),
        ],
    )
    engine = PricingEngine(rs)
    inputs = {"hacim_m3": 5.0, "mesafe_km": 250.0}
    result = engine.calculate(inputs)

    # Beklenen: 5*500=2500 + 400(kademe 250km) = 2900; mesafe 250 < 1000 => carpan yok
    # min=300 => 2900>300 => etkilenmez; max=50000 => 2900<50000 => etkilenmez
    assert result.total_price == pytest.approx(2900.0)
    assert len(result.breakdown) == 5
    assert result.rule_set_version == "1.0"
    assert result.rule_set_name == "ornek"


def test_combined_with_distant_multiplier():
    """Uzak sevkiyat zammi tetiklenir."""
    rs = RuleSet(
        version="1.0",
        name="ornek2",
        rules=[
            _unit_price_rule("r1", "hacim_m3", 500.0),
            PricingRule(
                id="r2",
                type="conditional_multiplier",
                condition_field="mesafe_km",
                operator=">",
                threshold=1000.0,
                multiplier=1.2,
            ),
        ],
    )
    engine = PricingEngine(rs)
    inputs = {"hacim_m3": 10.0, "mesafe_km": 1500.0}
    result = engine.calculate(inputs)
    # 10*500=5000; *1.2=6000
    assert result.total_price == pytest.approx(6000.0)


# ---------------------------------------------------------------------------
# Hata durumlari
# ---------------------------------------------------------------------------


def test_missing_input_field_raises_key_error():
    engine = _make_engine(_unit_price_rule("r1", "hacim_m3", 100.0))
    with pytest.raises(KeyError, match="hacim_m3"):
        engine.calculate({})


def test_result_stores_original_inputs():
    engine = _make_engine(_unit_price_rule())
    inputs = {"hacim_m3": 5.0}
    result = engine.calculate(inputs)
    assert result.inputs == inputs


def test_result_inputs_is_copy():
    """Motor, inputs dict'ini mutate etmemeli."""
    engine = _make_engine(_unit_price_rule())
    inputs = {"hacim_m3": 5.0}
    result = engine.calculate(inputs)
    result.inputs["hacim_m3"] = 999.0
    # Orijinal etkilenmemeli
    assert inputs["hacim_m3"] == 5.0


# ---------------------------------------------------------------------------
# FINDING-03: total_price round(..., 2) — float birikim testi
# ---------------------------------------------------------------------------


def test_total_price_rounded_to_two_decimals():
    """total_price her zaman en fazla 2 ondalik basamak tasimali."""
    # 1/3 carpan => sonsuz ondalik; round(2) uygulanmali
    engine = _make_engine(
        PricingRule(
            id="r1",
            type="unit_price",
            input_field="hacim_m3",
            unit_price=1.0 / 3.0,  # 0.333...
        )
    )
    result = engine.calculate({"hacim_m3": 1.0})
    # float str gösteriminde ondalik sayisi 2'yi asmamali
    decimal_part = str(result.total_price).split(".")[-1]
    assert len(decimal_part) <= 2, (
        f"total_price {result.total_price!r} 2'den fazla ondalik basamak tasiyor"
    )


def test_total_price_float_accumulation_stays_exact():
    """Kayan nokta birikiminin round(2) ile giderildigini dogrular."""
    # 0.1 + 0.1 + 0.1 = 0.30000000000000004 Python'da; round(2) => 0.3
    engine = _make_engine(
        PricingRule(
            id="r1",
            type="unit_price",
            input_field="adet",
            unit_price=0.1,
        )
    )
    result = engine.calculate({"adet": 3.0})
    # round(2) uygulanmissa 0.3 olur, ham float birikim degil
    assert result.total_price == pytest.approx(0.3)
    assert result.total_price == round(result.total_price, 2)
