"""metaheuristic.py — Simulated Annealing (SA) optimization layer.

This module is the project's *contribution beyond the baseline*.  It does NOT
modify the working constructive heuristics (bl.py / bfd.py); instead it builds
ON TOP of them.

Idea (PLAN.md §14 option c — "BL'yi inner-loop yap, parça sıralamasını optimize et"):
  - The constructive Bottom-Left rule places parts in whatever ORDER it is given.
  - That order is the decision variable.
  - Simulated Annealing searches the space of orderings to maximize plate
    utilization (placed area / plate area).

The Bottom-Left positioning logic (collision test, candidate points, orientation
enumeration) is reused VERBATIM from src.bl — no duplication, no edits to bl.py.

Determinism: all randomness flows through a single seeded random.Random instance,
so a given (parts, plate, seed, schedule) always yields the same result — required
for reproducible academic results.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from src.bl import (
    Placement,
    _allowed_orientations,
    _candidate_points,
    _fits,
    utilization_pct,
)
from src.part import Part
from src.plate import Plate


# ---------------------------------------------------------------------------
# Decoder — place parts in the EXACT given order (order is the decision variable)
# ---------------------------------------------------------------------------

def decode(order: List[Part], plate: Plate) -> Tuple[List[Placement], List[str]]:
    """Place parts in the caller-supplied order using Bottom-Left positioning.

    Unlike src.bl.bottom_left (which sorts parts by longest edge first), this
    respects `order` exactly.  That ordered sequence IS what the metaheuristic
    optimizes.

    Returns:
        (placements, unplaced_ids)
    """
    placements: List[Placement] = []
    unplaced: List[str] = []

    for part in order:
        placed_this = False
        candidates = _candidate_points(placements, plate)
        candidates.sort(key=lambda c: (c[1], c[0]))  # bottom-left preference

        for w, h, rotated in _allowed_orientations(part):
            for cx, cy in candidates:
                if _fits(cx, cy, w, h, placements, plate):
                    placements.append(
                        Placement(part.id, cx, cy, w, h, rotated)
                    )
                    placed_this = True
                    break
            if placed_this:
                break

        if not placed_this:
            unplaced.append(part.id)

    return placements, unplaced


def _utilization_of_order(order: List[Part], plate: Plate) -> float:
    """Decode an order and return its plate utilization (%)."""
    placements, _ = decode(order, plate)
    return utilization_pct(placements, plate)


# ---------------------------------------------------------------------------
# Neighbour moves on a permutation
# ---------------------------------------------------------------------------

def _neighbour(order: List[Part], rng: random.Random) -> List[Part]:
    """Return a new ordering one move away from `order`.

    Three move types (chosen at random) give the search both local and
    medium-range jumps:
      - swap     : exchange two positions
      - insert   : remove one element and re-insert it elsewhere
      - reverse  : reverse a contiguous segment (2-opt style)
    """
    n = len(order)
    if n < 2:
        return list(order)

    move = rng.random()
    new = list(order)

    if move < 0.5:  # swap
        i, j = rng.randrange(n), rng.randrange(n)
        new[i], new[j] = new[j], new[i]
    elif move < 0.8:  # insert
        i = rng.randrange(n)
        elem = new.pop(i)
        j = rng.randrange(n)
        new.insert(j, elem)
    else:  # reverse segment
        i, j = sorted((rng.randrange(n), rng.randrange(n)))
        new[i:j + 1] = reversed(new[i:j + 1])

    return new


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class SAResult:
    """Outcome of a Simulated Annealing run."""

    placements: List[Placement]
    unplaced: List[str]
    best_utilization: float                 # best utilization found (%)
    initial_utilization: float              # utilization of the starting order (%)
    history: List[float] = field(default_factory=list)  # best-so-far util per iteration
    iterations: int = 0
    accepted: int = 0                       # number of accepted moves


# ---------------------------------------------------------------------------
# Simulated Annealing
# ---------------------------------------------------------------------------

def simulated_annealing(
    parts: List[Part],
    plate: Plate,
    *,
    seed: int = 42,
    iterations: int = 3000,
    t0: float = 2.0,
    t_min: float = 0.01,
    initial_order: Optional[Callable[[List[Part]], List[Part]]] = None,
) -> SAResult:
    """Optimize part ordering with Simulated Annealing to maximize utilization.

    Energy = -utilization (minimizing energy maximizes utilization).  A worse
    neighbour is accepted with probability exp(-Δenergy / T); T cools
    geometrically from `t0` to `t_min` over `iterations` steps.  The best
    ordering ever seen is always retained, so the result never regresses below
    the starting solution.

    Args:
        parts: parts to place (rotation governed by Part.rotatable).
        plate: build platform.
        seed: RNG seed for reproducibility.
        iterations: number of SA steps.
        t0: initial temperature.
        t_min: final temperature (sets the geometric cooling rate).
        initial_order: optional callable producing the starting order; defaults
            to area-descending (a strong, decreasing-style start).

    Returns:
        SAResult with the best placements, utilization, and convergence history.
    """
    rng = random.Random(seed)

    if initial_order is None:
        current = sorted(parts, key=lambda p: p.width_mm * p.height_mm, reverse=True)
    else:
        current = initial_order(list(parts))

    current_util = _utilization_of_order(current, plate)
    initial_util = current_util

    best = list(current)
    best_util = current_util

    # Geometric cooling: T_k = t0 * cooling^k, reaching t_min at the last step.
    if iterations > 1:
        cooling = (t_min / t0) ** (1.0 / (iterations - 1))
    else:
        cooling = 1.0

    history: List[float] = [best_util]
    temperature = t0
    accepted = 0

    for _ in range(iterations):
        candidate = _neighbour(current, rng)
        cand_util = _utilization_of_order(candidate, plate)

        # Energy is -utilization; delta < 0 means improvement.
        delta = -(cand_util - current_util)

        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            current = candidate
            current_util = cand_util
            accepted += 1
            if current_util > best_util:
                best = list(current)
                best_util = current_util

        temperature *= cooling
        history.append(best_util)

    placements, unplaced = decode(best, plate)

    return SAResult(
        placements=placements,
        unplaced=unplaced,
        best_utilization=best_util,
        initial_utilization=initial_util,
        history=history,
        iterations=iterations,
        accepted=accepted,
    )
