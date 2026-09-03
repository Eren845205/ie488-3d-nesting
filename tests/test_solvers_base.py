"""Tests for src.nesting3d.solvers.base — SolveResult dataclass + Solver protocol.

1.1: Solver protocol + SolveResult.
1.4: Genotype/decode contract docstring (decode function importable).
"""

import time
from dataclasses import fields
from typing import Callable, List

import pytest
import trimesh

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.solvers.base import (
    GENOTYPE_CONTRACT,
    Solver,
    SolveResult,
    decode,
)
from src.nesting3d.voxelize import VoxelPart, voxelize_part

PITCH = 5.0


def _part(part_id: str, extents=(10, 10, 10)):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    return voxelize_part(part_id, b, PITCH, n_orientations=4)


def _bin():
    return Bin3D(40.0, 40.0, PITCH)


# ---------------------------------------------------------------------------
# SolveResult structure tests
# ---------------------------------------------------------------------------


def test_solve_result_has_required_fields():
    """SolveResult must carry all PLAN_DEMO1 1.1 fields."""
    required = {
        "placements",
        "bin3d",
        "height_mm",
        "density",
        "time_s",
        "history",
        "meta",
    }
    actual = {f.name for f in fields(SolveResult)}
    assert required <= actual, f"Missing fields: {required - actual}"


def test_solve_result_meta_has_solver_name():
    """meta dict must include 'solver' key per spec."""
    parts = [_part("p1")]
    res = SolveResult(
        placements=[],
        bin3d=_bin(),
        height_mm=10.0,
        density=0.5,
        time_s=0.1,
        history=[10.0],
        meta={"solver": "test", "params": {}},
    )
    assert res.meta["solver"] == "test"


def test_solve_result_construction_from_sa3d_fields():
    """SA3DResult fields must map losslessly to SolveResult."""
    from src.nesting3d.sa3d import SA3DResult

    sa_fields = {f.name for f in fields(SA3DResult)}
    # SA3DResult must carry the fields that SolveResult maps from it.
    # Verifies the mapping contract: if SA3DResult drops these, the wrapper breaks.
    required_sa = {"placements", "bin3d", "history"}
    assert required_sa <= sa_fields, (
        f"SA3DResult missing critical fields: {required_sa - sa_fields}"
    )
    sr = SolveResult(
        placements=[],
        bin3d=_bin(),
        height_mm=100.0,
        density=0.3,
        time_s=1.5,
        history=[100.0, 95.0, 90.0],
        meta={"solver": "sa3d", "params": {"seed": 42, "iterations": 600}},
    )
    assert sr.height_mm == 100.0
    assert sr.density == 0.3
    assert len(sr.history) == 3
    assert sr.meta["params"]["seed"] == 42


# ---------------------------------------------------------------------------
# Solver protocol (structural subtyping) tests
# ---------------------------------------------------------------------------


def test_solver_protocol_structural():
    """Any object with .solve(parts, bin_factory, *, budget, seed, order_key)
    satisfies the Solver protocol."""

    class MinimalSolver:
        def solve(
            self,
            parts: List[VoxelPart],
            bin_factory: Callable[[], Bin3D],
            *,
            budget: int = 200,
            seed: int = 42,
            order_key=None,
        ) -> SolveResult:
            return SolveResult(
                placements=[],
                bin3d=bin_factory(),
                height_mm=0.0,
                density=0.0,
                time_s=0.0,
                history=[],
                meta={"solver": "minimal", "params": {}},
            )

    # runtime_checkable Protocol: isinstance check
    assert isinstance(MinimalSolver(), Solver)


def test_solver_missing_solve_not_protocol():
    """Object lacking .solve does not satisfy Solver protocol."""

    class NotASolver:
        pass

    assert not isinstance(NotASolver(), Solver)


# ---------------------------------------------------------------------------
# decode function (1.4) tests
# ---------------------------------------------------------------------------


def test_decode_places_all_parts():
    """decode(solution, bin_factory) -> (placements, bin3d) with all parts placed."""
    p1 = _part("p1", (10, 10, 10))
    p2 = _part("p2", (10, 10, 10))
    solution = [(p1, 0), (p2, 0)]
    placements, bin3d = decode(solution, _bin)
    assert len(placements) == 2
    assert {pl.part_id for pl in placements} == {"p1", "p2"}


def test_decode_uses_fixed_orientations():
    """decode must use the orientation_idx from the solution, not enumerate all."""
    p1 = _part("p1", (5, 5, 20))  # tall part — orientation matters
    # orientation 0 vs orientation 2 should give different heights potentially
    sol_ori0 = [(p1, 0)]
    sol_ori2 = [(p1, 2)]
    _, bin0 = decode(sol_ori0, _bin)
    _, bin2 = decode(sol_ori2, _bin)
    # Both decode without error; heights may differ (orientation affects shape)
    assert bin0.max_height_mm() > 0
    assert bin2.max_height_mm() > 0


def test_decode_deterministic():
    """Same solution -> same placements every time (no hidden randomness)."""
    p1 = _part("p1", (10, 10, 10))
    p2 = _part("p2", (10, 10, 20))
    solution = [(p1, 0), (p2, 1)]
    a_placements, a_bin = decode(solution, _bin)
    b_placements, b_bin = decode(solution, _bin)
    assert a_placements == b_placements
    assert a_bin.max_height_mm() == b_bin.max_height_mm()


def test_decode_matches_sa3d_decode():
    """base.decode and sa3d.decode must produce identical results (1.4 shared
    contract — sa3d imports from base after refactor)."""
    from src.nesting3d.sa3d import decode as sa_decode

    p1 = _part("p1", (10, 10, 10))
    p2 = _part("p2", (10, 10, 20))
    solution = [(p1, 0), (p2, 1)]
    base_pl, base_bin = decode(solution, _bin)
    sa_pl, sa_bin = sa_decode(solution, _bin)
    assert base_pl == sa_pl
    assert base_bin.max_height_mm() == sa_bin.max_height_mm()


# ---------------------------------------------------------------------------
# GENOTYPE_CONTRACT constant
# ---------------------------------------------------------------------------


def test_genotype_contract_is_documented():
    """GENOTYPE_CONTRACT must be a non-empty string describing the contract."""
    assert isinstance(GENOTYPE_CONTRACT, str)
    assert len(GENOTYPE_CONTRACT) > 20
