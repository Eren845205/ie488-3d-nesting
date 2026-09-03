"""Tests for src.nesting3d.solvers.portfolio — portfolio runner (1.5).

Acceptance criteria (PLAN_DEMO1 §1.5):
  - run_portfolio(parts, bin_factory, solvers, budget) -> PortfolioResult
  - PortfolioResult has: results (list[SolveResult]), winner (SolveResult),
    table_md (str), table_csv (str)
  - Deterministic: same inputs -> same outputs
  - budget is per-solver (each solver gets `budget` iterations)
  - winner is the solver with lowest height_mm
"""

import textwrap

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.solvers.portfolio import PortfolioResult, run_portfolio
from src.nesting3d.solvers.sa_solver import SASolver
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
FAST_ITERS = 40


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
    ]


# ---------------------------------------------------------------------------
# PortfolioResult structure
# ---------------------------------------------------------------------------


def test_portfolio_result_has_required_fields():
    """PortfolioResult must expose results, winner, table_md, table_csv."""
    from dataclasses import fields
    field_names = {f.name for f in fields(PortfolioResult)}
    assert {"results", "winner", "table_md", "table_csv"} <= field_names


# ---------------------------------------------------------------------------
# run_portfolio basic behaviour
# ---------------------------------------------------------------------------


def test_run_portfolio_returns_portfolio_result():
    parts = _parts()
    solvers = [DBLFSolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=0, seed=42)
    assert isinstance(pr, PortfolioResult)


def test_run_portfolio_one_solver_winner_is_only_result():
    parts = _parts()
    solvers = [DBLFSolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=0, seed=42)
    assert pr.winner is pr.results[0]


def test_run_portfolio_two_solvers_result_count():
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    assert len(pr.results) == 2


def test_run_portfolio_winner_has_minimum_height():
    """winner must be the result with the smallest height_mm."""
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    min_height = min(r.height_mm for r in pr.results)
    assert pr.winner.height_mm == min_height


def test_run_portfolio_winner_is_one_of_results():
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    assert pr.winner in pr.results


def test_run_portfolio_all_parts_placed_in_winner():
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    assert len(pr.winner.placements) == len(parts)


# ---------------------------------------------------------------------------
# Markdown / CSV table
# ---------------------------------------------------------------------------


def test_run_portfolio_table_md_is_string():
    parts = _parts()
    pr = run_portfolio(parts, _bin, [DBLFSolver()], budget=0, seed=42)
    assert isinstance(pr.table_md, str)
    assert len(pr.table_md) > 0


def test_run_portfolio_table_md_has_header():
    """Markdown table must have a header row with solver, height_mm, density, time_s."""
    parts = _parts()
    pr = run_portfolio(parts, _bin, [DBLFSolver()], budget=0, seed=42)
    lower = pr.table_md.lower()
    assert "solver" in lower
    assert "height" in lower


def test_run_portfolio_table_md_has_winner_marker():
    """The winning row should be visually distinct (e.g. ** or WINNER)."""
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    # winner marker: either '**' bold or 'winner' anywhere in the table
    assert ("**" in pr.table_md) or ("winner" in pr.table_md.lower())


def test_run_portfolio_table_csv_is_string():
    parts = _parts()
    pr = run_portfolio(parts, _bin, [DBLFSolver()], budget=0, seed=42)
    assert isinstance(pr.table_csv, str)
    assert "solver" in pr.table_csv.lower()


def test_run_portfolio_table_csv_parseable():
    """CSV must be parseable with the csv module."""
    import csv
    import io

    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    reader = csv.DictReader(io.StringIO(pr.table_csv))
    rows = list(reader)
    assert len(rows) == 2
    assert "solver" in rows[0]
    assert "height_mm" in rows[0]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_run_portfolio_deterministic():
    """Same args -> identical heights and winner name."""
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr_a = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    pr_b = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    assert pr_a.winner.height_mm == pr_b.winner.height_mm
    assert pr_a.winner.meta["solver"] == pr_b.winner.meta["solver"]
    for a, b in zip(pr_a.results, pr_b.results):
        assert a.height_mm == b.height_mm


def test_run_portfolio_each_result_all_parts_placed():
    """Every solver result must have all parts placed."""
    parts = _parts()
    solvers = [DBLFSolver(), SASolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_ITERS, seed=42)
    for r in pr.results:
        placed = {p.part_id for p in r.placements}
        assert placed == {p.id for p in parts}
