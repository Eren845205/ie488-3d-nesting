"""solvers/sa_solver.py — Simulated Annealing solver wrapper (PLAN_DEMO1 §1.3).

Wraps sa3d.simulated_annealing_3d WITHOUT modifying sa3d.py.  sa3d.py is the
single source of truth for the SA logic.  This module adapts the SA3DResult to
the common SolveResult interface.

Determinism guarantee: same (parts, bin_factory, budget, seed, order_key) ->
bire bir identical SolveResult (same height_mm, same history, same placements).
This is guaranteed because simulated_annealing_3d uses a seeded random.Random
and this wrapper simply forwards the seed unchanged.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.voxelize import VoxelPart


class SASolver:
    """Simulated Annealing over the DBLF decoder.

    `budget` is forwarded as `iterations` to simulated_annealing_3d.

    Protocol note — t0 / t_min:
      The Solver protocol (solvers/base.py) only mandates
      solve(parts, bin_factory, *, budget, seed, order_key).  t0 and t_min
      are SA-specific hyper-parameters that are NOT part of the protocol and
      are therefore hard-coded here (t0=3.0, t_min=0.05, matching sa3d.py
      defaults calibrated 2026-06-09).
      Faz 4 plan ("t0=auto"): when auto-calibration is added, expose t0/t_min
      as __init__ constructor args on SASolver rather than extending the
      protocol, so other solvers (DBLFSolver, future solvers) remain unaffected.
    """

    def solve(
        self,
        parts: List[VoxelPart],
        bin_factory: Callable[[], Bin3D],
        *,
        budget: int = 200,
        seed: int = 42,
        order_key: Optional[Callable[[VoxelPart], tuple]] = None,
    ) -> SolveResult:
        t_start = time.perf_counter()
        res = simulated_annealing_3d(
            parts,
            bin_factory,
            seed=seed,
            iterations=budget,
            order_key=order_key,
        )
        elapsed = time.perf_counter() - t_start

        return SolveResult(
            placements=res.placements,
            bin3d=res.bin3d,
            height_mm=res.best_height_mm,
            density=res.best_density,
            time_s=elapsed,
            history=res.history,
            meta={
                "solver": "sa",
                "params": {
                    "seed": seed,
                    "iterations": budget,
                    "baseline_height_mm": res.baseline_height_mm,
                    "accepted": res.accepted,
                },
            },
        )
