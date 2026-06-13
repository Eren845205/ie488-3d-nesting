"""solvers/ga_solver.py — Genetic Algorithm solver (PLAN_DEMO1 §5.1).

Budget contract
---------------
`budget` passed to solve() equals pop_size * n_generations.  If the caller
passes a budget that does not evenly divide by pop_size, n_generations is
clamped to floor(budget / pop_size); if budget < pop_size the population is
still fully evaluated once (1 generation).  The actual total decode count is
reported in meta['params']['total_decodes'] for transparent comparison.

    total_decodes = pop_size * actual_generations
                    + pop_size  (initial population evaluation)
                  = pop_size * (actual_generations + 1)

Genotype contract (PLAN_DEMO1 §1.4)
-------------------------------------
Individual = List[Tuple[VoxelPart, orientation_idx: int]]
Same shared decode() from solvers/base.py as DBLF and SA — quality comparison
is fair because the placement routine is identical across solvers.

Initial population seeding
---------------------------
The first individual is always the DBLF solution (same order and orientation
choices that DBLF picks).  Subsequent individuals are produced by shuffling
the DBLF order with the seeded RNG and randomly reassigning orientations.
Because best-so-far is initialised from the DBLF individual, the GA can
NEVER finish worse than DBLF (the baseline guarantee).

Operators
---------
Order crossover (OX): preserves relative order of one parent's part sequence
while filling gaps from the other parent — standard permutation crossover.

Uniform crossover for orientations: each orientation index is independently
inherited from one of the two parents with p=0.5.

Mutation: reuses sa3d._neighbour move set (swap, insert, 2-opt segment
reverse, orientation flip) — imported, never copied.

Elitism: top-1 individual (current best) always survives to the next
generation, preventing regression.

Determinism: all randomness flows through one seeded random.Random instance
created at the start of solve() — same (parts, bin_factory, budget, seed,
order_key, pop_size, n_generations, crossover_rate, mutation_rate) always
produces the same SolveResult.
"""

from __future__ import annotations

import random
import time
from typing import Callable, List, Optional, Tuple

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.sa3d import _neighbour
from src.nesting3d.solvers.base import SolveResult, Solution, decode
from src.nesting3d.voxelize import VoxelPart

# Default hyper-parameters (calibrated for typical small-to-medium instances).
_DEFAULT_POP_SIZE = 20
_DEFAULT_N_GEN = 40
_DEFAULT_CROSSOVER_RATE = 0.8
_DEFAULT_MUTATION_RATE = 0.3


def _ox_crossover(
    parent_a: Solution,
    parent_b: Solution,
    rng: random.Random,
) -> Solution:
    """Order Crossover (OX) for part-order + uniform crossover for orientations.

    1. Choose a random contiguous segment from parent_a; copy it to the child.
    2. Fill remaining positions from parent_b in the order parts appear there,
       skipping parts already placed (permutation is preserved).
    3. For each position i in the child, pick the orientation from parent_a[i]
       or parent_b[i] with equal probability.

    The result is a valid permutation of all parts (each exactly once).
    """
    n = len(parent_a)
    if n == 0:
        return []
    if n == 1:
        # Orientation crossover only
        _, oi_a = parent_a[0]
        _, oi_b = parent_b[0]
        chosen_oi = oi_a if rng.random() < 0.5 else oi_b
        return [(parent_a[0][0], chosen_oi)]

    # Step 1: choose segment [lo, hi)
    lo = rng.randrange(n)
    hi = rng.randrange(n)
    if lo > hi:
        lo, hi = hi, lo
    hi += 1  # make hi inclusive → exclusive

    # segment parts (preserving order from parent_a)
    segment_parts = {id(parent_a[i][0]): i for i in range(lo, hi)}

    # Step 2: fill remaining from parent_b (object-identity check)
    child_order: List[Tuple[VoxelPart, int]] = [None] * n  # type: ignore[list-item]
    for i in range(lo, hi):
        child_order[i] = parent_a[i]

    fill_cursor = 0
    for pb_item in parent_b:
        pb_part, pb_oi = pb_item
        if id(pb_part) in segment_parts:
            continue  # already placed by segment
        # advance fill_cursor past segment positions
        while fill_cursor < n and child_order[fill_cursor] is not None:
            fill_cursor += 1
        if fill_cursor >= n:
            break
        child_order[fill_cursor] = (pb_part, pb_oi)
        fill_cursor += 1

    # Build a lookup: part object id -> orientation in each parent for crossover
    pa_oi: dict = {id(p): oi for p, oi in parent_a}
    pb_oi_map: dict = {id(p): oi for p, oi in parent_b}

    # Step 3: uniform orientation crossover at each position.
    # Both pa_oi and pb_oi_map contain every part (each parent is a complete
    # permutation), so the .get(..., oi_child) fallback is dead code —
    # id(part) is always present in both dicts.  The fallback is kept for
    # defensive safety only; the assert below will fire in debug mode if the
    # invariant is ever broken.
    result: Solution = []
    for part, oi_child in child_order:
        assert id(part) in pa_oi and id(part) in pb_oi_map, (
            "OX invariant violated: part missing from parent orientation map — "
            "child_order contains a part not found in both parents"
        )
        oi_a = pa_oi.get(id(part), oi_child)
        oi_b = pb_oi_map.get(id(part), oi_child)
        chosen_oi = oi_a if rng.random() < 0.5 else oi_b
        result.append((part, chosen_oi))
    return result


def _evaluate(individual: Solution, bin_factory: Callable[[], Bin3D]) -> float:
    """Evaluate an individual: returns height_mm (lower = better)."""
    _, bin3d = decode(individual, bin_factory)
    return bin3d.max_height_mm()


def _tournament_select(
    population: List[Solution],
    fitness: List[float],
    k: int,
    rng: random.Random,
) -> Solution:
    """Tournament selection: pick k random candidates, return the best."""
    candidates = rng.sample(range(len(population)), min(k, len(population)))
    best_idx = min(candidates, key=lambda i: fitness[i])
    return list(population[best_idx])


class GASolver:
    """Genetic Algorithm over the DBLF decoder.

    Parameters
    ----------
    pop_size        : population size (default 20)
    n_generations   : number of GA generations (default 40)
    crossover_rate  : probability of crossover vs cloning (default 0.8)
    mutation_rate   : probability of applying a mutation move per individual
                      per generation (default 0.3)
    tournament_k    : tournament size for parent selection (default 3)

    Budget contract
    ---------------
    The `budget` argument to solve() is the primary budget interface for the
    portfolio runner.  When budget > 0, it overrides n_generations:

        actual_generations = max(1, budget // pop_size)

    total_decodes reported in meta = pop_size * (actual_generations + 1).
    This includes initial population evaluation (generation 0).
    The DBLF call that seeds the population is NOT counted in total_decodes
    (it runs unconditionally and is shared with the baseline guarantee).
    When budget == 0, no population decodes are performed; the DBLF result
    is reused directly and total_decodes == 0 exactly.
    """

    def __init__(
        self,
        pop_size: int = _DEFAULT_POP_SIZE,
        n_generations: int = _DEFAULT_N_GEN,
        crossover_rate: float = _DEFAULT_CROSSOVER_RATE,
        mutation_rate: float = _DEFAULT_MUTATION_RATE,
        tournament_k: int = 3,
    ) -> None:
        self.pop_size = pop_size
        self.n_generations = n_generations
        self.crossover_rate = crossover_rate
        self.mutation_rate = mutation_rate
        self.tournament_k = tournament_k

    def solve(
        self,
        parts: List[VoxelPart],
        bin_factory: Callable[[], Bin3D],
        *,
        budget: int = 200,
        seed: int = 42,
        order_key=None,
    ) -> SolveResult:
        t_start = time.perf_counter()
        rng = random.Random(seed)

        # Derive actual generation count from budget.
        if budget > 0:
            actual_generations = max(1, budget // self.pop_size)
        else:
            actual_generations = 0

        # Build DBLF baseline individual (order + orientations from DBLF).
        base_placements, base_bin = dblf(parts, bin_factory, order_key=order_key)
        by_id = {p.id: p for p in parts}
        dblf_individual: Solution = [
            (by_id[pl.part_id], pl.orientation_idx) for pl in base_placements
        ]
        baseline_height = base_bin.max_height_mm()

        # Initialise best-so-far from DBLF (baseline guarantee).
        best: Solution = list(dblf_individual)
        best_height = baseline_height
        history: List[float] = [baseline_height]

        if actual_generations == 0:
            # Budget 0: return DBLF baseline immediately.
            # The DBLF call above already decoded the baseline; re-using its
            # placements/bin avoids a redundant second decode so total_decodes=0
            # is accurate (no neighbourhood evaluations were performed).
            elapsed = time.perf_counter() - t_start
            return SolveResult(
                placements=base_placements,
                bin3d=base_bin,
                height_mm=base_bin.max_height_mm(),
                density=base_bin.packing_density(),
                time_s=elapsed,
                history=history,
                meta={
                    "solver": "ga",
                    "params": {
                        "pop_size": self.pop_size,
                        "n_generations": 0,
                        "actual_generations": 0,
                        "seed": seed,
                        "crossover_rate": self.crossover_rate,
                        "mutation_rate": self.mutation_rate,
                        "total_decodes": 0,
                        "baseline_height_mm": baseline_height,
                    },
                },
            )

        # Build initial population.
        # Individual 0: pure DBLF solution.
        population: List[Solution] = [list(dblf_individual)]
        # Remaining individuals: shuffled DBLF order + random orientation choices.
        for _ in range(self.pop_size - 1):
            individual = list(dblf_individual)
            rng.shuffle(individual)
            # Random orientation per part.
            new_ind: Solution = []
            for part, _ in individual:
                n_or = len(part.orientations)
                new_oi = rng.randrange(n_or)
                new_ind.append((part, new_oi))
            population.append(new_ind)

        # Evaluate initial population.
        fitness = [_evaluate(ind, bin_factory) for ind in population]
        total_decodes = self.pop_size  # initial evaluation

        # Update best from initial population.
        for i, h in enumerate(fitness):
            if h < best_height:
                best_height = h
                best = list(population[i])
        history.append(best_height)

        # GA main loop.
        for _gen in range(actual_generations):
            new_population: List[Solution] = []

            # Elitism: carry best individual forward unchanged.
            elite_idx = min(range(len(population)), key=lambda i: fitness[i])
            new_population.append(list(population[elite_idx]))

            # Fill rest of new population.
            while len(new_population) < self.pop_size:
                # Selection.
                parent_a = _tournament_select(
                    population, fitness, self.tournament_k, rng
                )
                parent_b = _tournament_select(
                    population, fitness, self.tournament_k, rng
                )

                # Crossover.
                if rng.random() < self.crossover_rate:
                    child = _ox_crossover(parent_a, parent_b, rng)
                else:
                    child = list(parent_a)

                # Mutation (reuse SA neighbour moves).
                if rng.random() < self.mutation_rate:
                    child = _neighbour(child, rng)

                new_population.append(child)

            population = new_population
            # Evaluate new population.
            fitness = [_evaluate(ind, bin_factory) for ind in population]
            total_decodes += self.pop_size

            # Update best-so-far.
            for i, h in enumerate(fitness):
                if h < best_height:
                    best_height = h
                    best = list(population[i])
            history.append(best_height)

        # Final decode of best individual (canonical result).
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
                "solver": "ga",
                "params": {
                    "pop_size": self.pop_size,
                    "n_generations": actual_generations,
                    "constructor_n_generations": self.n_generations,
                    "actual_generations": actual_generations,
                    "seed": seed,
                    "crossover_rate": self.crossover_rate,
                    "mutation_rate": self.mutation_rate,
                    "total_decodes": total_decodes,
                    "baseline_height_mm": baseline_height,
                    "iterations": total_decodes,
                },
            },
        )
