"""Cizelgeleme modelleri: Order + Capacity (PLAN_DEMO1.md 8.1).

Tasarim ilkeleri
-----------------
- Tum dogrulama ``validate()`` yontemine gonderilir; dataclass olusumu
  dogrulamayı TETIKLEMEZ (test kolayligi + kademeli yapim icin).
- JSON round-trip: ``to_dict()`` / ``from_dict()`` / ``to_json()`` / ``from_json()``.
- Nesting3d veya pricing modullerine hicbir import bagimlilik YOKTUR
  (gevse baglasim — parca/hacim bilgisi duz alanlar olarak Order'da tasınır).
- Zaman referansi (today) parametrik: "simdi" zamanına bagli hesap YOK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------


@dataclass
class Order:
    """Tek bir musteri siparisini temsil eder.

    Alanlar
    -------
    order_id          : benzersiz siparis kimlik kodu
    customer          : musteri adi
    parts_ref         : parca listesi referansi (serbest metin veya ID)
    total_quantity    : toplam parca adedi
    total_volume_cm3  : toplam parca hacmi (cm^3) — nesting sonucu ya da tahmin.
                        0.0 = hacim henuz bilinmiyor; skor ve parti hesabinda 0 katki saglar.
                        Negatif deger gecersizdir.
    deadline          : termin tarihi (ISO 8601 str: "YYYY-MM-DD")
    priority_class    : oncelik sinifi (1 = en yuksek oncelik)
    """

    order_id: str
    customer: str
    parts_ref: str
    total_quantity: int
    total_volume_cm3: float
    deadline: str
    priority_class: int

    # -----------------------------------------------------------------------
    # Dogrulama
    # -----------------------------------------------------------------------

    def validate(self, today: date) -> None:
        """Siparisin gecerliligi dogrular.

        Parametreler
        ------------
        today : date
            Referans tarih; gecmis-tarih kontrolu icin kullanilar.
            Deterministik test garantisi: "simdi" cagirandan gelir.

        Hatalar
        -------
        ValueError
            Gecersiz alan bulunursa.
        """
        if not self.order_id:
            raise ValueError("order_id bos olamaz")
        if self.total_quantity <= 0:
            raise ValueError(
                f"total_quantity pozitif olmali; alinan: {self.total_quantity}"
            )
        if self.total_volume_cm3 < 0:
            raise ValueError(
                f"total_volume_cm3 negatif olamaz; alinan: {self.total_volume_cm3}"
            )
        if self.priority_class <= 0:
            raise ValueError(
                f"priority_class pozitif olmali; alinan: {self.priority_class}"
            )
        deadline_date = _parse_date(self.deadline)
        if deadline_date < today:
            raise ValueError(
                f"deadline gecmis tarih olamaz; alinan: {self.deadline}, bugun: {today}"
            )

    # -----------------------------------------------------------------------
    # JSON round-trip
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "customer": self.customer,
            "parts_ref": self.parts_ref,
            "total_quantity": self.total_quantity,
            "total_volume_cm3": self.total_volume_cm3,
            "deadline": self.deadline,
            "priority_class": self.priority_class,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Order":
        return cls(
            order_id=d["order_id"],
            customer=d["customer"],
            parts_ref=d["parts_ref"],
            total_quantity=int(d["total_quantity"]),
            total_volume_cm3=float(d["total_volume_cm3"]),
            deadline=d["deadline"],
            priority_class=int(d["priority_class"]),
        )

    @classmethod
    def from_json(cls, text: str) -> "Order":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


@dataclass
class Capacity:
    """Uretim kapasitesi tanimi.

    Alanlar
    -------
    num_machines             : kullanilabilir makine/kaynak sayisi
    batch_duration_hours     : tek bir parti suresi (saat)
    shifts_per_day           : gunluk vardiya sayisi
    max_volume_per_batch_cm3 : tek partide islenen maksimum hacim (cm^3)

    Not: ``max_volume_per_batch_cm3`` batcher tarafindan kullanilir;
    None birakilirsa sinir yoktur (acik kapasite).

    hours_per_shift : vardiya basina calisma suresi (saat); varsayilan 8.0.
        ``batch_days()`` ve fizibilite hesabinda kullanilir.
    """

    num_machines: int
    batch_duration_hours: float
    shifts_per_day: int
    max_volume_per_batch_cm3: Optional[float] = None
    hours_per_shift: float = 8.0

    # -----------------------------------------------------------------------
    # Dogrulama
    # -----------------------------------------------------------------------

    def validate(self) -> None:
        """Kapasite degerlerinin gecerliligi dogrular.

        Hatalar
        -------
        ValueError
            Negatif veya sifir deger bulunursa.
        """
        if self.num_machines <= 0:
            raise ValueError(
                f"num_machines pozitif olmali; alinan: {self.num_machines}"
            )
        if self.batch_duration_hours <= 0:
            raise ValueError(
                f"batch_duration_hours pozitif olmali; alinan: {self.batch_duration_hours}"
            )
        if self.shifts_per_day <= 0:
            raise ValueError(
                f"shifts_per_day pozitif olmali; alinan: {self.shifts_per_day}"
            )
        if self.max_volume_per_batch_cm3 is not None and self.max_volume_per_batch_cm3 <= 0:
            raise ValueError(
                "max_volume_per_batch_cm3 pozitif olmali; "
                f"alinan: {self.max_volume_per_batch_cm3}"
            )
        if self.hours_per_shift <= 0:
            raise ValueError(
                f"hours_per_shift pozitif olmali; alinan: {self.hours_per_shift}"
            )

    # -----------------------------------------------------------------------
    # Turetilmis hesaplar
    # -----------------------------------------------------------------------

    def daily_machine_hours(self) -> float:
        """Gunluk toplam makine-saat kapasitesi.

        Formul: num_machines * batch_duration_hours * shifts_per_day
        """
        return float(self.num_machines * self.batch_duration_hours * self.shifts_per_day)

    def batch_days(self) -> float:
        """Tek bir parti kac gune denk gelir (kesirli, tavan alinmamis).

        Formul: batch_duration_hours / (shifts_per_day * hours_per_shift)

        Ornek: batch_duration_hours=12, shifts_per_day=1, hours_per_shift=8
               => 12 / (1 * 8) = 1.5 gun (yani 2 tam gun yuvarlanacak).
        Tavan/yuvarlamaya karar vermek cagiran katmanin sorumluluğundadir.
        """
        return self.batch_duration_hours / (self.shifts_per_day * self.hours_per_shift)

    # -----------------------------------------------------------------------
    # JSON round-trip
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "num_machines": self.num_machines,
            "batch_duration_hours": self.batch_duration_hours,
            "shifts_per_day": self.shifts_per_day,
            "hours_per_shift": self.hours_per_shift,
        }
        if self.max_volume_per_batch_cm3 is not None:
            d["max_volume_per_batch_cm3"] = self.max_volume_per_batch_cm3
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Capacity":
        return cls(
            num_machines=int(d["num_machines"]),
            batch_duration_hours=float(d["batch_duration_hours"]),
            shifts_per_day=int(d["shifts_per_day"]),
            max_volume_per_batch_cm3=(
                float(d["max_volume_per_batch_cm3"])
                if "max_volume_per_batch_cm3" in d
                else None
            ),
            hours_per_shift=float(d["hours_per_shift"]) if "hours_per_shift" in d else 8.0,
        )

    @classmethod
    def from_json(cls, text: str) -> "Capacity":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> date:
    """ISO 8601 tarih dizisini date nesnesine cevirir."""
    return date.fromisoformat(date_str)
