"""TDD testleri — src/scheduling/models.py (PLAN_DEMO1.md 8.1).

Kapsam: Order + Capacity dataclass'lari, JSON round-trip, dogrulama.
"""

import json
from datetime import date

import pytest

from src.scheduling.models import Capacity, Order

# ---------------------------------------------------------------------------
# Fikstürler
# ---------------------------------------------------------------------------

TODAY = date(2026, 6, 13)


def make_order(
    order_id: str = "ORD-001",
    customer: str = "Ford",
    parts_ref: str = "Ford-Set-A",
    total_quantity: int = 50,
    total_volume_cm3: float = 12500.0,
    deadline: str = "2026-06-18",
    priority_class: int = 1,
) -> Order:
    return Order(
        order_id=order_id,
        customer=customer,
        parts_ref=parts_ref,
        total_quantity=total_quantity,
        total_volume_cm3=total_volume_cm3,
        deadline=deadline,
        priority_class=priority_class,
    )


def make_capacity(
    num_machines: int = 2,
    batch_duration_hours: float = 8.0,
    shifts_per_day: int = 1,
) -> Capacity:
    return Capacity(
        num_machines=num_machines,
        batch_duration_hours=batch_duration_hours,
        shifts_per_day=shifts_per_day,
    )


# ---------------------------------------------------------------------------
# Order — temel alanlar
# ---------------------------------------------------------------------------


def test_order_fields_stored():
    o = make_order()
    assert o.order_id == "ORD-001"
    assert o.customer == "Ford"
    assert o.parts_ref == "Ford-Set-A"
    assert o.total_quantity == 50
    assert o.total_volume_cm3 == 12500.0
    assert o.deadline == "2026-06-18"
    assert o.priority_class == 1


# ---------------------------------------------------------------------------
# Order — JSON round-trip
# ---------------------------------------------------------------------------


def test_order_to_dict_keys():
    o = make_order()
    d = o.to_dict()
    for key in ("order_id", "customer", "parts_ref", "total_quantity",
                "total_volume_cm3", "deadline", "priority_class"):
        assert key in d


def test_order_json_round_trip():
    o = make_order()
    json_str = o.to_json()
    parsed = json.loads(json_str)
    assert parsed["order_id"] == "ORD-001"
    o2 = Order.from_json(json_str)
    assert o2.order_id == o.order_id
    assert o2.customer == o.customer
    assert o2.total_quantity == o.total_quantity
    assert o2.total_volume_cm3 == o.total_volume_cm3
    assert o2.deadline == o.deadline
    assert o2.priority_class == o.priority_class


def test_order_from_dict_round_trip():
    o = make_order(order_id="ORD-002", customer="Baykar")
    d = o.to_dict()
    o2 = Order.from_dict(d)
    assert o2.order_id == "ORD-002"
    assert o2.customer == "Baykar"


# ---------------------------------------------------------------------------
# Order — dogrulama: gecmis tarih reddi
# ---------------------------------------------------------------------------


def test_order_validate_rejects_past_deadline():
    o = Order(
        order_id="ORD-X",
        customer="Test",
        parts_ref="ref",
        total_quantity=1,
        total_volume_cm3=100.0,
        deadline="2020-01-01",  # gecmis tarih
        priority_class=1,
    )
    with pytest.raises(ValueError, match="deadline"):
        o.validate(today=TODAY)


def test_order_validate_accepts_future_deadline():
    o = make_order(deadline="2026-12-31")
    o.validate(today=TODAY)  # hata firlatmamali


def test_order_validate_accepts_same_day_deadline():
    o = make_order(deadline="2026-06-13")
    o.validate(today=TODAY)  # bugun gecerli


def test_order_validate_rejects_nonpositive_quantity():
    o = make_order(total_quantity=0)
    with pytest.raises(ValueError, match="total_quantity"):
        o.validate(today=TODAY)


def test_order_validate_rejects_negative_volume():
    o = make_order(total_volume_cm3=-1.0)
    with pytest.raises(ValueError, match="total_volume_cm3"):
        o.validate(today=TODAY)


def test_order_validate_rejects_empty_order_id():
    o = make_order(order_id="")
    with pytest.raises(ValueError, match="order_id"):
        o.validate(today=TODAY)


def test_order_validate_rejects_nonpositive_priority_class():
    o = make_order(priority_class=0)
    with pytest.raises(ValueError, match="priority_class"):
        o.validate(today=TODAY)


# ---------------------------------------------------------------------------
# Capacity — temel alanlar
# ---------------------------------------------------------------------------


def test_capacity_fields_stored():
    c = make_capacity()
    assert c.num_machines == 2
    assert c.batch_duration_hours == 8.0
    assert c.shifts_per_day == 1


# ---------------------------------------------------------------------------
# Capacity — JSON round-trip
# ---------------------------------------------------------------------------


def test_capacity_to_dict_keys():
    c = make_capacity()
    d = c.to_dict()
    for key in ("num_machines", "batch_duration_hours", "shifts_per_day"):
        assert key in d


def test_capacity_json_round_trip():
    c = make_capacity(num_machines=3, batch_duration_hours=12.0, shifts_per_day=2)
    json_str = c.to_json()
    c2 = Capacity.from_json(json_str)
    assert c2.num_machines == 3
    assert c2.batch_duration_hours == 12.0
    assert c2.shifts_per_day == 2


def test_capacity_from_dict_round_trip():
    c = make_capacity()
    d = c.to_dict()
    c2 = Capacity.from_dict(d)
    assert c2.num_machines == c.num_machines
    assert c2.batch_duration_hours == c.batch_duration_hours


# ---------------------------------------------------------------------------
# Capacity — dogrulama: negatif kapasite reddi
# ---------------------------------------------------------------------------


def test_capacity_validate_rejects_zero_machines():
    c = Capacity(num_machines=0, batch_duration_hours=8.0, shifts_per_day=1)
    with pytest.raises(ValueError, match="num_machines"):
        c.validate()


def test_capacity_validate_rejects_negative_batch_duration():
    c = Capacity(num_machines=1, batch_duration_hours=-1.0, shifts_per_day=1)
    with pytest.raises(ValueError, match="batch_duration_hours"):
        c.validate()


def test_capacity_validate_rejects_zero_shifts():
    c = Capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=0)
    with pytest.raises(ValueError, match="shifts_per_day"):
        c.validate()


def test_capacity_validate_passes_for_valid():
    c = make_capacity()
    c.validate()  # hata firlatmamali


# ---------------------------------------------------------------------------
# Capacity — gunluk kapasite hesabi
# ---------------------------------------------------------------------------


def test_capacity_daily_machine_hours():
    """Gunluk toplam makine kapasitesi = num_machines * batch_duration * shifts."""
    c = Capacity(num_machines=2, batch_duration_hours=8.0, shifts_per_day=2)
    # 2 makine * 8 saat * 2 vardiya = 32 makine-saat/gun
    assert c.daily_machine_hours() == pytest.approx(32.0)


# ---------------------------------------------------------------------------
# Capacity — batch_days() formulu (FINDING-3/9)
# ---------------------------------------------------------------------------


def test_capacity_batch_days_default_8h_shift():
    """8 saatlik parti, 1 vardiya, 8 saat/vardiya varsayimi => 1.0 gun."""
    c = Capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    assert c.batch_days() == pytest.approx(1.0)


def test_capacity_batch_days_12h_shift():
    """12 saatlik vardiyada: 12 saat parti, 1 vardiya => 1.0 gun; 24 saat parti => 2.0 gun."""
    c12 = Capacity(
        num_machines=1,
        batch_duration_hours=12.0,
        shifts_per_day=1,
        hours_per_shift=12.0,
    )
    assert c12.batch_days() == pytest.approx(1.0)

    c24 = Capacity(
        num_machines=1,
        batch_duration_hours=24.0,
        shifts_per_day=1,
        hours_per_shift=12.0,
    )
    assert c24.batch_days() == pytest.approx(2.0)


def test_capacity_batch_days_two_shifts():
    """2 vardiya, 8 saat/vardiya, 8 saatlik parti => 0.5 gun."""
    c = Capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=2)
    # 8 / (2 * 8) = 0.5
    assert c.batch_days() == pytest.approx(0.5)


def test_capacity_validate_rejects_nonpositive_hours_per_shift():
    """hours_per_shift sifir veya negatif olursa validate ValueError firlatmali."""
    c = Capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1, hours_per_shift=0.0)
    with pytest.raises(ValueError, match="hours_per_shift"):
        c.validate()


def test_capacity_from_dict_backward_compat_no_hours_per_shift():
    """Eski JSON'da hours_per_shift yoksa from_dict default 8.0 kullanmali."""
    old_dict = {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
    }
    c = Capacity.from_dict(old_dict)
    assert c.hours_per_shift == pytest.approx(8.0)


def test_capacity_from_dict_with_hours_per_shift():
    """JSON'da hours_per_shift varsa dogru sekilde yuklenmeli."""
    d = {
        "num_machines": 1,
        "batch_duration_hours": 12.0,
        "shifts_per_day": 1,
        "hours_per_shift": 12.0,
    }
    c = Capacity.from_dict(d)
    assert c.hours_per_shift == pytest.approx(12.0)
    assert c.batch_days() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Order — sifir hacim gecerli, negatif gecersiz (FINDING-10)
# ---------------------------------------------------------------------------


def test_order_validate_accepts_zero_volume():
    """total_volume_cm3=0.0 gecerli olmali (hacim henuz bilinmiyor anlami)."""
    o = make_order(total_volume_cm3=0.0)
    o.validate(today=TODAY)  # hata firlatmamali


def test_order_validate_rejects_negative_volume_confirmed():
    """total_volume_cm3 negatifse ValueError firlatmali (davranis sabitlenir)."""
    o = make_order(total_volume_cm3=-0.001)
    with pytest.raises(ValueError, match="total_volume_cm3"):
        o.validate(today=TODAY)
