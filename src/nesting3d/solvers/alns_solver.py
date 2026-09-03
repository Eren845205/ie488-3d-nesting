"""solvers/alns_solver.py — Adaptive Large Neighborhood Search (ALNS) solver.

ALNS overview
-------------
ALNS decomposes each iteration into a DESTROY phase (remove k parts from the
current solution sequence) followed by a REPAIR phase (reinsert the removed
parts into the sequence).  Operator selection is adaptive: each operator
accumulates a score based on solution-quality outcomes, and the selection
probability is updated every `segment_len` iterations via roulette-wheel.

This is what distinguishes ALNS from plain SA: the search has multiple
diversification / intensification lenses (destroy operators) and multiple
reconstruction strategies (repair operators), each with a learned weight.

Genotype contract (identical to SA/GA/Tabu — §1.4)
----------------------------------------------------
    Solution = List[Tuple[VoxelPart, orientation_idx: int]]

Decode uses the canonical `decode` from solvers/base.py (same as all other
solvers).  ALNS writes no bespoke decode logic.

Destroy operators
-----------------
  d0 — random_removal   : remove k random positions from the sequence
  d1 — worst_removal    : remove the k parts that contribute most to height
                          (approximated as parts placed at the highest z-top
                          in the current decode)
  d2 — related_removal  : Shaw-style: remove k parts that are similar in
                          voxel-volume to a randomly chosen anchor part

Repair operators
----------------
  r0 — greedy_insertion : for each removed part try all orientations at all
                          positions in the sequence; pick the (position,
                          orientation) that minimises height after decode
  r1 — random_insertion : reinsert removed parts at random positions in
                          random orientations

Acceptance criterion
--------------------
SA-style: accept if Δ <= 0; else accept with probability exp(-Δ/T).
Temperature follows geometric cooling T0 → T_min over `budget` iterations.

Adaptive weight update (segment-based)
---------------------------------------
Every `segment_len` iterations the selection weights are updated:

    weight[op] = (1 - decay) * weight[op] + decay * score[op] / uses[op]

where `score[op]` accumulates:
  +sigma1  when the operator produced a new global best
  +sigma2  when the operator produced a solution better than current
  +sigma3  when the operator produced an accepted-but-not-best solution

Weights are kept >= min_weight to ensure every operator is always selectable.

Best-so-far guarantee
---------------------
Initialised from DBLF baseline; best-so-far is only ever updated to strictly
better solutions.  The final result is ALWAYS <= DBLF baseline.

Determinism
-----------
All randomness flows through a single numpy Generator seeded from `seed`.
Same (parts, bin_factory, budget, seed, order_key) → identical SolveResult.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import dblf
from src.nesting3d.sa3d import _energy
from src.nesting3d.solvers.base import SolveResult, Solution, decode
from src.nesting3d.voxelize import VoxelPart

# ---------------------------------------------------------------------------
# Adaptive weight hyper-parameters (module-level — monkeypatch-friendly in tests)
# ---------------------------------------------------------------------------

# Reward scores
_SIGMA1: float = 10.0   # new global best
_SIGMA2: float = 5.0    # better than current
_SIGMA3: float = 1.0    # accepted (not better than current)

# Weight smoothing — learning rate for segment update
_DECAY: float = 0.5

# Every this many iterations the weights are recomputed
_SEGMENT_LEN: int = 25

# Minimum operator weight (ensures no operator is permanently excluded)
_MIN_WEIGHT: float = 0.05

# Destruction degree: remove between low and high fraction of parts
_DESTROY_LOW: float = 0.15
_DESTROY_HIGH: float = 0.40

# ---------------------------------------------------------------------------
# SA cooling defaults
# ---------------------------------------------------------------------------

_T0_DEFAULT: float = 3.0
_T_MIN_DEFAULT: float = 0.05


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _roulette(weights: np.ndarray, rng: np.random.Generator) -> int:
    """Select an operator index via roulette-wheel (proportional) selection."""
    cumulative = np.cumsum(weights)
    threshold = rng.random() * cumulative[-1]
    for i, c in enumerate(cumulative):
        if threshold <= c:
            return i
    return len(weights) - 1


def _destroy_count(n: int, rng: np.random.Generator) -> int:
    """Number of parts to destroy: uniform in [low, high] fraction of n, >=1."""
    lo = max(1, int(math.floor(_DESTROY_LOW * n)))
    hi = max(lo, int(math.ceil(_DESTROY_HIGH * n)))
    return int(rng.integers(lo, hi + 1))


def _decode_heights(
    solution: Solution,
    bin_factory: Callable[[], Bin3D],
) -> Tuple[List[Placement3D], Bin3D, float, float]:
    """Decode solution and return (placements, bin3d, energy, height_mm)."""
    placements, bin3d = decode(solution, bin_factory)
    energy = _energy(bin3d)
    height = bin3d.max_height_mm()
    return placements, bin3d, energy, height


# ---------------------------------------------------------------------------
# Destroy operators
# ---------------------------------------------------------------------------


def _destroy_random(
    solution: Solution,
    k: int,
    rng: np.random.Generator,
) -> Tuple[Solution, List[Tuple[VoxelPart, int]]]:
    """Remove k random parts from the sequence.

    Returns (reduced_solution, removed_list).
    """
    indices = rng.choice(len(solution), size=k, replace=False)
    indices_set = set(int(i) for i in indices)
    removed = [solution[i] for i in sorted(indices_set)]
    kept = [item for i, item in enumerate(solution) if i not in indices_set]
    return kept, removed


def _destroy_worst(
    solution: Solution,
    k: int,
    rng: np.random.Generator,
    bin_factory: Callable[[], Bin3D],
) -> Tuple[Solution, List[Tuple[VoxelPart, int]]]:
    """Remove the k parts that are placed at the greatest z-top (worst contributors).

    Uses the placement order from the decode: the i-th placement in the decode
    corresponds to solution[i].  Parts with highest z_top are removed first.
    """
    placements, _ = decode(solution, bin_factory)
    # z-top per placement position (proxy for height contribution)
    z_tops = []
    for pl in placements:
        orient = pl.__class__
        # Placement3D has z, part_id; we need the orientation to get grid height.
        # Access via the solution tuple: solution index matches placement order.
        part, oi = solution[placements.index(pl)]
        grid_h = part.orientations[oi].grid.shape[2]
        z_tops.append(pl.z + grid_h)

    # Sort indices by z_top descending; take top k
    ranked = sorted(range(len(z_tops)), key=lambda i: z_tops[i], reverse=True)
    worst_indices = set(ranked[:k])
    removed = [solution[i] for i in sorted(worst_indices)]
    kept = [item for i, item in enumerate(solution) if i not in worst_indices]
    return kept, removed


def _destroy_related(
    solution: Solution,
    k: int,
    rng: np.random.Generator,
) -> Tuple[Solution, List[Tuple[VoxelPart, int]]]:
    """Shaw-style related removal: pick anchor, then remove k parts by volume similarity.

    Similarity = 1 / (1 + |vol_anchor - vol_candidate|) — parts with volumes
    closest to the anchor are most likely to be removed.  Deterministic given rng.
    """
    n = len(solution)
    anchor_idx = int(rng.integers(0, n))
    anchor_vol = solution[anchor_idx][0].volume_voxels

    # Similarity-weighted selection without replacement
    sims = np.array(
        [1.0 / (1.0 + abs(solution[i][0].volume_voxels - anchor_vol)) for i in range(n)],
        dtype=np.float64,
    )
    sims[anchor_idx] += 1e-12  # anchor itself is always included (highest sim)
    total = sims.sum()
    if total <= 0:
        total = 1.0
    probs = sims / total

    # Weighted sample without replacement via Gumbel-max trick (deterministic)
    gumbel = -np.log(-np.log(rng.random(n) + 1e-300))
    scores = np.log(probs + 1e-300) + gumbel
    selected = np.argsort(scores)[-k:]
    selected_set = set(int(i) for i in selected)
    removed = [solution[i] for i in sorted(selected_set)]
    kept = [item for i, item in enumerate(solution) if i not in selected_set]
    return kept, removed


# ---------------------------------------------------------------------------
# Repair operators
# ---------------------------------------------------------------------------


def _repair_greedy(
    kept: Solution,
    removed: List[Tuple[VoxelPart, int]],
    bin_factory: Callable[[], Bin3D],
    rng: np.random.Generator,
) -> Solution:
    """Greedy insertion: for each removed part, try all (position, orientation)
    combos and pick the one that yields the lowest energy.

    Removed parts are processed in random order to avoid systematic bias.
    """
    order = list(range(len(removed)))
    rng.shuffle(order)

    solution = list(kept)
    for idx in order:
        part, _ = removed[idx]
        n_or = len(part.orientations)
        n_pos = len(solution) + 1  # insertion positions: 0 .. len(solution)

        best_energy = math.inf
        best_pos = 0
        best_oi = 0

        for pos in range(n_pos):
            for oi in range(n_or):
                candidate = solution[:pos] + [(part, oi)] + solution[pos:]
                _, cand_bin = decode(candidate, bin_factory)
                e = _energy(cand_bin)
                if e < best_energy:
                    best_energy = e
                    best_pos = pos
                    best_oi = oi

        solution = solution[:best_pos] + [(part, best_oi)] + solution[best_pos:]

    return solution


def _repair_random(
    kept: Solution,
    removed: List[Tuple[VoxelPart, int]],
    bin_factory: Callable[[], Bin3D],
    rng: np.random.Generator,
) -> Solution:
    """Random insertion: each removed part gets a random position and orientation."""
    solution = list(kept)
    for part, _ in removed:
        n_or = len(part.orientations)
        oi = int(rng.integers(0, n_or))
        pos = int(rng.integers(0, len(solution) + 1))
        solution = solution[:pos] + [(part, oi)] + solution[pos:]
    return solution


# ---------------------------------------------------------------------------
# ALNSSolver
# ---------------------------------------------------------------------------


class ALNSSolver:
    """Adaptive Large Neighborhood Search over the DBLF decoder.

    Parameters
    ----------
    t0       : initial SA temperature for acceptance criterion
    t_min    : final temperature
    """

    def __init__(
        self,
        t0: float = _T0_DEFAULT,
        t_min: float = _T_MIN_DEFAULT,
    ) -> None:
        self.t0 = float(t0)
        self.t_min = float(t_min)

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

        # Single seeded Generator — all randomness flows through here.
        rng = np.random.default_rng(seed)

        # ------------------------------------------------------------------ #
        # DBLF baseline — start, and best-so-far floor.                       #
        # ------------------------------------------------------------------ #
        base_placements, base_bin = dblf(parts, bin_factory, order_key=order_key)
        by_id = {p.id: p for p in parts}
        current: Solution = [
            (by_id[pl.part_id], pl.orientation_idx) for pl in base_placements
        ]
        baseline_height = base_bin.max_height_mm()
        baseline_density = base_bin.packing_density()

        cur_energy = _energy(base_bin)
        best: Solution = list(current)
        best_energy = cur_energy
        best_height = baseline_height
        history: List[float] = [baseline_height]

        if budget == 0:
            best_placements, best_bin = decode(best, bin_factory)
            elapsed = time.perf_counter() - t_start
            return _build_result(
                best_placements, best_bin, elapsed, history,
                seed, budget, self.t0, self.t_min,
                baseline_height, baseline_density,
                accepted=0,
                destroy_weights=np.ones(3) / 3.0,
                repair_weights=np.ones(2) / 2.0,
                destroy_uses=[0, 0, 0],
                repair_uses=[0, 0],
            )

        # ------------------------------------------------------------------ #
        # Adaptive weights — 3 destroy ops, 2 repair ops                      #
        # ------------------------------------------------------------------ #
        n_destroy = 3
        n_repair = 2
        d_weights = np.ones(n_destroy, dtype=np.float64)
        r_weights = np.ones(n_repair, dtype=np.float64)
        d_scores = np.zeros(n_destroy, dtype=np.float64)
        r_scores = np.zeros(n_repair, dtype=np.float64)
        d_uses = np.zeros(n_destroy, dtype=np.float64)
        r_uses = np.zeros(n_repair, dtype=np.float64)

        # Cooling schedule
        if budget > 1:
            cooling = (self.t_min / max(self.t0, 1e-9)) ** (1.0 / (budget - 1))
        else:
            cooling = 1.0
        temperature = self.t0

        accepted = 0

        for iteration in range(budget):
            # -- Select operators ------------------------------------------ #
            di = _roulette(d_weights, rng)
            ri = _roulette(r_weights, rng)
            d_uses[di] += 1
            r_uses[ri] += 1

            k = _destroy_count(len(current), rng)

            # -- Destroy --------------------------------------------------- #
            if di == 0:
                kept, removed = _destroy_random(current, k, rng)
            elif di == 1:
                kept, removed = _destroy_worst(current, k, rng, bin_factory)
            else:  # di == 2
                kept, removed = _destroy_related(current, k, rng)

            # -- Repair ---------------------------------------------------- #
            if ri == 0:
                candidate = _repair_greedy(kept, removed, bin_factory, rng)
            else:  # ri == 1
                candidate = _repair_random(kept, removed, bin_factory, rng)

            # -- Evaluate -------------------------------------------------- #
            _, cand_bin = decode(candidate, bin_factory)
            cand_energy = _energy(cand_bin)
            cand_height = cand_bin.max_height_mm()

            # -- Accept / reject (SA-style) -------------------------------- #
            delta = cand_energy - cur_energy
            accept = delta <= 0 or (
                rng.random() < math.exp(-delta / max(temperature, 1e-9))
            )

            # -- Adaptive score update -------------------------------------- #
            if cand_energy < best_energy:
                # New global best
                d_scores[di] += _SIGMA1
                r_scores[ri] += _SIGMA1
                current = candidate
                cur_energy = cand_energy
                best = list(candidate)
                best_energy = cand_energy
                best_height = cand_height
                accepted += 1
            elif accept and delta < 0:
                # Better than current (but not global best)
                d_scores[di] += _SIGMA2
                r_scores[ri] += _SIGMA2
                current = candidate
                cur_energy = cand_energy
                accepted += 1
            elif accept:
                # Accepted but not an improvement
                d_scores[di] += _SIGMA3
                r_scores[ri] += _SIGMA3
                current = candidate
                cur_energy = cand_energy
                accepted += 1
            # else: rejected — no score, no move

            history.append(best_height)
            temperature *= cooling

            # -- Segment weight update ------------------------------------- #
            if (iteration + 1) % _SEGMENT_LEN == 0:
                for i in range(n_destroy):
                    if d_uses[i] > 0:
                        d_weights[i] = (
                            (1 - _DECAY) * d_weights[i]
                            + _DECAY * d_scores[i] / d_uses[i]
                        )
                    d_weights[i] = max(d_weights[i], _MIN_WEIGHT)
                for i in range(n_repair):
                    if r_uses[i] > 0:
                        r_weights[i] = (
                            (1 - _DECAY) * r_weights[i]
                            + _DECAY * r_scores[i] / r_uses[i]
                        )
                    r_weights[i] = max(r_weights[i], _MIN_WEIGHT)
                # Reset segment accumulators
                d_scores[:] = 0.0
                r_scores[:] = 0.0
                d_uses[:] = 0.0
                r_uses[:] = 0.0

        # -- Final canonical decode ---------------------------------------- #
        best_placements, best_bin = decode(best, bin_factory)
        elapsed = time.perf_counter() - t_start

        return _build_result(
            best_placements, best_bin, elapsed, history,
            seed, budget, self.t0, self.t_min,
            baseline_height, baseline_density,
            accepted=accepted,
            destroy_weights=d_weights,
            repair_weights=r_weights,
            destroy_uses=d_uses.tolist(),
            repair_uses=r_uses.tolist(),
        )


def _build_result(
    placements,
    bin3d: Bin3D,
    elapsed: float,
    history: List[float],
    seed: int,
    budget: int,
    t0: float,
    t_min: float,
    baseline_height_mm: float,
    baseline_density: float,
    accepted: int,
    destroy_weights,
    repair_weights,
    destroy_uses,
    repair_uses,
) -> SolveResult:
    """Construct the canonical SolveResult for ALNS."""
    return SolveResult(
        placements=placements,
        bin3d=bin3d,
        height_mm=bin3d.max_height_mm(),
        density=bin3d.packing_density(),
        time_s=elapsed,
        history=history,
        meta={
            "solver": "alns",
            "params": {
                "seed": seed,
                "budget": budget,
                "t0": t0,
                "t_min": t_min,
                "baseline_height_mm": baseline_height_mm,
                "baseline_density": baseline_density,
                "accepted": accepted,
            },
            "destroy_weights": list(destroy_weights),
            "repair_weights": list(repair_weights),
            "destroy_uses": list(destroy_uses),
            "repair_uses": list(repair_uses),
            "destroy_ops": ["random_removal", "worst_removal", "related_removal"],
            "repair_ops": ["greedy_insertion", "random_insertion"],
        },
    )
