"""Tests for src.nesting3d.solvers.alns_solver — ALNSSolver.

Acceptance criteria:
  - ALNSSolver implements Solver protocol
  - Determinism: same (parts, bin_factory, budget, seed) -> identical SolveResult
  - DBLF-baseline guarantee: result.height_mm <= DBLF baseline height_mm
  - SolveResult fields fully populated (placements, bin3d, height_mm, density,
    time_s, history, meta)
  - meta['solver'] == 'alns'; meta['params'] includes required keys
  - Adaptive weights updated: destroy_weights and repair_weights change during
    a run (verifiable via meta)
  - history is monotone non-increasing (best-so-far)
  - All parts placed exactly once
  - budget=0 returns DBLF baseline (no search)
  - order_key is forwarded and determinism still holds
"""

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.alns_solver import ALNSSolver
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
FAST_BUDGET = 50   # enough iterations for weight updates, short enough for CI


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
        _part("flat1", (15, 15, 3)),
        _part("rod1", (4, 4, 25)),
    ]


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_alns_solver_implements_solver_protocol():
    assert isinstance(ALNSSolver(), Solver)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


def test_alns_solver_returns_solve_result():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert isinstance(result, SolveResult)


def test_alns_solver_all_parts_placed():
    parts = _parts()
    result = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.placements) == len(parts)
    placed_ids = {p.part_id for p in result.placements}
    assert placed_ids == {p.id for p in parts}


def test_alns_solver_height_mm_positive():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert result.height_mm > 0


def test_alns_solver_density_in_range():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert 0.0 < result.density <= 1.0


def test_alns_solver_time_s_populated():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert result.time_s >= 0.0


def test_alns_solver_history_non_empty():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.history) >= 1


# ---------------------------------------------------------------------------
# Meta fields
# ---------------------------------------------------------------------------


def test_alns_solver_meta_solver_name():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert result.meta.get("solver") == "alns"


def test_alns_solver_meta_params_keys():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    params = result.meta.get("params", {})
    for key in ("seed", "budget", "t0", "t_min", "baseline_height_mm", "accepted"):
        assert key in params, f"missing key in meta['params']: {key}"


def test_alns_solver_meta_operator_fields():
    """meta must expose destroy/repair weights, uses and operator names."""
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    meta = result.meta
    assert "destroy_weights" in meta
    assert "repair_weights" in meta
    assert "destroy_uses" in meta
    assert "repair_uses" in meta
    assert "destroy_ops" in meta
    assert "repair_ops" in meta
    assert len(meta["destroy_weights"]) == 3
    assert len(meta["repair_weights"]) == 2
    assert len(meta["destroy_ops"]) == 3
    assert len(meta["repair_ops"]) == 2


def test_alns_solver_meta_baseline_height_present():
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    bh = result.meta["params"]["baseline_height_mm"]
    assert bh > 0


# ---------------------------------------------------------------------------
# DBLF baseline guarantee (CRITICAL)
# ---------------------------------------------------------------------------


def test_alns_never_worse_than_dblf_baseline():
    """ALNSSolver MUST finish <= DBLF baseline (best-so-far from DBLF start)."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert result.height_mm <= baseline.height_mm + 1e-9, (
        f"ALNS ({result.height_mm:.4f} mm) exceeded DBLF baseline "
        f"({baseline.height_mm:.4f} mm)"
    )


def test_alns_history_first_entry_is_dblf_baseline():
    """history[0] must equal the DBLF baseline height."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert abs(result.history[0] - baseline.height_mm) < 1e-9, (
        f"history[0]={result.history[0]:.4f} != baseline={baseline.height_mm:.4f}"
    )


# ---------------------------------------------------------------------------
# History monotonicity
# ---------------------------------------------------------------------------


def test_alns_history_monotone_non_increasing():
    """best-so-far history must never increase."""
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    h = result.history
    for i in range(len(h) - 1):
        assert h[i + 1] <= h[i] + 1e-9, (
            f"history not monotone at index {i}: {h[i]:.4f} -> {h[i+1]:.4f}"
        )


def test_alns_history_last_entry_matches_height_mm():
    """history[-1] must equal result.height_mm (final best-so-far)."""
    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    assert abs(result.history[-1] - result.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_alns_same_seed_same_result():
    """Two calls with the same seed must produce identical SolveResult."""
    parts = _parts()
    a = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    b = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert a.height_mm == b.height_mm
    assert a.history == b.history
    assert a.placements == b.placements


def test_alns_same_seed_same_meta():
    """Same seed -> same adaptive weights (determinism end-to-end)."""
    parts = _parts()
    a = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=99)
    b = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=99)
    assert a.meta["destroy_weights"] == b.meta["destroy_weights"]
    assert a.meta["repair_weights"] == b.meta["repair_weights"]


def test_alns_different_seeds_no_crash():
    """Different seeds must not raise and must return valid results."""
    parts = _parts()
    a = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=1)
    b = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=2)
    assert a.height_mm > 0
    assert b.height_mm > 0


# ---------------------------------------------------------------------------
# Adaptive weights
# ---------------------------------------------------------------------------


def test_alns_weights_updated_after_run():
    """After enough iterations, at least one weight must differ from 1.0
    (the initial uniform weight), proving the adaptive update ran.

    Uses a budget > segment_len (25) so at least one update fires.
    """
    from src.nesting3d.solvers import alns_solver as mod

    parts = _parts()
    result = ALNSSolver().solve(parts, _bin, budget=mod._SEGMENT_LEN + 10, seed=7)
    dw = result.meta["destroy_weights"]
    rw = result.meta["repair_weights"]
    # After at least one segment update the weights should not all be exactly 1.0
    # (unless no operator was ever used, which is impossible for budget > segment_len)
    weights_changed = any(abs(w - 1.0) > 1e-12 for w in dw + rw)
    assert weights_changed, (
        f"destroy_weights={dw}, repair_weights={rw} — "
        "adaptive weights did not change (segment update did not fire?)"
    )


def test_alns_weights_all_non_negative():
    """All operator weights must be positive (min_weight enforced)."""
    from src.nesting3d.solvers import alns_solver as mod

    result = ALNSSolver().solve(_parts(), _bin, budget=FAST_BUDGET, seed=42)
    for w in result.meta["destroy_weights"] + result.meta["repair_weights"]:
        assert w >= mod._MIN_WEIGHT - 1e-12, f"weight {w} below min_weight"


# ---------------------------------------------------------------------------
# Budget=0 edge case
# ---------------------------------------------------------------------------


def test_alns_budget_zero_returns_baseline():
    """budget=0 means no ALNS iterations — result must equal DBLF baseline."""
    parts = _parts()
    baseline = DBLFSolver().solve(parts, _bin, budget=0, seed=42)
    result = ALNSSolver().solve(parts, _bin, budget=0, seed=42)
    assert abs(result.height_mm - baseline.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# order_key forwarding
# ---------------------------------------------------------------------------


def test_alns_order_key_determinism():
    """order_key forwarded to DBLF start — determinism still holds."""
    parts = _parts()
    asc_key = lambda p: (p.volume_voxels,)
    a = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=5, order_key=asc_key)
    b = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=5, order_key=asc_key)
    assert a.height_mm == b.height_mm
    assert a.history == b.history


# ---------------------------------------------------------------------------
# Single-part edge case
# ---------------------------------------------------------------------------


def test_alns_single_part():
    """Single part — ALNS must return a valid result without crashing."""
    parts = [_part("only", (10, 10, 10))]
    result = ALNSSolver().solve(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert len(result.placements) == 1
    assert result.height_mm > 0


# ---------------------------------------------------------------------------
# Registry check (benchmark integration)
# ---------------------------------------------------------------------------


def test_alns_in_benchmark_registry():
    """ALNSSolver must be registered under 'alns' key in benchmark registry."""
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.benchmark import _SOLVER_REGISTRY
    assert "alns" in _SOLVER_REGISTRY
    assert _SOLVER_REGISTRY["alns"] is ALNSSolver
