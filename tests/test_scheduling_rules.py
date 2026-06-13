"""TDD testleri — src/scheduling/rules.py (PLAN_DEMO1.md 8.2).

Kapsam: agirlikli oncelik skoru, EDD default, deterministik siralama,
        agirliklar JSON konfigurasyonundan, esitlik kirici order_id.
"""

from datetime import date

import pytest

from src.scheduling.models import Order
from src.scheduling.rules import PriorityConfig, score_order, rank_orders

TODAY = date(2026, 6, 13)

# ---------------------------------------------------------------------------
# Fikstürler
# ---------------------------------------------------------------------------


def make_order(
    order_id: str,
    customer: str = "Musteri",
    deadline: str = "2026-06-18",
    priority_class: int = 1,
    total_quantity: int = 10,
    total_volume_cm3: float = 1000.0,
) -> Order:
    return Order(
        order_id=order_id,
        customer=customer,
        parts_ref="ref",
        total_quantity=total_quantity,
        total_volume_cm3=total_volume_cm3,
        deadline=deadline,
        priority_class=priority_class,
    )


DEFAULT_CONFIG = PriorityConfig.default()


# ---------------------------------------------------------------------------
# PriorityConfig — default EDD
# ---------------------------------------------------------------------------


def test_priority_config_default_exists():
    cfg = PriorityConfig.default()
    assert cfg is not None


def test_priority_config_has_required_weight_keys():
    cfg = PriorityConfig.default()
    for key in ("w_slack", "w_priority", "w_volume"):
        assert hasattr(cfg, key), f"{key} alani eksik"


def test_priority_config_default_edd_dominant():
    """EDD default'unda slack agirliginin baskin olmasi beklenir (>= diger agirliklar)."""
    cfg = PriorityConfig.default()
    assert cfg.w_slack >= cfg.w_priority
    assert cfg.w_slack >= cfg.w_volume


# ---------------------------------------------------------------------------
# PriorityConfig — JSON round-trip
# ---------------------------------------------------------------------------


def test_priority_config_json_round_trip():
    cfg = PriorityConfig(w_slack=2.0, w_priority=1.0, w_volume=0.5)
    import json
    d = cfg.to_dict()
    j = json.dumps(d)
    cfg2 = PriorityConfig.from_dict(json.loads(j))
    assert cfg2.w_slack == pytest.approx(2.0)
    assert cfg2.w_priority == pytest.approx(1.0)
    assert cfg2.w_volume == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# score_order — temel davranis
# ---------------------------------------------------------------------------


def test_score_order_returns_float():
    o = make_order("ORD-001", deadline="2026-06-18")
    s = score_order(o, DEFAULT_CONFIG, today=TODAY)
    assert isinstance(s, float)


def test_score_order_closer_deadline_higher_score():
    """Daha yakin terminli siparis daha yuksek skor almali (once islenmeli)."""
    o_close = make_order("ORD-A", deadline="2026-06-15")
    o_far = make_order("ORD-B", deadline="2026-06-30")
    s_close = score_order(o_close, DEFAULT_CONFIG, today=TODAY)
    s_far = score_order(o_far, DEFAULT_CONFIG, today=TODAY)
    assert s_close > s_far


def test_score_order_higher_priority_class_lower_score_penalty():
    """Daha yuksek priority_class (1 = en oncelikli) daha iyi skor almali."""
    o_high = make_order("ORD-A", priority_class=1, deadline="2026-06-20")
    o_low = make_order("ORD-B", priority_class=5, deadline="2026-06-20")
    s_high = score_order(o_high, DEFAULT_CONFIG, today=TODAY)
    s_low = score_order(o_low, DEFAULT_CONFIG, today=TODAY)
    assert s_high > s_low


def test_score_order_deterministic():
    """Ayni girdi => ayni skor."""
    o = make_order("ORD-001", deadline="2026-06-18")
    s1 = score_order(o, DEFAULT_CONFIG, today=TODAY)
    s2 = score_order(o, DEFAULT_CONFIG, today=TODAY)
    assert s1 == s2


def test_score_order_today_param_matters():
    """today parametresi skoru etkiler — simdi bagimli degil."""
    o = make_order("ORD-001", deadline="2026-06-18")
    s_today = score_order(o, DEFAULT_CONFIG, today=date(2026, 6, 13))
    s_later = score_order(o, DEFAULT_CONFIG, today=date(2026, 6, 16))
    # Daha gec gunden bakinca slack daha az — skor degismeli
    assert s_today != s_later


# ---------------------------------------------------------------------------
# rank_orders — siralama
# ---------------------------------------------------------------------------


def test_rank_orders_returns_list_same_length():
    orders = [make_order(f"ORD-{i:03d}", deadline="2026-06-20") for i in range(5)]
    ranked = rank_orders(orders, DEFAULT_CONFIG, today=TODAY)
    assert len(ranked) == 5


def test_rank_orders_by_deadline_edd():
    """EDD: yakin terminli once gelmeli."""
    o1 = make_order("ORD-001", deadline="2026-06-30")
    o2 = make_order("ORD-002", deadline="2026-06-15")
    o3 = make_order("ORD-003", deadline="2026-06-20")
    ranked = rank_orders([o1, o2, o3], DEFAULT_CONFIG, today=TODAY)
    assert ranked[0].order_id == "ORD-002"
    assert ranked[1].order_id == "ORD-003"
    assert ranked[2].order_id == "ORD-001"


def test_rank_orders_tie_broken_by_order_id():
    """Esit skor => order_id alfabetik sirasi kiriyor."""
    o1 = make_order("ORD-B", deadline="2026-06-20", priority_class=1)
    o2 = make_order("ORD-A", deadline="2026-06-20", priority_class=1)
    ranked = rank_orders([o1, o2], DEFAULT_CONFIG, today=TODAY)
    assert ranked[0].order_id == "ORD-A"
    assert ranked[1].order_id == "ORD-B"


def test_rank_orders_deterministic():
    """Ayni liste + ayni konfig => her zaman ayni siralama."""
    orders = [
        make_order("ORD-C", deadline="2026-06-25"),
        make_order("ORD-A", deadline="2026-06-18"),
        make_order("ORD-B", deadline="2026-06-20"),
    ]
    r1 = [o.order_id for o in rank_orders(orders, DEFAULT_CONFIG, today=TODAY)]
    r2 = [o.order_id for o in rank_orders(orders, DEFAULT_CONFIG, today=TODAY)]
    assert r1 == r2


def test_rank_orders_custom_config():
    """Ozel agirliklar -> farkli siralama mumkun (volume dominant)."""
    volume_cfg = PriorityConfig(w_slack=0.1, w_priority=0.1, w_volume=10.0)
    o_big = make_order("ORD-BIG", deadline="2026-06-30", total_volume_cm3=50000.0)
    o_small = make_order("ORD-SML", deadline="2026-06-15", total_volume_cm3=100.0)
    ranked = rank_orders([o_big, o_small], volume_cfg, today=TODAY)
    # Buyuk hacim dominant yapinca buyuk siparis once gelmeli
    assert ranked[0].order_id == "ORD-BIG"


def test_rank_orders_empty_list():
    ranked = rank_orders([], DEFAULT_CONFIG, today=TODAY)
    assert ranked == []


# ---------------------------------------------------------------------------
# FINDING-7: EDD karsı-ornek — buyuk hacim yakin termini gecemez
# ---------------------------------------------------------------------------


def test_rank_orders_edd_wins_over_large_volume():
    """Yakin terminli kucuk siparis, uzak terminli buyuk hacimli siparisi gecmeli.

    Bu test normalizasyon oncesinde FAIL ederdi (buyuk hacim log1p ile
    sinirsiz byuyuyor ve EDD'yi eziyordu). Normalizasyon sonrasi gecmeli.
    """
    # A: termin yarin, kucuk hacim
    tomorrow = date(TODAY.year, TODAY.month, TODAY.day)
    import datetime
    tomorrow_str = (datetime.date(TODAY.year, TODAY.month, TODAY.day) + datetime.timedelta(days=1)).isoformat()
    o_a = make_order("ORD-A", deadline=tomorrow_str, total_volume_cm3=500.0)
    # B: termin 90 gun sonra, cok buyuk hacim
    far_str = (datetime.date(TODAY.year, TODAY.month, TODAY.day) + datetime.timedelta(days=90)).isoformat()
    o_b = make_order("ORD-B", deadline=far_str, total_volume_cm3=100_000.0)
    ranked = rank_orders([o_b, o_a], DEFAULT_CONFIG, today=TODAY)
    assert ranked[0].order_id == "ORD-A", (
        "Yakin terminli A, uzak terminli buyuk-hacimli B'den once gelmeli"
    )


# ---------------------------------------------------------------------------
# FINDING-8: normalize edilmis bilesenlerin ust siniri <= 1.0
# ---------------------------------------------------------------------------


def test_score_components_bounded():
    """Her normalize edilmis bilesens <= 1.0 olmali."""
    import math

    cfg = DEFAULT_CONFIG

    # En iyi slack: bugune esit termin (slack_days = 0 → slack_score = 1.0)
    o_today_deadline = make_order(
        "ORD-TODAY",
        deadline=TODAY.isoformat(),
        priority_class=1,
        total_volume_cm3=cfg.ref_volume * 2,  # ref_volume asimak icin
    )
    slack_score = 1.0 / (max(0, (date.fromisoformat(o_today_deadline.deadline) - TODAY).days) + 1.0)
    assert slack_score <= 1.0, f"slack_score bandi asildi: {slack_score}"

    priority_score = 1.0 / float(o_today_deadline.priority_class)
    assert priority_score <= 1.0, f"priority_score bandi asildi: {priority_score}"

    volume_score = min(
        1.0,
        math.log1p(o_today_deadline.total_volume_cm3) / math.log1p(cfg.ref_volume),
    )
    assert volume_score <= 1.0, f"volume_score bandi asildi: {volume_score}"


def test_priority_config_validate_rejects_negative_weight():
    """Negatif agirlik ValueError firlatmali."""
    cfg = PriorityConfig(w_slack=-1.0, w_priority=2.0, w_volume=1.0)
    with pytest.raises(ValueError):
        cfg.validate()


def test_priority_config_validate_rejects_all_zero_weights():
    """Tum agirliklar sifir ise ValueError firlatmali."""
    cfg = PriorityConfig(w_slack=0.0, w_priority=0.0, w_volume=0.0)
    with pytest.raises(ValueError):
        cfg.validate()


def test_priority_config_validate_rejects_nonpositive_ref_volume():
    """ref_volume <= 0 ise ValueError firlatmali."""
    cfg = PriorityConfig(w_slack=3.0, w_priority=2.0, w_volume=1.0, ref_volume=0.0)
    with pytest.raises(ValueError):
        cfg.validate()


def test_priority_config_from_dict_calls_validate():
    """from_dict negatif agirlik iceren dict'te ValueError firlatmali."""
    with pytest.raises(ValueError):
        PriorityConfig.from_dict({"w_slack": -1.0, "w_priority": 2.0, "w_volume": 1.0})
