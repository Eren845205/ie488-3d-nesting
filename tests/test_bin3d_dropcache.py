"""tests/test_bin3d_dropcache.py — H-16 dirty-region drop_map onbellegi.

2026-07-05: drop_map'e OPT-IN (drop_cache=True) dirty-region onbellegi eklendi.
Ayni footprint-anahtarli (id(orient)) sorgu icin son tam Z saklanir; sonraki
cagrida yalniz aradaki place()'lerin kirlettigi aday-penceresi yeniden
hesaplanir. Bu testler onbellekli yolun onbelleksiz (uretim default) yolla
BIRE BIR ayni drop_map ve place_in_order sonucu urettigini DONDURUR:

  - Kalite garantisi: yukseklik/yerlesim onbellekten ETKILENMEZ (birebir).
  - Kapali-yol dokunulmazligi: drop_cache=False iken davranis ozdes
    (mevcut test_bin3d_dropmap.py suite'i degismeden gecer).

Kapsam: konkav/degisken-taban footprint, pencere kenar/kose/tasma, tip-gecisi
invalidasyonu, bellek-tavani dusurme (eviction) yolu, degismedi-hit yolu,
dblf place_in_order cache'li vs cache'siz ayni yerlesim listesi.
"""

from __future__ import annotations

from typing import List

import numpy as np
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import place_in_order
from src.nesting3d.voxelize import Orientation, VoxelPart


# --------------------------------------------------------------------------
# Kurulum yardimcilari
# --------------------------------------------------------------------------

def _orient(filled: np.ndarray, bottom: np.ndarray, top: np.ndarray) -> Orientation:
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
    filled = np.ones((fw, fh), dtype=bool)
    bottom = np.full((fw, fh), bottom_val, dtype=np.int32)
    top = np.full((fw, fh), bottom_val + fz, dtype=np.int32)
    return _orient(filled, bottom, top)


def _concave_orient(rng: np.random.Generator, fw: int, fh: int,
                    variable_bottom: bool) -> Orientation:
    filled = rng.random((fw, fh)) > 0.35
    if not filled.any():
        filled[0, 0] = True
    if variable_bottom:
        bottom = rng.integers(0, 8, size=(fw, fh)).astype(np.int32)
    else:
        bottom = np.full((fw, fh), int(rng.integers(0, 8)), dtype=np.int32)
    bottom[~filled] = 0
    top = bottom + rng.integers(1, 5, size=(fw, fh)).astype(np.int32)
    return _orient(filled, bottom, top)


def _part(orient: Orientation, pid: str) -> VoxelPart:
    """place() icin minimal VoxelPart (mesh drop_map/place'te kullanilmaz)."""
    return VoxelPart(id=pid, name=pid.rstrip("0123456789_") or pid,
                     mesh=None, orientations=[orient],
                     volume_voxels=int(orient.filled.sum()))


def _loop_full(bin3d: Bin3D, orient: Orientation) -> np.ndarray:
    """Referans full drop_map (dongu), onbellekten TAMAMEN bagimsiz."""
    fw, fh = orient.filled.shape
    npx, npy = bin3d.nx - fw + 1, bin3d.ny - fh + 1
    if npx <= 0 or npy <= 0:
        return None
    Z = np.zeros((npx, npy), dtype=np.int32)
    ci, cj = np.nonzero(orient.filled)
    for i, j, b in zip(ci, cj, orient.bottom[ci, cj]):
        np.maximum(Z, bin3d.height[i:i + npx, j:j + npy] - b, out=Z)
    np.maximum(Z, 0, out=Z)
    if bin3d.z_clearance:
        Z[Z > 0] += bin3d.z_clearance
    return Z


# --------------------------------------------------------------------------
# Cekirdek esdeglik: cache'li vs cache'siz drop_map BIREBIR
# --------------------------------------------------------------------------

class TestDropCacheEquivalence:
    """Onbellekli drop_map == onbelleksiz drop_map, uzun place dizisi boyunca."""

    @pytest.mark.parametrize("seed", range(8))
    @pytest.mark.parametrize("z_clearance", [0, 1])
    def test_cache_equals_uncached_random_sequence(self, seed, z_clearance):
        rng = np.random.default_rng(seed * 17 + z_clearance)
        # Sorgu havuzu: kutu + konkav + degisken-taban karisik. AYNI Orientation
        # nesneleri iki bin'de de sorgulanir (id-anahtar hit'i tetiklenir).
        pool: List[Orientation] = [
            _box_orient(6, 6, fz=3),
            _box_orient(4, 9, fz=2, bottom_val=2),
            _concave_orient(rng, 8, 5, variable_bottom=False),
            _concave_orient(rng, 5, 8, variable_bottom=True),
            _concave_orient(rng, 10, 10, variable_bottom=True),
        ]
        parts = [_part(o, f"p{i}") for i, o in enumerate(pool)]

        b_ref = Bin3D(120.0, 120.0, pitch=2.0, z_clearance=z_clearance)
        b_cache = Bin3D(120.0, 120.0, pitch=2.0, z_clearance=z_clearance,
                        drop_cache=True, drop_cache_cap_mb=50.0)

        for step in range(40):
            for o in pool:
                z_ref = b_ref.drop_map(o)
                z_cache = b_cache.drop_map(o)
                assert np.array_equal(z_ref, z_cache), (
                    f"seed={seed} zc={z_clearance} step={step}: cache != ref")
                # bagimsiz dongu referansiyla da dogrula (kalite garantisi)
                assert np.array_equal(z_ref, _loop_full(b_ref, o))

            # sonraki yerlestirme
            pi = int(rng.integers(0, len(parts)))
            part = parts[pi]
            o = part.orientations[0]
            fw, fh = o.filled.shape
            npx, npy = b_ref.nx - fw + 1, b_ref.ny - fh + 1
            x = int(rng.integers(0, npx))
            y = int(rng.integers(0, npy))
            z = b_ref.drop_z(o, x, y)
            b_ref.place(part, 0, x, y, z)
            b_cache.place(part, 0, x, y, z)
            assert b_ref.max_height_voxels() == b_cache.max_height_voxels()

        stats = b_cache.drop_cache_stats()
        assert stats["hits"] > 0, "cache hic HIT vermedi (mekanizma calismiyor)"

    def test_unchanged_hit_no_recompute(self):
        """Ayni orient art arda (place YOK) -> ikinci cagri _DC_UNCHANGED hit."""
        b = Bin3D(80.0, 80.0, pitch=2.0, drop_cache=True)
        o = _box_orient(5, 5, fz=3)
        z1 = b.drop_map(o)
        h0 = b.drop_cache_stats()["hits"]
        z2 = b.drop_map(o)
        assert np.array_equal(z1, z2)
        assert b.drop_cache_stats()["hits"] == h0 + 1

    def test_boundary_corner_windows(self):
        """Kenar/kose/tasma: parca grid koselerine/kenarlarina yerlesir; dirty
        pencere clamp'lenir; sonuc yine birebir."""
        rng = np.random.default_rng(99)
        o_query = _concave_orient(rng, 7, 7, variable_bottom=True)
        part = _part(_box_orient(6, 6, fz=4), "blk")
        b_ref = Bin3D(60.0, 60.0, pitch=2.0)
        b_cache = Bin3D(60.0, 60.0, pitch=2.0, drop_cache=True)
        nx = b_ref.nx
        # kose/kenar yerlesimleri: (0,0), (max,max), (0,max), (max,0), orta
        pw = nx - 6
        for (x, y) in [(0, 0), (pw, pw), (0, pw), (pw, 0), (pw // 2, pw // 2)]:
            z = b_ref.drop_z(part.orientations[0], x, y)
            b_ref.place(part, 0, x, y, z)
            b_cache.place(part, 0, x, y, z)
            assert np.array_equal(b_ref.drop_map(o_query),
                                  b_cache.drop_map(o_query))
            assert np.array_equal(b_cache.drop_map(o_query),
                                  _loop_full(b_ref, o_query))

    def test_type_transition_invalidation(self):
        """Tip-gecisi: iki farkli footprint donusumlu sorgulanir; her birinin
        cache'i digerinin place'leriyle dogru invalidate olur."""
        rng = np.random.default_rng(7)
        oa = _concave_orient(rng, 6, 8, variable_bottom=True)
        ob = _concave_orient(rng, 9, 4, variable_bottom=False)
        pa = _part(_box_orient(5, 5, fz=3), "a")
        pb = _part(_box_orient(4, 7, fz=2), "b")
        b_ref = Bin3D(90.0, 90.0, pitch=2.0)
        b_cache = Bin3D(90.0, 90.0, pitch=2.0, drop_cache=True)
        for step in range(25):
            for o in (oa, ob):
                assert np.array_equal(b_ref.drop_map(o), b_cache.drop_map(o))
            part = pa if step % 2 == 0 else pb
            o0 = part.orientations[0]
            fw, fh = o0.filled.shape
            x = int(rng.integers(0, b_ref.nx - fw + 1))
            y = int(rng.integers(0, b_ref.ny - fh + 1))
            z = b_ref.drop_z(o0, x, y)
            b_ref.place(part, 0, x, y, z)
            b_cache.place(part, 0, x, y, z)

    def test_memory_cap_eviction_path(self):
        """Cok kucuk bellek tavani -> her put evict eder -> cogu cagri tam
        hesap; sonuc HALA birebir (eviction dogrulugu bozmaz)."""
        rng = np.random.default_rng(3)
        pool = [_concave_orient(rng, 6, 6, True) for _ in range(4)]
        parts = [_part(_box_orient(5, 5, 3), f"p{i}") for i in range(4)]
        b_ref = Bin3D(80.0, 80.0, pitch=2.0)
        # ~kucuk tavan: tek Z ~ (35x35)*4B ~ 5KB; cap 0.002MB ~ 2KB -> surekli evict
        b_cache = Bin3D(80.0, 80.0, pitch=2.0, drop_cache=True,
                        drop_cache_cap_mb=0.002)
        for step in range(20):
            for o in pool:
                assert np.array_equal(b_ref.drop_map(o), b_cache.drop_map(o))
            part = parts[int(rng.integers(0, 4))]
            o0 = part.orientations[0]
            fw, fh = o0.filled.shape
            x = int(rng.integers(0, b_ref.nx - fw + 1))
            y = int(rng.integers(0, b_ref.ny - fh + 1))
            z = b_ref.drop_z(o0, x, y)
            b_ref.place(part, 0, x, y, z)
            b_cache.place(part, 0, x, y, z)
        assert b_cache.drop_cache_stats()["evictions"] > 0, "eviction yolu tetiklenmedi"

    def test_drop_region_equals_loop_window(self):
        """_drop_region (yerel yeniden-hesap) tam-dongu penceresiyle birebir."""
        rng = np.random.default_rng(11)
        b = Bin3D(100.0, 100.0, pitch=2.0, z_clearance=1)
        b.height = rng.integers(0, 40, size=b.height.shape).astype(np.int32)
        o = _concave_orient(rng, 8, 6, variable_bottom=True)
        full = _loop_full(b, o)
        npx, npy = b.nx - 8 + 1, b.ny - 6 + 1
        for (x0, x1, y0, y1) in [(0, 5, 0, 5), (10, 20, 8, 15),
                                 (npx - 4, npx, npy - 4, npy)]:
            reg = b._drop_region(o, x0, x1, y0, y1)
            assert np.array_equal(reg, full[x0:x1, y0:y1])

    def test_boundary_corner_windows_z_clearance(self):
        """Kenar/kose yerlesim + z_clearance=1: incremental _drop_region_into
        z_clearance dali (bin3d.py:199-200) calisir; cache'li vs cache'siz
        birebir (MEDIUM-1b: z_clearance>0 dirty-region kapsami bosluk kapama)."""
        rng = np.random.default_rng(101)
        o_query = _concave_orient(rng, 7, 7, variable_bottom=True)
        part = _part(_box_orient(6, 6, fz=4), "blk")
        b_ref = Bin3D(60.0, 60.0, pitch=2.0, z_clearance=1)
        b_cache = Bin3D(60.0, 60.0, pitch=2.0, z_clearance=1, drop_cache=True)
        # onbellegi bir kez doldur (sonraki place'ler artimli yeniden-hesabi
        # tetiklesin, ilk sorgu MISS olmasin)
        assert np.array_equal(b_ref.drop_map(o_query), b_cache.drop_map(o_query))
        nx = b_ref.nx
        pw = nx - 6
        for (x, y) in [(0, 0), (pw, pw), (0, pw), (pw, 0), (pw // 2, pw // 2)]:
            z = b_ref.drop_z(part.orientations[0], x, y)
            b_ref.place(part, 0, x, y, z)
            b_cache.place(part, 0, x, y, z)
            assert np.array_equal(b_ref.drop_map(o_query),
                                  b_cache.drop_map(o_query))
            assert np.array_equal(b_cache.drop_map(o_query),
                                  _loop_full(b_ref, o_query))
        assert b_cache.drop_cache_stats()["hits"] > 0


# --------------------------------------------------------------------------
# MEDIUM-1a: _dc_windows_since None-fallback dali (>96 pencere veya alan cap)
# --------------------------------------------------------------------------

class TestWindowsSinceNoneFallback:
    """Sorgular arasinda cok sayida dagilmis place yapilinca (>96 pencere)
    _dc_windows_since None doner -> tam-hesaba dusulur (bin3d.py:249-250).
    Dogruluk yine birebir korunur, sadece hizli-yol atlanir."""

    def test_many_scattered_places_trigger_fallback(self):
        rng = np.random.default_rng(21)
        b_ref = Bin3D(200.0, 200.0, pitch=2.0)
        b_cache = Bin3D(200.0, 200.0, pitch=2.0, drop_cache=True,
                        drop_cache_cap_mb=50.0)
        watched = _box_orient(6, 6, fz=3)
        filler_orient = _box_orient(2, 2, fz=1)
        filler = _part(filler_orient, "filler")

        # onbellegi bir kez doldur (watched anahtari kayitli olsun)
        z0_ref = b_ref.drop_map(watched)
        z0_cache = b_cache.drop_map(watched)
        assert np.array_equal(z0_ref, z0_cache)

        # sorgular ARASINDA watched'a HIC dokunmadan >96 dagilmis place yap
        # -> _dc_windows_since log'da 96'dan fazla ayri pencere gorur -> None
        npx, npy = b_ref.nx - 2 + 1, b_ref.ny - 2 + 1
        n_places = 110
        for _ in range(n_places):
            x = int(rng.integers(0, npx))
            y = int(rng.integers(0, npy))
            z = b_ref.drop_z(filler_orient, x, y)
            b_ref.place(filler, 0, x, y, z)
            b_cache.place(filler, 0, x, y, z)

        z1_ref = b_ref.drop_map(watched)
        z1_cache = b_cache.drop_map(watched)
        assert np.array_equal(z1_ref, z1_cache)
        assert np.array_equal(z1_cache, _loop_full(b_ref, watched))

        stats = b_cache.drop_cache_stats()
        assert stats["fallbacks"] > 0, (
            ">96 dagilmis place sonrasi None-fallback dali tetiklenmedi")


# --------------------------------------------------------------------------
# Kapali-yol dokunulmazligi
# --------------------------------------------------------------------------

class TestDropCacheDisabledUnchanged:
    """drop_cache=False (uretim default) -> davranis BIREBIR eski."""

    def test_disabled_matches_loop(self):
        rng = np.random.default_rng(5)
        b = Bin3D(100.0, 100.0, pitch=2.0)
        b.height = rng.integers(0, 30, size=b.height.shape).astype(np.int32)
        o = _concave_orient(rng, 9, 7, variable_bottom=True)
        assert np.array_equal(b.drop_map(o), _loop_full(b, o))
        # kapali iken cache yapilari bos kalir
        assert b.drop_cache_stats()["hits"] == 0
        assert b.drop_cache_stats()["keys"] == 0

    def test_disabled_place_no_log(self):
        b = Bin3D(60.0, 60.0, pitch=2.0)
        part = _part(_box_orient(5, 5, 3), "x")
        b.place(part, 0, 0, 0, 0)
        assert len(b._dc_log) == 0
        assert b._dc_seq == 0


# --------------------------------------------------------------------------
# dblf place_in_order: cache'li vs cache'siz AYNI yerlesim listesi
# --------------------------------------------------------------------------

class TestPlaceInOrderCacheEquivalence:
    def test_place_in_order_identical(self):
        rng = np.random.default_rng(42)
        # farkli tiplerden bir parca listesi; bazi tipler tekrarli (paylasan
        # orientation objesi -> cache hit); place_in_order tum oryantasyonlari dener
        types = [
            _box_orient(6, 4, 3),
            _box_orient(3, 7, 2, bottom_val=1),
            _concave_orient(rng, 5, 5, True),
        ]
        parts: List[VoxelPart] = []
        for ti, o in enumerate(types):
            for k in range(6):  # ayni tip -> paylasilan orient nesnesi
                parts.append(VoxelPart(id=f"t{ti}_{k}", name=f"t{ti}",
                                       mesh=None, orientations=[o],
                                       volume_voxels=int(o.filled.sum())))

        def orient_for(_i, part):
            return range(len(part.orientations))

        b_ref = Bin3D(100.0, 100.0, pitch=2.0)
        b_cache = Bin3D(100.0, 100.0, pitch=2.0, drop_cache=True)
        pl_ref = place_in_order(list(parts), b_ref, orient_for)
        pl_cache = place_in_order(list(parts), b_cache, orient_for)

        assert len(pl_ref) == len(pl_cache)
        for a, c in zip(pl_ref, pl_cache):
            assert (a.part_id, a.x, a.y, a.z, a.orientation_idx) == \
                   (c.part_id, c.x, c.y, c.z, c.orientation_idx)
        assert b_ref.max_height_voxels() == b_cache.max_height_voxels()
        assert b_cache.drop_cache_stats()["hits"] > 0
