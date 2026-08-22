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


def test_eksen_rot_bul_en_iyi_eslesme():
    """Neredeyse-kare kesit (seed2 dersi): fark < tol iken ILK-eslesme
    identity'yi alip x/y'yi takas ediyordu; EN-IYI eslesme tam permutasyonu
    secmeli (max hata ~0, takasli ~0.31 degil)."""
    import numpy as np
    rot = eksen_rot_bul((15.28, 14.97, 359.01), (14.97, 15.28, 359.01))
    assert rot is not None
    r = np.abs(np.asarray(rot)[:3, :3]) @ np.asarray((15.28, 14.97, 359.01))
    assert np.max(np.abs(r - np.asarray((14.97, 15.28, 359.01)))) < 1e-6, \
        f"takasli poz secildi: {r}"


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
    pins = pin_listesi(plan, [("rod", None)] * 54, "kitle", None, 2.0)
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


def test_kafes_plani_v2_yukseklik_tahmini_secimi():
    """K-66-d v2 (fsm dersi 400<458): skor_v2 kapasite yerine h_pred'e
    bakar — fsm sayilarinda v1 dik/324 secerken v2 yatik-ince duz/297
    secmeli (olu-bant 31,6 vs 3,6 ayirt edici); default v1 BIT-OZDES."""
    rod = (95.0, 10.0, 399.6)
    kitle = (32.0, 90.0, 9.6)
    v1 = kafes_plani(rod, 54, kitle, 520, 335.0, 335.0, 2.0, pitch=2.0)
    assert v1["oryantasyon"] == "dik" and v1["kapasite"] == 324
    assert "h_pred" in v1                      # bilgi alani v1'de de var
    v2 = kafes_plani(rod, 54, kitle, 520, 335.0, 335.0, 2.0, pitch=2.0,
                     skor_v2=True)
    assert v2["oryantasyon"] == "duz" and v2["kapasite"] == 297
    assert v2["h_pred"] < v1["h_pred"]


def test_kafes_plani_v2_durus_koru_korunur():
    ozel = [((32.0, 90.0, 9.6), "geldigi"), ((90.0, 32.0, 9.6), "yaw90")]
    p = kafes_plani((10.0, 95.0, 399.6), 54, (32.0, 90.0, 9.6), 520,
                    335.0, 335.0, 2.0, pitch=2.0,
                    oryantasyonlar_ozel=ozel, skor_v2=True)
    assert p["uygun"] is True
    assert p["oryantasyon"] in ("geldigi", "yaw90")


def test_kafes_coz_instance_tetik_ve_plan_only():
    """kafes_coz_instance (M4 kol girisi): tetikli ailede plan kurar
    (plan_only cozumsuz-ucuz), tetiksiz ailede kol uretmez."""
    from scripts.k66_d_kafes_dekod import kafes_coz_instance
    from src.nesting3d.instances.format import ContainerSpec
    from src.nesting3d.instances.synthetic import (
        mass_plate_rod_mix, random_boxes)
    cnt = ContainerSpec(width_mm=335.0, depth_mm=335.0, height_mm=None)
    inst = mass_plate_rod_mix(container=cnt, seed=0, qty_per_plate=40)
    r = kafes_coz_instance(inst, plan_only=True)
    assert r["tetik"] is True
    assert r["plan"]["uygun"] is True
    assert r["n_pins"] > 0
    # durus-koru modu da plan kurabilmeli (cubuklar dik uretiliyor)
    rd = kafes_coz_instance(inst, durus_koru=True, plan_only=True)
    assert rd["tetik"] is True and rd["plan"]["uygun"] is True
    assert rd["plan"]["oryantasyon"] in ("geldigi", "yaw90")
    # kontrol ailesi: tetik yok
    rb = random_boxes(n_parts=16, container=cnt, seed=0)
    assert kafes_coz_instance(rb, plan_only=True)["tetik"] is False


def test_durus_koru_oryantasyon_kisiti():
    # ozel liste verilince yalniz o duruslardan secilir (geldigi+yaw)
    ozel = [((32.0, 90.0, 9.6), "geldigi"), ((90.0, 32.0, 9.6), "yaw90")]
    plan = kafes_plani((10.0, 95.0, 399.6), 54, (32.0, 90.0, 9.6), 520,
                       335.0, 335.0, 2.0, pitch=2.0,
                       oryantasyonlar_ozel=ozel)
    assert plan["uygun"] is True
    assert plan["oryantasyon"] in ("geldigi", "yaw90")
    assert plan["cell"][2] == 9.6  # yukselik GELDIGI gibi (dik'e donmedi)
