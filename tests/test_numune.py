"""Tests for the numune scenario: slice voxelization + native-scale loading.

Hocanın gönderdiği 8 gerçek parça (Numuneler/, 2026-06-10).  Slice yöntemi
sentetik geometrilerde subdivide ile karşılaştırılarak doğrulanır; numune
yükleyici gerçek mm boyutlarını (ölçeklemesiz) korumalı.
"""

import numpy as np
import pytest
import trimesh

from src.nesting3d.models import NUMUNE_DIR, NUMUNE_QUANTITIES, numune_model_set
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0


def _box(w=20.0, d=20.0, h=20.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


def _l_shape():
    a = trimesh.creation.box(extents=(40, 10, 10))
    a.apply_translation((20, 5, 5))
    b = trimesh.creation.box(extents=(10, 10, 30))
    b.apply_translation((5, 5, 15))
    return trimesh.util.concatenate([a, b])


def test_slice_box_is_volume_exact():
    """20mm kutu @ pitch 5: slice tam 4x4x4=64 voxel vermeli (8000mm3).

    Subdivide yüzeye değen voxelleri de doldurur (5x5x5=125, ~2x hacim) —
    slice yönteminin varlık sebebi bu şişirmeyi önlemek.
    """
    sub = voxelize_part("box", _box(), PITCH, n_orientations=1)
    sli = voxelize_part("box", _box(), PITCH, n_orientations=1, method="slice")
    o = sli.orientations[0]
    assert o.shape == (4, 4, 4)
    assert o.voxel_count == 64  # solid box fully filled, volume-exact
    assert o.voxel_count <= sub.orientations[0].voxel_count


def test_slice_profiles_consistent():
    vp = voxelize_part("L", _l_shape(), PITCH, n_orientations=4, method="slice")
    for o in vp.orientations:
        nz = o.shape[2]
        assert o.filled.any()
        assert (o.bottom[o.filled] < o.top[o.filled]).all()
        assert (o.top <= nz).all()
        assert (o.bottom[~o.filled] == 0).all()


def test_slice_origin_is_voxel_centre():
    """Export hizalaması: voxel (0,0,0) merkezi = pitch/2 (min-köşe origin'de)."""
    vp = voxelize_part("box", _box(), PITCH, n_orientations=1, method="slice")
    assert np.allclose(vp.orientations[0].voxel_origin, PITCH / 2)


def test_numune_quantities_match_hoca_directive():
    assert NUMUNE_QUANTITIES == {
        "n1": 4, "n2": 16, "n3": 3, "n4": 15, "n5": 1, "n6": 3, "n7": 3, "n8": 3,
    }
    assert sum(NUMUNE_QUANTITIES.values()) == 48


@pytest.mark.skipif(not NUMUNE_DIR.exists(), reason="Numuneler/ klasörü yok")
def test_numune_model_set_native_scale():
    ms = numune_model_set()
    assert [name for name, *_ in ms] == list(NUMUNE_QUANTITIES)
    by_name = {name: (mesh, qty, disp) for name, mesh, qty, disp in ms}
    # n4 = 304.8mm (12") şerit — ölçekleme YAPILMAMALI
    mesh, qty, disp = by_name["n4"]
    assert qty == 15
    assert mesh.extents.max() == pytest.approx(304.8, abs=0.1)
    for name, (mesh, _qty, disp) in by_name.items():
        assert np.allclose(mesh.bounds[0], 0, atol=1e-6), name
        assert len(disp.faces) <= len(mesh.faces), name
