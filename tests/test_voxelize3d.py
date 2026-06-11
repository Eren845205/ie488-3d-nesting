"""Tests for src.nesting3d.voxelize (PLAN_3D.md §4)."""

import numpy as np
import pytest
import trimesh

from src.nesting3d.models import MODELS_DIR, model_set
from src.nesting3d.voxelize import (
    expand_quantities,
    rotation_matrices,
    voxelize_part,
)

PITCH = 5.0


def _box(w=20.0, d=20.0, h=20.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


def _l_shape():
    """Asymmetric composite (an L) — orientations must differ."""
    a = trimesh.creation.box(extents=(40, 10, 10))
    a.apply_translation((20, 5, 5))
    b = trimesh.creation.box(extents=(10, 10, 30))
    b.apply_translation((5, 5, 15))
    return trimesh.util.concatenate([a, b])


def test_rotation_matrices_count():
    assert len(rotation_matrices(1)) == 1
    assert len(rotation_matrices(4)) == 4
    assert np.allclose(rotation_matrices(4)[0], np.eye(4))


def test_box_voxelizes_solid():
    vp = voxelize_part("box", _box(), PITCH, n_orientations=1)
    o = vp.orientations[0]
    assert o.voxel_count > 0
    # a solid box must be FILLED, not a hollow shell (fill() requirement)
    nx, ny, nz = o.shape
    assert o.voxel_count == nx * ny * nz


def test_column_profiles_consistent():
    vp = voxelize_part("L", _l_shape(), PITCH, n_orientations=4)
    for o in vp.orientations:
        nz = o.shape[2]
        assert o.filled.any()
        assert (o.bottom[o.filled] < o.top[o.filled]).all()
        assert (o.top <= nz).all()
        assert (o.bottom >= 0).all()
        # empty columns carry zero profiles
        assert (o.bottom[~o.filled] == 0).all()
        assert (o.top[~o.filled] == 0).all()


def test_box_profiles_are_flat():
    o = voxelize_part("box", _box(), PITCH, n_orientations=1).orientations[0]
    assert (o.bottom[o.filled] == 0).all()
    assert (o.top[o.filled] == o.shape[2]).all()


def test_orientations_change_footprint():
    vp = voxelize_part("L", _l_shape(), PITCH, n_orientations=4)
    shapes = {o.shape for o in vp.orientations}
    assert len(shapes) > 1  # tipping the L must change the grid shape


def test_margin_dilation_grows_volume():
    plain = voxelize_part("box", _box(), PITCH, n_orientations=1)
    fat = voxelize_part("box", _box(), PITCH, n_orientations=1, margin=1)
    assert fat.orientations[0].voxel_count > plain.orientations[0].voxel_count
    # dilation YATAY (x, y) — dikey boşluk Bin3D.z_clearance'ta (2026-06-11)
    px, py, pz = plain.orientations[0].shape
    assert fat.orientations[0].shape == (px + 2, py + 2, pz)


@pytest.mark.skipif(
    not (MODELS_DIR / "chair.stl").exists(),
    reason="data/models yok — scripts/generate_models.py koşulmamış",
)
def test_expand_quantities_default_set():
    parts = expand_quantities(model_set("default"), 220.0 / 64)
    assert len(parts) == 30  # 10 + 5 + 15 (hoca direktifi)
    ids = [p.id for p in parts]
    assert len(set(ids)) == 30
    chairs = [p for p in parts if p.name == "chair"]
    assert len(chairs) == 10
    # instances share orientation data (voxelize once per model)
    assert chairs[0].orientations is chairs[1].orientations
