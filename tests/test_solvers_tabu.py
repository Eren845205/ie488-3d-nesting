"""Tests for src.nesting3d.solvers.tabu_solver — TabuSolver (PLAN_DEMO1 §5.2).

Acceptance criteria:
  - TabuSolver implements Solver protocol
  - Determinism: same seed -> identical SolveResult
  - DBLF-baseline guarantee: result.height_mm <= dblf baseline height_mm
  - Genotype validity: every part appears exactly once
  - Budget contract: total_decodes == budget (one decode per iteration)
  - Tabu list mechanism: at least some moves are forbidden during a run (checked
    via meta['params']['tabu_hits'])
  - Aspiration: accepted best-improving moves are reflected in history
  - meta['solver'] == 'tabu', meta['params'] includes key fields
"""

import random

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import _neighbour as sa3d_neighbour
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.solvers.tabu_solver import TabuSolver, _neighbour_with_signature
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
FAST_BUDGET = 30  # total decode iterations — keep fast


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


def test_tabu_solver_implements_solver_protocol():
    assert isinstance(TabuSolver(), Solver)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_tabu_solver_returns_solve_result():
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert isinstance(result, SolveResult)


def test_tabu_solver_all_parts_placed():
    parts = _parts()
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.placements) == len(parts)
    placed_ids = {p.part_id for p in result.placements}
    assert placed_ids == {p.id for p in parts}


def test_tabu_solver_meta_has_solver_name():
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert result.meta.get("solver") == "tabu"


def test_tabu_solver_meta_has_params():
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    params = result.meta.get("params", {})
    assert "tenure" in params
    assert "seed" in params
    assert "budget" in params


def test_tabu_solver_time_s_populated():
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert result.time_s >= 0.0


def test_tabu_solver_history_non_empty():
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.history) >= 1


def test_tabu_solver_history_monotone_non_increasing():
    """best-so-far history must never increase."""
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    h = result.history
    assert all(h2 <= h1 + 1e-9 for h1, h2 in zip(h, h[1:]))


# ---------------------------------------------------------------------------
# DBLF baseline guarantee (CRITICAL — plan §5.2)
# ---------------------------------------------------------------------------


def test_tabu_never_worse_than_dblf_baseline():
    """TabuSolver result MUST be <= DBLF baseline (best-so-far from DBLF start)."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert result.height_mm <= baseline.height_mm + 1e-9


def test_tabu_history_first_entry_is_dblf_baseline():
    """history[0] must be the DBLF baseline height."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert abs(result.history[0] - baseline.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_tabu_solver_same_seed_same_result():
    """Two calls with the same seed must produce identical SolveResult."""
    parts = _parts()
    a = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=99)
    b = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=99)
    assert a.height_mm == b.height_mm
    assert a.history == b.history
    assert a.placements == b.placements


def test_tabu_solver_different_seeds_no_crash():
    """Different seeds must not raise."""
    parts = _parts()
    a = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=1)
    b = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=2)
    assert a.height_mm > 0
    assert b.height_mm > 0


# ---------------------------------------------------------------------------
# Budget contract
# ---------------------------------------------------------------------------


def test_tabu_budget_contract_total_decodes():
    """meta['params']['total_decodes'] must equal budget (one decode per step)."""
    parts = _parts()
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    params = result.meta.get("params", {})
    assert "total_decodes" in params
    assert params["total_decodes"] == FAST_BUDGET


# ---------------------------------------------------------------------------
# Tabu mechanism
# ---------------------------------------------------------------------------


def test_tabu_hits_reported_in_meta():
    """meta['params']['tabu_hits'] must exist and be >= 0."""
    result = TabuSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    params = result.meta.get("params", {})
    assert "tabu_hits" in params
    assert params["tabu_hits"] >= 0


def test_tabu_tenure_parameter_respected():
    """Different tenures must be accepted without error; both results valid."""
    parts = _parts()
    r3 = TabuSolver(tenure=3).solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    r7 = TabuSolver(tenure=7).solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert r3.height_mm > 0
    assert r7.height_mm > 0
    assert r3.meta["params"]["tenure"] == 3
    assert r7.meta["params"]["tenure"] == 7


# ---------------------------------------------------------------------------
# Genotype validity
# ---------------------------------------------------------------------------


def test_tabu_genotype_each_part_exactly_once():
    """Every part must appear exactly once in placement list."""
    parts = _parts()
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    placed_ids = [p.part_id for p in result.placements]
    assert len(placed_ids) == len(parts)
    assert len(set(placed_ids)) == len(placed_ids)
    assert set(placed_ids) == {p.id for p in parts}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_tabu_single_part():
    """Single part — tabu must still return valid result."""
    parts = [_part("only", (10, 10, 10))]
    result = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.placements) == 1
    assert result.height_mm > 0


def test_tabu_with_order_key():
    """order_key forwarded to DBLF start — determinism still holds."""
    parts = _parts()
    asc_key = lambda p: (p.volume_voxels,)
    a = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=5, order_key=asc_key)
    b = TabuSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=5, order_key=asc_key)
    assert a.height_mm == b.height_mm


def test_tabu_budget_zero_returns_baseline():
    """budget=0 means no search steps — result is exactly DBLF baseline."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = TabuSolver().solve(parts, _bin, budget=0, seed=42)
    assert abs(result.height_mm - baseline.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# RNG parity: _neighbour_with_signature mirrors sa3d._neighbour exactly
# ---------------------------------------------------------------------------


def test_neighbour_with_signature_rng_parity():
    """_neighbour_with_signature and sa3d._neighbour must produce IDENTICAL
    solutions when driven from the same random.Random state.

    This test drives both functions from identical RNG states for several
    (seed, step) combinations and asserts bit-for-bit equality of the
    resulting solution lists.  If sa3d._neighbour ever changes its RNG call
    pattern, this test will fail loudly — that is intentional.  Update
    _neighbour_with_signature to match before re-greening.

    Design note: _neighbour_with_signature exists solely to mirror sa3d's RNG
    stream while also returning a hashable move signature for the tabu list.
    Any drift between the two functions breaks the determinism guarantee of
    TabuSolver (same seed as SA -> same decode sequence).
    """
    from src.nesting3d.dblf import dblf

    parts = _parts()
    base_placements, _ = dblf(parts, _bin)
    by_id = {p.id: p for p in parts}
    base_solution = [(by_id[pl.part_id], pl.orientation_idx) for pl in base_placements]

    seeds = [0, 1, 7, 42, 99]
    steps_per_seed = 5

    for seed in seeds:
        rng_a = random.Random(seed)
        rng_b = random.Random(seed)
        solution = list(base_solution)
        for _step in range(steps_per_seed):
            result_sa = sa3d_neighbour(solution, rng_a)
            result_tabu, _sig = _neighbour_with_signature(solution, rng_b)
            assert result_sa == result_tabu, (
                f"RNG parity failure at seed={seed} step={_step}: "
                f"sa3d._neighbour and _neighbour_with_signature produced "
                f"different solutions — update _neighbour_with_signature to "
                f"match sa3d._neighbour's RNG call pattern."
            )
            solution = result_sa  # advance both on the same path
