# -*- coding: utf-8 -*-
"""Dejenere-poz dayanikliligi (2026-07-08, plan3 n24 None.exterior fix).

Kayitli bug: trimesh polygons_full bazi acili pozlarda None poligonda
.exterior cagirip AttributeError firlatiyordu -> TEK bozuk poz TUM cozumu
(ax24 plan3_n24 kosusu) olduruyordu. Fix iki katman:
  1) _slice_voxelize: polygons_full patlarsa polygons_closed'in None-olmayan
     uyelerine dus (delikler dolu = KONSERVATIF overapproximation).
  2) voxelize_part (slice yolu): bozuk poz ATLANIR, hicbir poz kalmazsa
     hata YUKSELIR (sessiz bos menu yok).
  3) coarse_to_fine hizalamasi: kazananin rot matrisi tasinir; indeks
     kelepcelenir (liste kisalinca IndexError/yanlis-poz olmaz).
"""
import numpy as np
import pytest
import trimesh

import src.nesting3d.voxelize as vox
from src.nesting3d.voxelize import voxelize_part


def _box(w=20.0, d=20.0, h=20.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


PITCH = 5.0


def test_degenerate_orientation_skipped(monkeypatch):
    """2. poz patlarsa: cozum olmez, kalan pozlar doner."""
    real = vox._slice_voxelize
    calls = {"n": 0}

    def sahte(mesh, pitch, *, allow_empty=False):
        calls["n"] += 1
        if calls["n"] == 2:
            raise AttributeError("'NoneType' object has no attribute 'exterior'")
        return real(mesh, pitch, allow_empty=allow_empty)

    monkeypatch.setattr(vox, "_slice_voxelize", sahte)
    p = voxelize_part("kutu", _box(), PITCH, n_orientations=4, method="slice")
    assert len(p.orientations) == 3          # 4 pozdan 1'i atlandi
    assert all(o.grid.any() for o in p.orientations)


def test_all_orientations_fail_raises(monkeypatch):
    """Hicbir poz kurtarilamazsa gercek hata yukselir (sessiz bos menu YOK)."""
    def hep_patla(mesh, pitch, *, allow_empty=False):
        raise AttributeError("'NoneType' object has no attribute 'exterior'")

    monkeypatch.setattr(vox, "_slice_voxelize", hep_patla)
    with pytest.raises(AttributeError):
        voxelize_part("kutu", _box(), PITCH, n_orientations=4, method="slice")


def test_polygons_full_fallback_to_closed():
    """polygons_full patlayan kesitte polygons_closed None'lari suzulup
    kullanilir — grid bos KALMAZ (konservatif dolgu)."""
    import shapely.geometry as sg

    class SahteSec:
        @property
        def polygons_full(self):
            raise AttributeError("'NoneType' object has no attribute 'exterior'")

        @property
        def polygons_closed(self):
            return [None, sg.box(0.0, 0.0, 20.0, 20.0)]

    class SahteMesh:
        extents = np.array([20.0, 20.0, 20.0])

        def section_multiplane(self, plane_origin, plane_normal, heights):
            return [SahteSec() for _ in heights]

    grid = vox._slice_voxelize(SahteMesh(), PITCH)
    assert grid.shape == (4, 4, 4)
    assert grid.all()                        # kutu tamamen dolu isaretlendi


def test_default_path_bit_identical():
    """Fix normal yolda BIT-OZDES: saglikli mesh'te grid degismedi."""
    p = voxelize_part("kutu", _box(), PITCH, n_orientations=4, method="slice")
    assert len(p.orientations) == 4
    g = p.orientations[0].grid
    assert g.shape == (4, 4, 4) and g.all()
