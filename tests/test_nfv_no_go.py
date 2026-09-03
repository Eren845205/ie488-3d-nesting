# -*- coding: utf-8 -*-
"""NFV NO-GO destegi (2026-07-09, kullanici karari: 'hepsine eklenecek').

Mekanizma: yasak kolonlar OccupancyBin3D/decode_gpu occupancy'sinde TAM
YUKSEKLIK muhurlenir -> FFT feasibility + is_feasible + drop-fallback
otomatik kacinir. fine_settle occ'u da muhurlenir (jitter sizmasi olmasin).
default None = BIT-OZDES eski davranis.
"""
import numpy as np
import pytest
import trimesh

from src.nesting3d.extreme_point import OccupancyBin3D
from src.nesting3d.parallel_decode import decode
from src.nesting3d.voxelize import voxelize_part
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.instances.format import NestingInstance, ContainerSpec, PartSpec

PITCH = 5.0


def _box_part(w=20.0, d=20.0, h=10.0, name="kutu"):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return voxelize_part(name, b, PITCH, n_orientations=1, method="slice")


def test_occupancy_bin_no_go_seal():
    # sag yari yasak: 20x20 grid, x>=10 muhurlu
    mask = np.zeros((20, 20), dtype=bool)
    mask[10:, :] = True
    ob = OccupancyBin3D(20, 20, nz_limit=8, pitch=PITCH, no_go_mask=mask)
    o = _box_part().orientations[0]           # 4x4x2 voxel
    assert ob.is_feasible(o, 0, 0, 0)         # serbest bolge
    assert not ob.is_feasible(o, 12, 0, 0)    # yasak ici
    assert not ob.is_feasible(o, 8, 0, 0)     # yasak SINIRINI tasiyor
    assert not ob.is_feasible(o, 12, 0, 100)  # yasak ustu YUKSEKTE de yasak
    # z-genisleme muhuru tasimali
    ob._ensure_z_capacity(64)
    assert ob.occupancy[12, 0, 60]            # yeni katmanlar da muhurlu
    assert not ob.is_feasible(o, 12, 0, 60)
    # yukseklik metrigi muhurden zehirlenmez
    assert ob.max_height_voxels() == 0


def test_decode_avoids_no_go():
    mask = np.zeros((20, 20), dtype=bool)
    mask[:, 10:] = True                       # ust yari yasak (y>=10)
    parts = [_box_part(name=f"k{i}") for i in range(3)]
    h, pls = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
                    no_go_mask=mask)
    assert len(pls) == 3
    for (_pid, oi, x, y, z) in pls:
        g = parts[0].orientations[oi].grid
        assert y + g.shape[1] <= 10, f"yasak bolgeye tasti: y={y}"


def test_solve_nfv_no_go_bounds():
    inst = NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[PartSpec(id="box_a", name="box_a", qty=3, source="box",
                        width_mm=30.0, depth_mm=30.0, height_mm=10.0)])
    ng = ((0.0, 50.0), (100.0, 100.0))        # ust yari (y>=50mm) yasak
    r = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0,
                  fine_pitch=PITCH, n_orientations=1, fine_settle=False,
                  no_go_bounds=ng)
    assert r.n_placed == 3
    mask = Bin3D.no_go_mask_from_bounds(ng, 100.0, 100.0, float(r.fine_pitch))
    for pl in r.placements:
        o = r.fine_voxel_parts[pl.part_id].orientations[pl.orientation_idx]
        fw, fd = o.grid.shape[0], o.grid.shape[1]
        pencere = mask[pl.x:pl.x + fw, pl.y:pl.y + fd]
        assert not pencere.any(), f"{pl.part_id} yasak bolgeyle kesisti"


def test_solve_nfv_default_bit_identical():
    inst = NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[PartSpec(id="box_a", name="box_a", qty=4, source="box",
                        width_mm=30.0, depth_mm=20.0, height_mm=10.0)])
    r0 = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False)
    r1 = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False,
                   no_go_bounds=None)
    assert r0.height_mm == r1.height_mm
    assert [(p.part_id, p.x, p.y, p.z, p.orientation_idx) for p in r0.placements] == \
           [(p.part_id, p.x, p.y, p.z, p.orientation_idx) for p in r1.placements]
