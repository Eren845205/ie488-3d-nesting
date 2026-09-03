"""Tests for NFV dikey clearance mekanizmasi (EVAL-1 kok-neden fix'i).

NFV yolu FFT-fizibilitesi saf sifir-cakisma + replay tam (x,y,z) idi; dikey
bosluk mekanizmasi HIC YOKtu (voxelize._dilate yalniz x/y). Bu fix:
  * voxelize.voxelize_part / to_voxel_parts'a `z_dilate` (TEK-TARAFLI +z) param,
  * solve_nfv'ye `clearance_mm` param (default 0.0 = BIT-OZDES),
  * fine_settle_raw ayni kurala uyar,
  * parallel_decode _drop_fallback None -> graceful (atla-ve-say).

Kabul kriterleri:
  1. z_dilate yalniz UST yonu buyutur (taban / index-0 profili SABIT) -> parca
     plaka tabanina oturabilir.
  2. Iki z-dilate'li grid ustuste konunca gercek (dilate-oncesi) yuzeyler
     arasi >= z_dilate voxel dikey bosluk garanti.
  3. z_dilate=0 -> grid eski davranisla BIT-OZDES.
  4. clearance_to_voxels(clearance,pitch) formul esleismesi (margin==z_c).
  5. solve_nfv clearance_mm=0.0 -> mevcut davranisla ayni (grid'ler ozdes).
  6. solve_nfv clearance_mm>0 -> yerlesim dikeyde acilir (yukseklik >= clearance=0).
"""
from __future__ import annotations

import numpy as np
import trimesh

from src.nesting3d.voxelize import voxelize_part, _dilate, _dilate_z_up
from src.nesting3d.instances.format import (
    ContainerSpec, NestingInstance, PartSpec, to_voxel_parts,
)
from src.nesting3d.coarse_to_fine import clearance_to_voxels
from src.nesting3d.nfv_solve import solve_nfv, _voxelize_nfv
from src.nesting3d.fft_backend import get_backend
from src.nesting3d.parallel_decode import decode, best_decode


PITCH = 5.0


def _box(w=20.0, d=20.0, h=20.0):
    m = trimesh.creation.box(extents=(w, d, h))
    m.apply_translation(-m.bounds[0])
    return m


# ---------------------------------------------------------------------------
# 1-3: _dilate_z_up mekanigi
# ---------------------------------------------------------------------------

def test_z_dilate_grows_only_upward():
    """TEK-TARAFLI +z: taban (index 0) DEGISMEZ, tepe z_dilate kadar buyur."""
    g = np.zeros((3, 3, 4), dtype=bool)
    g[1, 1, 1:3] = True  # tek kolon, z=1..2 dolu
    out = _dilate_z_up(g, 2)
    # z ekseni 2 katman buyudu
    assert out.shape == (3, 3, 6)
    col = out[1, 1, :]
    # alt sinir korunur: dilate-oncesi en dusuk dolu z (1) hala en dusuk
    assert not col[0]              # index 0 hala bos (taban etkilenmedi)
    assert col[1]                  # orijinal alt dolu voxel yerinde
    # tepe yukari buyudu: z=2 (orijinal tepe) -> +2 = z=4'e kadar dolu
    assert col[3] and col[4]
    # dilate-oncesi bos olan alt hucreler yukari dilation'la DOLMAZ
    lowest_before = int(np.argmax(g[1, 1, :]))
    lowest_after = int(np.argmax(out[1, 1, :]))
    assert lowest_after == lowest_before


def test_z_dilate_guarantees_vertical_gap():
    """Iki z-dilate'li grid ustuste: gercek yuzeyler arasi >= z_dilate voxel."""
    zc = 2
    g = np.zeros((1, 1, 2), dtype=bool)
    g[0, 0, :] = True                 # dolu blok, gercek tepe = index 1
    gd = _dilate_z_up(g, zc)          # dilate: tepe index 1 -> 1+zc = 3
    # A tabanda: gercek voxel 0..1, dilate voxel 0..3
    # B, A'nin dilate tepesine oturur: B_taban = 3+1 = 4 (ust ust binmez)
    a_real_top = 1                    # A'nin gercek en yuksek dolu z
    b_base = int(np.argmax(gd[0, 0, ::-1])) # dilate son dolu index
    b_base = gd.shape[2] - b_base     # ilk bos z ustte = B'nin oturacagi taban
    gap = b_base - (a_real_top + 1)   # gercek yuzeyler arasi bos voxel
    assert gap >= zc


def test_z_dilate_zero_is_identity():
    """z_dilate=0 -> voxelize_part grid'i eski davranisla BIT-OZDES."""
    plain = voxelize_part("box", _box(), PITCH, n_orientations=1)
    z0 = voxelize_part("box", _box(), PITCH, n_orientations=1, z_dilate=0)
    np.testing.assert_array_equal(plain.orientations[0].grid,
                                  z0.orientations[0].grid)
    assert plain.orientations[0].shape == z0.orientations[0].shape


def test_z_dilate_grows_grid_top_not_bottom_profile():
    """voxelize_part z_dilate: bottom profili SABIT, top profili +z_dilate."""
    plain = voxelize_part("box", _box(), PITCH, n_orientations=1)
    tall = voxelize_part("box", _box(), PITCH, n_orientations=1, z_dilate=2)
    px, py, pz = plain.orientations[0].shape
    assert tall.orientations[0].shape == (px, py, pz + 2)
    # bottom profili (en dusuk dolu z) DEGISMEZ (taban etkilenmez)
    np.testing.assert_array_equal(plain.orientations[0].bottom,
                                  tall.orientations[0].bottom)
    # top profili z_dilate kadar artar (dolu kolonlarda)
    fill = plain.orientations[0].filled
    assert (tall.orientations[0].top[fill]
            == plain.orientations[0].top[fill] + 2).all()


def test_z_dilate_with_xy_margin_combined():
    """margin (x/y) + z_dilate (z) birlikte: grid 3 eksende de buyur."""
    plain = voxelize_part("box", _box(), PITCH, n_orientations=1)
    both = voxelize_part("box", _box(), PITCH, n_orientations=1,
                         margin=1, z_dilate=2)
    px, py, pz = plain.orientations[0].shape
    assert both.orientations[0].shape == (px + 2, py + 2, pz + 2)


# ---------------------------------------------------------------------------
# 4: clearance_to_voxels formul esleismesi
# ---------------------------------------------------------------------------

def test_clearance_formula_margin_equals_zc():
    for pitch in (0.5, 1.0, 2.0, 5.0):
        m, zc = clearance_to_voxels(1.0, pitch)
        assert m == zc == max(1, int(np.ceil(1.0 / pitch)))
    assert clearance_to_voxels(0.0, 2.0) == (0, 1)


# ---------------------------------------------------------------------------
# to_voxel_parts z_dilate kanali
# ---------------------------------------------------------------------------

def _make_instance():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[PartSpec(id="b", name="b", qty=1, source="box",
                        width_mm=20.0, depth_mm=20.0, height_mm=20.0)],
    )


def test_to_voxel_parts_z_dilate_passthrough():
    plain = to_voxel_parts(_make_instance(), PITCH, n_orientations=1)
    tall = to_voxel_parts(_make_instance(), PITCH, n_orientations=1, z_dilate=2)
    _, _, pz = plain[0].orientations[0].shape
    _, _, tz = tall[0].orientations[0].shape
    assert tz == pz + 2


# ---------------------------------------------------------------------------
# 5-6: solve_nfv clearance_mm entegrasyonu
# ---------------------------------------------------------------------------

def _clear_instance():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="a", name="a", qty=2, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="b", name="b", qty=2, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


def test_voxelize_nfv_clearance_zero_identity():
    """_voxelize_nfv clearance_mm=0.0 -> margin param davranisiyla BIT-OZDES."""
    inst = _clear_instance()
    base, p0 = _voxelize_nfv(inst, PITCH, PITCH, 2, 1)
    same, p1 = _voxelize_nfv(inst, PITCH, PITCH, 2, 1, clearance_mm=0.0)
    assert p0 == p1
    for a, b in zip(base, same):
        np.testing.assert_array_equal(a.orientations[0].grid,
                                      b.orientations[0].grid)


def test_voxelize_nfv_clearance_positive_adds_zdilation():
    """clearance_mm>0 -> grid'ler dikeyde (ve x/y) formulden buyur."""
    inst = _clear_instance()
    base, _ = _voxelize_nfv(inst, PITCH, PITCH, 2, 1)
    fat, used = _voxelize_nfv(inst, PITCH, PITCH, 2, 1, clearance_mm=1.0)
    m, zc = clearance_to_voxels(1.0, used)
    for a, b in zip(base, fat):
        pw, pd, ph = a.orientations[0].shape
        fw, fd, fh = b.orientations[0].shape
        # margin farki (base margin=1 vs formul m) x/y'de, z_dilate zc z'de
        assert fh == ph + zc
        assert fw == pw + 2 * (m - 1)
        assert fd == pd + 2 * (m - 1)


def test_solve_nfv_default_clearance_bit_identical():
    """solve_nfv default (clearance_mm=0.0) -> mevcut yukseklik BIREBIR (determinizm)."""
    inst = _clear_instance()
    r0 = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0, fine_pitch=PITCH,
                   n_orientations=2, margin=1, force="cpu-kolA")
    r1 = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0, fine_pitch=PITCH,
                   n_orientations=2, margin=1, force="cpu-kolA", clearance_mm=0.0)
    assert abs(r0.height_mm - r1.height_mm) < 1e-9
    assert r0.n_placed == r1.n_placed == 4


def test_solve_nfv_clearance_opens_vertical_gap():
    """clearance_mm>0 yerlesimi dikeyde acar -> yukseklik >= clearance=0 hali."""
    inst = _clear_instance()
    r0 = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0, fine_pitch=PITCH,
                   n_orientations=2, margin=1, force="cpu-kolA", clearance_mm=0.0)
    rc = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0, fine_pitch=PITCH,
                   n_orientations=2, margin=1, force="cpu-kolA", clearance_mm=1.0)
    assert rc.n_placed == 4
    # clearance ekleyince istifleme dikeyde acilir -> asla daha kisa olamaz
    assert rc.height_mm >= r0.height_mm - 1e-9


# ---------------------------------------------------------------------------
# parallel_decode graceful drop (_drop_fallback None -> atla-ve-say, cokme YOK)
# ---------------------------------------------------------------------------

def _oversize_parts():
    """Plakadan BUYUK bir parca (hicbir oryantasyonda sigmaz) + normal parca."""
    inst = NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="huge", name="huge", qty=1, source="box",
                     width_mm=200.0, depth_mm=200.0, height_mm=200.0),
            PartSpec(id="ok", name="ok", qty=1, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=20.0),
        ],
    )
    parts = to_voxel_parts(inst, PITCH, n_orientations=1)
    return parts, int(100.0 // PITCH), int(100.0 // PITCH)


def test_decode_drop_fallback_none_is_graceful():
    """_drop_fallback None -> eski TypeError yerine parcayi atla (cokme YOK)."""
    parts, nx, ny = _oversize_parts()
    fm, _ = get_backend("scipy")
    skip = {}
    h, raw = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                    return_placements=True, skip_status=skip)
    ids = {r[0] for r in raw}
    assert any(i.startswith("ok") for i in ids)     # sigan parca yerlesti
    assert not any(i.startswith("huge") for i in ids)  # plakadan buyuk atlandi
    dropped = skip.get("dropped", [])               # SESSIZ yutma YOK
    assert any(i.startswith("huge") for i in dropped)


def test_best_decode_surfaces_dropped_in_strategy():
    """best_decode atlanan parcayi strateji izine yazar (-> adaptive_reason)."""
    parts, nx, ny = _oversize_parts()
    h, raw, strategy = best_decode(parts, nx, ny, pitch=PITCH, force="serial")
    assert "dropped" in strategy
    assert all(ord(c) < 128 for c in strategy)  # SAF ASCII (cp1254 guvenli)
