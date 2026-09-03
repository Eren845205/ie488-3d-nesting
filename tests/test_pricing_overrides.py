"""TDD testleri — src/pricing/overrides.py (PLAN_DEMO1.md 7.3).

Kapsam: iki seviyeli override, iz kaydi, orijinal hesap korunmasi.
"""

import pytest

from src.pricing.schema import PricingRule, RuleSet
from src.pricing.engine import PricingEngine
from src.pricing.overrides import (
    OverriddenQuote,
    OverrideLog,
    QuoteOverrideRecord,
    RuleOverrideRecord,
    apply_quote_override,
    override_rule_param,
)
from src.pricing.versioning import read_all_records


# ---------------------------------------------------------------------------
# Fikstür
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_rule_set() -> RuleSet:
    return RuleSet(
        version="1.0",
        name="base",
        rules=[
            PricingRule(
                id="r_hacim",
                type="unit_price",
                input_field="hacim_m3",
                unit_price=500.0,
                description="Hacim birim fiyat",
            ),
            PricingRule(id="r_min", type="min_clamp", min_price=300.0),
        ],
    )


# ---------------------------------------------------------------------------
# Seviye (a): Kural duzeyi override
# ---------------------------------------------------------------------------


def test_rule_override_creates_new_version(base_rule_set):
    new_rs, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="Yakit zammi",
        new_version="1.1",
    )
    assert new_rs.version == "1.1"
    assert base_rule_set.version == "1.0"  # orijinal degismez


def test_rule_override_does_not_mutate_original(base_rule_set):
    original_price = base_rule_set.rules[0].unit_price
    override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=999.0,
        reason="test",
        new_version="2.0",
    )
    assert base_rule_set.rules[0].unit_price == original_price  # original degismedi


def test_rule_override_new_price_applies(base_rule_set):
    new_rs, _ = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="Yakit zammi",
        new_version="1.1",
    )
    engine = PricingEngine(new_rs)
    result = engine.calculate({"hacim_m3": 10.0})
    assert result.total_price == pytest.approx(6000.0)


def test_rule_override_old_engine_unchanged(base_rule_set):
    engine_old = PricingEngine(base_rule_set)
    override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    result_old = engine_old.calculate({"hacim_m3": 10.0})
    assert result_old.total_price == pytest.approx(5000.0)  # eski fiyat


def test_rule_override_record_stores_before_after(base_rule_set):
    _, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=750.0,
        reason="Yil sonu revizyon",
        new_version="1.2",
    )
    assert record.changed_params["unit_price"]["before"] == 500.0
    assert record.changed_params["unit_price"]["after"] == 750.0
    assert record.reason == "Yil sonu revizyon"
    assert record.original_rule_set_version == "1.0"
    assert record.new_rule_set_version == "1.2"


def test_rule_override_record_has_timestamp(base_rule_set):
    _, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    assert record.timestamp  # bos olmamali


def test_rule_override_record_to_dict(base_rule_set):
    _, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    d = record.to_dict()
    assert d["rule_id"] == "r_hacim"
    assert d["reason"] == "test"
    assert "timestamp" in d


def test_rule_override_raises_if_rule_not_found(base_rule_set):
    with pytest.raises(KeyError, match="olmayan_kural"):
        override_rule_param(
            base_rule_set,
            rule_id="olmayan_kural",
            param="unit_price",
            new_value=100.0,
            reason="test",
            new_version="2.0",
        )


def test_rule_override_validates_new_rule_set(base_rule_set):
    """Gecersiz deger => yeni kural seti validate'i gecer degil."""
    with pytest.raises(ValueError):
        override_rule_param(
            base_rule_set,
            rule_id="r_hacim",
            param="unit_price",
            new_value=-999.0,  # negatif birim fiyat gecersiz
            reason="hata testi",
            new_version="1.1",
        )


# ---------------------------------------------------------------------------
# FINDING-06: new_version == rule_set.version => ValueError
# ---------------------------------------------------------------------------


def test_rule_override_raises_if_same_version(base_rule_set):
    """new_version mevcut versiyonla ayni ise ValueError firlatiyor olmali."""
    with pytest.raises(ValueError, match="1.0"):
        override_rule_param(
            base_rule_set,
            rule_id="r_hacim",
            param="unit_price",
            new_value=600.0,
            reason="test",
            new_version="1.0",  # mevcut versiyonla ayni => hata
        )


def test_rule_override_different_version_succeeds(base_rule_set):
    """Farkli new_version gecerliyse hata firlatiyor olmamali."""
    new_rs, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    assert new_rs.version == "1.1"
    assert record.new_rule_set_version == "1.1"


# ---------------------------------------------------------------------------
# Seviye (b): Teklif duzeyi override
# ---------------------------------------------------------------------------


def test_quote_override_sets_final_price():
    quote = apply_quote_override(
        quote_id="Q-001",
        original_price=5000.0,
        overridden_price=4500.0,
        reason="Musteri indirimi",
        operator="ek_kullanici",
    )
    assert quote.final_price == pytest.approx(4500.0)


def test_quote_override_preserves_original_price():
    quote = apply_quote_override(
        quote_id="Q-001",
        original_price=5000.0,
        overridden_price=4500.0,
        reason="test",
        operator="op1",
    )
    assert quote.original_price == pytest.approx(5000.0)


def test_quote_override_was_overridden_flag():
    quote = apply_quote_override(
        quote_id="Q-002",
        original_price=1000.0,
        overridden_price=900.0,
        reason="test",
        operator="op1",
    )
    assert quote.was_overridden is True


def test_quote_override_record_stores_reason_and_operator():
    quote = apply_quote_override(
        quote_id="Q-003",
        original_price=2000.0,
        overridden_price=1800.0,
        reason="Urun hasari tazminati",
        operator="muhasebe_muduru",
    )
    record = quote.override_record
    assert record.reason == "Urun hasari tazminati"
    assert record.operator == "muhasebe_muduru"
    assert record.quote_id == "Q-003"


def test_quote_override_stores_breakdown_summary():
    breakdown = ["[r1] unit_price | hacim_m3=5.0 | ara_deger=2500.0 | toplam_sonra=2500.0"]
    quote = apply_quote_override(
        quote_id="Q-004",
        original_price=2500.0,
        overridden_price=2000.0,
        reason="test",
        operator="op1",
        breakdown_lines=breakdown,
    )
    assert "unit_price" in quote.override_record.original_breakdown_summary
    assert quote.breakdown_lines == breakdown


def test_quote_override_record_to_dict():
    quote = apply_quote_override(
        quote_id="Q-005",
        original_price=3000.0,
        overridden_price=2700.0,
        reason="test",
        operator="op1",
    )
    d = quote.override_record.to_dict()
    assert d["quote_id"] == "Q-005"
    assert d["original_price"] == 3000.0
    assert d["overridden_price"] == 2700.0
    assert "timestamp" in d


def test_quote_override_record_has_timestamp():
    quote = apply_quote_override(
        quote_id="Q-006",
        original_price=1000.0,
        overridden_price=900.0,
        reason="test",
        operator="op1",
    )
    assert quote.override_record.timestamp


# ---------------------------------------------------------------------------
# OverrideLog
# ---------------------------------------------------------------------------


def test_override_log_records_rule_override(base_rule_set):
    log = OverrideLog()
    _, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    log.record_rule_override(record)
    assert len(log.rule_overrides()) == 1
    assert log.rule_overrides()[0].rule_id == "r_hacim"


def test_override_log_records_quote_override():
    log = OverrideLog()
    quote = apply_quote_override(
        quote_id="Q-007",
        original_price=5000.0,
        overridden_price=4500.0,
        reason="test",
        operator="op1",
    )
    log.record_quote_override(quote.override_record)
    assert len(log.quote_overrides()) == 1
    assert log.quote_overrides()[0].quote_id == "Q-007"


def test_override_log_lookup_by_quote_id():
    log = OverrideLog()
    q1 = apply_quote_override("Q-A", 1000.0, 900.0, "r1", "op1")
    q2 = apply_quote_override("Q-B", 2000.0, 1800.0, "r2", "op1")
    log.record_quote_override(q1.override_record)
    log.record_quote_override(q2.override_record)
    found = log.quote_override_for("Q-B")
    assert found is not None
    assert found.quote_id == "Q-B"
    assert found.original_price == 2000.0


def test_override_log_lookup_not_found_returns_none():
    log = OverrideLog()
    assert log.quote_override_for("OLMAYAN") is None


def test_override_log_returns_copies():
    """Dondurulan liste mutasyonu log'u etkilememeli."""
    log = OverrideLog()
    q = apply_quote_override("Q-X", 1000.0, 900.0, "r", "op1")
    log.record_quote_override(q.override_record)
    lst = log.quote_overrides()
    lst.clear()
    assert len(log.quote_overrides()) == 1


# ---------------------------------------------------------------------------
# FINDING-09: override_rule_param log_path entegrasyon testi
# ---------------------------------------------------------------------------


def test_override_rule_param_with_log_path_writes_record(tmp_path, base_rule_set):
    """log_path verilirse override kaydi JSONL dosyasina otomatik yazilmali."""
    log_file = str(tmp_path / "override_log.jsonl")
    _, record = override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=650.0,
        reason="entegrasyon testi",
        new_version="1.1",
        log_path=log_file,
    )
    records = read_all_records(log_file)
    assert len(records) == 1
    r = records[0]
    assert r["record_type"] == "rule_override"
    assert r["rule_id"] == "r_hacim"
    assert r["reason"] == "entegrasyon testi"
    assert r["new_version"] == "1.1"


def test_override_rule_param_without_log_path_no_file(tmp_path, base_rule_set):
    """log_path verilmezse hicbir dosya olusturulmamali (eski davranis korunur)."""
    log_file = str(tmp_path / "should_not_exist.jsonl")
    override_rule_param(
        base_rule_set,
        rule_id="r_hacim",
        param="unit_price",
        new_value=650.0,
        reason="test",
        new_version="1.1",
        # log_path=None (varsayilan)
    )
    import os
    assert not os.path.exists(log_file)
