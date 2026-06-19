"""pricing/layer_cost.py — Katman-bazli maliyet modulu (Eklemeli Uretim / AM).

Mantik (hocanin gorusmede anlattigi standart AM makine-zamani hesabi):

    katman sayisi   N  =  ceil(Z-height / katman kalinligi)
    toplam sure        =  N x katman basina sure
    toplam maliyet     =  N x katman basina maliyet

Maliyet, parcanin hacmiyle DEGIL build yonundeki Z-yuksekligiyle (katman
sayisiyla) orantilidir: makine her katmani tek tek serer + tarar (recoat +
scan). Z ne kadar kisaysa o kadar az katman -> o kadar az sure -> o kadar az
euro. Bu yuzden nesting'in Z-height'i dusurmesi DOGRUDAN euro/saat tasarrufuna
cevrilebilir.

DEGISMEZ: motor modullerini (bin3d/sa3d/voxelize) import ETMEZ. Saf hesap.
Determinizm: ayni (height, params) -> ayni sonuc.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Parametreler (makineye gore degisir; default'lar hocanin ornegi)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerCostParams:
    """Katman-bazli maliyet parametreleri.

    Fields
    ------
    layer_thickness_mm : Katman kalinligi (mm). Default 0.12 mm = 120 mikron.
    seconds_per_layer  : Katman basina makine suresi (sn). Default 20 sn.
    cost_per_layer_eur : Katman basina maliyet (EUR). Default 10 EUR.
    """

    layer_thickness_mm: float = 0.12
    seconds_per_layer: float = 20.0
    cost_per_layer_eur: float = 10.0

    def __post_init__(self) -> None:
        if self.layer_thickness_mm <= 0:
            raise ValueError(
                f"layer_thickness_mm > 0 olmali (gelen: {self.layer_thickness_mm})"
            )
        if self.seconds_per_layer < 0:
            raise ValueError(
                f"seconds_per_layer >= 0 olmali (gelen: {self.seconds_per_layer})"
            )
        if self.cost_per_layer_eur < 0:
            raise ValueError(
                f"cost_per_layer_eur >= 0 olmali (gelen: {self.cost_per_layer_eur})"
            )


# ---------------------------------------------------------------------------
# Tekil build maliyeti
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerCostResult:
    """Tek bir build'in katman-bazli maliyet dokumu."""

    height_mm: float
    layer_thickness_mm: float
    n_layers: int
    total_seconds: float
    total_hours: float
    total_cost_eur: float

    def to_dict(self) -> dict:
        return {
            "height_mm": round(self.height_mm, 3),
            "layer_thickness_mm": self.layer_thickness_mm,
            "n_layers": self.n_layers,
            "total_seconds": round(self.total_seconds, 1),
            "total_hours": round(self.total_hours, 3),
            "total_cost_eur": round(self.total_cost_eur, 2),
        }


def layer_count(height_mm: float, params: LayerCostParams) -> int:
    """Z-height'i katman sayisina cevir: ceil(height / kalinlik).

    Yukari yuvarlama: kismi katman da tam bir kaplama+tarama turu gerektirir.
    height_mm <= 0 ise 0 katman.
    """
    if height_mm <= 0:
        return 0
    return math.ceil(height_mm / params.layer_thickness_mm)


def compute_cost(
    height_mm: float, params: LayerCostParams | None = None
) -> LayerCostResult:
    """Verilen Z-height icin katman sayisi, sure ve maliyet dokumu uret."""
    p = params if params is not None else LayerCostParams()
    n = layer_count(height_mm, p)
    total_seconds = n * p.seconds_per_layer
    return LayerCostResult(
        height_mm=float(height_mm),
        layer_thickness_mm=p.layer_thickness_mm,
        n_layers=n,
        total_seconds=total_seconds,
        total_hours=total_seconds / 3600.0,
        total_cost_eur=n * p.cost_per_layer_eur,
    )


# ---------------------------------------------------------------------------
# Tasarruf (baseline -> iyilestirilmis Z-height)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerSavings:
    """Baseline'dan iyilestirilmis Z-height'e gecisin getirisi.

    Tum 'saved_*' degerleri >= 0 (iyilestirme negatifse 0'a kelepcelenir;
    monoton kabul garantisi geregi tuned <= baseline beklenir).
    """

    baseline_height_mm: float
    tuned_height_mm: float
    delta_height_mm: float
    saved_layers: int
    saved_seconds: float
    saved_hours: float
    saved_cost_eur: float
    pct_height: float  # Z-height yuzde dususu (0..100)

    def to_dict(self) -> dict:
        return {
            "baseline_height_mm": round(self.baseline_height_mm, 3),
            "tuned_height_mm": round(self.tuned_height_mm, 3),
            "delta_height_mm": round(self.delta_height_mm, 3),
            "saved_layers": self.saved_layers,
            "saved_seconds": round(self.saved_seconds, 1),
            "saved_hours": round(self.saved_hours, 3),
            "saved_cost_eur": round(self.saved_cost_eur, 2),
            "pct_height": round(self.pct_height, 2),
        }


def compute_savings(
    baseline_height_mm: float,
    tuned_height_mm: float,
    params: LayerCostParams | None = None,
) -> LayerSavings:
    """Baseline ve iyilestirilmis Z-height arasindaki euro/saat tasarrufu.

    Tasarruf, GERCEK katman farki uzerinden hesaplanir:
        saved_layers = N(baseline) - N(tuned)
    (her ikisi de ceil; boylece kismi-katman tutarsizligi olmaz.)

    tuned >= baseline ise (iyilestirme yok / kotulesme) tum tasarruflar 0.
    """
    p = params if params is not None else LayerCostParams()
    n_base = layer_count(baseline_height_mm, p)
    n_tuned = layer_count(tuned_height_mm, p)

    saved_layers = max(0, n_base - n_tuned)
    delta_height = max(0.0, baseline_height_mm - tuned_height_mm)
    saved_seconds = saved_layers * p.seconds_per_layer
    pct = (delta_height / baseline_height_mm * 100.0) if baseline_height_mm > 0 else 0.0

    return LayerSavings(
        baseline_height_mm=float(baseline_height_mm),
        tuned_height_mm=float(tuned_height_mm),
        delta_height_mm=delta_height,
        saved_layers=saved_layers,
        saved_seconds=saved_seconds,
        saved_hours=saved_seconds / 3600.0,
        saved_cost_eur=saved_layers * p.cost_per_layer_eur,
        pct_height=pct,
    )
