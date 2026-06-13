"""TDD testleri — src/scheduling/report.py (PLAN_DEMO1.md 8.5).

Kapsam: oncelik sirasi + parti plani + termin uyarilari => ozet dict + markdown string.
        Deterministik; Ford-5gun/Baykar-30gun entegrasyon senaryosu.
"""

from datetime import date

import pytest

from src.scheduling.models import Capacity, Order
from src.scheduling.rules import PriorityConfig
from src.scheduling.batcher import Batch, build_batches
from src.scheduling.feasibility import DeadlineWarning, check_feasibility
from src.scheduling.report import build_report

TODAY = date(2026, 6, 13)

# ---------------------------------------------------------------------------
# Yardimci fonksiyonlar
# ---------------------------------------------------------------------------


def make_order(
    order_id: str,
    customer: str = "Ford",
    deadline: str = "2026-06-18",
    priority_class: int = 1,
    total_volume_cm3: float = 5000.0,
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
    max_volume_per_batch_cm3: float = 50000.0,
) -> Capacity:
    return Capacity(
        num_machines=num_machines,
        batch_duration_hours=batch_duration_hours,
        shifts_per_day=shifts_per_day,
        max_volume_per_batch_cm3=max_volume_per_batch_cm3,
    )


# ---------------------------------------------------------------------------
# build_report — donus yapisi
# ---------------------------------------------------------------------------


def test_build_report_returns_dict_and_markdown():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    cfg = PriorityConfig.default()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert isinstance(result, dict)
    assert "markdown" in result
    assert isinstance(result["markdown"], str)


def test_build_report_dict_has_required_keys():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    for key in ("ranked_orders", "batches", "warnings", "markdown", "generated_at"):
        assert key in result, f"Eksik anahtar: {key}"


def test_build_report_ranked_orders_list():
    orders = [make_order("ORD-001"), make_order("ORD-002", deadline="2026-07-01")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=True)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert len(result["ranked_orders"]) == 2


def test_build_report_batches_list():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert len(result["batches"]) >= 1


def test_build_report_warnings_list():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert isinstance(result["warnings"], list)


# ---------------------------------------------------------------------------
# Markdown icerigi
# ---------------------------------------------------------------------------


def test_markdown_contains_order_ids():
    orders = [make_order("ORD-001"), make_order("ORD-002")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=True)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    md = result["markdown"]
    assert "ORD-001" in md
    assert "ORD-002" in md


def test_markdown_contains_batch_ids():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    md = result["markdown"]
    assert batches[0].batch_id in md


def test_markdown_contains_warnings_section():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    md = result["markdown"]
    # Uyari bolumu baslik icermeli
    assert "Uyar" in md or "Warning" in md or "uyar" in md


def test_markdown_contains_today_date():
    orders = [make_order("ORD-001")]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    md = result["markdown"]
    assert "2026-06-13" in md


# ---------------------------------------------------------------------------
# Deterministik
# ---------------------------------------------------------------------------


def test_build_report_deterministic():
    orders = [
        make_order("ORD-001", deadline="2026-06-18"),
        make_order("ORD-002", deadline="2026-06-25", customer="Baykar"),
    ]
    cap = make_capacity()
    batches = build_batches(orders, cap, allow_mixing=True)
    warnings = check_feasibility(batches, cap, today=TODAY)
    r1 = build_report(ranked_orders=orders, batches=batches, warnings=warnings, today=TODAY)
    r2 = build_report(ranked_orders=orders, batches=batches, warnings=warnings, today=TODAY)
    assert r1["markdown"] == r2["markdown"]


# ---------------------------------------------------------------------------
# Ford-5gun / Baykar-30gun entegrasyon senaryosu
# ---------------------------------------------------------------------------


def test_ford_baykar_integration_scenario():
    """
    Senaryo: Ford-5gun / Baykar-30gun.

    Siparis modeli atomik birimdir: her Order tek bir islem birimi olarak
    bir partiye girer. Hacim ozeti alanı (total_volume_cm3) Order'in kimlik
    bilgisidir; batcher parcalamaz.

    Siparis dagılımı:
      - Ford: 3 siparis (her biri 5000 cm3), deadline 2026-06-18 (5 gun), priority 1
      - Baykar: 4 siparis (her biri 15000 cm3), deadline 2026-07-13 (30 gun), priority 2

    Kapasite: 1 makine, 8 saat/parti, 1 vardiya, max 20000 cm3/parti.
    allow_mixing=False (farkli musteriler karismiyor).

    Beklenti:
      - Ford siparisleri once siralanmali (yakin termin + yuksek oncelik)
      - Ford: 3 x 5000 cm3 = 15000 cm3 => 20000 siniri icinde 1 partiye sigar (hepsi)
        Veya 2 partiye sıgabilir (sirayla ekle stratejisi); en az 1 parti.
      - Baykar: 4 x 15000 cm3 = 60000 cm3 => her 15000'lik siparis ayri 1 parti
        (20000 siniri icinde 1 siparis sıgar) => 4 parti
      - Toplam: 1 + 4 = 5 parti VEYA Ford 2 parti olursa 2 + 4 = 6 parti
        (en az 5 parti beklenir)
      - Ford uyarisi yok: Ford partileri ilk islenir, deadline 5 gun var
      - Baykar uyarisi yok: deadline 30 gun var; 5-6 gunde biter
    """
    cap = make_capacity(
        num_machines=1,
        batch_duration_hours=8.0,
        shifts_per_day=1,
        max_volume_per_batch_cm3=20000.0,
    )
    # 3 Ford siparisi — her biri 5000 cm3 (tek partiye sigar = 3x5000=15000 < 20000)
    ford_orders = [
        make_order(
            f"ORD-FORD-{i}",
            customer="Ford",
            deadline="2026-06-18",
            priority_class=1,
            total_volume_cm3=5000.0,
            total_quantity=10,
        )
        for i in range(1, 4)
    ]
    # 4 Baykar siparisi — her biri 15000 cm3 (her biri kendi partisine girer)
    baykar_orders = [
        make_order(
            f"ORD-BAYKAR-{i}",
            customer="Baykar",
            deadline="2026-07-13",
            priority_class=2,
            total_volume_cm3=15000.0,
            total_quantity=50,
        )
        for i in range(1, 5)
    ]
    all_orders = ford_orders + baykar_orders

    from src.scheduling.rules import rank_orders

    ranked = rank_orders(all_orders, PriorityConfig.default(), today=TODAY)
    batches = build_batches(ranked, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    report = build_report(
        ranked_orders=ranked,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )

    # Ford siparisleri once siralanmali (ilk 3 sirada Ford olmali)
    ranked_ids = [o.order_id for o in ranked]
    ford_positions = [i for i, oid in enumerate(ranked_ids) if oid.startswith("ORD-FORD")]
    baykar_positions = [i for i, oid in enumerate(ranked_ids) if oid.startswith("ORD-BAYKAR")]
    assert max(ford_positions) < min(baykar_positions), (
        f"Ford siparisleri Baykar'dan once gelmeli; Ford pos: {ford_positions}, "
        f"Baykar pos: {baykar_positions}"
    )

    # Toplam parti sayisi: Ford partileri + 4 Baykar partisi >= 5
    assert len(batches) >= 5

    # Her partide tek musteri (allow_mixing=False)
    for b in batches:
        customers = {o.customer for o in b.orders}
        assert len(customers) == 1

    # Markdown raporunda tum siparis ID'leri var
    md = report["markdown"]
    for o in all_orders:
        assert o.order_id in md

    # Zaman rahatsa Ford uyarisi yok
    warned_ids = {w.order_id for w in warnings}
    for fo in ford_orders:
        assert fo.order_id not in warned_ids, (
            f"{fo.order_id} uyarisi var ama olmamaliydi"
        )
    # Baykar uyarisi da yok (30 gun cok rahat)
    for bo in baykar_orders:
        assert bo.order_id not in warned_ids, (
            f"{bo.order_id} uyarisi var ama olmamaliydi"
        )

    # warnings listesi raporda mevcut
    assert isinstance(report["warnings"], list)


# ---------------------------------------------------------------------------
# FINDING-4/6: oversized parti raporda gorunmeli
# ---------------------------------------------------------------------------


def test_oversized_batch_appears_in_capacity_warnings():
    """Hacim sinirini asan siparis => raporda capacity_warnings listesinde gorulmeli."""
    cap = make_capacity(max_volume_per_batch_cm3=5000.0)
    orders = [make_order("ORD-HUGE", total_volume_cm3=9000.0)]
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert "capacity_warnings" in result
    assert len(result["capacity_warnings"]) == 1
    assert result["capacity_warnings"][0]["batch_id"] == batches[0].batch_id
    assert result["capacity_warnings"][0]["order_id"] == "ORD-HUGE"


def test_oversized_batch_appears_in_markdown():
    """Hacim sinirini asan siparis => markdown'da 'Kapasite Uyarilari' bolumunde gorulmeli."""
    cap = make_capacity(max_volume_per_batch_cm3=5000.0)
    orders = [make_order("ORD-HUGE", total_volume_cm3=9000.0)]
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    md = result["markdown"]
    assert "Kapasite Uyarilari" in md
    assert "ORD-HUGE" in md


def test_no_oversized_capacity_warnings_empty():
    """Normal siparis => capacity_warnings listesi bos olmali ve markdown 'yok' mesaji icermeli."""
    cap = make_capacity(max_volume_per_batch_cm3=20000.0)
    orders = [make_order("ORD-OK", total_volume_cm3=5000.0)]
    batches = build_batches(orders, cap, allow_mixing=False)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    assert result["capacity_warnings"] == []
    assert "Kapasite Uyarilari" in result["markdown"]
    assert "yok" in result["markdown"]


# ---------------------------------------------------------------------------
# FINDING-5: customers listesi raporda gorunmeli
# ---------------------------------------------------------------------------


def test_report_batch_dict_contains_customers_list():
    """Rapordaki parti sozlugunde 'customers' listesi bulunmali."""
    cap = make_capacity(max_volume_per_batch_cm3=50000.0)
    orders = [
        make_order("ORD-F1", customer="Ford", total_volume_cm3=3000.0),
        make_order("ORD-B1", customer="Baykar", total_volume_cm3=3000.0),
    ]
    batches = build_batches(orders, cap, allow_mixing=True)
    warnings = check_feasibility(batches, cap, today=TODAY)
    result = build_report(
        ranked_orders=orders,
        batches=batches,
        warnings=warnings,
        today=TODAY,
    )
    for b_dict in result["batches"]:
        assert "customers" in b_dict, f"Parti {b_dict['batch_id']} 'customers' alani eksik"
    # Karisik partide her iki musteri de listede olmali
    mixed = [b for b in result["batches"] if b["customer"] == "MIXED"]
    assert len(mixed) >= 1
    assert "Ford" in mixed[0]["customers"]
    assert "Baykar" in mixed[0]["customers"]
