"""solvers/portfolio.py — Portfolio runner (PLAN_DEMO1 §1.5, §5.3).

run_portfolio(parts, bin_factory, solvers, budget, seed, order_key)
  -> PortfolioResult

  Runs each solver in `solvers` against the same (parts, bin_factory) instance.
  All solvers receive the same `budget`, `seed`, and `order_key`.
  Returns a PortfolioResult with:
    - results    : list of SolveResult, one per solver (same order as `solvers`)
    - winner     : the SolveResult with the lowest height_mm (ties: first in list)
    - table_md   : markdown comparison table (winner row bold-marked)
    - table_csv  : CSV comparison table

Default solver set (§5.3 — four-solver portfolio for Demo-1 comparison table):
  dblf   — DBLFSolver  (deterministic greedy baseline)
  sa     — SASolver    (simulated annealing)
  ga     — GASolver    (genetic algorithm; A12 kısmi sinyal: hocanın önerisi)
  tabu   — TabuSolver  (tabu search)

All four solvers share the same genotype/decode contract (solvers/base.py §1.4)
so quality comparisons are fair — the decoder is identical across solvers.

Determinism: this function is a pure loop over deterministic solvers.
Same inputs always produce the same PortfolioResult.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.base import Solver, SolveResult
from src.nesting3d.voxelize import VoxelPart

_CSV_FIELDS = ["solver", "height_mm", "density", "time_s", "iterations", "winner"]


@dataclass
class PortfolioResult:
    """Outcome of running a portfolio of solvers on one instance."""

    results: List[SolveResult]
    winner: SolveResult
    table_md: str
    table_csv: str


def _build_table_md(results: List[SolveResult], winner: SolveResult) -> str:
    """Build a GitHub-flavoured markdown comparison table."""
    header = "| solver | height_mm | density | time_s | iters | winner |"
    sep = "|---|---|---|---|---|---|"
    rows = [header, sep]
    for r in results:
        # Identity check is safe: winner is always the actual object from results
        # (selected by min(enumerate(...)) above), never a copy.
        is_winner = r is winner
        iters = r.meta.get("params", {}).get("iterations", 0)
        mark = " **WINNER**" if is_winner else ""
        solver_name = r.meta.get("solver", "?")
        row = (
            f"| **{solver_name}**{mark}"
            f" | {r.height_mm:.2f}"
            f" | {r.density:.4f}"
            f" | {r.time_s:.3f}"
            f" | {iters}"
            f" | {'**YES**' if is_winner else ''} |"
        )
        rows.append(row)
    return "\n".join(rows)


def _build_table_csv(results: List[SolveResult], winner: SolveResult) -> str:
    """Build a CSV comparison table."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for r in results:
        iters = r.meta.get("params", {}).get("iterations", 0)
        writer.writerow({
            "solver": r.meta.get("solver", "?"),
            "height_mm": round(r.height_mm, 4),
            "density": round(r.density, 6),
            "time_s": round(r.time_s, 6),
            "iterations": iters,
            # r is winner: identity check safe, winner is always a results member.
            "winner": "yes" if r is winner else "",
        })
    return buf.getvalue()


def run_portfolio(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    solvers: List[Solver],
    budget: int = 200,
    seed: int = 42,
    order_key: Optional[Callable[[VoxelPart], tuple]] = None,
) -> PortfolioResult:
    """Run all solvers on the same instance; return comparison table + winner.

    Each solver receives the same budget, seed, and order_key so that the
    comparison is fair (equal resources).  Solvers are run sequentially;
    the result order matches the input `solvers` list.

    Winner selection: lowest height_mm; ties broken by first occurrence.
    """
    if not solvers:
        raise ValueError("solvers list must not be empty")

    results: List[SolveResult] = []
    for solver in solvers:
        result = solver.solve(
            parts,
            bin_factory,
            budget=budget,
            seed=seed,
            order_key=order_key,
        )
        results.append(result)

    winner = min(enumerate(results), key=lambda pair: (pair[1].height_mm, pair[0]))[1]
    table_md = _build_table_md(results, winner)
    table_csv = _build_table_csv(results, winner)

    return PortfolioResult(
        results=results,
        winner=winner,
        table_md=table_md,
        table_csv=table_csv,
    )
