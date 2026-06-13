"""Cizelgeleme onceliklendirme kurallari (PLAN_DEMO1.md 8.2).

Tasarim ilkeleri
-----------------
- Hicbir oncelik kurali/agirlik koda gomulmez — konfigürasyon (JSON/dict).
- Varsayilan kural: EDD (Earliest Due Date) — termin yakinligi baskın.
- Agirlikli skor formulu:
    score = w_slack * slack_score + w_priority * priority_score + w_volume * volume_score

  Bilesenler (tumu [0, 1] bandinda normalize):
    slack_score    : yüksek = yakin termin  — 1 / (slack_days + 1)          ∈ (0, 1]
    priority_score : yüksek = kucuk class   — 1 / priority_class             ∈ (0, 1]
    volume_score   : yüksek = buyuk hacim   — log1p(vol) / log1p(ref_volume) ∈ [0, 1]
                    (vol >= ref_volume ise 1.0 ile sinirlanir)

- Esitlik kirici: order_id alfabetik sirasi (deterministik).
- today parametresi her cagiriye gecilir — "simdi" zamanina bagli hesap YOK.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List

from src.scheduling.models import Order, _parse_date


# ---------------------------------------------------------------------------
# PriorityConfig
# ---------------------------------------------------------------------------


@dataclass
class PriorityConfig:
    """Agirlikli oncelik skoru icin konfigürasyon.

    Alanlar
    -------
    w_slack    : termin yakinligı (slack) agirligı
    w_priority : musteri oncelik sinifi agirligı
    w_volume   : is buyüklügü (hacim) agirligı
    ref_volume : hacim normalizasyonu icin referans deger (cm^3).
                 volume_score = log1p(vol) / log1p(ref_volume); 1.0 ile sinirlanir.

    JSON ornegi::

        {"w_slack": 3.0, "w_priority": 2.0, "w_volume": 1.0, "ref_volume": 1000000.0}

    Geriye uyumluluk: JSON'da "ref_volume" yoksa varsayilan (1_000_000.0) kullanilir.
    """

    w_slack: float
    w_priority: float
    w_volume: float
    ref_volume: float = 1_000_000.0

    # -----------------------------------------------------------------------
    # Dogrulama
    # -----------------------------------------------------------------------

    def validate(self) -> None:
        """Konfigürasyon degerlerinin gecerliligi dogrular.

        Kurallar
        --------
        - Tum agirliklar >= 0 olmali.
        - En az bir agirlik > 0 olmali.
        - ref_volume > 0 olmali.

        EDD garantisi notu: EDD baskinligi icin
        w_slack >= w_priority + w_volume tavsiye edilir.
        Bu kural zorunlu tutulmaz (musteri konfigürasyon ozgurlugu);
        default() bu orani saglar.

        Hatalar
        -------
        ValueError
            Gecersiz deger bulunursa.
        """
        if self.w_slack < 0 or self.w_priority < 0 or self.w_volume < 0:
            raise ValueError(
                f"Tum agirliklar >= 0 olmali; alinan: w_slack={self.w_slack}, "
                f"w_priority={self.w_priority}, w_volume={self.w_volume}"
            )
        if self.w_slack == 0 and self.w_priority == 0 and self.w_volume == 0:
            raise ValueError("En az bir agirlik > 0 olmali")
        if self.ref_volume <= 0:
            raise ValueError(
                f"ref_volume > 0 olmali; alinan: {self.ref_volume}"
            )

    @classmethod
    def default(cls) -> "PriorityConfig":
        """EDD (Earliest Due Date) agirlikli varsayilan konfigürasyon.

        Agirliklar: w_slack=3.0, w_priority=2.0, w_volume=1.0
        Tum bilesenler [0,1] bandinda normalize edildiginden agirlik
        oranlari skor uzerinde dogrudan orantilidir.

        EDD garantisi: w_slack (3) >= w_priority + w_volume (2+1=3) esitligini
        saglar — bu esik degerde hacim farkina karin yakin terminli siparis
        her zaman kazanir. Daha guclu EDD garantisi icin w_slack > 3 kullanin.

        ref_volume=1_000_000 cm^3: tipik buyuk siparis hacim tavan referansi.
        """
        return cls(w_slack=3.0, w_priority=2.0, w_volume=1.0, ref_volume=1_000_000.0)

    # -----------------------------------------------------------------------
    # JSON round-trip
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "w_slack": self.w_slack,
            "w_priority": self.w_priority,
            "w_volume": self.w_volume,
            "ref_volume": self.ref_volume,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PriorityConfig":
        cfg = cls(
            w_slack=float(d["w_slack"]),
            w_priority=float(d["w_priority"]),
            w_volume=float(d["w_volume"]),
            ref_volume=float(d.get("ref_volume", 1_000_000.0)),
        )
        cfg.validate()
        return cfg

    @classmethod
    def from_json(cls, text: str) -> "PriorityConfig":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Skor hesabi
# ---------------------------------------------------------------------------


def score_order(order: Order, config: PriorityConfig, today: date) -> float:
    """Tek siparis icin agirlikli oncelik skoru hesaplar.

    Yuksek skor = once islenmeli.

    Parametreler
    ------------
    order  : siparis
    config : agirlik konfigürasyonu
    today  : referans tarih (deterministik test icin parametrik)

    Donus
    -----
    float — oncelik skoru (yuksek = once)

    Bilesenler (tumu [0, 1] bandinda):
        slack_score    = 1 / (slack_days + 1)
        priority_score = 1 / priority_class
        volume_score   = min(1.0, log1p(vol) / log1p(ref_volume))
    """
    deadline_date = _parse_date(order.deadline)
    slack_days = max(0, (deadline_date - today).days)
    slack_score = 1.0 / (slack_days + 1.0)

    priority_score = 1.0 / float(order.priority_class)

    volume_score = min(
        1.0,
        math.log1p(order.total_volume_cm3) / math.log1p(config.ref_volume),
    )

    return (
        config.w_slack * slack_score
        + config.w_priority * priority_score
        + config.w_volume * volume_score
    )


# ---------------------------------------------------------------------------
# Siralama
# ---------------------------------------------------------------------------


def rank_orders(
    orders: List[Order],
    config: PriorityConfig,
    today: date,
) -> List[Order]:
    """Siparis listesini oncelik skoruna gore siralar.

    Esitlik kirici: order_id alfabetik sirasi (deterministik).

    Parametreler
    ------------
    orders : siparis listesi
    config : agirlik konfigürasyonu
    today  : referans tarih

    Donus
    -----
    Yeni siralanmis liste (orijinal liste degismez).
    """
    if not orders:
        return []

    def sort_key(o: Order):
        s = score_order(o, config, today)
        return (-s, o.order_id)

    return sorted(orders, key=sort_key)
