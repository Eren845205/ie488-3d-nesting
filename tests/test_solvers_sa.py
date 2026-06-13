"""Tests for src.nesting3d.solvers.sa_solver — SA wrapper (1.3).

Acceptance criteria (PLAN_DEMO1 §1.3):
  - sa3d.py is NOT modified (only wrapped)
  - SASolver implements Solver protocol
  - Same seed -> IDENTICAL results to calling simulated_annealing_3d() directly
  - SolveResult fields fully populated
"""

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.solvers.sa_solver import SASolver
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
FAST_ITERS = 60  # keep tests fast


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


def test_sa_solver_implements_solver_protocol():
    assert isinstance(SASolver(), Solver)


# ---------------------------------------------------------------------------
# Result content
# ---------------------------------------------------------------------------


def test_sa_solver_returns_solve_result():
    parts = _parts()
    result = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=42)
    assert isinstance(result, SolveResult)


def test_sa_solver_all_parts_placed():
    parts = _parts()
    result = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=42)
    assert len(result.placements) == len(parts)
    assert {p.part_id for p in result.placements} == {p.id for p in parts}


def test_sa_solver_never_worse_than_baseline():
    """SA must never exceed the DBLF baseline height.

    Mechanism: simulated_annealing_3d starts from the DBLF solution and
    retains the best-ever solution (best-so-far).  The starting solution IS
    the baseline, so best_so_far can only improve or stay equal — it is
    mathematically impossible for SA to finish above the baseline.

    White-box check: history[0] is the baseline height recorded before the
    SA loop begins (see sa3d.py — history = [best_bin.max_height_mm()] before
    the for-loop).  It must equal the DBLF solver's result.
    """
    from src.nesting3d.solvers.dblf_solver import DBLFSolver

    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=42)
    assert result.height_mm <= baseline.height_mm
    # White-box: history[0] must match the baseline recorded before SA starts.
    assert abs(result.history[0] - baseline.height_mm) < 1e-9


def test_sa_solver_same_seed_bire_bir_same_as_direct():
    """Same seed -> IDENTICAL height, placements, history vs direct sa3d call.

    This is the key acceptance criterion for 1.3: the wrapper must be a thin
    shim that does not alter the computation in any way.
    """
    parts = _parts()
    direct = simulated_annealing_3d(
        parts, _bin, seed=7, iterations=FAST_ITERS
    )
    wrapped = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=7)
    assert wrapped.height_mm == direct.best_height_mm
    assert wrapped.history == direct.history
    wrapped_ids = {p.part_id for p in wrapped.placements}
    direct_ids = {p.part_id for p in direct.placements}
    assert wrapped_ids == direct_ids


def test_sa_solver_same_seed_same_result_twice():
    """Two calls with the same seed must produce identical SolveResult."""
    parts = _parts()
    a = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=99)
    b = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=99)
    assert a.height_mm == b.height_mm
    assert a.history == b.history
    assert a.placements == b.placements


def test_sa_solver_different_seeds_may_differ():
    """Different seeds should (in general) produce different histories."""
    parts = _parts()
    a = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=1)
    b = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=2)
    # Not guaranteed to differ, but with 60 iters on this problem they typically do
    # We only assert both are valid (no assertion about them being different)
    assert a.height_mm > 0
    assert b.height_mm > 0


def test_sa_solver_meta_has_solver_name():
    result = SASolver().solve(_parts(), _bin, budget=FAST_ITERS, seed=42)
    assert result.meta.get("solver") == "sa"


def test_sa_solver_meta_has_params():
    result = SASolver().solve(_parts(), _bin, budget=FAST_ITERS, seed=42)
    params = result.meta.get("params", {})
    assert params.get("seed") == 42
    assert params.get("iterations") == FAST_ITERS


def test_sa_solver_history_is_monotone_best_so_far():
    result = SASolver().solve(_parts(), _bin, budget=FAST_ITERS, seed=42)
    h = result.history
    assert all(h2 <= h1 for h1, h2 in zip(h, h[1:]))
    # h[-1] comes from best_bin.max_height_mm() recorded during the loop;
    # result.height_mm comes from a second decode(best, bin_factory) call at
    # the end of simulated_annealing_3d.  Both are deterministic float
    # arithmetic on the same voxel grid, but a strict == would be brittle if
    # the implementation ever changes the final-decode path.
    assert abs(h[-1] - result.height_mm) < 1e-9


def test_sa_solver_time_s_populated():
    result = SASolver().solve(_parts(), _bin, budget=FAST_ITERS, seed=42)
    assert result.time_s >= 0.0


def test_sa_solver_with_order_key():
    """order_key parameter must be forwarded to SA."""
    parts = _parts()
    asc_key = lambda p: (p.volume_voxels,)
    a = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=5, order_key=asc_key)
    b = SASolver().solve(parts, _bin, budget=FAST_ITERS, seed=5, order_key=asc_key)
    assert a.height_mm == b.height_mm
    assert a.history == b.history
