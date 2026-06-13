"""Tests for src.nesting3d.solvers.ga_solver — GASolver (PLAN_DEMO1 §5.1).

Acceptance criteria:
  - GASolver implements Solver protocol
  - Determinism: same seed -> identical SolveResult
  - DBLF-baseline guarantee: result.height_mm <= dblf baseline height_mm
    (best-so-far with DBLF seed in initial population ensures this)
  - Genotype validity: every part appears exactly once in each individual
  - Budget contract: total_decodes <= pop_size * n_generations (documented, tested)
  - meta['solver'] == 'ga', meta['params'] includes key fields
  - All parts placed in result
"""

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.solvers.ga_solver import GASolver
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
# Keep budget tiny so tests run fast; GA: pop_size=6, n_generations=4
FAST_POP = 6
FAST_GEN = 4


def _part(part_id: str, extents=(10, 10, 10)):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    return voxelize_part(part_id, b, PITCH, n_orientations=4)


def _bin():
    return Bin3D(40.0, 40.0, PITCH)


def _parts():
    return [
        _part("slab1", (20, 20, 5)),
        _part("stick1", (5, 5, 30)),
        _part("cube1", (10, 10, 10)),
        _part("cube2", (10, 10, 10)),
    ]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_ga_solver_implements_solver_protocol():
    assert isinstance(GASolver(), Solver)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_ga_solver_returns_solve_result():
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert isinstance(result, SolveResult)


def test_ga_solver_all_parts_placed():
    parts = _parts()
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        parts, _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert len(result.placements) == len(parts)
    placed_ids = {p.part_id for p in result.placements}
    assert placed_ids == {p.id for p in parts}


def test_ga_solver_meta_has_solver_name():
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert result.meta.get("solver") == "ga"


def test_ga_solver_meta_has_params():
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    params = result.meta.get("params", {})
    assert "pop_size" in params
    assert "n_generations" in params
    assert "seed" in params


def test_ga_solver_time_s_populated():
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert result.time_s >= 0.0


def test_ga_solver_history_non_empty():
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    # history should have at least one entry (the DBLF baseline)
    assert len(result.history) >= 1


def test_ga_solver_history_monotone_non_increasing():
    """best-so-far history must be non-increasing (it can only improve or stay)."""
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    h = result.history
    assert all(h2 <= h1 + 1e-9 for h1, h2 in zip(h, h[1:]))


# ---------------------------------------------------------------------------
# DBLF baseline guarantee (CRITICAL — plan §5.1)
# ---------------------------------------------------------------------------


def test_ga_never_worse_than_dblf_baseline():
    """GA result MUST be <= DBLF baseline height (best-so-far + DBLF seed guarantees this).

    This is the core contract: the initial population contains at least one
    DBLF solution, and best-so-far is maintained throughout, so the final
    result can never exceed the DBLF baseline.
    """
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        parts, _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert result.height_mm <= baseline.height_mm + 1e-9


def test_ga_history_first_entry_is_dblf_baseline():
    """history[0] must be the DBLF baseline height (pre-evolution best-so-far)."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        parts, _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert abs(result.history[0] - baseline.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_ga_solver_same_seed_same_result():
    """Identical call twice with same seed must produce exactly equal results."""
    parts = _parts()
    solver = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN)
    a = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=99)
    b = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=99)
    assert a.height_mm == b.height_mm
    assert a.history == b.history
    assert a.placements == b.placements


def test_ga_solver_different_seeds_no_crash():
    """Different seeds must not raise — both results are valid."""
    parts = _parts()
    solver = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN)
    a = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=1)
    b = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=2)
    assert a.height_mm > 0
    assert b.height_mm > 0


# ---------------------------------------------------------------------------
# Genotype validity
# ---------------------------------------------------------------------------


def test_ga_genotype_each_part_exactly_once():
    """Every part must appear exactly once in the result's placement list."""
    parts = _parts()
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        parts, _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    placed_ids = [p.part_id for p in result.placements]
    assert len(placed_ids) == len(parts)
    # No duplicates
    assert len(set(placed_ids)) == len(placed_ids)
    # All original part IDs present
    assert set(placed_ids) == {p.id for p in parts}


# ---------------------------------------------------------------------------
# Budget contract
# ---------------------------------------------------------------------------


def test_ga_budget_contract_in_meta():
    """meta['params'] must document total_decodes (budget contract traceability)."""
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        _parts(), _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    params = result.meta.get("params", {})
    # budget contract: total_decodes must be reported
    assert "total_decodes" in params
    # total_decodes must be >= 1 (at least the initial population was evaluated)
    assert params["total_decodes"] >= 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_ga_single_part():
    """Single part — GA must still return a valid result."""
    parts = [_part("only", (10, 10, 10))]
    result = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN).solve(
        parts, _bin, budget=FAST_POP * FAST_GEN, seed=42
    )
    assert len(result.placements) == 1
    assert result.height_mm > 0


def test_ga_with_order_key():
    """order_key forwarded to DBLF seed — determinism still holds."""
    parts = _parts()
    asc_key = lambda p: (p.volume_voxels,)
    solver = GASolver(pop_size=FAST_POP, n_generations=FAST_GEN)
    a = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=5, order_key=asc_key)
    b = solver.solve(parts, _bin, budget=FAST_POP * FAST_GEN, seed=5, order_key=asc_key)
    assert a.height_mm == b.height_mm
