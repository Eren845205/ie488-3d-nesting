"""Cizelgeleme termin fizibilite kontrolu (PLAN_DEMO1.md 8.4).

Tasarim ilkeleri
-----------------
- Giris: parti plani (Batch listesi) + kapasite.
- Cikis: termin asim uyari listesi (DeadlineWarning).
- Bitis tarihi hesabi:
    Partiler sırayla islenir (paralel makine yoktur — tek hat varsayimi).
    i. partinin bitis tarihi = today + (i * batch_gun_sayisi)
    batch_gun_sayisi = ceil(capacity.batch_days()), min 1
- Bir siparisin bitis tarihi = icinde bulundugu partinin bitis tarihi.
- deadline < bitis => uyari.
- today parametresi deterministik test icin zorunlu (simdi bagimsiz).
- Nesting3d/pricing'e import bagimlilik YOKTUR.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

from src.scheduling.models import Capacity, _parse_date
from src.scheduling.batcher import Batch


# ---------------------------------------------------------------------------
# DeadlineWarning dataclass
# ---------------------------------------------------------------------------


@dataclass
class DeadlineWarning:
    """Tek bir termin asim uyarisini temsil eder.

    Alanlar
    -------
    order_id             : geciken siparisin kimlik kodu
    deadline             : siparinin termini (ISO str)
    estimated_completion : tahmini bitis tarihi (ISO str)
    delay_days           : gecikme (gun); bitis - deadline
    batch_id             : siparinin dahil oldugu parti
    """

    order_id: str
    deadline: str
    estimated_completion: str
    delay_days: int
    batch_id: str


# ---------------------------------------------------------------------------
# Fizibilite kontrolu
# ---------------------------------------------------------------------------


def check_feasibility(
    batches: List[Batch],
    capacity: Capacity,
    today: date,
) -> List[DeadlineWarning]:
    """Parti plani + kapasite => termin asim uyari listesi.

    Her partinin tahmini bitis tarihi hesaplanir; bir siparisin termini
    bitis tarihinden onceyse uyari uretilir.

    Varsayimlar
    -----------
    - Partiler sirayla islenir (tek hat).
    - Bir partinin suresi = capacity.batch_days() gun (tavan alinir, min 1).
      capacity.batch_days() = batch_duration_hours / (shifts_per_day * hours_per_shift).
      Ornek (8 saat vardiya, 8 saat parti, 1 vardiya): ceil(8/8) = 1 gun.
    - today = partilerin baslangic gunu.

    Parametreler
    ------------
    batches  : parti plani (sirasina gore)
    capacity : kapasite tanimi
    today    : referans tarih (deterministik test icin parametrik)

    Donus
    -----
    DeadlineWarning listesi; uyari yoksa bos liste.
    """
    if not batches:
        return []

    batch_days_int = max(1, math.ceil(capacity.batch_days()))

    warnings: List[DeadlineWarning] = []
    current_day = 0

    for batch in batches:
        current_day += batch_days_int
        completion_date = today + timedelta(days=current_day)

        for order in batch.orders:
            deadline_date = _parse_date(order.deadline)
            if completion_date > deadline_date:
                delay = (completion_date - deadline_date).days
                warnings.append(
                    DeadlineWarning(
                        order_id=order.order_id,
                        deadline=order.deadline,
                        estimated_completion=completion_date.isoformat(),
                        delay_days=delay,
                        batch_id=batch.batch_id,
                    )
                )

    return warnings
