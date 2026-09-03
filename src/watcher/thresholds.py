"""thresholds.py — Watcher esik sabitleri.

Statik varsayilanlar burada tutulur.
Opsiyonel data/watcher_baseline.json varsa medyan referansi oradan okunur;
yoksa statik degerler kullanilir (zarif dusus).

Esik kategorileri:
  - parse:    eksik alan orani, boyut-sigma katsayisi
  - nest:     statik doluluk tabani, medyan toleransi, yukseklik orani
  - price:    total/medyan oran sinirlari
  - priority: uyari sayisi esigi
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class WatcherThresholds:
    """Pipeline denetcisi esik degerleri.

    Parametreler
    ------------
    baseline_path : opsiyonel watcher_baseline.json dosya yolu.
                    Varsa medyan referans degerleri buradan okunur.
                    Yoksa ya da okunmazsa statik varsayilanlar kullanilir.
    """

    # --- Parse esikleri ---
    _PARSE_MISSING_FIELD_RATIO_MAX = 0.25   # %25 eksik alan -> uyari
    _PARSE_SIGMA_MULTIPLIER = 3.0           # boyut std * katsayi = esik
    _PARSE_SIGMA_MIN_PARTS = 3              # sigma icin min parca

    # --- Nest esikleri ---
    _NEST_DENSITY_STATIC_MIN = 0.25        # statik taban doluluk
    _NEST_DENSITY_TOLERANCE = 0.15         # medyan*(1-tol) esik
    _NEST_HEIGHT_RATIO_MAX = 0.95          # konteyner yuksekliginin max %'si

    # --- Price esikleri ---
    _PRICE_RATIO_MIN = 0.5                 # total < median*0.5 -> uyari
    _PRICE_RATIO_MAX = 2.0                 # total > median*2.0 -> uyari

    # --- Priority esikleri ---
    _PRIORITY_WARNING_COUNT_MAX = 3        # 3'ten fazla termin uyarisi -> uyari

    def __init__(self, baseline_path: Optional[str] = None) -> None:
        # Statik varsayilanlar
        self.parse_missing_field_ratio_max = self._PARSE_MISSING_FIELD_RATIO_MAX
        self.parse_sigma_multiplier = self._PARSE_SIGMA_MULTIPLIER
        self.parse_sigma_min_parts = self._PARSE_SIGMA_MIN_PARTS

        self.nest_density_static_min = self._NEST_DENSITY_STATIC_MIN
        self.nest_density_tolerance = self._NEST_DENSITY_TOLERANCE
        self.nest_height_ratio_max = self._NEST_HEIGHT_RATIO_MAX
        self.nest_density_baseline_median: Optional[float] = None

        self.price_ratio_min = self._PRICE_RATIO_MIN
        self.price_ratio_max = self._PRICE_RATIO_MAX

        self.priority_warning_count_max = self._PRIORITY_WARNING_COUNT_MAX

        # Baseline JSON — zarif dusus: hata -> statik kalmaya devam
        if baseline_path:
            self._load_baseline(baseline_path)
        else:
            self._try_default_baseline()

    def _try_default_baseline(self) -> None:
        """data/watcher_baseline.json varsa yukle; yoksa sessizce atla."""
        default_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "watcher_baseline.json"
        )
        if default_path.exists():
            self._load_baseline(str(default_path))

    def _load_baseline(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            median = data.get("nest_density_median")
            if isinstance(median, (int, float)) and 0.0 < median < 1.0:
                self.nest_density_baseline_median = float(median)
                logger.info(
                    "Watcher baseline yuklendi: nest_density_median=%.3f",
                    self.nest_density_baseline_median,
                )
        except Exception as exc:
            logger.warning(
                "Watcher baseline yuklenemedi (%s: %s) — statik esikler kullaniliyor.",
                path, exc,
            )

    def effective_nest_density_min(self) -> float:
        """Etkin doluluk alt siniri: baseline medyani yoksa statik taban."""
        if self.nest_density_baseline_median is not None:
            return self.nest_density_baseline_median * (1.0 - self.nest_density_tolerance)
        return self.nest_density_static_min
