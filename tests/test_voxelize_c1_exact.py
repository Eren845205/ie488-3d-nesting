"""C1 hız optimizasyonu birebirlik testleri (2026-07-02).

`_surface_cells` eksen-bazlı/buffer-reuse yeniden yazımı ve `_slice_voxelize`
bbox-kırpması, ESKİ implementasyonla BİT-DÜZEYİ aynı grid üretmek zorunda
(birebirlik kapısı — YONTEM_HARITASI §6 madde 5). Bu dosya eski kodun donmuş
kopyalarını referans alır; üretim fonksiyonu ne zaman değişirse değişsin
özdeşlik burada sınanmaya devam eder.
"""

import numpy as np
import pytest
import trimesh

from src.nesting3d.voxelize import _slice_voxelize, _surface_cells


# ---------------------------------------------------------------------------
# DONMUŞ referanslar — 2026-07-02 öncesi üretim kodunun birebir kopyası
# ---------------------------------------------------------------------------

def _surface_cells_reference(mesh, pitch, shape):
    tri = mesh.triangles
    edge = np.linalg.norm(tri - np.roll(tri, 1, axis=1), axis=2).max(axis=1)
    k_per_tri = np.maximum(np.ceil(edge / (pitch / 2.0)).astype(int), 1)

    grid = np.zeros(shape, dtype=bool)

    def _mark(points):
        idx = np.floor(points / pitch).astype(int)
        np.clip(idx, 0, np.asarray(shape) - 1, out=idx)
        grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True

    _PTS_CHUNK_ELEMS = 8_000_000
    for k in np.unique(k_per_tri):
        sub = tri[k_per_tri == k]
        ii, jj = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (ii + jj) <= k
        u = (ii[keep] / k)[None, :, None]
        v = (jj[keep] / k)[None, :, None]
        n_bary = int(keep.sum())
        chunk_mk = max(1, _PTS_CHUNK_ELEMS // max(1, n_bary * 3))
        for s0 in range(0, sub.shape[0], chunk_mk):
            chunk = sub[s0:s0 + chunk_mk]
            pts = (chunk[:, 0:1, :] * (1.0 - u - v)
                   + chunk[:, 1:2, :] * u
                   + chunk[:, 2:3, :] * v)
            _mark(pts.reshape(-1, 3))
    return grid


def _slice_voxelize_reference(mesh, pitch):
    from shapely import contains_xy

    ext = mesh.extents
    n = np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1)
    zs = np.minimum((np.arange(n[2]) + 0.5) * pitch, ext[2] - 1e-6)
    sections = mesh.section_multiplane(
        plane_origin=[0.0, 0.0, 0.0], plane_normal=[0.0, 0.0, 1.0], heights=zs
    )
    xs = (np.arange(n[0]) + 0.5) * pitch
    ys = (np.arange(n[1]) + 0.5) * pitch
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    px, py = XX.ravel(), YY.ravel()

    grid = np.zeros((n[0], n[1], n[2]), dtype=bool)
    for k, sec in enumerate(sections):
        if sec is None:
            continue
        mask = np.zeros(px.shape, dtype=bool)
        for poly in sec.polygons_full:
            mask |= contains_xy(poly, px, py)
        grid[:, :, k] = mask.reshape(n[0], n[1])
    if not grid.any():
        raise ValueError("boş grid")
    return grid


# ---------------------------------------------------------------------------
# Sentetik test gövdeleri — sınır durumları kasıtlı:
#   - pitch-hizalı köşeler (floor tam sınırda)
#   - ince plaka (dev düz üçgen → büyük k, chunk döngüsü)
#   - irrasyonel koordinatlar (icosphere — hizalı olmayan yüzey)
#   - bileşik L (içbükey)
# ---------------------------------------------------------------------------

def _norm(m):
    m.apply_translation(-m.bounds[0])
    return m


def _shapes():
    box = _norm(trimesh.creation.box(extents=(20.0, 20.0, 20.0)))
    plate = _norm(trimesh.creation.box(extents=(120.0, 90.0, 3.0)))
    sphere = _norm(trimesh.creation.icosphere(subdivisions=3, radius=17.3))
    a = trimesh.creation.box(extents=(40, 10, 10))
    a.apply_translation((20, 5, 5))
    b = trimesh.creation.box(extents=(10, 10, 30))
    b.apply_translation((5, 5, 15))
    lshape = _norm(trimesh.util.concatenate([a, b]))
    cyl = _norm(trimesh.creation.cylinder(radius=11.7, height=44.0, sections=48))
    return [("box", box), ("plate", plate), ("sphere", sphere),
            ("L", lshape), ("cyl", cyl)]


@pytest.mark.parametrize("pitch", [5.0, 2.0, 1.0])
def test_surface_cells_bitwise_identical(pitch):
    for name, mesh in _shapes():
        ext = mesh.extents
        shape = tuple(np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1))
        ref = _surface_cells_reference(mesh, pitch, shape)
        new = _surface_cells(mesh, pitch, shape)
        assert np.array_equal(ref, new), f"{name} @ {pitch}mm: grid FARKLI"


@pytest.mark.parametrize("pitch", [5.0, 2.0, 1.0])
def test_slice_voxelize_bitwise_identical(pitch):
    for name, mesh in _shapes():
        ref = _slice_voxelize_reference(mesh, pitch)
        new = _slice_voxelize(mesh, pitch)
        assert np.array_equal(ref, new), f"{name} @ {pitch}mm: grid FARKLI"


def test_surface_cells_chunk_boundary():
    """Chunk sınırı sonucu değiştirmemeli — küçük chunk tavanıyla da özdeş."""
    import src.nesting3d.voxelize as vx

    mesh = _shapes()[2][1]  # sphere (çok üçgen, çeşitli k)
    pitch = 2.0
    shape = tuple(np.maximum(np.ceil(mesh.extents / pitch - 1e-9).astype(int), 1))
    ref = _surface_cells_reference(mesh, pitch, shape)

    orig = vx._SURF_CHUNK_ELEMS
    try:
        vx._SURF_CHUNK_ELEMS = 1_000  # aşırı küçük chunk → sınırlar her yerde
        new = _surface_cells(mesh, pitch, shape)
    finally:
        vx._SURF_CHUNK_ELEMS = orig
    assert np.array_equal(ref, new)


def test_slice_voxelize_empty_grid_still_raises():
    """Fazla kaba pitch'te açık ValueError davranışı korunmalı."""
    # x'te 0.4mm: tek x-hücresinin merkezi (2.5) parça dışında kalır → boş grid
    # (z dilimleri parça içine kelepçelendiğinden inceliği x'e koyuyoruz)
    thin = _norm(trimesh.creation.box(extents=(0.4, 30.0, 30.0)))
    with pytest.raises(ValueError):
        _slice_voxelize(thin, 5.0)
