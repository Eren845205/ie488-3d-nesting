"""tests/test_bin3d_dropmap.py — drop_map hızlı yol eşdeğerlik testleri.

2026-06-14: drop_map'e kutu parçalar (dolu-dikdörtgen footprint + tek-değer
taban) için ayrılabilir kaydırmalı-maksimum hızlı yolu eklendi (~38x hız).
Bu testler hızlı yolun genel döngüyle BİRE BİR aynı sonucu verdiğini garanti
eder — optimizasyon sonucu değiştirmemeli, yalnız hızlandırmalı.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.voxelize import VoxelPart, Orientation


def _loop_drop_map(bin3d: Bin3D, orient: Orientation) -> np.ndarray:
    """Referans: drop_map'in genel döngü implementasyonu (hızlı yol BYPASS)."""
    fw, fh = orient.filled.shape
    npx, npy = bin3d.nx - fw + 1, bin3d.ny - fh + 1
    Z = np.zeros((npx, npy), dtype=np.int32)
    ci, cj = np.nonzero(orient.filled)
    for i, j, b in zip(ci, cj, orient.bottom[ci, cj]):
        np.maximum(Z, bin3d.height[i:i + npx, j:j + npy] - b, out=Z)
    np.maximum(Z, 0, out=Z)
    if bin3d.z_clearance:
        Z[Z > 0] += bin3d.z_clearance
    return Z


def _orient(filled: np.ndarray, bottom: np.ndarray, top: np.ndarray) -> Orientation:
    """Orientation kur — drop_map yalnız filled/bottom/top kullanır; rot/origin/
    grid alanları dummy (zorunlu ama bu testlerde ilgisiz)."""
    fw, fh = filled.shape
    fz = int(top.max()) if top.size else 1
    grid = np.zeros((fw, fh, max(fz, 1)), dtype=bool)
    return Orientation(
        rot_matrix=np.eye(4),
        voxel_origin=np.zeros(3),
        grid=grid,
        filled=filled,
        bottom=bottom,
        top=top,
        voxel_count=int(filled.sum()) * max(fz, 1),
    )


def _box_orient(fw: int, fh: int, fz: int, bottom_val: int = 0) -> Orientation:
    """Dolu-dikdörtgen kutu orientation (filled hep True, bottom tek-değer)."""
    filled = np.ones((fw, fh), dtype=bool)
    bottom = np.full((fw, fh), bottom_val, dtype=np.int32)
    top = np.full((fw, fh), bottom_val + fz, dtype=np.int32)
    return _orient(filled, bottom, top)


class TestDropMapFastEquivalence:
    @pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
    @pytest.mark.parametrize("fw,fh", [(1, 1), (2, 3), (10, 4), (24, 24), (7, 30), (30, 7)])
    def test_fast_equals_loop_box(self, seed, fw, fh):
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=2.0)
        b.height = np.random.default_rng(seed).integers(
            0, 40, size=b.height.shape
        ).astype(np.int32)
        orient = _box_orient(fw, fh, fz=3)
        npx, npy = b.nx - fw + 1, b.ny - fh + 1
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None, "kutu orientation hızlı yola girmeli"
        assert np.array_equal(fast, _loop_drop_map(b, orient))

    def test_fast_equals_loop_nonzero_bottom(self):
        b = Bin3D(plate_w_mm=80.0, plate_d_mm=80.0, pitch=2.0)
        b.height = np.random.default_rng(9).integers(
            0, 25, size=b.height.shape
        ).astype(np.int32)
        orient = _box_orient(8, 6, fz=4, bottom_val=5)  # tek-değer taban=5
        npx, npy = b.nx - 8 + 1, b.ny - 6 + 1
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None
        assert np.array_equal(fast, _loop_drop_map(b, orient))

    def test_drop_map_public_matches_loop(self):
        """Genel drop_map() (hızlı yolu içinde çağırır) döngü referansıyla aynı."""
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=2.0)
        b.height = np.random.default_rng(3).integers(
            0, 30, size=b.height.shape
        ).astype(np.int32)
        orient = _box_orient(12, 9, fz=2)
        assert np.array_equal(b.drop_map(orient), _loop_drop_map(b, orient))

    def test_concave_footprint_uses_loop_path(self):
        """Konkav footprint (delikli) hızlı yola GİRMEMELİ (None döner)."""
        b = Bin3D(plate_w_mm=60.0, plate_d_mm=60.0, pitch=2.0)
        filled = np.ones((5, 5), dtype=bool)
        filled[2, 2] = False  # delik → dolu-dikdörtgen değil
        bottom = np.zeros((5, 5), dtype=np.int32)
        top = np.ones((5, 5), dtype=np.int32)
        orient = _orient(filled, bottom, top)
        npx, npy = b.nx - 5 + 1, b.ny - 5 + 1
        assert b._drop_map_fast(orient, npx, npy) is None
        # ama genel drop_map yine doğru sonucu vermeli
        assert np.array_equal(b.drop_map(orient), _loop_drop_map(b, orient))

    def test_variable_bottom_uses_loop_path(self):
        """Değişken taban (dolu footprint ama farklı bottom) hızlı yola girmemeli."""
        b = Bin3D(plate_w_mm=60.0, plate_d_mm=60.0, pitch=2.0)
        filled = np.ones((4, 4), dtype=bool)
        bottom = np.zeros((4, 4), dtype=np.int32)
        bottom[0, 0] = 3  # değişken taban
        top = bottom + 2
        orient = _orient(filled, bottom, top)
        npx, npy = b.nx - 4 + 1, b.ny - 4 + 1
        assert b._drop_map_fast(orient, npx, npy) is None
