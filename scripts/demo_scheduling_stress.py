"""demo_scheduling_stress.py — Cizelgeleme motoru zorlu senaryo kosusu.

Amac: src/scheduling iskeletinin sinirlarini gormek (PLAN_DEMO1 Faz 8 sonrasi
elle stres testi). Iki bilincli tuzak icerir:

1. KAPASITE DARBOGAZI: 1 makine, 1 parti/gun; ayni gune yigilmis terminler
   -> bazi siparisler MUTLAKA gecikir, uyari listesi dolu olmali.
2. SKOR DENGESI SONDASI: dev hacimli + uzak terminli siparis (MEGA), yarin
   terminli kucuk siparislerin onune geciyor mu? (Reviewer FINDING adayi:
   log1p(hacim) terimi slack terimini domine edebilir.)

Kullanim: python scripts/demo_scheduling_stress.py
Sure: milisaniyeler (nesting yok, saf cizelgeleme).
"""

import sys
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.scheduling.models import Capacity, Order
from src.scheduling.rules import PriorityConfig, rank_orders, score_order
from src.scheduling.batcher import build_batches
from src.scheduling.feasibility import check_feasibility
from src.scheduling.report import build_report

TODAY = date(2026, 6, 13)  # parametrik referans tarih (deterministik)


def _order(oid, customer, vol, deadline, prio, qty=10):
    return Order(
        order_id=oid, customer=customer, parts_ref=f"parts/{oid}",
        total_quantity=qty, total_volume_cm3=vol,
        deadline=deadline, priority_class=prio,
    )


ORDERS = [
    # --- ACIL kucuk siparisler (yarin / 2 gun) ---
    _order("ORD-FORD-A1", "FORD", 2000, "2026-06-14", 1),
    _order("ORD-FORD-A2", "FORD", 1500, "2026-06-14", 1),
    _order("ORD-ASEL-A1", "ASELSAN-YK", 3000, "2026-06-15", 1),
    # --- SONDA: dev hacim + uzak termin (45 gun) ---
    _order("ORD-BAYK-MEGA", "BAYKAR", 90000, "2026-07-28", 2),
    # --- Ayni gune yigilmis terminler (darbogaz tuzagi: +3 gun) ---
    _order("ORD-TAI-B1", "TAI", 12000, "2026-06-16", 2),
    _order("ORD-ROKE-B1", "ROKETSAN", 14000, "2026-06-16", 2),
    _order("ORD-ASEL-B1", "ASELSAN-YK", 16000, "2026-06-16", 2),
    # --- Orta vadeliler (5-12 gun) ---
    _order("ORD-FORD-C1", "FORD", 8000, "2026-06-18", 2),
    _order("ORD-BAYK-C1", "BAYKAR", 9000, "2026-06-20", 3),
    _order("ORD-TAI-C1", "TAI", 11000, "2026-06-22", 3),
    _order("ORD-ROKE-C1", "ROKETSAN", 7000, "2026-06-25", 3),
    _order("ORD-ASEL-C1", "ASELSAN-YK", 6000, "2026-06-25", 2),
    # --- Rahat terminliler (20-30 gun) ---
    _order("ORD-FORD-D1", "FORD", 10000, "2026-07-03", 3),
    _order("ORD-BAYK-D1", "BAYKAR", 13000, "2026-07-08", 3),
    _order("ORD-TAI-D1", "TAI", 5000, "2026-07-13", 3),
]

CAPACITY = Capacity(
    num_machines=1, batch_duration_hours=8, shifts_per_day=1,
    max_volume_per_batch_cm3=20000.0,
)


def run(config, label):
    print("=" * 72)
    print(f"KOSU: {label}  |  agirliklar: slack={config.w_slack} "
          f"priority={config.w_priority} volume={config.w_volume}")
    print("=" * 72)

    for o in ORDERS:
        o.validate(TODAY)
    CAPACITY.validate()

    ranked = rank_orders(ORDERS, config, TODAY)
    batches = build_batches(ranked, CAPACITY, allow_mixing=False)
    warnings = check_feasibility(batches, CAPACITY, TODAY)
    report = build_report(ranked, batches, warnings, TODAY)

    print(report["markdown"])

    # --- Sonda analizi ---
    rank_of = {o.order_id: i + 1 for i, o in enumerate(ranked)}
    mega = rank_of["ORD-BAYK-MEGA"]
    urgent_worst = max(rank_of["ORD-FORD-A1"], rank_of["ORD-FORD-A2"],
                       rank_of["ORD-ASEL-A1"])
    print("--- SONDA: skor dengesi ---")
    for oid in ("ORD-FORD-A1", "ORD-BAYK-MEGA"):
        o = next(x for x in ORDERS if x.order_id == oid)
        print(f"  {oid:16s} skor={score_order(o, config, TODAY):8.3f} "
              f"sira={rank_of[oid]:2d}  termin={o.deadline}  "
              f"hacim={o.total_volume_cm3:8.0f}")
    if mega < urgent_worst:
        print("  SONUC: !!! MEGA (45 gun terminli dev siparis), yarin/2-gun "
              "terminli acil siparis(ler)in ONUNE GECTI — termin onceligi "
              "ihlali (skor dengesi sorunu DOGRULANDI).")
    else:
        print("  SONUC: acil siparisler onde — termin onceligi korunuyor.")
    print(f"  Uyari sayisi: {len(warnings)}")
    print()
    return ranked, warnings


if __name__ == "__main__":
    # Kosu 1: builder'in default agirliklari
    run(PriorityConfig.default(), "DEFAULT (w=3/2/1)")

    # Kosu 2: termin-baskin alternatif (olasi duzeltme yonu)
    run(PriorityConfig(w_slack=10.0, w_priority=1.0, w_volume=0.05),
        "TERMIN-BASKIN (w=10/1/0.05)")
