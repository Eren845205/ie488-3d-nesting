# -*- coding: utf-8 -*-
"""K-56 testleri — parça-bazlı EK poz enjeksiyonu (extra_rot_overrides zinciri).

Zincir: voxelize_part(extra_rot_matrices) -> expand_quantities /
to_voxel_parts(extra_rot_overrides) -> solve_coarse_to_fine(extra_rot_overrides)
-> eval_gate._run_champion/evaluate_set(extra_rot_overrides).

Değişmezler:
  - Default (None) HER katmanda bit-özdeş (meta-ders 10: üretim default'una
    dokunulmaz; K-56 opt-in altyapı).
  - Ek pozlar default setin SONUNA eklenir (coarse/fine indeks tutarlılığı:
    iki aşama aynı sırayla kurar; rot-matris hizalaması zaten dayanıklı).
  - Ekler yalnız adı eşleşen modele uygulanır.
"""
from __future__ import annotations

import math

import numpy as np
import trimesh

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
    to_voxel_parts,
)
from src.nesting3d.voxelize import expand_quantities, voxelize_part

PITCH = 5.0


def _box(w=30.0, d=20.0, h=10.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


def _tilt(deg, axis=(1, 0, 0)):
    return trimesh.transformations.rotation_matrix(math.radians(deg), axis)


def _make_instance():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="box_a", name="box_a", qty=2, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="box_b", name="box_b", qty=2, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


# ---------------------------------------------------------------------------
# voxelize_part
# ---------------------------------------------------------------------------

def test_voxelize_part_extra_none_bit_ozdes():
    a = voxelize_part("p", _box(), PITCH, n_orientations=4)
    b = voxelize_part("p", _box(), PITCH, n_orientations=4,
                      extra_rot_matrices=None)
    assert len(a.orientations) == len(b.orientations) == 4
    for oa, ob in zip(a.orientations, b.orientations):
        assert np.array_equal(oa.grid, ob.grid)
        assert np.allclose(oa.rot_matrix, ob.rot_matrix)


def test_voxelize_part_extra_sona_eklenir():
    R = _tilt(45.0)
    base = voxelize_part("p", _box(), PITCH, n_orientations=4)
    vp = voxelize_part("p", _box(), PITCH, n_orientations=4,
                       extra_rot_matrices=[R])
    assert len(vp.orientations) == 5
    # onceki 4 poz birebir korunur
    for oa, ob in zip(base.orientations, vp.orientations[:4]):
        assert np.array_equal(oa.grid, ob.grid)
    # son poz verilen matris
    assert np.allclose(vp.orientations[-1].rot_matrix, R)


def test_voxelize_part_extra_rot_matrices_ile_birlikte():
    """rot_matrices (tam ezme) + extra: ekler yine sona gelir."""
    R0 = np.eye(4)
    R1 = _tilt(30.0)
    vp = voxelize_part("p", _box(), PITCH, rot_matrices=[R0],
                       extra_rot_matrices=[R1])
    assert len(vp.orientations) == 2
    assert np.allclose(vp.orientations[1].rot_matrix, R1)


# ---------------------------------------------------------------------------
# expand_quantities / to_voxel_parts
# ---------------------------------------------------------------------------

def test_expand_quantities_yalniz_eslesen_model():
    model_set = [("m_a", _box(), 2), ("m_b", _box(20, 20, 15), 1)]
    parts = expand_quantities(model_set, PITCH, n_orientations=4,
                              extra_rot_overrides={"m_a": [_tilt(30.0)]})
    a = [p for p in parts if p.name == "m_a"]
    b = [p for p in parts if p.name == "m_b"]
    assert all(len(p.orientations) == 5 for p in a)
    assert all(len(p.orientations) == 4 for p in b)


def test_to_voxel_parts_gecis_ve_default():
    inst = _make_instance()
    duz = to_voxel_parts(inst, PITCH, n_orientations=4)
    extra = to_voxel_parts(inst, PITCH, n_orientations=4,
                           extra_rot_overrides={"box_b": [_tilt(30.0)]})
    duz_by = {p.id: p for p in duz}
    for p in extra:
        if p.name == "box_b":
            assert len(p.orientations) == 5
        else:
            assert len(p.orientations) == len(duz_by[p.id].orientations)


# ---------------------------------------------------------------------------
# solve_coarse_to_fine
# ---------------------------------------------------------------------------

def _fast_menu():
    from src.nesting3d.solvers.dblf_solver import DBLFSolver
    return {"dblf_only": {"solver": DBLFSolver(), "params": {}}}


def test_c2f_extra_none_bit_ozdes():
    from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
    kw = dict(plate_w_mm=100.0, plate_d_mm=100.0, coarse_pitch=10.0,
              fine_pitch=5.0, budget=10, seed=42, menu=_fast_menu())
    r1 = solve_coarse_to_fine(_make_instance(), **kw)
    r2 = solve_coarse_to_fine(_make_instance(), extra_rot_overrides=None, **kw)
    assert r1.height_mm == r2.height_mm
    assert [p.part_id for p in r1.placements] == \
           [p.part_id for p in r2.placements]


def test_c2f_extra_rot_kosuyu_tamamlar():
    from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
    kw = dict(plate_w_mm=100.0, plate_d_mm=100.0, coarse_pitch=10.0,
              fine_pitch=5.0, budget=10, seed=42, menu=_fast_menu())
    r = solve_coarse_to_fine(_make_instance(),
                             extra_rot_overrides={"box_b": [_tilt(30.0)]},
                             **kw)
    assert len(r.placements) == 4
    fine_b = [p for p in r.fine_voxel_parts.values() if p.name == "box_b"]
    assert fine_b and all(len(p.orientations) == 5 for p in fine_b)


# ---------------------------------------------------------------------------
# eval_gate geçişi
# ---------------------------------------------------------------------------

def _mini_inst():
    return _make_instance()


def test_run_champion_heightmap_extra_rot_gecer(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_c2f(inst, **kw):
        yakalanan.update(kw)
        return "HM_SONUC"

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    monkeypatch.setattr(eg, "solve_coarse_to_fine", sahte_c2f)
    ekler = {"baseplate_v2": [_tilt(10.0)]}
    r, _ = eg._run_champion("t", _mini_inst(), 42, extra_rot_overrides=ekler)
    assert r == "HM_SONUC"
    assert yakalanan["extra_rot_overrides"] is ekler


def test_run_champion_heightmap_extra_yoksa_kw_da_yok(monkeypatch):
    """Default None -> kw'ya HIC girmez (bit-özdeş imza; bayat-mock A9)."""
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_c2f(inst, **kw):
        yakalanan.update(kw)
        return "HM_SONUC"

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    monkeypatch.setattr(eg, "solve_coarse_to_fine", sahte_c2f)
    eg._run_champion("t", _mini_inst(), 42)
    assert "extra_rot_overrides" not in yakalanan


def test_run_champion_nfv_dalinda_extra_rot_hata(monkeypatch):
    import pytest
    import scripts.eval_gate as eg

    class _Dec:
        mode = "nfv"
        nfv_quality = "fast"

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    with pytest.raises(ValueError, match="extra_rot_overrides"):
        eg._run_champion("t", _mini_inst(), 42,
                         extra_rot_overrides={"x": [_tilt(10.0)]})
