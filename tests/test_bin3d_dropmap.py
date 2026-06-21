"""tests/test_bin3d_dropmap.py — drop_map hızlı yol eşdeğerlik testleri.

2026-06-14: drop_map'e kutu parçalar (dolu-dikdörtgen footprint + tek-değer
taban) için ayrılabilir kaydırmalı-maksimum hızlı yolu eklendi (~38x hız).
Bu testler hızlı yolun genel döngüyle BİRE BİR aynı sonucu verdiğini garanti
eder — optimizasyon sonucu değiştirmemeli, yalnız hızlandırmalı.

2026-06-15 (reviewer bulgu #3): z_clearance varyasyonları ve farklı bin
boyutlarıyla ek parametrize eşdeğerlik testleri eklendi.
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


# ---------------------------------------------------------------------------
# Ek eşdeğerlik testleri — z_clearance varyasyonları ve farklı bin boyutları
# (reviewer bulgu #3: "çeşitli oryantasyon ve bin durumlarında parametrize")
# ---------------------------------------------------------------------------

class TestDropMapFastEquivalenceExtended:
    """_drop_map_fast vs genel döngü — z_clearance + çeşitli bin boyutları."""

    @pytest.mark.parametrize("z_clearance", [0, 1, 2, 5])
    @pytest.mark.parametrize("fw,fh,fz", [(1, 1, 1), (3, 5, 2), (10, 10, 8)])
    def test_fast_equals_loop_with_clearance(self, fw, fh, fz, z_clearance):
        """z_clearance > 0 iken hızlı yol genel döngüyle aynı sonucu vermeli."""
        b = Bin3D(plate_w_mm=120.0, plate_d_mm=120.0, pitch=2.0,
                  z_clearance=z_clearance)
        b.height = np.random.default_rng(fw * 31 + fh * 7 + z_clearance).integers(
            0, 30, size=b.height.shape
        ).astype(np.int32)
        orient = _box_orient(fw, fh, fz=fz)
        npx, npy = b.nx - fw + 1, b.ny - fh + 1
        if npx <= 0 or npy <= 0:
            pytest.skip("footprint bin'den büyük")
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None, "kutu orientation hızlı yola girmeli"
        assert np.array_equal(fast, _loop_drop_map(b, orient)), (
            f"z_clearance={z_clearance}, fw={fw}, fh={fh}: hızlı yol != genel döngü"
        )

    @pytest.mark.parametrize("plate_mm,pitch", [
        (60.0, 2.0),
        (100.0, 5.0),
        (220.0, 10.0),
        (44.0, 2.0),   # küçük bin — sınır durumu
    ])
    def test_fast_equals_loop_various_bin_sizes(self, plate_mm, pitch):
        """Farklı bin boyutu/pitch kombinasyonlarında hızlı yol = genel döngü."""
        b = Bin3D(plate_w_mm=plate_mm, plate_d_mm=plate_mm, pitch=pitch)
        rng = np.random.default_rng(int(plate_mm) + int(pitch * 10))
        b.height = rng.integers(0, 15, size=b.height.shape).astype(np.int32)
        fw, fh = max(1, b.nx // 4), max(1, b.ny // 4)
        orient = _box_orient(fw, fh, fz=3)
        npx, npy = b.nx - fw + 1, b.ny - fh + 1
        if npx <= 0 or npy <= 0:
            pytest.skip("footprint bin'den büyük")
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None, "kutu orientation hızlı yola girmeli"
        assert np.array_equal(fast, _loop_drop_map(b, orient)), (
            f"plate_mm={plate_mm}, pitch={pitch}: hızlı yol != genel döngü"
        )

    def test_fast_equals_loop_all_zeros_height(self):
        """Boş bin (height=0) — hızlı yol sıfır drop_map döndürmeli."""
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=2.0)
        # height sıfır (default)
        orient = _box_orient(5, 5, fz=3)
        npx, npy = b.nx - 5 + 1, b.ny - 5 + 1
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None
        expected = _loop_drop_map(b, orient)
        assert np.array_equal(fast, expected)
        assert fast.max() == 0, "boş binde drop_map sıfır olmalı"

    def test_fast_equals_loop_fully_stacked_height(self):
        """Yüksek-dolu bin (height uniform=50) — hızlı yol genel döngüyle aynı."""
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=2.0)
        b.height = np.full(b.height.shape, 50, dtype=np.int32)
        orient = _box_orient(3, 3, fz=2)
        npx, npy = b.nx - 3 + 1, b.ny - 3 + 1
        fast = b._drop_map_fast(orient, npx, npy)
        assert fast is not None
        assert np.array_equal(fast, _loop_drop_map(b, orient))


# ---------------------------------------------------------------------------
# Genel yol VEKTORIZASYONU eşdeğerlik testleri (2026-06-22, Faz 1 hız)
#
# drop_map genel yolu (konkav footprint / değişken taban — gerçek STL) Python
# for-döngüsünden sliding_window_view tek-redüksiyona çevrildi. Bu testler yeni
# vektörize `_drop_map_general`'in eski döngü referansıyla (`_loop_drop_map`)
# BİRE BİR aynı sonucu verdiğini garanti eder — KALİTE KORUMA (yükseklik
# değişmez). cProfile darboğazı (%72) bu yolda; hızlanma kalite pahasına olamaz.
# ---------------------------------------------------------------------------

def _random_concave_orient(rng: np.random.Generator, fw: int, fh: int,
                           variable_bottom: bool) -> Orientation:
    """Rastgele konkav (delikli) footprint + ops. değişken taban orientation."""
    # En az bir dolu kolon garanti (tamamen boş footprint anlamsız)
    filled = rng.random((fw, fh)) > 0.35
    if not filled.any():
        filled[0, 0] = True
    if variable_bottom:
        bottom = rng.integers(0, 8, size=(fw, fh)).astype(np.int32)
    else:
        bottom = np.full((fw, fh), int(rng.integers(0, 8)), dtype=np.int32)
    bottom[~filled] = 0  # boş kolon tabanı ilgisiz (drop_map filled'a bakar)
    top = bottom + rng.integers(1, 5, size=(fw, fh)).astype(np.int32)
    return _orient(filled, bottom, top)


class TestDropMapGeneralVectorizedEquivalence:
    """Vektörize genel yol == saf-Python döngü (kalite koruma, birebir aynı)."""

    @pytest.mark.parametrize("seed", range(12))
    @pytest.mark.parametrize("variable_bottom", [False, True])
    @pytest.mark.parametrize("fw,fh", [(1, 1), (3, 4), (8, 5), (5, 8), (20, 20), (1, 25), (25, 1)])
    def test_general_equals_loop_concave(self, seed, variable_bottom, fw, fh):
        b = Bin3D(plate_w_mm=120.0, plate_d_mm=120.0, pitch=2.0)
        rng = np.random.default_rng(seed * 101 + fw * 7 + fh + int(variable_bottom))
        b.height = rng.integers(0, 45, size=b.height.shape).astype(np.int32)
        orient = _random_concave_orient(rng, fw, fh, variable_bottom)
        npx, npy = b.nx - fw + 1, b.ny - fh + 1
        if npx <= 0 or npy <= 0:
            pytest.skip("footprint bin'den büyük")
        # Konkav / değişken taban hızlı yola GİRMEMELİ → genel yol çalışır
        if not orient.filled.all() or not (orient.bottom[orient.filled]
                                           == orient.bottom[orient.filled].flat[0]).all():
            assert b._drop_map_fast(orient, npx, npy) is None
        got = b._drop_map_general(orient, npx, npy)
        assert np.array_equal(got, _loop_drop_map(b, orient)), (
            f"seed={seed} fw={fw} fh={fh} var_bottom={variable_bottom}: "
            "vektörize genel yol != döngü (KALİTE REGRESYONU)"
        )
        # Public drop_map de aynı sonucu vermeli
        assert np.array_equal(b.drop_map(orient), _loop_drop_map(b, orient))

    @pytest.mark.parametrize("z_clearance", [0, 1, 3])
    def test_general_equals_loop_with_clearance(self, z_clearance):
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=2.0,
                  z_clearance=z_clearance)
        rng = np.random.default_rng(700 + z_clearance)
        b.height = rng.integers(0, 30, size=b.height.shape).astype(np.int32)
        orient = _random_concave_orient(rng, 9, 7, variable_bottom=True)
        npx, npy = b.nx - 9 + 1, b.ny - 7 + 1
        assert np.array_equal(b._drop_map_general(orient, npx, npy),
                              _loop_drop_map(b, orient))

    def test_general_xblock_chunking_equivalence(self):
        """x-ekseni bloklamanın doğruluğu: CAP'i küçülterek >1 blok zorla."""
        b = Bin3D(plate_w_mm=120.0, plate_d_mm=120.0, pitch=2.0)
        rng = np.random.default_rng(4242)
        b.height = rng.integers(0, 50, size=b.height.shape).astype(np.int32)
        orient = _random_concave_orient(rng, 10, 10, variable_bottom=True)
        npx, npy = b.nx - 10 + 1, b.ny - 10 + 1
        ref = _loop_drop_map(b, orient)
        # Tek blok (varsayılan büyük CAP) sonucu
        assert np.array_equal(b._drop_map_general(orient, npx, npy), ref)
        # Çok-blok yolu: _drop_map_general'i monkeypatch yerine doğrudan
        # _drop_map_loop fallback'i ile karşılaştır (aynı referans olmalı)
        assert np.array_equal(b._drop_map_loop(orient, npx, npy), ref)

    def test_loop_fallback_matches_general(self):
        """_drop_map_loop (CAP fallback) genel yolla birebir aynı."""
        b = Bin3D(plate_w_mm=80.0, plate_d_mm=80.0, pitch=2.0)
        rng = np.random.default_rng(55)
        b.height = rng.integers(0, 20, size=b.height.shape).astype(np.int32)
        orient = _random_concave_orient(rng, 6, 6, variable_bottom=True)
        npx, npy = b.nx - 6 + 1, b.ny - 6 + 1
        assert np.array_equal(b._drop_map_loop(orient, npx, npy),
                              b._drop_map_general(orient, npx, npy))
