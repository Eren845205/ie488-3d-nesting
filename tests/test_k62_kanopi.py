# -*- coding: utf-8 -*-
"""tests/test_k62_kanopi.py — K-62 Ç1: delikli-parça düz-poz gerçek-geometri
no-go fizibilitesi + kanopi mekanizma temelleri (Bin3D pin testleri).

Degismezler:
  - Delikli çerçeve: no-go dikdörtgenini deliğine alan düz yerleşim BULUNUR
    (bbox şerit testinin yanlış-pozitifi gerçek geometride açılır).
  - Aynı bbox'lı DOLU plaka: düz yerleşim YOK (bbox testi dolu parçada zaten
    doğruydu — konservatiflik tek yönlü).
  - marj parametresi no-go'yu genişletir; delikten büyük marj fizibiliteyi
    düşürür.
  - no_go_bounds=None -> None (kısıt yok; çağıran zincir hiç tetiklenmez —
    bit-özdeşlik güvencesi).
  - Bin3D mekanizma pinleri: (a) delik kolonundan kule geçer (çarpışma değil),
    (b) no-go mühürü dolu kolonu engeller ama deliğin üstünden geçişi
    engellemez, (c) order_key ile SON gelen çerçeve yığının ÜSTÜNE (kanopi)
    iner.

Sentetik geometri — veri-adı YOK (A11): çerçeve = 4 kol kutusunun birleşimi
(60x60x6, iç delik 24x24), kule = 10x10x40 kutu.
"""
from __future__ import annotations

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.kanopi import (
    duz_poz_nogo_fizibilite,
    duz_rot_matrisleri,
)
from src.nesting3d.voxelize import voxelize_part


def _kutu(w, d, h, cx=0.0, cy=0.0, cz=0.0):
    m = trimesh.creation.box(extents=(w, d, h))
    m.apply_translation([cx, cy, cz])
    return m


def _cerceve_mesh():
    """60x60x6 çerçeve, iç delik 24x24 (4 kol kutusu, çakışmasız döşeme)."""
    return trimesh.util.concatenate([
        _kutu(18, 60, 6, cx=-21),          # bati kolu  x[-30,-12]
        _kutu(18, 60, 6, cx=+21),          # dogu kolu  x[+12,+30]
        _kutu(24, 18, 6, cy=+21),          # kuzey kolu y[+12,+30], x[-12,+12]
        _kutu(24, 18, 6, cy=-21),          # guney kolu y[-12,-30]
    ])


def _dolu_plaka_mesh():
    return _kutu(60, 60, 6)


# ---------------------------------------------------------------------------
# duz_rot_matrisleri
# ---------------------------------------------------------------------------

def test_duz_rot_kalinlik_eksenini_z_yapar():
    # Kalinlik ekseni X olan parca: duz poz X'i Z'ye tasimali.
    m = _kutu(6, 60, 60)
    rots = duz_rot_matrisleri(m)
    assert len(rots) == 4
    for R in rots:
        mm = m.copy()
        mm.apply_transform(R)
        assert mm.extents[2] == pytest.approx(6.0, abs=1e-6)


# ---------------------------------------------------------------------------
# duz_poz_nogo_fizibilite
# ---------------------------------------------------------------------------

_PLAKA = 70.0
# Plaka-merkezli no-go: 12x12, merkez (35,35) — cercevenin deligi (24x24)
# uygun ofsette bunu tamamen icine alabilir.
_NOGO = ((29.0, 29.0), (41.0, 41.0))


def test_delikli_cerceve_duz_poz_bulunur():
    r = duz_poz_nogo_fizibilite(
        _cerceve_mesh(), _PLAKA, _PLAKA, _NOGO, pitch=1.0)
    assert r is not None
    assert r["pozlar"], "delikli cercevede duz poz bulunmali"
    assert r["doluluk"] < 0.9  # delikli footprint dolu sayilmamali
    p = r["pozlar"][0]
    assert set(p) >= {"rot_deg", "dx_mm", "dy_mm"}


def test_dolu_plaka_duz_poz_yok():
    r = duz_poz_nogo_fizibilite(
        _dolu_plaka_mesh(), _PLAKA, _PLAKA, _NOGO, pitch=1.0)
    assert r is not None
    assert r["pozlar"] == []  # bbox konservatifligi dolu parcada dogruydu


def test_marj_fizibiliteyi_dusurur():
    # Delik 24, no-go 12: marj 8 -> etkin 12+2*8=28 > 24 -> yerlesemez.
    r0 = duz_poz_nogo_fizibilite(
        _cerceve_mesh(), _PLAKA, _PLAKA, _NOGO, pitch=1.0, marj_mm=0.0)
    r8 = duz_poz_nogo_fizibilite(
        _cerceve_mesh(), _PLAKA, _PLAKA, _NOGO, pitch=1.0, marj_mm=8.0)
    assert r0["pozlar"]
    assert r8["pozlar"] == []


def test_nogo_yoksa_none():
    assert duz_poz_nogo_fizibilite(
        _cerceve_mesh(), _PLAKA, _PLAKA, None, pitch=1.0) is None


def test_plakaya_sigmayan_parca_bos():
    r = duz_poz_nogo_fizibilite(
        _cerceve_mesh(), 50.0, 50.0, ((10.0, 10.0), (20.0, 20.0)), pitch=1.0)
    assert r is not None
    assert r["pozlar"] == []


# ---------------------------------------------------------------------------
# Bin3D mekanizma pinleri (mevcut motor yetenekleri — kanopi temelleri)
# ---------------------------------------------------------------------------

_PITCH = 2.0


def _vox(name, mesh, rot=None):
    rots = [np.eye(4)] if rot is None else [rot]
    return voxelize_part(name, mesh, _PITCH, rot_matrices=rots)


def test_kule_delikten_gecer():
    # Cerceve z=0'da; kule deligin icine z=0'a duser (delik kolonlari
    # drop_map'te carpisma DEGIL).
    cerceve = _vox("cerceve", _cerceve_mesh())
    kule = _vox("kule", _kutu(10, 10, 40))
    placements, b = dblf(
        [cerceve, kule], lambda: Bin3D(_PLAKA, _PLAKA, _PITCH),
        order_key=lambda p: (0 if p.id == "cerceve" else 1,),
    )
    zler = {p.part_id: p.z for p in placements}
    assert zler["cerceve"] == 0
    assert zler["kule"] == 0, "kule cercevenin deliginden z=0'a inmeli"


def test_nogo_muhru_dolu_kolonu_engeller_deligi_engellemez():
    # Ayni no-go altinda: delikli cerceve z=0'a yerlesebilir (delik no-go
    # ustune hizalanir), dolu plaka z=0'a YERLESEMEZ (muhur her kolonu iter).
    mask = Bin3D.no_go_mask_from_bounds(_NOGO, _PLAKA, _PLAKA, _PITCH)

    cerceve = _vox("cerceve", _cerceve_mesh())
    pl_c, _ = dblf([cerceve],
                   lambda: Bin3D(_PLAKA, _PLAKA, _PITCH, no_go_mask=mask))
    assert pl_c and pl_c[0].z == 0, "delikli cerceve no-go'ya ragmen z=0 almali"

    dolu = _vox("dolu", _dolu_plaka_mesh())
    pl_d, _ = dblf([dolu],
                   lambda: Bin3D(_PLAKA, _PLAKA, _PITCH, no_go_mask=mask))
    assert (not pl_d) or pl_d[0].z >= Bin3D.NO_GO_SEAL, \
        "dolu plaka no-go kolonuna oturamamali (muhur)"


def test_son_gelen_cerceve_kanopi_olur():
    # Kule plakada; cerceve SON sirada gelirse kule bir kolun ALTINDA
    # kaldiginda cerceve yiginin USTUNE (kanopi) iner — drop-ustune-inme
    # mekanigi kanopiyi tasiyor.
    kule = _vox("kule", _kutu(10, 10, 40))
    cerceve = _vox("cerceve", _cerceve_mesh())
    placements, b = dblf(
        [kule, cerceve], lambda: Bin3D(_PLAKA, _PLAKA, _PITCH),
        order_key=lambda p: (0 if p.id == "kule" else 1,),
    )
    zler = {p.part_id: p.z for p in placements}
    assert zler["kule"] == 0
    # BLF kuleyi kose (0,0)'a atar; 70'lik plakada 60'lik cercevenin bati
    # kolu (18 kalin) her ofsette koseyi kapsar -> cerceve kulenin ustune
    # oturmali (z = kulenin voxel yuksekligi; kapsayici yuvarlama grid'den
    # okunur, mm/pitch'ten TURETILMEZ).
    kule_vox_boy = kule.orientations[0].grid.shape[2]
    assert zler["cerceve"] == kule_vox_boy, \
        "son gelen cerceve yiginin ustune (kanopi) inmeli"
