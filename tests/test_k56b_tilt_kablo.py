# -*- coding: utf-8 -*-
"""K-56b testleri — hedefli-tilt uretim kablosu.

Zincir: predict_nfv_benefit ADIM -1 -> ModeDecision.tilt_parca (yapisal) ->
targeted_tilt.hedefli_tilt_overrides -> eval_gate/demo_pipeline c2f
extra_rot_overrides. Degismezler: tilt-zorunlu parca yoksa HER SEY bit-ozdes;
acik extra_rot_overrides otomatik havuzu HER ZAMAN ezer.
"""
from __future__ import annotations

import numpy as np

from src.nesting3d.adaptive_params import predict_nfv_benefit
from src.nesting3d.instances.format import (ContainerSpec, NestingInstance,
                                            PartSpec)
from src.nesting3d.targeted_tilt import _yerlesebilir, hedefli_tilt_overrides

PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def _inst_tiltli():
    """plan1-benzeri: 330x302 baseplate (hicbir duz poz no-go'lu plakaya
    sigmaz) + kucuk kutu."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE[0], depth_mm=PLATE[1]),
        parts=[
            PartSpec(id="tabla", name="tabla", qty=1, source="box",
                     width_mm=330.0, depth_mm=302.0, height_mm=6.0),
            PartSpec(id="kutu", name="kutu", qty=2, source="box",
                     width_mm=30.0, depth_mm=30.0, height_mm=20.0),
        ],
    )


def _inst_serbest():
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE[0], depth_mm=PLATE[1]),
        parts=[PartSpec(id="kutu", name="kutu", qty=2, source="box",
                        width_mm=30.0, depth_mm=30.0, height_mm=20.0)],
    )


# ---------------------------------------------------------------------------
# ModeDecision.tilt_parca
# ---------------------------------------------------------------------------

def test_dec_tilt_parca_dolu():
    dec = predict_nfv_benefit(_inst_tiltli(), no_go_bounds=NOGO)
    assert dec.mode == "heightmap"
    assert dec.tilt_parca == "tabla"


def test_dec_tilt_parca_yoksa_none():
    dec = predict_nfv_benefit(_inst_serbest(), no_go_bounds=NOGO)
    assert dec.tilt_parca is None
    dec2 = predict_nfv_benefit(_inst_tiltli())  # no-go'suz -> kapi calismaz
    assert dec2.tilt_parca is None


# ---------------------------------------------------------------------------
# _yerlesebilir serit formulu
# ---------------------------------------------------------------------------

def test_yerlesebilir_seritler():
    # sol serit: x1=152.5 >= W
    assert _yerlesebilir(150.0, 300.0, *PLATE, NOGO)
    # ote serit: y2=45 <= 335-D -> D <= 290
    assert _yerlesebilir(334.0, 289.0, *PLATE, NOGO)
    # hicbiri: 330x302 (plan1 baseplate durumu)
    assert not _yerlesebilir(330.0, 302.0, *PLATE, NOGO)
    # plakaya sigmayan
    assert not _yerlesebilir(340.0, 10.0, *PLATE, None)
    # no-go'suz yalniz plaka
    assert _yerlesebilir(330.0, 302.0, *PLATE, None)


# ---------------------------------------------------------------------------
# hedefli_tilt_overrides
# ---------------------------------------------------------------------------

def test_hedefli_tilt_pozlar_uretilir_ve_deterministik():
    inst = _inst_tiltli()
    r1 = hedefli_tilt_overrides(inst, "tabla", plate_w_mm=PLATE[0],
                                plate_d_mm=PLATE[1], no_go_bounds=NOGO,
                                fine_pitch=2.0, clearance_mm=2.0)
    assert r1 is not None and "tabla" in r1
    assert len(r1["tabla"]) > 0
    r2 = hedefli_tilt_overrides(inst, "tabla", plate_w_mm=PLATE[0],
                                plate_d_mm=PLATE[1], no_go_bounds=NOGO,
                                fine_pitch=2.0, clearance_mm=2.0)
    assert len(r1["tabla"]) == len(r2["tabla"])
    for a, b in zip(r1["tabla"], r2["tabla"]):
        assert np.allclose(a, b)


def test_hedefli_tilt_olmayan_ad_none():
    assert hedefli_tilt_overrides(
        _inst_tiltli(), "yok-boyle-parca", plate_w_mm=PLATE[0],
        plate_d_mm=PLATE[1], no_go_bounds=NOGO, fine_pitch=2.0) is None


# ---------------------------------------------------------------------------
# eval_gate kablosu
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


def test_run_champion_tilt_parca_otomatik_havuz(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    havuz = {"tabla": [np.eye(4)]}
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "hedefli_tilt_overrides",
                        lambda *a, **k: havuz)
    from tests.test_k56b_tilt_kablo import _inst_tiltli
    eg._run_champion("t", _inst_tiltli(), 42)
    assert yakalanan["extra_rot_overrides"] is havuz


def test_run_champion_acik_override_ezer(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "hedefli_tilt_overrides",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("otomatik havuz KURULMAMALIYDI")))
    acik = {"tabla": [np.eye(4)]}
    eg._run_champion("t", _inst_tiltli(), 42, extra_rot_overrides=acik)
    assert yakalanan["extra_rot_overrides"] is acik


def test_run_champion_havuz_none_ise_tiltsiz(monkeypatch):
    eg, yakalanan = _hm_ortam(monkeypatch, "tabla")
    import src.nesting3d.targeted_tilt as tt
    monkeypatch.setattr(tt, "hedefli_tilt_overrides", lambda *a, **k: None)
    eg._run_champion("t", _inst_tiltli(), 42)
    assert "extra_rot_overrides" not in yakalanan
