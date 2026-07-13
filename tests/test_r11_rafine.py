"""R11 v4 — dogrula_ve_rafine: pay tamponu yerine kesin oturma.

Kabul kriterleri:
  1. Ihlalli dz (cift < 2.0) rafine sonrasi min_clearance >= 2.0 + converged.
  2. Geri kaldirma yalniz DUSMUS parcada (dz asla < 0; orijinal-legal taban).
  3. Ihlalsiz girdi aynen gecer (tur=0, converged).
  4. Determinizm.
  5. Entegrasyon: kucuk-pay kompakt + rafine, buyuk-pay tek-atistan ALCAK
     veya esit sonuc verir (v4'un varlik sebebi) ve yine legal.
"""
from __future__ import annotations

import numpy as np
import trimesh

from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import (
    apply_dz,
    continuous_z_settle,
    dogrula_ve_rafine,
)


def _box(w, d, h, at=(0.0, 0.0, 0.0)):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2 + at[0], d / 2 + at[1], h / 2 + at[2]])
    return m


def test_ihlal_rafine_ile_duzelir():
    a = _box(20, 20, 10, at=(0, 0, 0))
    b = _box(20, 20, 10, at=(0, 0, 13))          # bosluk 3.0 (legal)
    dz = [0.0, 1.5]                               # asiri dusme -> bosluk 1.5 IHLAL
    yeni_dz, rapor, tur, ok = dogrula_ve_rafine([a, b], dz, samples_per_mesh=4000)
    assert ok and tur >= 1
    assert rapor.min_mm >= 2.0
    assert yeni_dz[0] == 0.0                      # dusmemis parcaya dokunulmaz
    assert 0.0 <= yeni_dz[1] < 1.5                # geri kaldirildi ama negatif degil


def test_ihlalsiz_aynen_gecer():
    a = _box(20, 20, 10, at=(0, 0, 0))
    b = _box(20, 20, 10, at=(0, 0, 13))
    yeni_dz, rapor, tur, ok = dogrula_ve_rafine([a, b], [0.0, 0.9],
                                                samples_per_mesh=4000)
    assert ok and tur == 0
    assert list(yeni_dz) == [0.0, 0.9]


def test_determinizm():
    a = _box(20, 20, 10, at=(0, 0, 0))
    b = _box(18, 16, 9, at=(1, 2, 13.5))
    r1 = dogrula_ve_rafine([a, b], [0.0, 1.4], samples_per_mesh=4000)
    r2 = dogrula_ve_rafine([a, b], [0.0, 1.4], samples_per_mesh=4000)
    assert list(r1[0]) == list(r2[0]) and r1[2] == r2[2]


def test_entegrasyon_kucuk_pay_plus_rafine_daha_iyi():
    kule = [_box(20, 20, 8, at=(0, 0, 0)),
            _box(20, 20, 8, at=(0, 0, 11.5)),
            _box(20, 20, 8, at=(0, 0, 23.0))]
    buyuk = continuous_z_settle(kule, clearance_mm=2.0, pay_mm=1.2,
                                samples_per_mesh=4000)
    kucuk = continuous_z_settle(kule, clearance_mm=2.0, pay_mm=0.15,
                                samples_per_mesh=4000)
    dz4, rapor4, _, ok4 = dogrula_ve_rafine(kule, kucuk.dz,
                                            samples_per_mesh=4000)
    assert ok4 and rapor4.min_mm >= 2.0
    h4 = max(float(m.bounds[1][2]) for m in apply_dz(kule, dz4))
    assert h4 <= buyuk.height_mm + 1e-6          # v4 buyuk-pay'dan kotu olamaz
    assert min_clearance(apply_dz(kule, dz4), samples_per_mesh=4000).min_mm >= 2.0
