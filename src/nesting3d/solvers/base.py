"""solvers/base.py — Solver protocol + SolveResult dataclass (PLAN_DEMO1 §1.1, §1.4).

Genotype / decode contract (§1.4)
----------------------------------
A *solution* (genotype) is a list of (VoxelPart, orientation_idx) pairs:

    Solution = List[Tuple[VoxelPart, int]]

Decoding a solution means placing the parts in the EXACT order they appear in
the list, each with its fixed orientation index, using dblf.place_in_order.
This shared decode function is used by DBLF, SA, GA, and Tabu Search so that
quality comparisons are fair — the only variable is the search heuristic that
generates the genotype, not the placement routine.

    placements, bin3d = decode(solution, bin_factory)

The `decode` function here is the canonical implementation.  sa3d.decode is
re-exported from this module so that sa3d.py can import it without a circular
dependency (sa3d still owns simulated_annealing_3d; only the stateless decode
helper is shared).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Any, List, Optional, Tuple
from typing import runtime_checkable, Protocol

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.voxelize import VoxelPart

# ---------------------------------------------------------------------------
# §1.4 — Genotype contract (single authoritative location)
# ---------------------------------------------------------------------------

GENOTYPE_CONTRACT: str = (
    "Solution = List[Tuple[VoxelPart, orientation_idx: int]].\n"
    "decode(solution, bin_factory) -> (placements, bin3d):\n"
    "  Parts placed in list order, each with its fixed orientation_idx,\n"
    "  via dblf.place_in_order.  All solvers (DBLF, SA, GA, Tabu) use this\n"
    "  same decode so quality comparisons are fair."
)

Solution = List[Tuple[VoxelPart, int]]


def decode(
    solution: Solution,
    bin_factory: Callable[[], Bin3D],
) -> Tuple[List[Placement3D], Bin3D]:
    """Place the solution's parts in order with their fixed orientations.

    Canonical decode used by all solvers.  sa3d.decode is an alias for this
    function (§1.4 backward-compatible contract).
    """
    from src.nesting3d.dblf import place_in_order

    parts = [p for p, _ in solution]
    orients = [oi for _, oi in solution]
    bin3d = bin_factory()
    placements = place_in_order(parts, bin3d, lambda i, _p: (orients[i],))
    return placements, bin3d


# ---------------------------------------------------------------------------
# §1.1 — SolveResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class SolveResult:
    """Common result container returned by every Solver.

    Fields
    ------
    placements  : ordered list of Placement3D for the best solution found
    bin3d       : Bin3D state after placing `placements`
    height_mm   : max height in mm (primary objective)
    density     : packing density 0..1
    time_s      : wall-clock seconds for this solver
    history     : best-height-mm per iteration (empty for non-iterative solvers)
    meta        : solver-specific metadata; MUST include 'solver' (str) and
                  'params' (dict) keys for portfolio table rendering
    """

    placements: List[Placement3D]
    bin3d: Bin3D
    height_mm: float
    density: float
    time_s: float
    history: List[float] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# §1.1 — Solver protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Solver(Protocol):
    """Protocol for all nesting solvers.

    A solver receives a list of VoxelPart instances, a bin factory, and
    budget/seed/order_key control parameters; it returns a SolveResult.

    Parameters
    ----------
    parts        : list of VoxelPart (qty-expanded; read-only)
    bin_factory  : callable () -> Bin3D — creates a fresh empty bin
    budget       : iteration count (meaning is solver-specific; 0 = greedy/
                   constructive only)
    seed         : integer seed for all randomness (determinism guarantee)
    order_key    : optional sort key for the initial order; forwarded to DBLF
                   baseline construction
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
        ...
