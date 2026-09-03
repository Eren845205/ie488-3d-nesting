# -*- coding: utf-8 -*-
"""NO-GO area testleri (hoca gercek-makine kisiti, 2026-07-07).

Kurallar: no_go_mask=None -> BIT-OZDES eski davranis; maske verilince drop o
kolonlara yerlesim koyamaz; metrikler (max/mean/rms) muhurlu kolonlari yok sayar.
"""
import numpy as np

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.format import (
    ContainerSpec, NestingInstance, PartSpec, to_voxel_parts,
)
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine

PITCH = 5.0


def _inst(n=6):
    return NestingInstance(
        container=ContainerSpec(width_mm=60.0, depth_mm=60.0),
        parts=[PartSpec(id="b", name="b", qty=n, source="box",
                        width_mm=20.0, depth_mm=20.0, height_mm=10.0)])


def _mask_right_half(nx, ny):
    m = np.zeros((nx, ny), dtype=bool)
    m[nx // 2:, :] = True
    return m


def test_none_bit_ozdes():
    parts = to_voxel_parts(_inst(), PITCH, n_orientations=1)
    _, b0 = dblf(parts, lambda: Bin3D(60, 60, PITCH))
    _, b1 = dblf(parts, lambda: Bin3D(60, 60, PITCH, no_go_mask=None))
    assert b0.max_height_mm() == b1.max_height_mm()
    np.testing.assert_array_equal(b0.height, b1.height)


def test_yasak_bolgeye_yerlesim_olmaz():
    parts = to_voxel_parts(_inst(), PITCH, n_orientations=1)
    nx = ny = int(60 // PITCH)
    mask = _mask_right_half(nx, ny)
    _, b = dblf(parts, lambda: Bin3D(60, 60, PITCH, no_go_mask=mask))
    # yerlesimler yalniz SOL yarida (x + genislik <= nx/2)
    for p in b.placements:
        assert p.x + int(20 // PITCH) <= nx // 2 + 0, f"yasak bolgede: {p}"
    # muhurlu kolonlar metrige sizmiyor
    assert b.max_height_mm() < Bin3D.NO_GO_SEAL * PITCH / 2
    # alan yarilaninca ayni parcalar daha YUKSEK istiflenir (davranis kaniti)
    _, b_free = dblf(parts, lambda: Bin3D(60, 60, PITCH))
    assert b.max_height_mm() >= b_free.max_height_mm()


def test_mask_sekil_dogrulama():
    try:
        Bin3D(60, 60, PITCH, no_go_mask=np.zeros((3, 3), dtype=bool))
        raise AssertionError("sekil hatasi yakalanmadi")
    except ValueError:
        pass


def test_bounds_maskesi():
    m = Bin3D.no_go_mask_from_bounds(((10.0, 0.0), (20.0, 15.0)), 60, 60, PITCH)
    assert m.shape == (12, 12)
    assert m[2, 0] and m[3, 2]            # bbox ici
    assert not m[0, 0] and not m[5, 5]    # disi
    # 3D trimesh.bounds da kabul (z yok sayilir)
    m3 = Bin3D.no_go_mask_from_bounds(
        np.array([[10.0, 0.0, 0.0], [20.0, 15.0, 600.0]]), 60, 60, PITCH)
    np.testing.assert_array_equal(m, m3)


def test_solve_coarse_to_fine_no_go():
    inst = _inst(4)
    r0 = solve_coarse_to_fine(inst, plate_w_mm=60, plate_d_mm=60,
                              coarse_pitch=PITCH, fine_pitch=PITCH,
                              budget=3, seed=42)
    r1 = solve_coarse_to_fine(inst, plate_w_mm=60, plate_d_mm=60,
                              coarse_pitch=PITCH, fine_pitch=PITCH,
                              budget=3, seed=42,
                              no_go_bounds=((30.0, 0.0), (60.0, 60.0)))
    assert r0.n_placed == r1.n_placed == 4
    assert r1.height_mm >= r0.height_mm        # alan kisitlaninca dusmez
    nx_half = int(60 // PITCH) // 2
    for p in r1.placements:
        g = r1.fine_voxel_parts[p.part_id].orientations[p.orientation_idx].grid
        assert p.x + g.shape[0] <= nx_half, f"yasak bolgede: {p}"
