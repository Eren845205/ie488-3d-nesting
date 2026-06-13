"""Cizelgeleme parti kurucusu (PLAN_DEMO1.md 8.3).

Tasarim ilkeleri
-----------------
- Giris: oncelik sirasina konulmus siparis listesi + kapasite.
- Cikis: Batch listesi (parti plani).
- allow_mixing=False => her parti tek-musterili.
- allow_mixing=True  => farkli musteriler ayni partide olabilir.
- Hacim kisiti: tek bir siparisin hacmi kapasite sinirini asiyorsa
  o siparis kendi partisine girer (uyari isin feasibility katmaninda).
- Deterministik: rastgellik yok; sira her zaman ayni giriste ayni sonucu verir.
- Nesting3d/pricing'e import bagimlilik YOKTUR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.scheduling.models import Capacity, Order


# ---------------------------------------------------------------------------
# Batch dataclass
# ---------------------------------------------------------------------------


@dataclass
class Batch:
    """Tek bir uretim partisini temsil eder.

    Alanlar
    -------
    batch_id         : benzersiz parti kimlik kodu (orn. "B001")
    orders           : bu partiye dahil siparis listesi
    total_volume_cm3 : partinin toplam hacmi (cm^3)
    customer         : allow_mixing=False durumunda tek musteri adi;
                       allow_mixing=True durumunda bos string veya "MIXED"
    customers        : partideki gercek musteri listesi (sirali, tekillestirilmis)
    oversized        : True => tek siparisli parti hacim sinirini asti
                       (fiziksel olarak tek seferde islenemez; operator uyarisi gerekir)
    """

    batch_id: str
    orders: List[Order]
    total_volume_cm3: float
    customer: str = ""
    customers: List[str] = field(default_factory=list)
    oversized: bool = False


# ---------------------------------------------------------------------------
# Parti kurucusu
# ---------------------------------------------------------------------------


def build_batches(
    ordered_orders: List[Order],
    capacity: Capacity,
    allow_mixing: bool,
) -> List[Batch]:
    """Oncelik sirasindaki siparislerden kapasite partileri kurar.

    Algoritma
    ---------
    Her siparis sirayla islenir:
      - allow_mixing=False: mevcut acik partilerden ayni musteriye ait olanı
        bul; hacim siniri asılmiyorsa ekle, yoksa yeni parti ac.
      - allow_mixing=True: mevcut acik partilerden hacim sinirına sıgabileni
        bul; yoksa yeni parti ac.
    Tek siparisin hacmi siniri asıyorsa (oversized) kendi partisine girer.

    Parametreler
    ------------
    ordered_orders : oncelik sirasina konulmus siparis listesi
    capacity       : kapasite tanimi
    allow_mixing   : True => karisik parti, False => tek-musterili

    Donus
    -----
    Batch listesi (parti plani); deterministik.
    """
    if not ordered_orders:
        return []

    max_vol = capacity.max_volume_per_batch_cm3

    batches: List[Batch] = []
    _counter = [0]

    def _new_batch(customer: str) -> Batch:
        _counter[0] += 1
        return Batch(
            batch_id=f"B{_counter[0]:03d}",
            orders=[],
            total_volume_cm3=0.0,
            customer=customer,
            customers=[customer] if customer else [],
        )

    def _fits(batch: Batch, order: Order) -> bool:
        if max_vol is None:
            return True
        return batch.total_volume_cm3 + order.total_volume_cm3 <= max_vol

    def _compatible(batch: Batch, order: Order) -> bool:
        if allow_mixing:
            return True
        return batch.customer == order.customer

    for order in ordered_orders:
        placed = False

        for batch in batches:
            if _compatible(batch, order) and _fits(batch, order):
                batch.orders.append(order)
                batch.total_volume_cm3 += order.total_volume_cm3
                if order.customer not in batch.customers:
                    batch.customers = sorted(batch.customers + [order.customer])
                if allow_mixing and len({o.customer for o in batch.orders}) > 1:
                    batch.customer = "MIXED"
                placed = True
                break

        if not placed:
            # Yeni parti ac
            new_batch = _new_batch(order.customer)
            new_batch.orders.append(order)
            new_batch.total_volume_cm3 = order.total_volume_cm3
            # Hacim siniri asiliyor mu? (oversized: tek siparis, kapasite yetersiz)
            if max_vol is not None and order.total_volume_cm3 > max_vol:
                new_batch.oversized = True
            batches.append(new_batch)

    return batches
