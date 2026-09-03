"""TDD testleri — src/pricing/versioning.py (PLAN_DEMO1.md 7.4).

Kapsam: append-only JSONL log, teklif kaydi, override kaydi, geri sorgu.
"""

import json
import os
import tempfile
import pytest

from src.pricing.schema import PricingRule, RuleSet
from src.pricing.engine import PricingEngine
from src.pricing.overrides import apply_quote_override, override_rule_param
from src.pricing.versioning import (
    append_quote_record,
    append_rule_override_record,
    append_quote_override_record,
    find_quote_record,
    find_quote_overrides,
    find_rule_set_version_for_quote,
    read_all_records,
)


# ---------------------------------------------------------------------------
# Fikstür
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_log(tmp_path):
    return str(tmp_path / "pricing_log.jsonl")


@pytest.fixture()
def simple_rule_set():
    return RuleSet(
        version="1.0",
        name="test_rs",
        rules=[
            PricingRule(
                id="r1",
                type="unit_price",
                input_field="hacim_m3",
                unit_price=500.0,
            )
        ],
    )


@pytest.fixture()
def simple_engine(simple_rule_set):
    return PricingEngine(simple_rule_set)


# ---------------------------------------------------------------------------
# Teklif kaydi yaz / oku
# ---------------------------------------------------------------------------


def test_append_quote_record_creates_file(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-001", result)
    assert os.path.exists(tmp_log)


def test_append_quote_record_valid_json(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-001", result)
    records = read_all_records(tmp_log)
    assert len(records) == 1
    r = records[0]
    assert r["record_type"] == "quote"
    assert r["quote_id"] == "Q-001"


def test_append_quote_record_stores_price(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-001", result)
    records = read_all_records(tmp_log)
    assert records[0]["total_price"] == pytest.approx(2500.0)


def test_append_quote_record_stores_rule_set_version(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-001", result)
    records = read_all_records(tmp_log)
    assert records[0]["rule_set_version"] == "1.0"


def test_append_quote_record_stores_inputs(tmp_log, simple_engine):
    inputs = {"hacim_m3": 7.0}
    result = simple_engine.calculate(inputs)
    append_quote_record(tmp_log, "Q-002", result)
    records = read_all_records(tmp_log)
    assert records[0]["inputs"]["hacim_m3"] == pytest.approx(7.0)


def test_append_quote_record_stores_breakdown(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 3.0})
    append_quote_record(tmp_log, "Q-003", result)
    records = read_all_records(tmp_log)
    assert len(records[0]["breakdown"]) == 1  # tek kural
    assert "unit_price" in records[0]["breakdown"][0]


def test_append_quote_record_has_timestamp(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 1.0})
    append_quote_record(tmp_log, "Q-004", result)
    records = read_all_records(tmp_log)
    assert records[0]["timestamp"]


# ---------------------------------------------------------------------------
# Append-only — birden fazla kayit
# ---------------------------------------------------------------------------


def test_multiple_records_all_readable(tmp_log, simple_engine):
    r1 = simple_engine.calculate({"hacim_m3": 1.0})
    r2 = simple_engine.calculate({"hacim_m3": 2.0})
    append_quote_record(tmp_log, "Q-001", r1)
    append_quote_record(tmp_log, "Q-002", r2)
    records = read_all_records(tmp_log)
    assert len(records) == 2
    assert records[0]["quote_id"] == "Q-001"
    assert records[1]["quote_id"] == "Q-002"


def test_each_record_on_separate_line(tmp_log, simple_engine):
    """JSONL formatinda her kayit ayri satirda olmali."""
    r = simple_engine.calculate({"hacim_m3": 1.0})
    append_quote_record(tmp_log, "Q-A", r)
    append_quote_record(tmp_log, "Q-B", r)
    with open(tmp_log, encoding="utf-8") as fh:
        lines = [line.strip() for line in fh if line.strip()]
    assert len(lines) == 2
    # Her satir gecerli JSON olmali
    for line in lines:
        json.loads(line)


# ---------------------------------------------------------------------------
# Geri sorgu: hangi kural versiyonuyla hesaplandi
# ---------------------------------------------------------------------------


def test_find_quote_record_returns_correct(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-FIND", result)
    found = find_quote_record(tmp_log, "Q-FIND")
    assert found is not None
    assert found["quote_id"] == "Q-FIND"


def test_find_quote_record_returns_none_for_missing(tmp_log):
    found = find_quote_record(tmp_log, "OLMAYAN")
    assert found is None


def test_find_rule_set_version_for_quote(tmp_log, simple_engine):
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-V", result)
    version = find_rule_set_version_for_quote(tmp_log, "Q-V")
    assert version == "1.0"


def test_find_rule_set_version_returns_none_if_not_found(tmp_log):
    version = find_rule_set_version_for_quote(tmp_log, "OLMAYAN")
    assert version is None


def test_find_quote_different_versions(tmp_log, simple_rule_set):
    """Farkli versiyon kural setleriyle hesaplanan tekliflerin versiyonlari dogru geri okunur."""
    engine_v1 = PricingEngine(simple_rule_set)

    new_rs, _ = override_rule_param(
        simple_rule_set,
        rule_id="r1",
        param="unit_price",
        new_value=600.0,
        reason="revizyon",
        new_version="1.1",
    )
    engine_v2 = PricingEngine(new_rs)

    r1 = engine_v1.calculate({"hacim_m3": 5.0})
    r2 = engine_v2.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-V1", r1)
    append_quote_record(tmp_log, "Q-V2", r2)

    assert find_rule_set_version_for_quote(tmp_log, "Q-V1") == "1.0"
    assert find_rule_set_version_for_quote(tmp_log, "Q-V2") == "1.1"


# ---------------------------------------------------------------------------
# Kural override kaydi
# ---------------------------------------------------------------------------


def test_append_rule_override_record(tmp_log, simple_rule_set):
    _, record = override_rule_param(
        simple_rule_set,
        rule_id="r1",
        param="unit_price",
        new_value=600.0,
        reason="test",
        new_version="1.1",
    )
    append_rule_override_record(tmp_log, record)
    records = read_all_records(tmp_log)
    assert len(records) == 1
    r = records[0]
    assert r["record_type"] == "rule_override"
    assert r["rule_id"] == "r1"
    assert r["reason"] == "test"
    assert r["original_version"] == "1.0"
    assert r["new_version"] == "1.1"


def test_rule_override_record_changed_params_stored(tmp_log, simple_rule_set):
    _, record = override_rule_param(
        simple_rule_set,
        rule_id="r1",
        param="unit_price",
        new_value=750.0,
        reason="fiyat guncelleme",
        new_version="2.0",
    )
    append_rule_override_record(tmp_log, record)
    records = read_all_records(tmp_log)
    params = records[0]["changed_params"]["unit_price"]
    assert params["before"] == 500.0
    assert params["after"] == 750.0


# ---------------------------------------------------------------------------
# Teklif override kaydi
# ---------------------------------------------------------------------------


def test_append_quote_override_record(tmp_log):
    quote = apply_quote_override(
        quote_id="Q-OVR",
        original_price=5000.0,
        overridden_price=4500.0,
        reason="Musteri indirimi",
        operator="satis_mudur",
        breakdown_lines=["[r1] unit_price | hacim_m3=10.0"],
    )
    append_quote_override_record(tmp_log, quote.override_record)
    records = read_all_records(tmp_log)
    assert len(records) == 1
    r = records[0]
    assert r["record_type"] == "quote_override"
    assert r["quote_id"] == "Q-OVR"
    assert r["original_price"] == 5000.0
    assert r["overridden_price"] == 4500.0
    assert r["reason"] == "Musteri indirimi"
    assert r["operator"] == "satis_mudur"


def test_find_quote_overrides_returns_all(tmp_log):
    q1 = apply_quote_override("Q-OVR", 5000.0, 4500.0, "r1", "op1")
    q2 = apply_quote_override("Q-OVR", 4500.0, 4000.0, "r2", "op2")
    q3 = apply_quote_override("Q-BASKA", 1000.0, 900.0, "r3", "op1")
    for q in [q1, q2, q3]:
        append_quote_override_record(tmp_log, q.override_record)

    overrides = find_quote_overrides(tmp_log, "Q-OVR")
    assert len(overrides) == 2
    assert all(r["quote_id"] == "Q-OVR" for r in overrides)


def test_find_quote_overrides_empty_for_no_overrides(tmp_log):
    overrides = find_quote_overrides(tmp_log, "OLMAYAN")
    assert overrides == []


# ---------------------------------------------------------------------------
# Karma log (farkli kayit tipleri bir arada)
# ---------------------------------------------------------------------------


def test_mixed_log_read_all_records(tmp_log, simple_rule_set):
    engine = PricingEngine(simple_rule_set)
    result = engine.calculate({"hacim_m3": 5.0})

    _, rule_rec = override_rule_param(
        simple_rule_set, "r1", "unit_price", 600.0, "test", "1.1"
    )
    quote_ovr = apply_quote_override("Q-1", 2500.0, 2000.0, "indirim", "op1")

    append_quote_record(tmp_log, "Q-1", result)
    append_rule_override_record(tmp_log, rule_rec)
    append_quote_override_record(tmp_log, quote_ovr.override_record)

    all_recs = read_all_records(tmp_log)
    assert len(all_recs) == 3
    types = {r["record_type"] for r in all_recs}
    assert types == {"quote", "rule_override", "quote_override"}


# ---------------------------------------------------------------------------
# Bos / olmayan log dosyasi
# ---------------------------------------------------------------------------


def test_read_all_records_nonexistent_returns_empty(tmp_path):
    path = str(tmp_path / "nonexistent.jsonl")
    records = read_all_records(path)
    assert records == []


# ---------------------------------------------------------------------------
# FINDING-05: duplicate quote_id => ValueError
# ---------------------------------------------------------------------------


def test_append_quote_record_duplicate_raises_value_error(tmp_log, simple_engine):
    """Ayni quote_id ikinci kez yazilirsa ValueError firlatiyor olmali."""
    result = simple_engine.calculate({"hacim_m3": 5.0})
    append_quote_record(tmp_log, "Q-DUP", result)
    with pytest.raises(ValueError, match="Q-DUP"):
        append_quote_record(tmp_log, "Q-DUP", result)


def test_append_quote_record_different_ids_both_written(tmp_log, simple_engine):
    """Farkli quote_id'ler sorunsuz yazilmali — ValueError yok."""
    r1 = simple_engine.calculate({"hacim_m3": 1.0})
    r2 = simple_engine.calculate({"hacim_m3": 2.0})
    append_quote_record(tmp_log, "Q-UNIQ-1", r1)
    append_quote_record(tmp_log, "Q-UNIQ-2", r2)
    records = read_all_records(tmp_log)
    assert len(records) == 2


def test_log_creates_parent_dirs(tmp_path):
    nested = str(tmp_path / "deep" / "nested" / "pricing_log.jsonl")
    rs = RuleSet(
        version="1.0",
        name="x",
        rules=[PricingRule(id="r1", type="unit_price", input_field="hacim_m3", unit_price=1.0)],
    )
    engine = PricingEngine(rs)
    result = engine.calculate({"hacim_m3": 1.0})
    append_quote_record(nested, "Q-X", result)
    assert os.path.exists(nested)
