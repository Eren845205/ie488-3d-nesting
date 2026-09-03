# -*- coding: utf-8 -*-
"""tests/test_constraint_compiler.py — sembolik kisit -> motor parametresi.

Degismezler (K-56g Faz 3):
  - Yon->poz tablosu 28-poz master setten GEOMETRIK turetilir; bbox ile
    fiziksel dogrulanir (dik pozlar yuksekligi korur, yatay pozlar yatirir).
  - Ad eslemesi toleransli ama tek-aday sart; eslesmeyen kisit uygulanmaz.
  - Aktif poz setiyle bos kesisim = derleme hatasi (sessiz genisletme yok).
  - pinned_* DAIMA golge (hoca semantigi bekliyor); plaka-disi koordinat
    ayrica isaretlenir.
"""
from __future__ import annotations

import pytest

from src.runtime.constraint_compiler import (
    compile_constraints,
    yon_poz_tablosu,
)


def _k(tip="orientation_lock", ad="braket", deger=None, guven="yuksek"):
    return {"tip": tip, "parca_adi": ad,
            "deger": {"yon": "dik"} if deger is None else deger,
            "guven": guven, "gerekce": "test", "kaynak_satir": "test satiri"}


# ---------------------------------------------------------------------------
# Yon -> poz tablosu (geometrik dogrulama)
# ---------------------------------------------------------------------------


def test_yon_tablosu_matris_semantigi():
    t = yon_poz_tablosu()
    # dik: kimlik + Rz donusleri (kendi +Z'si yukari); ters pozlar HARIC
    assert t["dik"] == (0, 1, 4, 5)
    # yatay: tum yan/yuz pozlari; egik 8..11 hicbir kumede degil
    assert set(t["yatay"]) == {2, 3, 12, 13, 16, 17, 18, 19,
                               20, 21, 22, 23, 24, 25, 26, 27}
    assert not (set(t["dik"]) | set(t["yatay"])) & {8, 9, 10, 11}


def test_yon_tablosu_bbox_fiziksel_dogrulama():
    # 10x10x40 uzun kutu: dik pozlarda z-boyu 40 kalir, yatay pozlarda 10 olur
    trimesh = pytest.importorskip("trimesh")
    import numpy as np
    from src.nesting3d.voxelize import N_MASTER_POSES, rotation_matrices

    mats = rotation_matrices(N_MASTER_POSES)
    t = yon_poz_tablosu()
    for i in t["dik"]:
        m = trimesh.creation.box(extents=(10, 10, 40))
        m.apply_transform(mats[i])
        z = m.bounds[1][2] - m.bounds[0][2]
        assert np.isclose(z, 40.0), f"dik poz {i} yuksekligi korumali"
    for i in t["yatay"]:
        m = trimesh.creation.box(extents=(10, 10, 40))
        m.apply_transform(mats[i])
        z = m.bounds[1][2] - m.bounds[0][2]
        assert np.isclose(z, 10.0), f"yatay poz {i} parcayi yatirmali"


# ---------------------------------------------------------------------------
# compile_constraints
# ---------------------------------------------------------------------------


def test_dik_kilidi_derlenir():
    r = compile_constraints([_k()], ["braket", "kapak"])
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [0, 1, 4, 5]
    assert r.operator_isaretleri == []
    assert r.durumlar[0]["durum"] == "derlendi"


def test_ad_eslesme_toleransli():
    # buyuk harf + TR karakter + altcizgi toleransi (parser _norm_name)
    r = compile_constraints([_k(ad="BRAKET_SOL")], ["braket sol", "kapak"])
    assert "braket sol" in r.motor_kisitlari["orientation_overrides"]


def test_ad_eslenemezse_uygulanmaz():
    r = compile_constraints([_k(ad="olmayan_parca")], ["braket"])
    assert r.motor_kisitlari == {}
    assert len(r.uygulanmayan) == 1
    assert "eslenemedi" in r.uygulanmayan[0]["sebep"]
    assert r.operator_isaretleri


def test_dar_poz_setinde_yatay_bos_kesisim():
    # Ilk 2 poz (dik 0/90) yatay icermez -> yatay kilidi n=2 setiyle kesismez
    r = compile_constraints([_k(deger={"yon": "yatay"})], ["braket"],
                            n_orientations=2)
    assert r.motor_kisitlari == {}
    assert "kesismiyor" in r.uygulanmayan[0]["sebep"]


def test_n4_setinde_yatay_yan_pozlara_derlenir():
    # n=4 kesitinde yatay = yan pozlar {2,3} (master set sirasi: dik,dik,yan,yan)
    r = compile_constraints([_k(deger={"yon": "yatay"})], ["braket"],
                            n_orientations=4)
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [2, 3]


def test_dar_poz_setinde_dik_calisir():
    r = compile_constraints([_k()], ["braket"], n_orientations=4)
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [0, 1]


def test_celisen_yon_kilitleri():
    r = compile_constraints(
        [_k(), _k(deger={"yon": "yatay"})], ["braket"])
    # ilk kilit derlenir; ikincisi ayni parcada bos kesisim -> dusurulur
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [0, 1, 4, 5]
    assert any("celisen" in d["sebep"] for d in r.uygulanmayan)


def test_gecersiz_yon_degeri():
    r = compile_constraints([_k(deger={"yon": "capraz"})], ["braket"])
    assert r.motor_kisitlari == {}
    assert "gecersiz yon" in r.uygulanmayan[0]["sebep"]


def test_belirsiz_tip_uygulanmaz():
    r = compile_constraints([_k(tip="belirsiz", deger=None)], ["braket"])
    assert r.motor_kisitlari == {}
    assert "belirsiz" in r.uygulanmayan[0]["sebep"]


def test_durus_koru_dik_kumesine_derlenir():
    # Hoca S2 (2026-07-22): "konumu degismeyecek" = durus kilidi; durus_koru
    # kumesi = R.ez=+ez pozlari (dik ile ayni indeksler, Rz serbest).
    r = compile_constraints([_k(deger={"yon": "durus_koru"})], ["braket"])
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [0, 1, 4, 5]
    assert r.durumlar[0]["durum"] == "derlendi"


def test_pinned_orientation_artik_derlenir():
    # Hoca S2 teyidi sonrasi pinned_orientation golgeden cikti: durus_koru
    # kumesine derlenir (z/x-y serbest — orientation_overrides yeterli).
    r = compile_constraints(
        [_k(tip="pinned_orientation", deger={"referans": "onceki_yerlesim"})],
        ["braket"])
    assert r.motor_kisitlari["orientation_overrides"]["braket"] == [0, 1, 4, 5]
    assert r.operator_isaretleri == []


def test_pinned_position_golgede_kalir():
    r = compile_constraints(
        [_k(tip="pinned_position", deger={"referans": "onceki_yerlesim"})],
        ["braket"])
    assert r.motor_kisitlari == {}
    assert "golge" in r.uygulanmayan[0]["sebep"]


def test_pinned_plaka_disi_koordinat_isareti():
    r = compile_constraints(
        [_k(tip="pinned_position", deger={"x_mm": 900.0, "y_mm": 10.0})],
        ["braket"], plate_w_mm=325.0, plate_d_mm=325.0)
    assert r.motor_kisitlari == {}
    assert "plaka disi" in r.uygulanmayan[0]["sebep"]


def test_pinned_gecerli_koordinat_yine_golge():
    r = compile_constraints(
        [_k(tip="pinned_position", deger={"x_mm": 10.0, "y_mm": 10.0})],
        ["braket"], plate_w_mm=325.0, plate_d_mm=325.0)
    assert r.motor_kisitlari == {}
    assert "golge" in r.uygulanmayan[0]["sebep"]
