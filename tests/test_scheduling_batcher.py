"""TDD testleri — src/scheduling/batcher.py (PLAN_DEMO1.md 8.3).

Kapsam: oncelik sirasindaki siparislerden kapasiteye sigan partiler;
        allow_mixing bayragi (tek-musterili vs karisik mod).
"""

from datetime import date

import pytest

from src.scheduling.models import Capacity, Order
from src.scheduling.batcher import Batch, build_batches

TODAY = date(2026, 6, 13)

# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------


def make_order(
    order_id: str,
    customer: str = "Ford",
    total_volume_cm3: float = 5000.0,
    deadline: str = "2026-06-18",
    priority_class: int = 1,
    total_quantity: int = 10,
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
# Batch dataclass
# ---------------------------------------------------------------------------


def test_batch_has_required_fields():
    cap = make_capacity()
    orders = [make_order("ORD-001")]
    batches = build_batches(orders, cap, allow_mixing=False)
    assert len(batches) >= 1
    b = batches[0]
    assert hasattr(b, "batch_id")
    assert hasattr(b, "orders")
    assert hasattr(b, "total_volume_cm3")
    assert hasattr(b, "customer")


def test_batch_orders_list_nonempty():
    cap = make_capacity()
    orders = [make_order("ORD-001")]
    batches = build_batches(orders, cap, allow_mixing=False)
    for b in batches:
        assert len(b.orders) > 0


# ---------------------------------------------------------------------------
# Kapasite sigdirma — hacim kisiti
# ---------------------------------------------------------------------------


def test_all_orders_placed_in_batches():
    """Tum siparisler en az bir partide yer almali."""
    cap = make_capacity(max_volume_per_batch_cm3=10000.0)
    orders = [make_order(f"ORD-{i:03d}", total_volume_cm3=3000.0) for i in range(4)]
    batches = build_batches(orders, cap, allow_mixing=True)
    placed_ids = {o.order_id for b in batches for o in b.orders}
    all_ids = {o.order_id for o in orders}
    assert placed_ids == all_ids


def test_batch_volume_does_not_exceed_capacity():
    """Her partideki toplam hacim kapasite sinirini asmamali."""
    cap = make_capacity(max_volume_per_batch_cm3=10000.0)
    orders = [make_order(f"ORD-{i:03d}", total_volume_cm3=3500.0) for i in range(5)]
    batches = build_batches(orders, cap, allow_mixing=True)
    for b in batches:
        assert b.total_volume_cm3 <= cap.max_volume_per_batch_cm3 + 1e-9


def test_single_order_larger_than_capacity_goes_in_own_batch():
    """Kapasitenin ustundeki tekil siparis kendi partisine girer (sigdirilamaz uyarisi verir)."""
    cap = make_capacity(max_volume_per_batch_cm3=5000.0)
    orders = [make_order("ORD-BIG", total_volume_cm3=8000.0)]
    # Ozel siparis kendi partisine girmeli (hacim asimina ragmen yerlestirilir)
    batches = build_batches(orders, cap, allow_mixing=False)
    assert len(batches) == 1
    assert batches[0].orders[0].order_id == "ORD-BIG"


# ---------------------------------------------------------------------------
# allow_mixing=False — tek-musterili partiler
# ---------------------------------------------------------------------------


def test_no_mixing_partitions_by_customer():
    """Karisim kapali => her parti tek musterinin siparislerini icerir."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford", total_volume_cm3=3000.0),
        make_order("ORD-B1", customer="Baykar", total_volume_cm3=3000.0),
        make_order("ORD-F2", customer="Ford", total_volume_cm3=3000.0),
    ]
    batches = build_batches(orders, cap, allow_mixing=False)
    for b in batches:
        customers = {o.customer for o in b.orders}
        assert len(customers) == 1, f"Parti {b.batch_id} birden fazla musteri iceriyor: {customers}"


def test_no_mixing_all_customers_covered():
    """Karisim kapali => Ford + Baykar siparisleri ayri partilerde yer almali."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford"),
        make_order("ORD-B1", customer="Baykar"),
    ]
    batches = build_batches(orders, cap, allow_mixing=False)
    customers_in_batches = {b.customer for b in batches}
    assert "Ford" in customers_in_batches
    assert "Baykar" in customers_in_batches


# ---------------------------------------------------------------------------
# allow_mixing=True — karisik mod
# ---------------------------------------------------------------------------


def test_mixing_allows_multiple_customers_per_batch():
    """Karisim acik => farkli musteriler ayni partide olabilir."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford", total_volume_cm3=3000.0),
        make_order("ORD-B1", customer="Baykar", total_volume_cm3=3000.0),
    ]
    batches = build_batches(orders, cap, allow_mixing=True)
    # En az bir partide 2 musteri olmali (kapasiteli ortamda)
    multi = any(len({o.customer for o in b.orders}) > 1 for b in batches)
    assert multi


# ---------------------------------------------------------------------------
# Parti siralama + deterministik
# ---------------------------------------------------------------------------


def test_batches_ordered_consistently():
    """Parti sirasi deterministik olmali."""
    cap = make_capacity(max_volume_per_batch_cm3=10000.0)
    orders = [make_order(f"ORD-{i:03d}", total_volume_cm3=3000.0) for i in range(4)]
    b1 = [b.batch_id for b in build_batches(orders, cap, allow_mixing=True)]
    b2 = [b.batch_id for b in build_batches(orders, cap, allow_mixing=True)]
    assert b1 == b2


def test_empty_order_list():
    cap = make_capacity()
    batches = build_batches([], cap, allow_mixing=False)
    assert batches == []


# ---------------------------------------------------------------------------
# Batch total_volume dogru
# ---------------------------------------------------------------------------


def test_batch_total_volume_matches_sum():
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [make_order(f"ORD-{i}", total_volume_cm3=1500.0) for i in range(3)]
    batches = build_batches(orders, cap, allow_mixing=True)
    for b in batches:
        expected = sum(o.total_volume_cm3 for o in b.orders)
        assert b.total_volume_cm3 == pytest.approx(expected)


# ---------------------------------------------------------------------------
# FINDING-4/6: oversized flag
# ---------------------------------------------------------------------------


def test_oversized_order_sets_oversized_flag():
    """Kapasitenin ustundeki siparis kendi partisine girmeli ve oversized=True olmali."""
    cap = make_capacity(max_volume_per_batch_cm3=5000.0)
    orders = [make_order("ORD-HUGE", total_volume_cm3=9000.0)]
    batches = build_batches(orders, cap, allow_mixing=False)
    assert len(batches) == 1
    assert batches[0].oversized is True


def test_normal_order_oversized_flag_false():
    """Kapasiteye sigan siparis icin oversized=False olmali."""
    cap = make_capacity(max_volume_per_batch_cm3=20000.0)
    orders = [make_order("ORD-OK", total_volume_cm3=5000.0)]
    batches = build_batches(orders, cap, allow_mixing=False)
    assert len(batches) == 1
    assert batches[0].oversized is False


# ---------------------------------------------------------------------------
# FINDING-5: customers list
# ---------------------------------------------------------------------------


def test_customers_list_single_customer():
    """Tek musterili partide customers listesi o musteriyi icermeli."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford", total_volume_cm3=3000.0),
        make_order("ORD-F2", customer="Ford", total_volume_cm3=3000.0),
    ]
    batches = build_batches(orders, cap, allow_mixing=False)
    assert len(batches) == 1
    assert batches[0].customers == ["Ford"]


def test_customers_list_mixed_batch():
    """allow_mixing=True ve farkli musteriler ayni partideyse customers listesi her iki musteriyi icermeli."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford", total_volume_cm3=3000.0),
        make_order("ORD-B1", customer="Baykar", total_volume_cm3=3000.0),
    ]
    batches = build_batches(orders, cap, allow_mixing=True)
    # Hepsi tek partide toplanmali (kapasite yeterli)
    assert len(batches) == 1
    assert "Ford" in batches[0].customers
    assert "Baykar" in batches[0].customers
