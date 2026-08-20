# -*- coding: utf-8 -*-
"""test_plaka_bolme.py — U1 v1a LB hakemi + bolme onerisi saf-mantik testleri."""
from __future__ import annotations

import pytest

from src.scheduling.plaka_bolme import (
    BolmeKarari, ParcaOzeti, asan_mi, bbox_hucre_tahmin_mm, bolme_karari,
    gercek_hacim_lb_mm, parca_atama, rapor_alani)

PLATE = 335.0
CLEAR = 2.0


def _p(ad="a", qty=1, w=100.0, d=100.0, h=10.0, gv=None):
    return ParcaOzeti(ad=ad, qty=qty, w_mm=w, d_mm=d, h_mm=h,
                      gercek_hacim_mm3=gv)


def test_gercek_hacim_lb_temel():
    # 335x335 plakada tam-plaka-tabanli 10mm'lik katman = LB 10mm
    p = _p(qty=1, w=PLATE, d=PLATE, h=10.0, gv=PLATE * PLATE * 10.0)
    assert gercek_hacim_lb_mm([p], PLATE, PLATE) == pytest.approx(10.0)


def test_bbox_tahmin_clearance_katar():
    p = _p(qty=1, w=100.0, d=100.0, h=10.0)
    t = bbox_hucre_tahmin_mm([p], PLATE, PLATE, CLEAR)
    assert t == pytest.approx(102 * 102 * 12 / (PLATE * PLATE))


def test_asan_mi():
    assert asan_mi(_p(w=95, d=10, h=399.6), PLATE, PLATE, CLEAR) is True
    assert asan_mi(_p(w=32, d=90, h=9.6), PLATE, PLATE, CLEAR) is False


def test_bolme_zorunlu_yalniz_kesin_lb_asiminda():
    # gercek hacim 700mm'lik katmana esdeger -> 600 plakaya SIGMAZ, zorunlu
    hacim = PLATE * PLATE * 700.0
    p = _p(qty=1, w=300, d=300, h=650, gv=hacim)
    k = bolme_karari([p], PLATE, PLATE, 600.0, CLEAR)
    assert k.bolme_zorunlu is True
    assert k.oneri_n >= 2


def test_zorunlu_icin_tum_hacimler_bilinmeli():
    # gercek hacmi BILINMEYEN parca varken zorunlu hukmu VERILMEZ
    # (bbox hacmi LB'yi sisirir — kesin vasfi bozulur)
    p = _p(qty=1, w=330, d=330, h=700, gv=None)  # bbox 700-katman ustu
    k = bolme_karari([p], PLATE, PLATE, 600.0, CLEAR)
    assert k.bolme_zorunlu is False


def test_lb_sigarken_erken_bolme_yok():
    # fsm610-sinifi ornek: gercek hacim ~140mm katman -> tek plaka beklenir
    p = _p(qty=520, w=32, d=90, h=9.6, gv=32 * 90 * 9.6 * 0.79)
    k = bolme_karari([p], PLATE, PLATE, 600.0, CLEAR)
    assert k.bolme_zorunlu is False
    assert k.oneri_n == 1


def test_plaka_yuksekligi_bilinmiyorsa_kapi_devre_disi():
    k = bolme_karari([_p()], PLATE, PLATE, None, CLEAR)
    assert k.bolme_zorunlu is False and k.oneri_n == 1
    assert "devre disi" in k.not_


def test_atama_asanlar_ilk_plakada():
    parcalar = [_p("cubuk", 5, 95, 10, 399.6),
                _p("plaka", 100, 32, 90, 9.6),
                _p("braket", 30, 76, 79, 48)]
    atama = parca_atama(parcalar, 3, PLATE, PLATE, CLEAR)
    assert "cubuk" in atama[0]
    # tum modeller tam bir plakada (butunluk korunur)
    hepsi = [ad for pl in atama for ad in pl]
    assert sorted(hepsi) == sorted(["cubuk", "plaka", "braket"])


def test_rapor_alani_asim_yorumu_algoritma_sucu():
    # LB sigar diyor ama sonuc asmis -> "algoritma/mod" yorumu (Eren mimarisi)
    k = BolmeKarari(lb_kesin_mm=140.0, lb_tahmin_mm=300.0, plaka_h_mm=600.0,
                    bolme_zorunlu=False, oneri_n=1, atama=[["x"]], not_="")
    r = rapor_alani(k, 691.2)
    assert r["asim_mm"] == pytest.approx(91.2)
    assert "ALGORITMA" in r["asim_yorumu"].upper()


def test_rapor_alani_asim_yoksa_alan_yok():
    k = BolmeKarari(140.0, 300.0, 600.0, False, 1, [["x"]], "")
    r = rapor_alani(k, 458.4)
    assert "asim_mm" not in r
