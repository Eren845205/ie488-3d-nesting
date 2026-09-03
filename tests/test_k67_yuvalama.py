# -*- coding: utf-8 -*-
"""test_k67_yuvalama.py - K-67 yuvalama-derinligi olcumu saf-mantik testleri.

Grid-tabanli testler kosusuz/ucuz: dolu blok yuvalanamaz (z_adim >= h +
clearance); U-kanal (ustu acik kesit) derin yuvalanir; clearance buyudukce
z_adim monoton artar.
"""
from __future__ import annotations

import numpy as np

from scripts.k67_yuvalama_derinligi import yuvalama_derinligi_grid

PITCH = 1.0
CLEAR = 2.0


def _dolu_blok(w=6, d=6, h=10):
    return np.ones((w, d, h), dtype=bool)


def _u_kanal(w=10, d=6, h=12, et=2):
    """DIK-duvarli U-kesit (agiz +z): taban + iki dusey yan duvar."""
    g = np.zeros((w, d, h), dtype=bool)
    g[:, :, :et] = True            # taban
    g[:et, :, :] = True            # sol duvar
    g[-et:, :, :] = True           # sag duvar
    return g


def _konik_canak(h=12, et=2, w0=3, d=6):
    """KONIK canak (V-kesit, agiz +z): duvar yarim-genisligi yukseklikle
    buyur -> ust kopya alttakinin agzina GIRER (PLAN8 braket sinifi)."""
    W = 2 * (w0 + h + et) + 3
    cx = W // 2
    g = np.zeros((W, d, h), dtype=bool)
    for k in range(h):
        yw = w0 + k                      # bu katmandaki yarim-genislik
        if k < et:                       # taban dolu
            g[cx - yw:cx + yw + 1, :, k] = True
        else:                            # yalniz egimli duvarlar
            g[cx - yw:cx - yw + et, :, k] = True
            g[cx + yw - et + 1:cx + yw + 1, :, k] = True
    return g


def test_dolu_blok_yuvalanamaz():
    r = yuvalama_derinligi_grid(_dolu_blok(), PITCH, CLEAR)
    # ust kopya ancak alttakinin clearance-bandinin ustune oturur
    assert r["z_adim_mm"] >= r["h_mm"] + CLEAR - 1e-9
    assert r["yuvalanabilir"] is False
    assert r["tasarruf_orani"] == 0.0


def test_dik_duvarli_kanal_xy_hizali_yuvalanamaz():
    """K-67 OGRENIMI (2026-08-20 gece): dik-duvarli kanal xy-hizali
    YUVALANMAZ - ust kopyanin tabani alttakinin duvarina biner. PLAN8
    braketinin yuvalanmasi duvar KONIKLIGINDEN gelir; tetik olcumu bunu
    geometriden ayirt etmeli (olcum dogru: burada tam-boy adim doner)."""
    r = yuvalama_derinligi_grid(_u_kanal(), PITCH, CLEAR)
    assert r["yuvalanabilir"] is False
    assert r["z_adim_mm"] >= r["h_mm"]


def test_konik_canak_derin_yuvalanir():
    r = yuvalama_derinligi_grid(_konik_canak(), PITCH, CLEAR)
    # egimli duvar: adim ~ max(duvar-kacikligi, taban+clearance) << h
    assert r["yuvalanabilir"] is True
    assert r["z_adim_mm"] < 0.7 * r["h_mm"]
    assert r["z_adim_mm"] >= CLEAR   # bosluk garantisi z-dilation'dan
    assert r["tasarruf_orani"] >= 0.5


def test_clearance_monoton():
    a = yuvalama_derinligi_grid(_konik_canak(), PITCH, 1.0)["z_adim_mm"]
    b = yuvalama_derinligi_grid(_konik_canak(), PITCH, 2.0)["z_adim_mm"]
    c = yuvalama_derinligi_grid(_konik_canak(), PITCH, 6.0)["z_adim_mm"]
    assert a <= b <= c
    assert a < c


def test_z_adim_pitch_carpani():
    r = yuvalama_derinligi_grid(_konik_canak(), 2.0, CLEAR)
    assert abs(r["z_adim_mm"] / 2.0 - round(r["z_adim_mm"] / 2.0)) < 1e-9


# ---------------------------------------------------------------------------
# sindil_adimi_grid — (dy, dz) taramasi (MK-04)
# ---------------------------------------------------------------------------

def _egik_kanat(w=6, d=12, h=10):
    """y-yonunde egimli kanat: katman k'da y in [k, k+3) dolu -> kopyalar
    dy kaydirmali sindille ic ice girer (xy-hizali girmez)."""
    g = np.zeros((w, d, h), dtype=bool)
    for k in range(h):
        y0 = min(k, d - 3)
        g[:, y0:y0 + 3, k] = True
    return g


def test_sindil_dolu_blok_kazanc_yok():
    from scripts.k67_yuvalama_derinligi import sindil_adimi_grid
    r = sindil_adimi_grid(_dolu_blok(), PITCH, CLEAR)
    assert r["yuvalanabilir"] is False
    assert r["dz_mm"] >= r["h_mm"] + CLEAR - 1e-9


def test_sindil_egik_kanat_dy_ile_yuvalanir():
    from scripts.k67_yuvalama_derinligi import (
        sindil_adimi_grid, yuvalama_derinligi_grid)
    g = _egik_kanat()
    duz = yuvalama_derinligi_grid(g, PITCH, CLEAR)
    sindil = sindil_adimi_grid(g, PITCH, CLEAR)
    # dy'li sindil xy-hizalidan KESIN derin girer (PLAN8 sinifi)
    assert sindil["yuvalanabilir"] is True
    assert sindil["dy_mm"] > 0
    assert sindil["dz_mm"] < duz["z_adim_mm"]


def test_sindil_dy_siniri_dejenere_yok():
    from scripts.k67_yuvalama_derinligi import sindil_adimi_grid
    r = sindil_adimi_grid(_dolu_blok(w=6, d=6, h=10), PITCH, CLEAR)
    # dy en fazla d/2 (3mm) — "yan-yana kacis" (dy=d) yapisal kapali
    assert r["dy_mm"] <= 3.0 + 1e-9
