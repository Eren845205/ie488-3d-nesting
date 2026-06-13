"""solvers/dblf_solver.py — DBLF constructive solver wrapper (PLAN_DEMO1 §1.2).

Wraps dblf.dblf WITHOUT modifying dblf.py.  dblf.py is the single source of
truth for the placement logic; this module adapts the function's return value
to the common SolveResult interface.
"""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.voxelize import VoxelPart


class DBLFSolver:
    """Deterministic constructive baseline: Deepest-Bottom-Left-Fill.

    `budget` and `seed` are accepted for interface compatibility but ignored —
    DBLF is a greedy deterministic algorithm with no randomness.
    """

    def solve(
        self,
        parts: List[VoxelPart],
        bin_factory: Callable[[], Bin3D],
        *,
        budget: int = 0,
        seed: int = 42,
        order_key: Optional[Callable[[VoxelPart], tuple]] = None,
    ) -> SolveResult:
        t_start = time.perf_counter()
        placements, bin3d = dblf(parts, bin_factory, order_key=order_key)
        elapsed = time.perf_counter() - t_start

        return SolveResult(
            placements=placements,
            bin3d=bin3d,
            height_mm=bin3d.max_height_mm(),
            density=bin3d.packing_density(),
            time_s=elapsed,
            history=[],
            meta={
                "solver": "dblf",
                "params": {"order_key": str(order_key)},
            },
        )
