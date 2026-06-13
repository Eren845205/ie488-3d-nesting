"""TDD testleri — src/pricing/schema.py (PLAN_DEMO1.md 7.1).

Kapsam: JSON round-trip, dogrulama, kural tipleri, hata durumlari.
"""

import json
import pytest

from src.pricing.schema import (
    PricingRule,
    RuleSet,
    TierEntry,
    RULE_TYPES,
    STANDARD_INPUT_FIELDS,
)


# ---------------------------------------------------------------------------
# Fikstür: ornek kural seti
# ---------------------------------------------------------------------------

SAMPLE_RULE_SET_DICT = {
    "version": "1.0",
    "name": "Test Kural Seti",
    "rules": [
        {
            "id": "r_hacim",
            "type": "unit_price",
            "input_field": "hacim_m3",
            "unit_price": 500.0,
            "description": "Hacim bazi birim fiyat",
        },
        {
            "id": "r_mesafe",
            "type": "tier_table",
            "input_field": "mesafe_km",
            "description": "Mesafe kademeleri",
            "tiers": [
                {"up_to": 100.0, "price": 200.0},
                {"up_to": 500.0, "price": 400.0},
                {"up_to": None, "price": 700.0},
            ],
        },
        {
            "id": "r_uzak",
            "type": "conditional_multiplier",
            "condition_field": "mesafe_km",
            "operator": ">",
            "threshold": 1000.0,
            "multiplier": 1.2,
            "description": "1000 km ustu uzak sevkiyat zammi",
        },
        {
            "id": "r_min",
            "type": "min_clamp",
            "min_price": 300.0,
            "description": "Minimum teklif tabanis",
        },
        {
            "id": "r_max",
            "type": "max_clamp",
            "max_price": 50000.0,
            "description": "Maksimum teklif tavani",
        },
    ],
}


@pytest.fixture()
def sample_rule_set() -> RuleSet:
    return RuleSet.from_dict(SAMPLE_RULE_SET_DICT)


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------


def test_rule_types_set_contains_expected():
    expected = {"unit_price", "tier_table", "conditional_multiplier", "min_clamp", "max_clamp"}
    assert expected == RULE_TYPES


def test_standard_input_fields_contains_core_fields():
    for field in ("hacim_m3", "agirlik_kg", "konteyner_sayisi", "doluluk_oran", "mesafe_km"):
        assert field in STANDARD_INPUT_FIELDS


# ---------------------------------------------------------------------------
# TierEntry round-trip
# ---------------------------------------------------------------------------


def test_tier_entry_round_trip():
    tier = TierEntry(price=200.0, up_to=100.0)
    d = tier.to_dict()
    assert d == {"up_to": 100.0, "price": 200.0}
    tier2 = TierEntry.from_dict(d)
    assert tier2.price == tier.price
    assert tier2.up_to == tier.up_to


def test_tier_entry_unlimited_up_to():
    tier = TierEntry(price=700.0, up_to=None)
    d = tier.to_dict()
    assert d["up_to"] is None
    tier2 = TierEntry.from_dict(d)
    assert tier2.up_to is None


# ---------------------------------------------------------------------------
# PricingRule round-trip
# ---------------------------------------------------------------------------


def test_unit_price_rule_round_trip():
    rule = PricingRule(
        id="r1",
        type="unit_price",
        input_field="hacim_m3",
        unit_price=500.0,
        description="test",
    )
    d = rule.to_dict()
    rule2 = PricingRule.from_dict(d)
    assert rule2.id == "r1"
    assert rule2.type == "unit_price"
    assert rule2.input_field == "hacim_m3"
    assert rule2.unit_price == 500.0


def test_tier_table_rule_round_trip():
    rule = PricingRule(
        id="r2",
        type="tier_table",
        input_field="mesafe_km",
        tiers=[
            TierEntry(price=200.0, up_to=100.0),
            TierEntry(price=700.0, up_to=None),
        ],
    )
    d = rule.to_dict()
    rule2 = PricingRule.from_dict(d)
    assert rule2.type == "tier_table"
    assert len(rule2.tiers) == 2
    assert rule2.tiers[0].price == 200.0
    assert rule2.tiers[1].up_to is None


def test_conditional_multiplier_rule_round_trip():
    rule = PricingRule(
        id="r3",
        type="conditional_multiplier",
        condition_field="mesafe_km",
        operator=">",
        threshold=1000.0,
        multiplier=1.2,
    )
    d = rule.to_dict()
    rule2 = PricingRule.from_dict(d)
    assert rule2.multiplier == 1.2
    assert rule2.operator == ">"
    assert rule2.threshold == 1000.0


def test_min_clamp_rule_round_trip():
    rule = PricingRule(id="r4", type="min_clamp", min_price=300.0)
    d = rule.to_dict()
    rule2 = PricingRule.from_dict(d)
    assert rule2.min_price == 300.0


def test_max_clamp_rule_round_trip():
    rule = PricingRule(id="r5", type="max_clamp", max_price=50000.0)
    d = rule.to_dict()
    rule2 = PricingRule.from_dict(d)
    assert rule2.max_price == 50000.0


# ---------------------------------------------------------------------------
# RuleSet round-trip
# ---------------------------------------------------------------------------


def test_rule_set_from_dict_round_trip(sample_rule_set):
    d = sample_rule_set.to_dict()
    rs2 = RuleSet.from_dict(d)
    assert rs2.version == sample_rule_set.version
    assert rs2.name == sample_rule_set.name
    assert len(rs2.rules) == len(sample_rule_set.rules)


def test_rule_set_json_round_trip(sample_rule_set):
    json_str = sample_rule_set.to_json()
    # Gecerli JSON oldugunu dogrula
    parsed = json.loads(json_str)
    assert parsed["version"] == "1.0"
    # Tekrar parse et
    rs2 = RuleSet.from_json(json_str)
    assert rs2.name == sample_rule_set.name
    assert len(rs2.rules) == len(sample_rule_set.rules)


def test_rule_set_preserves_all_rule_types(sample_rule_set):
    types = {r.type for r in sample_rule_set.rules}
    assert types == RULE_TYPES


# ---------------------------------------------------------------------------
# Dogrulama — gecerli kural setleri
# ---------------------------------------------------------------------------


def test_validate_passes_for_valid_rule_set(sample_rule_set):
    sample_rule_set.validate()  # hata firlatmamali


def test_validate_passes_for_minimal_unit_price():
    rs = RuleSet(
        version="1.0",
        name="minimal",
        rules=[PricingRule(id="r1", type="unit_price", input_field="hacim_m3", unit_price=100.0)],
    )
    rs.validate()


# ---------------------------------------------------------------------------
# Dogrulama — hata durumlari
# ---------------------------------------------------------------------------


def test_validate_rejects_empty_version():
    rs = RuleSet(version="", name="test", rules=[])
    with pytest.raises(ValueError, match="version"):
        rs.validate()


def test_validate_rejects_empty_name():
    rs = RuleSet(version="1.0", name="", rules=[])
    with pytest.raises(ValueError, match="name"):
        rs.validate()


def test_validate_rejects_unknown_rule_type():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="gelecek_tip", input_field="hacim_m3")],
    )
    with pytest.raises(ValueError, match="Gecersiz kural tipi"):
        rs.validate()


def test_validate_rejects_duplicate_rule_ids():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[
            PricingRule(id="r1", type="unit_price", input_field="hacim_m3", unit_price=100.0),
            PricingRule(id="r1", type="min_clamp", min_price=50.0),
        ],
    )
    with pytest.raises(ValueError, match="Tekrar kural id"):
        rs.validate()


def test_validate_rejects_unit_price_missing_field():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="unit_price", unit_price=100.0)],  # input_field yok
    )
    with pytest.raises(ValueError, match="input_field"):
        rs.validate()


def test_validate_rejects_negative_unit_price():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="unit_price", input_field="hacim_m3", unit_price=-1.0)],
    )
    with pytest.raises(ValueError, match="negatif"):
        rs.validate()


def test_validate_rejects_empty_tiers():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="tier_table", input_field="mesafe_km", tiers=[])],
    )
    with pytest.raises(ValueError, match="bos tiers"):
        rs.validate()


def test_validate_rejects_invalid_operator():
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[
            PricingRule(
                id="r1",
                type="conditional_multiplier",
                condition_field="mesafe_km",
                operator="??",
                threshold=100.0,
                multiplier=1.5,
            )
        ],
    )
    with pytest.raises(ValueError, match="operator"):
        rs.validate()


def test_validate_rejects_non_final_tier_with_null_up_to():
    """Sadece son kademedeki up_to None olabilir."""
    tiers = [
        TierEntry(price=200.0, up_to=None),   # ara kademe, yanlis
        TierEntry(price=700.0, up_to=None),
    ]
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="tier_table", input_field="mesafe_km", tiers=tiers)],
    )
    with pytest.raises(ValueError, match="up_to=null"):
        rs.validate()


def test_validate_rejects_reversed_tier_order():
    """Tersine siralanmis kademeler (500, 100, null) reddedilmeli."""
    tiers = [
        TierEntry(price=400.0, up_to=500.0),
        TierEntry(price=200.0, up_to=100.0),   # 100 < 500: azalan sira
        TierEntry(price=700.0, up_to=None),
    ]
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="tier_table", input_field="mesafe_km", tiers=tiers)],
    )
    with pytest.raises(ValueError, match="kesin artan"):
        rs.validate()


def test_validate_rejects_duplicate_up_to_values():
    """Ozdes up_to degerli iki kademe reddedilmeli."""
    tiers = [
        TierEntry(price=200.0, up_to=100.0),
        TierEntry(price=350.0, up_to=100.0),   # ayni up_to
        TierEntry(price=700.0, up_to=None),
    ]
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="tier_table", input_field="mesafe_km", tiers=tiers)],
    )
    with pytest.raises(ValueError, match="kesin artan"):
        rs.validate()


def test_validate_accepts_strictly_ascending_tiers():
    """Gecerli artan sirali kademe seti hata firlatmamali."""
    tiers = [
        TierEntry(price=200.0, up_to=100.0),
        TierEntry(price=400.0, up_to=500.0),
        TierEntry(price=700.0, up_to=None),
    ]
    rs = RuleSet(
        version="1.0",
        name="test",
        rules=[PricingRule(id="r1", type="tier_table", input_field="mesafe_km", tiers=tiers)],
    )
    rs.validate()  # ValueError firlatmamali
