"""Cizelgeleme ozet raporu (PLAN_DEMO1.md 8.5).

Tasarim ilkeleri
-----------------
- Giris: siralı siparis listesi + parti plani + termin uyarilari.
- Cikis: ozet dict + markdown string.
- Deterministik: ayni giris => her zaman ayni markdown.
- today parametresi rapor tarihini belirler (deterministik test icin).
- Nesting3d/pricing'e import bagimlilik YOKTUR.
- Bu modul SADECE rapor uretir; hesap yapmaz — hesaplar
  rules/batcher/feasibility katmanlarinda yapilir.

Rapor yapisi (dict)
-------------------
{
  "generated_at": "YYYY-MM-DD",
  "ranked_orders": [{"order_id": ..., "customer": ..., "deadline": ..., ...}],
  "batches": [{"batch_id": ..., "customer": ..., "orders": [...], "total_volume_cm3": ...}],
  "warnings": [{"order_id": ..., "deadline": ..., "estimated_completion": ..., "delay_days": ..., "batch_id": ...}],
  "markdown": "<tam markdown metni>",
}
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from src.scheduling.batcher import Batch
from src.scheduling.feasibility import DeadlineWarning
from src.scheduling.models import Order


# ---------------------------------------------------------------------------
# Ana rapor fonksiyonu
# ---------------------------------------------------------------------------


def build_report(
    ranked_orders: List[Order],
    batches: List[Batch],
    warnings: List[DeadlineWarning],
    today: date,
) -> Dict[str, Any]:
    """Oncelik sirasi + parti plani + termin uyarilari => ozet dict + markdown.

    Parametreler
    ------------
    ranked_orders : oncelik sirasina konulmus siparis listesi
    batches       : parti plani (build_batches ciktisi)
    warnings      : termin asim uyarilari (check_feasibility ciktisi)
    today         : rapor tarihi (deterministik test icin parametrik)

    Donus
    -----
    dict — "markdown" alani dahil tam ozet.
    """
    orders_data = [_order_to_dict(o) for o in ranked_orders]
    batches_data = [_batch_to_dict(b) for b in batches]
    warnings_data = [_warning_to_dict(w) for w in warnings]
    capacity_warnings_data = [
        _capacity_warning_to_dict(b) for b in batches if b.oversized
    ]
    markdown = _build_markdown(ranked_orders, batches, warnings, today)

    return {
        "generated_at": today.isoformat(),
        "ranked_orders": orders_data,
        "batches": batches_data,
        "warnings": warnings_data,
        "capacity_warnings": capacity_warnings_data,
        "markdown": markdown,
    }


# ---------------------------------------------------------------------------
# Markdown olusturucu
# ---------------------------------------------------------------------------


def _build_markdown(
    ranked_orders: List[Order],
    batches: List[Batch],
    warnings: List[DeadlineWarning],
    today: date,
) -> str:
    lines: List[str] = []

    lines.append(f"# Cizelgeleme Raporu — {today.isoformat()}")
    lines.append("")

    # --- Oncelik Sirasi ---
    lines.append("## Oncelik Sirasi")
    lines.append("")
    lines.append("| # | Siparis | Musteri | Termin | Oncelik |")
    lines.append("|---|---------|---------|--------|---------|")
    for i, o in enumerate(ranked_orders, 1):
        lines.append(
            f"| {i} | {o.order_id} | {o.customer} | {o.deadline} | {o.priority_class} |"
        )
    lines.append("")

    # --- Parti Plani ---
    lines.append("## Parti Plani")
    lines.append("")
    if batches:
        lines.append("| Parti | Musteri | Siparis | Hacim (cm3) |")
        lines.append("|-------|---------|---------|-------------|")
        for b in batches:
            order_ids = ", ".join(o.order_id for o in b.orders)
            lines.append(
                f"| {b.batch_id} | {b.customer} | {order_ids} | {b.total_volume_cm3:.0f} |"
            )
    else:
        lines.append("_Parti bulunamadi._")
    lines.append("")

    # --- Termin Uyarilari ---
    lines.append("## Termin Uyarilari")
    lines.append("")
    if warnings:
        lines.append("| Siparis | Termin | Tahmini Bitis | Gecikme (gun) | Parti |")
        lines.append("|---------|--------|---------------|---------------|-------|")
        for w in warnings:
            lines.append(
                f"| {w.order_id} | {w.deadline} | {w.estimated_completion} "
                f"| {w.delay_days} | {w.batch_id} |"
            )
    else:
        lines.append("_Termin asimi uyarisi yok._")
    lines.append("")

    # --- Kapasite Uyarilari ---
    oversized_batches = [b for b in batches if b.oversized]
    lines.append("## Kapasite Uyarilari")
    lines.append("")
    if oversized_batches:
        lines.append("| Parti | Siparis | Hacim (cm3) | Musteriler |")
        lines.append("|-------|---------|-------------|------------|")
        for b in oversized_batches:
            order_id = b.orders[0].order_id if b.orders else "-"
            customers_str = ", ".join(b.customers)
            lines.append(
                f"| {b.batch_id} | {order_id} | {b.total_volume_cm3:.0f} | {customers_str} |"
            )
    else:
        lines.append("_Kapasite asimi uyarisi yok._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Yardimci donusturucular
# ---------------------------------------------------------------------------


def _order_to_dict(o: Order) -> Dict[str, Any]:
    return {
        "order_id": o.order_id,
        "customer": o.customer,
        "parts_ref": o.parts_ref,
        "total_quantity": o.total_quantity,
        "total_volume_cm3": o.total_volume_cm3,
        "deadline": o.deadline,
        "priority_class": o.priority_class,
    }


def _batch_to_dict(b: Batch) -> Dict[str, Any]:
    return {
        "batch_id": b.batch_id,
        "customer": b.customer,
        "customers": list(b.customers),
        "orders": [o.order_id for o in b.orders],
        "total_volume_cm3": b.total_volume_cm3,
        "oversized": b.oversized,
    }


def _warning_to_dict(w: DeadlineWarning) -> Dict[str, Any]:
    return {
        "order_id": w.order_id,
        "deadline": w.deadline,
        "estimated_completion": w.estimated_completion,
        "delay_days": w.delay_days,
        "batch_id": w.batch_id,
    }


def _capacity_warning_to_dict(b: Batch) -> Dict[str, Any]:
    """Hacim sinirini asan (oversized) parti icin kapasite uyarisi ozeti."""
    return {
        "batch_id": b.batch_id,
        "order_id": b.orders[0].order_id if b.orders else "",
        "total_volume_cm3": b.total_volume_cm3,
        "customers": list(b.customers),
    }
