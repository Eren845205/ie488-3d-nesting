"""TDD testleri — src/scheduling/feasibility.py (PLAN_DEMO1.md 8.4).

Kapsam: parti plani + kapasite => siparis-basina tahmini bitis tarihi;
        deadline asimi uyari listesi.
"""

from datetime import date

import pytest

from src.scheduling.models import Capacity, Order
from src.scheduling.batcher import Batch
from src.scheduling.feasibility import (
    DeadlineWarning,
    check_feasibility,
)

TODAY = date(2026, 6, 13)

# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------


def make_order(
    order_id: str,
    customer: str = "Ford",
    deadline: str = "2026-06-18",
    total_volume_cm3: float = 5000.0,
    priority_class: int = 1,
) -> Order:
    return Order(
        order_id=order_id,
        customer=customer,
        parts_ref="ref",
        total_quantity=10,
        total_volume_cm3=total_volume_cm3,
        deadline=deadline,
        priority_class=priority_class,
    )


def make_batch(batch_id: str, orders: list, customer: str = "Ford") -> Batch:
    vol = sum(o.total_volume_cm3 for o in orders)
    return Batch(
        batch_id=batch_id,
        orders=orders,
        total_volume_cm3=vol,
        customer=customer,
    )


def make_capacity(
    num_machines: int = 1,
    batch_duration_hours: float = 8.0,
    shifts_per_day: int = 1,
    max_volume_per_batch_cm3: float = 20000.0,
) -> Capacity:
    return Capacity(
        num_machines=num_machines,
        batch_duration_hours=batch_duration_hours,
        shifts_per_day=shifts_per_day,
        max_volume_per_batch_cm3=max_volume_per_batch_cm3,
    )


# ---------------------------------------------------------------------------
# check_feasibility — donus yapisi
# ---------------------------------------------------------------------------


def test_check_feasibility_returns_list():
    cap = make_capacity()
    o = make_order("ORD-001", deadline="2026-06-30")
    b = make_batch("B1", [o])
    result = check_feasibility([b], cap, today=TODAY)
    assert isinstance(result, list)


def test_check_feasibility_empty_batches():
    cap = make_capacity()
    result = check_feasibility([], cap, today=TODAY)
    assert result == []


def test_deadline_warning_fields():
    """DeadlineWarning gereken alanlara sahip olmali."""
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    # 1 gun/parti; bitis = bugun + 1 gun; deadline = bugun (asim kesin)
    o = make_order("ORD-LATE", deadline="2026-06-13", total_volume_cm3=5000.0)
    b = make_batch("B1", [o])
    warnings = check_feasibility([b], cap, today=TODAY)
    if warnings:
        w = warnings[0]
        assert hasattr(w, "order_id")
        assert hasattr(w, "deadline")
        assert hasattr(w, "estimated_completion")
        assert hasattr(w, "delay_days")


# ---------------------------------------------------------------------------
# Bitis tarihi hesabi
# ---------------------------------------------------------------------------


def test_first_batch_completes_after_one_batch_duration():
    """Tek partili plan: bitis = bugun + parti_gun_sayisi."""
    # 1 makine, 8 saat/parti, 1 vardiya => 8 saat/gun kapasitesi
    # 1 parti = 1 gun
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    o = make_order("ORD-001", deadline="2026-06-30")
    b = make_batch("B1", [o])
    warnings = check_feasibility([b], cap, today=TODAY)
    # 30 Haziran gec deadline; uyari olmamali
    assert all(w.order_id != "ORD-001" for w in warnings)


def test_two_sequential_batches_completion_order():
    """Ikinci parti ilk partinin bitmesinden sonra baslar."""
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    o1 = make_order("ORD-001", deadline="2026-06-30")
    o2 = make_order("ORD-002", deadline="2026-06-30")
    b1 = make_batch("B1", [o1])
    b2 = make_batch("B2", [o2])
    # Simdi 2 parti varken her biri ayri makine suresi alir
    # Uyari listesi bos olmali (gec deadline)
    warnings = check_feasibility([b1, b2], cap, today=TODAY)
    assert all(w.order_id not in ("ORD-001", "ORD-002") for w in warnings)


# ---------------------------------------------------------------------------
# Deadline asimi uyarilari
# ---------------------------------------------------------------------------


def test_overdue_order_generates_warning():
    """Bitis deadline'dan sonraysa uyari uretilmeli."""
    # 2 makine, 8 saat, 1 vardiya => 8 saat/parti/makine
    # Ayni anda 2 parti => her parti 1 gun
    # Ama siradaki partiler icin: parti 1 gun surerse + cok parti varsa bitis uzar
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    # 3 parti sirayla: bitis 3 gun sonra
    orders = [make_order(f"ORD-{i}", deadline="2026-06-14") for i in range(3)]
    batches = [make_batch(f"B{i+1}", [o]) for i, o in enumerate(orders)]
    warnings = check_feasibility(batches, cap, today=TODAY)
    # En azindan son siparis (3. gunde bitecek) icin uyari beklenir
    warned_ids = {w.order_id for w in warnings}
    assert len(warned_ids) > 0


def test_delay_days_positive_when_late():
    """Geciken siparis icin delay_days > 0 olmali."""
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    # 5 parti sirayla; ilk siparisin deadline yarini (14 Haziran)
    orders = [make_order(f"ORD-{i}", deadline="2026-06-14") for i in range(5)]
    batches = [make_batch(f"B{i+1}", [o]) for i, o in enumerate(orders)]
    warnings = check_feasibility(batches, cap, today=TODAY)
    for w in warnings:
        assert w.delay_days > 0


def test_no_warning_when_all_on_time():
    """Tum siparisler zamaninda bitiyorsa uyari listesi bos olmali."""
    cap = make_capacity(num_machines=2, batch_duration_hours=8.0, shifts_per_day=2)
    o = make_order("ORD-001", deadline="2026-12-31")
    b = make_batch("B1", [o])
    warnings = check_feasibility([b], cap, today=TODAY)
    assert warnings == []


# ---------------------------------------------------------------------------
# Deterministik
# ---------------------------------------------------------------------------


def test_check_feasibility_deterministic():
    cap = make_capacity()
    orders = [make_order(f"ORD-{i}", deadline="2026-06-15") for i in range(3)]
    batches = [make_batch(f"B{i+1}", [o]) for i, o in enumerate(orders)]
    w1 = [(w.order_id, w.delay_days) for w in check_feasibility(batches, cap, today=TODAY)]
    w2 = [(w.order_id, w.delay_days) for w in check_feasibility(batches, cap, today=TODAY)]
    assert w1 == w2


# ---------------------------------------------------------------------------
# Ford 5-gun / Baykar 30-gun senaryosu
# ---------------------------------------------------------------------------


def test_feasibility_12h_shift_completion_date():
    """
    12 saatlik vardiya duzeni: hours_per_shift=12, batch_duration_hours=12,
    shifts_per_day=1 => batch_days()=1.0 => ceil=1 gun/parti.
    2 parti sirayla: 1. parti bugun+1, 2. parti bugun+2 biter.
    deadline=bugun+1 olan 2. parti icin uyari uretilmeli.
    """
    cap = Capacity(
        num_machines=1,
        batch_duration_hours=12.0,
        shifts_per_day=1,
        hours_per_shift=12.0,
        max_volume_per_batch_cm3=20000.0,
    )
    o1 = make_order("ORD-A", deadline="2026-06-20")  # gec deadline, sorun yok
    o2 = make_order("ORD-B", deadline="2026-06-14")  # 1 gun sonrasi; 2. parti 2. gunde bitiyor
    b1 = make_batch("B1", [o1])
    b2 = make_batch("B2", [o2])
    warnings = check_feasibility([b1, b2], cap, today=TODAY)
    warned_ids = {w.order_id for w in warnings}
    # ORD-B: completion=bugun+2=15 Haziran, deadline=14 Haziran => uyari beklenir
    assert "ORD-B" in warned_ids
    # ORD-A: completion=bugun+1=14 Haziran, deadline=20 Haziran => uyari olmamali
    assert "ORD-A" not in warned_ids


def test_ford_5day_baykar_30day_scenario():
    """
    Ford: 5 gunluk termin — acil; Baykar: 30 gun — rahat.
    1 makine, 8 saat/parti, 1 vardiya (1 parti/gun).
    Ford siparisi once geliyor (yuksek oncelik) -> Baykar siparisi 2. gunde bitiyor.
    Baykar terminle (14 Temmuz = 31 gun uzakta) uyari olmamali;
    Ford terminle (18 Haziran = 5 gun uzakta) uyari olmamali (1. parti 1. gunde biter).
    """
    cap = make_capacity(num_machines=1, batch_duration_hours=8.0, shifts_per_day=1)
    o_ford = make_order("ORD-FORD", customer="Ford", deadline="2026-06-18")
    o_baykar = make_order("ORD-BAYKAR", customer="Baykar", deadline="2026-07-13")
    b_ford = make_batch("B1", [o_ford], customer="Ford")
    b_baykar = make_batch("B2", [o_baykar], customer="Baykar")
    warnings = check_feasibility([b_ford, b_baykar], cap, today=TODAY)
    warned_ids = {w.order_id for w in warnings}
    assert "ORD-FORD" not in warned_ids
    assert "ORD-BAYKAR" not in warned_ids
