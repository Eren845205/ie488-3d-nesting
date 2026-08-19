# -*- coding: utf-8 -*-
"""test_k66_d_kafes.py — K-66-d kafes dekod saf-mantik testleri (kosusuz)."""
from __future__ import annotations

import math

from scripts.k66_d_kafes_dekod import (
    adet_parse, asan_mi, eksen_rot_bul, kafes_plani, pin_listesi)


def test_adet_parse():
    assert adet_parse("520 adet") == 520
    assert adet_parse("27adet_") == 27
    assert adet_parse("kapak") == 1


def test_asan_mi_geometrik():
    # iki buyuk boyut plakaya sigmali; 399.6 uzun cubuk 335'e sigmaz
    assert asan_mi((95.0, 10.0, 399.6), 335.0, 335.0, 2.0) is True
    # duz plaka sigar
    assert asan_mi((32.0, 90.0, 9.6), 335.0, 335.0, 2.0) is False
    # tam-sinir: 333+2=335 sigar (<=)
    assert asan_mi((10.0, 100.0, 333.0), 335.0, 335.0, 2.0) is False


def test_eksen_rot_bul_permutasyon():
    rot = eksen_rot_bul((95.0, 10.0, 399.6), (10.0, 95.0, 399.6))
    assert rot is not None
    rot2 = eksen_rot_bul((32.0, 90.0, 9.6), (32.0, 9.6, 90.0))
    assert rot2 is not None
    # imkansiz hedef -> None
    assert eksen_rot_bul((1.0, 2.0, 3.0), (5.0, 5.0, 5.0)) is None


def test_kafes_plani_dar_kenar_yonelimi():
    """Cubuk dar kenari x'e donunce satir kapasitesi buyumeli (28/satir)."""
    plan = kafes_plani((95.0, 10.0, 399.6), 54, (32.0, 90.0, 9.6), 520,
                       335.0, 335.0, 2.0)
    assert plan["uygun"] is True
    assert plan["rod"]["rows_x"] >= 20  # dar-kenar yonelimi secildi
    assert plan["rod"]["n_rows"] == math.ceil(54 / plan["rod"]["rows_x"])
    assert 0 < plan["kapasite"] <= 520
    assert plan["d_kullanim"] <= 335.0 + 2.0


def test_kafes_plani_sigmaz_durumda_uygun_degil():
    # cubuk footprint'i plakadan buyuk -> plan yok
    plan = kafes_plani((400.0, 400.0, 500.0), 5, (30.0, 30.0, 5.0), 100,
                       335.0, 335.0, 2.0)
    assert plan["uygun"] is False


def test_pin_listesi_sayim_ve_cakismasizlik():
    plan = kafes_plani((95.0, 10.0, 399.6), 54, (32.0, 90.0, 9.6), 520,
                       335.0, 335.0, 2.0)
    pins = pin_listesi(plan, "rod", 54, "kitle", None, None, 2.0)
    rods = [p for p in pins if p["ad"] == "rod"]
    kitle = [p for p in pins if p["ad"] == "kitle"]
    assert len(rods) == 54
    assert len(kitle) == plan["kapasite"]
    # rod'lar zeminde; kitle katmanlari rod yuksekligini asmaz
    assert all(p["z_mm"] == 0.0 for p in rods)
    cell_h = plan["cell"][2]
    assert all(p["z_mm"] + cell_h <= plan["rod"]["h"] + 1e-6 for p in kitle)
    # ayni (x,y,z) iki kez kullanilmamis
    konumlar = [(p["ad"], p["x_mm"], p["y_mm"], p["z_mm"]) for p in pins]
    assert len(konumlar) == len(set(konumlar))
    # plaka siniri: x + genislik <= plate (rod dar kenar w, kitle cw)
    for p in rods:
        assert p["x_mm"] + plan["rod"]["w"] <= 335.0 + 1e-6
    for p in kitle:
        assert p["x_mm"] + plan["cell"][0] <= 335.0 + 1e-6
