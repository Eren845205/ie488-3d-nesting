"""Tests for src.nesting3d.sa3d (PLAN_3D.md §4)."""

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0


def _part(part_id: str, extents):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    vp = voxelize_part(part_id, b, PITCH, n_orientations=4)
    vp.id = part_id
    return vp


def _parts():
    # mixed slabs/sticks on a small base — order & orientation both matter
    return [
        _part("slab1", (20, 20, 10)),
        _part("slab2", (20, 20, 10)),
        _part("stick1", (10, 10, 30)),
        _part("stick2", (10, 10, 30)),
        _part("cube1", (10, 10, 10)),
    ]


def _bin():
    return Bin3D(40.0, 40.0, PITCH)  # 8x8 voxel base


def test_never_worse_than_baseline():
    res = simulated_annealing_3d(_parts(), _bin, seed=42, iterations=60)
    assert res.best_height_mm <= res.baseline_height_mm


def test_reproducible_with_same_seed():
    a = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=60)
    b = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=60)
    assert a.best_height_mm == b.best_height_mm
    assert a.placements == b.placements
    assert a.history == b.history


def test_history_is_monotone_best_so_far():
    res = simulated_annealing_3d(_parts(), _bin, seed=42, iterations=60)
    assert len(res.history) == res.iterations + 1
    assert all(h2 <= h1 for h1, h2 in zip(res.history, res.history[1:]))
    assert res.history[-1] == res.best_height_mm


def test_all_parts_placed():
    parts = _parts()
    res = simulated_annealing_3d(parts, _bin, seed=42, iterations=60)
    assert len(res.placements) == len(parts)
    assert {p.part_id for p in res.placements} == {p.id for p in parts}


def test_sa_finds_flat_orientation_for_sticks():
    # Two 10x10x30 sticks on a 40x40 base: standing = 30 mm; lying = 10 mm.
    # The baseline may already lie them down; SA must certainly end <= 20 mm
    # (i.e. it must NOT leave both sticks standing).
    parts = [_part("stick1", (10, 10, 30)), _part("stick2", (10, 10, 30))]
    res = simulated_annealing_3d(parts, _bin, seed=42, iterations=80)
    assert res.best_height_mm <= 20.0
