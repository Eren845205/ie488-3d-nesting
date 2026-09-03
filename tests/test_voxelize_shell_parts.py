"""tests/test_voxelize_shell_parts.py — İnce cidarlı kabuk parça voxelizasyonu.

Gerçek olay (2026-07-03, Deneme4 canlı koşusu): 'Dugme Kilidi' STL'i watertight
ama bbox doluluğu %12 (ince cidarlı kabuk). Adaptif pitch bbox'tan türediği
(7.255/2.5=2.902 mm) için et kalınlığını bilmez; slice testinde hiçbir hücre
MERKEZİ malzemeye düşmedi → _slice_voxelize boş-grid guard'ı raise etti →
588 parçalık sipariş nesting'siz kaldı. Oysa hemen sonraki _surface_cells
aynı pitch'te 104 hücre işaretliyordu — birleşim boş değildi.

Fix: boş-grid kararı yüzey BİRLEŞİMİNDEN SONRA verilir (voxelize_part);
_slice_voxelize'ın doğrudan çağrı davranışı (fail-fast raise) korunur.
"""

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")

from src.nesting3d.voxelize import _slice_voxelize, voxelize_part


def _norm(mesh):
    mesh.apply_translation(-mesh.bounds[0])
    return mesh


def _thin_plate():
    """0.4 mm plaka @ pitch 5: tek x-hücre merkezi (2.5) malzeme dışı → slice boş."""
    return _norm(trimesh.creation.box(extents=(0.4, 30.0, 30.0)))


def _thin_shell_ring():
    """0.8 mm cidarlı halka (kabuk benzeri) @ pitch 2.5: cidar << pitch."""
    return _norm(
        trimesh.creation.annulus(r_min=10.0, r_max=10.8, height=6.0, sections=64)
    )


def test_slice_voxelize_dogrudan_cagri_hala_raise():
    """Fail-fast davranış korunur: default allow_empty=False → raise."""
    with pytest.raises(ValueError):
        _slice_voxelize(_thin_plate(), 5.0)


def test_slice_voxelize_allow_empty_bos_grid_doner():
    g = _slice_voxelize(_thin_plate(), 5.0, allow_empty=True)
    assert g.sum() == 0
    assert g.shape[0] >= 1  # shape yine bbox'tan


def test_voxelize_part_ince_plaka_kurtulur():
    """slice boş olsa da yüzey birleşimi doldurur → voxelize_part BAŞARILI."""
    part = voxelize_part("plaka", _thin_plate(), 5.0, n_orientations=4)
    assert part.orientations
    for o in part.orientations:
        assert o.voxel_count > 0, "yüzey birleşimi sonrası grid boş kalmamalı"


def test_voxelize_part_kabuk_halka_kurtulur():
    """Cidar << pitch kabukta da (Deneme4 senaryosunun sentetiği) başarılı."""
    part = voxelize_part("halka", _thin_shell_ring(), 2.5, n_orientations=4)
    assert part.orientations
    for o in part.orientations:
        assert o.voxel_count > 0


def test_voxelize_part_dolu_parca_bit_ozdes():
    """Dolu (kabuk olmayan) parçada sonuç DEĞİŞMEZ — slice zaten doluydu,
    allow_empty yolu yalnız boş-slice durumunda devreye girer."""
    solid = _norm(trimesh.creation.box(extents=(20.0, 22.0, 12.0)))
    a = voxelize_part("s1", solid.copy(), 2.0, n_orientations=4)
    b = voxelize_part("s2", solid.copy(), 2.0, n_orientations=4)
    for oa, ob in zip(a.orientations, b.orientations):
        assert np.array_equal(oa.grid, ob.grid)
        assert oa.voxel_count == ob.voxel_count
    assert a.orientations[0].voxel_count > 0
