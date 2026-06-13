"""solvers/tabu_solver.py — Tabu Search solver (PLAN_DEMO1 §5.2).

Budget contract
---------------
`budget` = total number of neighbourhood decode evaluations.  Each search step
generates exactly ONE candidate neighbour and decodes it, so:

    total_decodes == budget  (exactly, reported in meta['params']['total_decodes'])

This matches SA's contract (one decode per iteration) and makes cross-solver
comparison fair when all solvers are given the same budget.

When budget == 0 the DBLF baseline is returned without any search.

Neighbourhood
--------------
Reuses sa3d._neighbour move set (imported, not copied):
  - swap(i, j)            — swap two positions in the sequence
  - insert(i)             — remove part at i, reinsert at random position
  - reverse segment       — 2-opt style reverse of a contiguous sub-sequence
  - orientation flip(i)   — change part i's orientation to a different index

Tabu list
----------
Move signatures stored as a dict {signature: expiry_step} for O(1) lookup:
  - swap move     → ("swap",  min(i,j), max(i,j))
  - insert move   → ("ins",  i, dest)          (source index, destination index)
  - reverse seg   → ("rev",  lo, hi)
  - orient flip   → ("ori",  i, new_oi)

Because _neighbour returns the mutated solution without exposing the move
type, TabuSolver generates the move type separately using a parallel RNG call
that mirrors the logic in _neighbour exactly.  This avoids modifying sa3d.py.

Aspiration criterion
---------------------
If a tabu move produces a solution STRICTLY better than the best-so-far, the
tabu status is overridden and the move is accepted (classic aspiration).

Best-so-far guarantee
---------------------
Initialised from DBLF baseline.  The search can never finish worse than DBLF.

Determinism
-----------
All randomness flows through one seeded random.Random.  The neighbour
generation uses the same RNG sequence as sa3d._neighbour with identical
branching, so the tabu evaluation is fully reproducible.
"""

from __future__ import annotations

import random
import time
from typing import Callable, List, Optional, Tuple

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.solvers.base import SolveResult, Solution, decode
from src.nesting3d.voxelize import VoxelPart

_DEFAULT_TENURE = 7


def _neighbour_with_signature(
    solution: Solution,
    rng: random.Random,
) -> Tuple[Solution, tuple]:
    """Generate one neighbour and return (new_solution, move_signature).

    Mirrors the branching in sa3d._neighbour EXACTLY so that the RNG stream
    stays in sync.  The move signature is a hashable tuple for tabu list storage.

    Move probability bands (must match sa3d._neighbour):
      [0.00, 0.25)  swap(i, j)
      [0.25, 0.40)  insert(i)
      [0.40, 0.50)  reverse segment [i, j]
      [0.50, 1.00)  orientation flip(i)
    """
    n = len(solution)
    new = list(solution)
    if n < 2:
        return new, ("noop",)

    move = rng.random()
    if move < 0.25:
        i = rng.randrange(n)
        j = rng.randrange(n)
        new[i], new[j] = new[j], new[i]
        sig = ("swap", min(i, j), max(i, j))
    elif move < 0.40:
        i = rng.randrange(n)
        elem = new.pop(i)
        dest = rng.randrange(n)
        new.insert(dest, elem)
        sig = ("ins", i, dest)
    elif move < 0.50:
        i = rng.randrange(n)
        j = rng.randrange(n)
        lo, hi = (i, j) if i <= j else (j, i)
        new[lo:hi + 1] = reversed(new[lo:hi + 1])
        sig = ("rev", lo, hi)
    else:
        i = rng.randrange(n)
        part, oi = new[i]
        n_or = len(part.orientations)
        if n_or > 1:
            choices = [k for k in range(n_or) if k != oi]
            new_oi = rng.choice(choices)
            new[i] = (part, new_oi)
            sig = ("ori", i, new_oi)
        else:
            sig = ("ori_skip", i)
    return new, sig


class TabuSolver:
    """Tabu Search over the DBLF decoder.

    Parameters
    ----------
    tenure         : number of iterations a move stays tabu (default 7)

    Budget contract
    ---------------
    `budget` = total number of neighbourhood decode evaluations.
    Each search step generates exactly ONE neighbour and decodes it.
    total_decodes == budget exactly.  This matches SA's one-decode-per-iteration
    contract so cross-solver comparison with equal budget is fair.

    Single-candidate design note
    ----------------------------
    Each iteration generates EXACTLY ONE candidate neighbour, not a full
    neighbourhood scan.  The accepted move is therefore a tabu-excluded random
    walk rather than the classical "best admissible neighbour" strategy.
    Practical consequences:
      - Exploration is cheaper (one decode/step, equal budget to SA).
      - Solution quality may lag behind SA on hard instances because there is
        no "pick the best of k neighbours" step.
      - k > 1 candidate sampling is a known future improvement (left for a
        dedicated tuning phase); the current design is intentional for the
        demo comparison at fixed equal budget.
    """

    def __init__(
        self,
        tenure: int = _DEFAULT_TENURE,
    ) -> None:
        self.tenure = tenure

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
        rng = random.Random(seed)

        # DBLF baseline — start of the tabu walk.
        base_placements, base_bin = dblf(parts, bin_factory, order_key=order_key)
        by_id = {p.id: p for p in parts}
        current: Solution = [
            (by_id[pl.part_id], pl.orientation_idx) for pl in base_placements
        ]
        baseline_height = base_bin.max_height_mm()

        # best-so-far initialised from baseline (guarantee: can never regress).
        best: Solution = list(current)
        best_height = baseline_height
        history: List[float] = [baseline_height]

        if budget == 0:
            best_placements, best_bin = decode(best, bin_factory)
            elapsed = time.perf_counter() - t_start
            return SolveResult(
                placements=best_placements,
                bin3d=best_bin,
                height_mm=best_bin.max_height_mm(),
                density=best_bin.packing_density(),
                time_s=elapsed,
                history=history,
                meta={
                    "solver": "tabu",
                    "params": {
                        "tenure": self.tenure,
                        "seed": seed,
                        "budget": budget,
                        "total_decodes": 0,
                        "tabu_hits": 0,
                        "aspiration_accepts": 0,
                        "iterations": 0,
                    },
                },
            )

        # Tabu list: deque of (signature, expiry_iter) pairs.
        # We store signatures in a dict signature -> expiry for O(1) lookup.
        tabu_dict: dict = {}
        tabu_hits = 0
        aspiration_accepts = 0
        total_decodes = 0

        for step in range(budget):
            # Generate exactly ONE neighbour candidate (budget = decode count).
            cand_sol, sig = _neighbour_with_signature(current, rng)
            _, cand_bin = decode(cand_sol, bin_factory)
            total_decodes += 1
            cand_height = cand_bin.max_height_mm()

            is_tabu = tabu_dict.get(sig, -1) >= step

            if is_tabu:
                tabu_hits += 1
                # Aspiration: accept tabu move if it beats global best.
                if cand_height < best_height:
                    aspiration_accepts += 1
                    current = cand_sol
                    tabu_dict[sig] = step + self.tenure
                    best_height = cand_height
                    best = list(cand_sol)
                # else: tabu and no aspiration — do not move (stay at current)
            else:
                # Non-tabu: always accept (classic tabu: accept best neighbour;
                # with 1 candidate the best IS the only one).
                current = cand_sol
                tabu_dict[sig] = step + self.tenure
                if cand_height < best_height:
                    best_height = cand_height
                    best = list(cand_sol)

            history.append(best_height)

        # Final canonical decode.
        best_placements, best_bin = decode(best, bin_factory)
        elapsed = time.perf_counter() - t_start

        return SolveResult(
            placements=best_placements,
            bin3d=best_bin,
            height_mm=best_bin.max_height_mm(),
            density=best_bin.packing_density(),
            time_s=elapsed,
            history=history,
            meta={
                "solver": "tabu",
                "params": {
                    "tenure": self.tenure,
                    "seed": seed,
                    "budget": budget,
                    "total_decodes": total_decodes,
                    "tabu_hits": tabu_hits,
                    "aspiration_accepts": aspiration_accepts,
                    "baseline_height_mm": baseline_height,
                    "iterations": budget,
                },
            },
        )
