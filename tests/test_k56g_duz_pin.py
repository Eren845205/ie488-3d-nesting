# -*- coding: utf-8 -*-
"""K-56g testleri — sozlesme-kapili DUZ-PINLEME kablosu.

Zincir: plate_config.resolve_no_go_soft (ilan yoksa None -> kablo OLU KOD) ->
targeted_tilt.duz_pin_onerisi (geometrik pin karari; A11: kodda set adi yok) ->
eval_gate._run_champion / demo_pipeline c2f dali: pinned_placements + tilt
havuzunun susturulmasi (bos dict).

Degismezler:
  * no_go_soft ILAN EDILMEDIKCE her sey bit-ozdes (pin dali hic calismaz);
  * acik pinned_placements / extra_rot_overrides parametreleri otomatik pini
    HER ZAMAN ezer (operator/siparis-notu otoritesi);
  * pin cikarsa pahali tilt taramasi HIC kosulmaz.
"""
from __future__ import annotations

import json

import numpy as np

from src.nesting3d.instances.format import (ContainerSpec, NestingInstance,
                                            PartSpec)
from src.nesting3d.targeted_tilt import duz_pin_onerisi
from src.runtime.plate_config import resolve_no_go, resolve_no_go_soft

PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))
PITCH = 2.0


def _inst(fp_w=330.0, fp_d=302.0, h=6.0):
    """plan1-benzeri sentetik: buyuk duz plaka + kucuk kutular (set adi YOK)."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE[0], depth_mm=PLATE[1]),
        parts=[
            PartSpec(id="tabla", name="tabla", qty=1, source="box",
                     width_mm=fp_w, depth_mm=fp_d, height_mm=h),
            PartSpec(id="kutu", name="kutu", qty=2, source="box",
                     width_mm=30.0, depth_mm=30.0, height_mm=20.0),
        ],
    )


# ---------------------------------------------------------------------------
# resolve_no_go_soft (sozlesme kapisi)
# ---------------------------------------------------------------------------

def _cfg_yaz(tmp_path, data):
    d = tmp_path / "configs"
    d.mkdir(exist_ok=True)
    (d / "plate.local.json").write_text(json.dumps(data), encoding="utf-8")


def test_soft_ilan_yoksa_none_ve_hard_bozulmadi(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_NOGO_SOFT", raising=False)
    _cfg_yaz(tmp_path, {"width_mm": 335.0,
                        "no_go": [[152.5, 0.2], [185.5, 45.0]]})
    assert resolve_no_go_soft(tmp_path) is None
    # refactor regresyonu (_no_go_coz): hard no-go cozumu birebir
    assert resolve_no_go(tmp_path) == NOGO


def test_soft_configten_cozulur(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_NOGO_SOFT", raising=False)
    _cfg_yaz(tmp_path, {"no_go_soft": [[152.5, 0.2], [185.5, 33.0]]})
    assert resolve_no_go_soft(tmp_path) == NOGO_SOFT


def test_soft_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATE_NOGO_SOFT", "152.5,0.2,185.5,33.0")
    assert resolve_no_go_soft(tmp_path) == NOGO_SOFT  # config dosyasi yok


def test_soft_bozuk_format_none(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_NOGO_SOFT", raising=False)
    _cfg_yaz(tmp_path, {"no_go_soft": [[185.5, 33.0], [152.5, 0.2]]})  # ters
    assert resolve_no_go_soft(tmp_path) is None


# ---------------------------------------------------------------------------
# duz_pin_onerisi (geometrik karar)
# ---------------------------------------------------------------------------

def test_pin_koordinatlari_ve_giris():
    pin = duz_pin_onerisi(_inst(), "tabla", plate_w_mm=PLATE[0],
                          plate_d_mm=PLATE[1], no_go_soft=NOGO_SOFT,
                          fine_pitch=PITCH, giris_tolerans_mm=2.0)
    assert pin is not None
    assert pin["ad"] == "tabla"
    assert pin["z_mm"] == 0.0 and pin["rot"] is None
    # x ortalanmis (335-330)/2 = 2.5 civari, bir voxel toleransla
    assert 0.0 <= pin["x_mm"] <= 2.5 + PITCH
    # y uzak kenara dayali: 335-302 = 33 civari (voxel kuantizasyonu)
    assert 33.0 - 2 * PITCH <= pin["y_mm"] <= 33.0 + PITCH
    # soft sinira giris tutarli ve tolerans icinde
    assert pin["giris_mm"] == round(max(0.0, NOGO_SOFT[1][1] - pin["y_mm"]), 3)
    assert 0.0 <= pin["giris_mm"] <= 2.0


def test_pin_deterministik():
    a = duz_pin_onerisi(_inst(), "tabla", plate_w_mm=PLATE[0],
                        plate_d_mm=PLATE[1], no_go_soft=NOGO_SOFT,
                        fine_pitch=PITCH)
    b = duz_pin_onerisi(_inst(), "tabla", plate_w_mm=PLATE[0],
                        plate_d_mm=PLATE[1], no_go_soft=NOGO_SOFT,
                        fine_pitch=PITCH)
    assert a == b


def test_pin_plakaya_sigmayan_none():
    assert duz_pin_onerisi(_inst(fp_w=340.0), "tabla", plate_w_mm=PLATE[0],
                           plate_d_mm=PLATE[1], no_go_soft=NOGO_SOFT,
                           fine_pitch=PITCH) is None


def test_pin_giris_toleransi_asilirsa_none():
    soft_buyuk = ((152.5, 0.2), (185.5, 60.0))  # giris ~27mm > tolerans
    assert duz_pin_onerisi(_inst(), "tabla", plate_w_mm=PLATE[0],
                           plate_d_mm=PLATE[1], no_go_soft=soft_buyuk,
                           fine_pitch=PITCH, giris_tolerans_mm=2.0) is None


def test_pin_soft_none_ise_none():
    assert duz_pin_onerisi(_inst(), "tabla", plate_w_mm=PLATE[0],
                           plate_d_mm=PLATE[1], no_go_soft=None,
                           fine_pitch=PITCH) is None


def test_pin_olmayan_ad_none():
    assert duz_pin_onerisi(_inst(), "yok-boyle-parca", plate_w_mm=PLATE[0],
                           plate_d_mm=PLATE[1], no_go_soft=NOGO_SOFT,
                           fine_pitch=PITCH) is None


# ---------------------------------------------------------------------------
# eval_gate kablosu (_run_champion; test_k56b deseni)
# ---------------------------------------------------------------------------

def _hm_ortam(monkeypatch, tilt_parca):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_c2f(inst, **kw):
        yakalanan.update(kw)
        return "HM_SONUC"

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    _Dec.tilt_parca = tilt_parca
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit",
                        lambda inst, **k: _Dec())
    monkeypatch.setattr(eg, "solve_coarse_to_fine", sahte_c2f)
    return eg, yakalanan


def _patlat(mesaj):
    def _f(*a, **k):
        raise AssertionError(mesaj)
    return _f


def test_sozlesme_sabitleri_soft_kalici(monkeypatch):
    """SOZLESME PINI (2026-08-04, Eren karari — kapi-2 f615d8d): soft no-go
    y-ust 33 KALICI sozlesme; NOGO_STD == NOGO_SOFT, hard dikdortgen
    NOGO_HARD'da tarihsel kayit olarak durur. Bu degerler A11 madde 4 sinifi
    olmadan degistirilemez."""
    import scripts.eval_gate as eg
    assert eg.NOGO_STD == ((152.5, 0.2), (185.5, 33.0))
    assert eg.NOGO_SOFT == eg.NOGO_STD
    assert eg.NOGO_HARD == ((152.5, 0.2), (185.5, 45.0))


def test_run_champion_soft_yokken_pin_dali_olu(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    # NOGO_SOFT=None semantigi korunur: kablo kapali -> pin dali OLU KOD.
    # (Kalici sozlesmede default artik SOFT; None davranisi monkeypatch ile
    # pinlenmeye devam eder — opt-out yolu kirilmasin.)
    monkeypatch.setattr(eg, "NOGO_SOFT", None)
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "duz_pin_onerisi",
                        _patlat("NOGO_SOFT None iken pin cagrilmamaliydi"))
    monkeypatch.setattr(tt, "hedefli_tilt_overrides", lambda *a, **k: None)
    eg._run_champion("t", _inst(), 42)
    assert "pinned_placements" not in yakalanan


def test_run_champion_soft_ile_pin_ve_tilt_susturma(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    monkeypatch.setattr(eg, "NOGO_SOFT", NOGO_SOFT)
    pin = {"ad": "tabla", "x_mm": 2.0, "y_mm": 32.0, "z_mm": 0.0,
           "rot": None, "giris_mm": 1.0}
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "duz_pin_onerisi", lambda *a, **k: dict(pin))
    monkeypatch.setattr(tt, "hedefli_tilt_overrides",
                        _patlat("pin varken tilt taramasi kosulmamaliydi"))
    eg._run_champion("t", _inst(), 42)
    assert yakalanan["pinned_placements"] == [
        {"ad": "tabla", "x_mm": 2.0, "y_mm": 32.0, "z_mm": 0.0, "rot": None}]
    assert yakalanan["extra_rot_overrides"] == {}


def test_run_champion_pin_none_ise_tilt_yolu(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    monkeypatch.setattr(eg, "NOGO_SOFT", NOGO_SOFT)
    havuz = {"tabla": [np.eye(4)]}
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "duz_pin_onerisi", lambda *a, **k: None)
    monkeypatch.setattr(tt, "hedefli_tilt_overrides", lambda *a, **k: havuz)
    eg._run_champion("t", _inst(), 42)
    assert "pinned_placements" not in yakalanan
    assert yakalanan["extra_rot_overrides"] is havuz


def test_run_champion_acik_pin_otomatigi_ezer(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    monkeypatch.setattr(eg, "NOGO_SOFT", NOGO_SOFT)
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "duz_pin_onerisi",
                        _patlat("acik pin varken otomatik cagrilmamaliydi"))
    monkeypatch.setattr(tt, "hedefli_tilt_overrides", lambda *a, **k: None)
    acik = [{"ad": "tabla", "x_mm": 1.0, "y_mm": 1.0, "z_mm": 0.0, "rot": None}]
    eg._run_champion("t", _inst(), 42, pinned_placements=acik)
    assert yakalanan["pinned_placements"] is acik


def test_run_champion_acik_extra_rot_otomatigi_ezer(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    monkeypatch.setattr(eg, "NOGO_SOFT", NOGO_SOFT)
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "duz_pin_onerisi",
                        _patlat("acik extra_rot varken otomatik cagrilmamaliydi"))
    acik = {"tabla": [np.eye(4)]}
    eg._run_champion("t", _inst(), 42, extra_rot_overrides=acik)
    assert yakalanan["extra_rot_overrides"] is acik
