"""sa3d.py — Simulated Annealing layer over the DBLF decoder (PLAN_3D.md §2.7).

Direct port of the 2D src/metaheuristic.py skeleton; differences only where
3D requires them:
  - Solution  = ordered list of (part, orientation_idx) — orientation joined
    the decision variable (2D had only the order; rotation was enumerated
    inside the decoder).
  - Decoder   = dblf.place_in_order with the solution's FIXED orientation per
    part (single-orientation decode keeps SA iterations cheap).
  - Energy    = max_height_mm + 0.1 * rms_height_mm.  Primary objective is
    the bin height; the RMS term breaks the plateau ties a discrete voxel
    heightmap produces — it strictly prefers flat, spread-out poses over tall
    ones of equal volume, giving SA a gradient toward compact layouts.
  - Start     = the full DBLF baseline solution (order AND chosen
    orientations), so SA can never end worse than the baseline
    (best-so-far is retained, same guarantee as 2D).

Determinism: all randomness flows through one seeded random.Random — same
(parts, bin, seed, schedule) always gives the same result.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Callable, List, Tuple

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import dblf, place_in_order
from src.nesting3d.voxelize import VoxelPart

Solution = List[Tuple[VoxelPart, int]]


def decode(solution: Solution, bin_factory: Callable[[], Bin3D]):
    """Place the solution's parts in order with their fixed orientations."""
    parts = [p for p, _ in solution]
    orients = [oi for _, oi in solution]
    bin3d = bin_factory()
    placements = place_in_order(parts, bin3d, lambda i, _p: (orients[i],))
    return placements, bin3d


def _energy(bin3d: Bin3D) -> float:
    """max height (primary, mm) + RMS compactness gradient (see Bin3D.rms_height_mm)."""
    return bin3d.max_height_mm() + 0.1 * bin3d.rms_height_mm()


def _neighbour(solution: Solution, rng: random.Random) -> Solution:
    """One move away: order move (as in 2D) or an orientation flip."""
    n = len(solution)
    new = list(solution)
    if n < 2:
        return new

    move = rng.random()
    if move < 0.25:  # swap
        i, j = rng.randrange(n), rng.randrange(n)
        new[i], new[j] = new[j], new[i]
    elif move < 0.40:  # insert
        i = rng.randrange(n)
        elem = new.pop(i)
        new.insert(rng.randrange(n), elem)
    elif move < 0.50:  # reverse segment (2-opt style)
        i, j = sorted((rng.randrange(n), rng.randrange(n)))
        new[i:j + 1] = reversed(new[i:j + 1])
    else:  # orientation flip
        i = rng.randrange(n)
        part, oi = new[i]
        n_or = len(part.orientations)
        if n_or > 1:
            choices = [k for k in range(n_or) if k != oi]
            new[i] = (part, rng.choice(choices))
    return new


@dataclass
class SA3DResult:
    """Outcome of a 3D Simulated Annealing run."""

    placements: List[Placement3D]
    bin3d: Bin3D
    best_height_mm: float
    baseline_height_mm: float           # height of the DBLF starting solution
    best_density: float
    baseline_density: float
    history: List[float] = field(default_factory=list)  # best-so-far height/iter
    iterations: int = 0
    accepted: int = 0


def simulated_annealing_3d(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    *,
    seed: int = 42,
    iterations: int = 600,
    t0: float = 3.0,
    t_min: float = 0.05,
) -> SA3DResult:
    """Minimize bin height by searching (order, orientation) space with SA.

    Energy deltas are in mm, so t0 is too: t0=3 (calibrated 2026-06-09; 8 was
    too hot — pure random walk) accepts early uphill moves below one voxel
    layer; geometric cooling reaches t_min at the last step.  Best solution
    ever seen is retained — never regresses below baseline.
    """
    rng = random.Random(seed)

    # Start from the full DBLF baseline (order + orientation choices).
    base_placements, base_bin = dblf(parts, bin_factory)
    by_id = {p.id: p for p in parts}
    current: Solution = [
        (by_id[pl.part_id], pl.orientation_idx) for pl in base_placements
    ]
    baseline_height = base_bin.max_height_mm()
    baseline_density = base_bin.packing_density()

    cur_bin = base_bin
    cur_energy = _energy(cur_bin)

    best = list(current)
    best_bin = cur_bin
    best_energy = cur_energy

    cooling = (t_min / t0) ** (1.0 / (iterations - 1)) if iterations > 1 else 1.0
    temperature = t0
    history: List[float] = [best_bin.max_height_mm()]
    accepted = 0

    for _ in range(iterations):
        candidate = _neighbour(current, rng)
        _, cand_bin = decode(candidate, bin_factory)
        cand_energy = _energy(cand_bin)

        delta = cand_energy - cur_energy
        if delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-9)):
            current, cur_bin, cur_energy = candidate, cand_bin, cand_energy
            accepted += 1
            if cur_energy < best_energy:
                best, best_bin, best_energy = list(current), cur_bin, cur_energy

        temperature *= cooling
        history.append(best_bin.max_height_mm())

    best_placements, best_bin = decode(best, bin_factory)
    return SA3DResult(
        placements=best_placements,
        bin3d=best_bin,
        best_height_mm=best_bin.max_height_mm(),
        baseline_height_mm=baseline_height,
        best_density=best_bin.packing_density(),
        baseline_density=baseline_density,
        history=history,
        iterations=iterations,
        accepted=accepted,
    )
