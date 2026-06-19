"""tests/test_layer_cost.py — Katman-bazli maliyet modulu testleri."""

import math

import pytest

from src.pricing.layer_cost import (
    LayerCostParams,
    compute_cost,
    compute_savings,
    layer_count,
)


# ---------------------------------------------------------------------------
# layer_count: Z-height -> katman sayisi (ceil)
# ---------------------------------------------------------------------------


def test_layer_count_hocanin_ornegi_500mm_120micron():
    # 500 mm / 0.12 mm = 4166.67 -> ceil -> 4167 katman
    p = LayerCostParams(layer_thickness_mm=0.12)
    assert layer_count(500.0, p) == 4167


def test_layer_count_tam_bolunme():
    p = LayerCostParams(layer_thickness_mm=0.25)
    # 500 / 0.25 = 2000 (tam) -> 2000
    assert layer_count(500.0, p) == 2000


def test_layer_count_kismi_katman_yukari_yuvarlanir():
    p = LayerCostParams(layer_thickness_mm=0.1)
    # 10.05 / 0.1 = 100.5 -> 101
    assert layer_count(10.05, p) == 101


def test_layer_count_sifir_height_sifir_katman():
    assert layer_count(0.0, LayerCostParams()) == 0
    assert layer_count(-5.0, LayerCostParams()) == 0


# ---------------------------------------------------------------------------
# compute_cost: sure + maliyet dokumu
# ---------------------------------------------------------------------------


def test_compute_cost_500mm_default_params():
    # default: 0.12 mm, 20 sn/katman, 10 EUR/katman
    r = compute_cost(500.0)
    assert r.n_layers == 4167
    assert r.total_seconds == pytest.approx(4167 * 20)
    assert r.total_hours == pytest.approx(4167 * 20 / 3600.0)
    assert r.total_cost_eur == pytest.approx(4167 * 10)


def test_compute_cost_2000_katman_ornegi():
    # Z=500, kalinlik 0.25 -> 2000 katman -> 20000 EUR
    p = LayerCostParams(layer_thickness_mm=0.25)
    r = compute_cost(500.0, p)
    assert r.n_layers == 2000
    assert r.total_cost_eur == pytest.approx(20000.0)


def test_compute_cost_determinizm():
    a = compute_cost(317.4)
    b = compute_cost(317.4)
    assert a == b


# ---------------------------------------------------------------------------
# compute_savings: baseline -> tuned tasarrufu
# ---------------------------------------------------------------------------


def test_savings_500_to_450_default():
    # 500 -> 450 mm, 0.12 kalinlik
    # N(500)=4167, N(450)=3750 -> 417 katman tasarruf
    s = compute_savings(500.0, 450.0)
    assert s.saved_layers == 4167 - 3750
    assert s.saved_cost_eur == pytest.approx((4167 - 3750) * 10)
    assert s.saved_seconds == pytest.approx((4167 - 3750) * 20)
    assert s.saved_hours == pytest.approx((4167 - 3750) * 20 / 3600.0)
    assert s.delta_height_mm == pytest.approx(50.0)
    assert s.pct_height == pytest.approx(10.0)


def test_savings_iyilesme_yoksa_sifir():
    # tuned == baseline -> hic tasarruf yok
    s = compute_savings(300.0, 300.0)
    assert s.saved_layers == 0
    assert s.saved_cost_eur == 0.0
    assert s.saved_hours == 0.0
    assert s.pct_height == 0.0


def test_savings_kotulesme_negatife_dusmez():
    # tuned > baseline (kotulesme) -> monoton kabul: tasarruf 0'a kelepce
    s = compute_savings(300.0, 350.0)
    assert s.saved_layers == 0
    assert s.saved_cost_eur == 0.0
    assert s.delta_height_mm == 0.0


def test_savings_determinizm():
    assert compute_savings(412.3, 388.1) == compute_savings(412.3, 388.1)


# ---------------------------------------------------------------------------
# Parametre dogrulama
# ---------------------------------------------------------------------------


def test_params_sifir_kalinlik_reddedilir():
    with pytest.raises(ValueError):
        LayerCostParams(layer_thickness_mm=0.0)


def test_params_negatif_maliyet_reddedilir():
    with pytest.raises(ValueError):
        LayerCostParams(cost_per_layer_eur=-1.0)


def test_to_dict_alanlari():
    d = compute_cost(500.0).to_dict()
    assert d["n_layers"] == 4167
    assert "total_cost_eur" in d and "total_hours" in d
    sd = compute_savings(500.0, 450.0).to_dict()
    assert sd["saved_layers"] == 417 and "saved_cost_eur" in sd
