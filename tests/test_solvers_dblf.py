"""Tests for src.nesting3d.solvers.dblf_solver — DBLF wrapper (1.2).

Acceptance criteria (PLAN_DEMO1 §1.2):
  - dblf.py is NOT modified (only wrapped)
  - DBLFSolver implements Solver protocol
  - Results are identical to calling dblf.dblf() directly (same height, same placements)
  - SolveResult fields are fully populated
"""

import trimesh

import pytest
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0


def _part(part_id: str, extents=(10, 10, 10)):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    return voxelize_part(part_id, b, PITCH, n_orientations=4)


def _bin():
    return Bin3D(40.0, 40.0, PITCH)


def _parts():
    return [
        _part("slab1", (20, 20, 5)),
        _part("slab2", (20, 20, 5)),
        _part("stick1", (5, 5, 30)),
        _part("cube1", (10, 10, 10)),
    ]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_dblf_solver_implements_solver_protocol():
    assert isinstance(DBLFSolver(), Solver)


# ---------------------------------------------------------------------------
# Result content
# ---------------------------------------------------------------------------


def test_dblf_solver_returns_solve_result():
    parts = _parts()
    result = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    assert isinstance(result, SolveResult)


def test_dblf_solver_all_parts_placed():
    parts = _parts()
    result = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    assert len(result.placements) == len(parts)
    placed_ids = {p.part_id for p in result.placements}
    assert placed_ids == {p.id for p in parts}


def test_dblf_solver_height_matches_direct_call():
    """Wrapper must produce identical height to calling dblf() directly."""
    parts = _parts()
    direct_placements, direct_bin = dblf(parts, _bin)
    result = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    assert result.height_mm == direct_bin.max_height_mm()


def test_dblf_solver_placements_match_direct_call():
    """Placement coordinates must be identical to direct dblf() call."""
    parts = _parts()
    direct_placements, _ = dblf(parts, _bin)
    result = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    # Sort by part_id for comparison (order may differ)
    dp = sorted(direct_placements, key=lambda p: p.part_id)
    rp = sorted(result.placements, key=lambda p: p.part_id)
    for d, r in zip(dp, rp):
        assert d.part_id == r.part_id
        assert d.x == r.x
        assert d.y == r.y
        assert d.z == r.z
        assert d.orientation_idx == r.orientation_idx


def test_dblf_solver_meta_has_solver_name():
    result = DBLFSolver().solve(_parts(), _bin, budget=0, seed=42)
    assert result.meta.get("solver") == "dblf"


def test_dblf_solver_time_s_populated():
    result = DBLFSolver().solve(_parts(), _bin, budget=0, seed=42)
    assert result.time_s >= 0.0


def test_dblf_solver_density_positive():
    result = DBLFSolver().solve(_parts(), _bin, budget=0, seed=42)
    assert 0.0 < result.density <= 1.0


def test_dblf_solver_with_order_key():
    """order_key parameter must be forwarded to dblf()."""
    parts = _parts()
    # ascending volume order (inverts default)
    asc_key = lambda p: (p.volume_voxels,)
    result = DBLFSolver().solve(parts, _bin, budget=0, seed=42, order_key=asc_key)
    direct_placements, _ = dblf(parts, _bin, order_key=asc_key)
    dp = sorted(direct_placements, key=lambda p: p.part_id)
    rp = sorted(result.placements, key=lambda p: p.part_id)
    for d, r in zip(dp, rp):
        assert d.x == r.x and d.y == r.y and d.z == r.z


def test_dblf_solver_deterministic():
    """Two calls with the same args must produce identical results."""
    parts = _parts()
    a = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    b = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    assert a.height_mm == b.height_mm
    assert a.placements == b.placements
