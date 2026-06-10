"""Tests for src/metaheuristic.py — Simulated Annealing optimization layer.

Covers:
  - decode() respects the given order and never overlaps / leaves the plate
  - SA is deterministic for a fixed seed
  - SA never regresses below its starting order (best-so-far retention)
  - SA improves utilization on a demand-constrained set (medium)
  - small set: all parts already fit, so utilization equals total part area ratio
"""

from pathlib import Path

import pytest

from src.bl import _overlaps, utilization_pct
from src.loader import load_parts
from src.metaheuristic import decode, simulated_annealing
from src.part import Part
from src.plate import Plate

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SET = {
    "small": _PROJECT_ROOT / "data" / "test_set_small.csv",
    "medium": _PROJECT_ROOT / "data" / "test_set_medium.csv",
    "stress": _PROJECT_ROOT / "data" / "test_set_stress.csv",
}


def _no_overlaps(placements, plate):
    """Assert no two placements overlap and all stay within the plate."""
    m = plate.margin_mm
    for p in placements:
        assert p.x >= m - 1e-3
        assert p.y >= m - 1e-3
        assert p.x + p.width <= plate.width_mm - m + 1e-3
        assert p.y + p.height <= plate.height_mm - m + 1e-3
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            a, b = placements[i], placements[j]
            assert not _overlaps(
                a.x, a.y, a.width, a.height,
                b.x, b.y, b.width, b.height, m,
            )


def test_decode_respects_order_and_is_valid():
    plate = Plate()
    parts = load_parts(_SET["medium"])
    placements, unplaced = decode(parts, plate)
    # every part is accounted for exactly once
    assert len(placements) + len(unplaced) == len(parts)
    _no_overlaps(placements, plate)


def test_decode_order_changes_result():
    """A different order should be able to yield a different placement set."""
    plate = Plate()
    parts = load_parts(_SET["medium"])
    placed_a, _ = decode(parts, plate)
    placed_b, _ = decode(list(reversed(parts)), plate)
    # Not a hard guarantee in theory, but for this constrained set the placed
    # counts differ — confirms order is actually the decision variable.
    assert (len(placed_a), tuple(p.part_id for p in placed_a)) != (
        len(placed_b),
        tuple(p.part_id for p in placed_b),
    )


def test_sa_is_deterministic():
    plate = Plate()
    parts = load_parts(_SET["medium"])
    r1 = simulated_annealing(parts, plate, seed=42, iterations=300)
    r2 = simulated_annealing(parts, plate, seed=42, iterations=300)
    assert r1.best_utilization == r2.best_utilization
    assert [p.part_id for p in r1.placements] == [p.part_id for p in r2.placements]


def test_sa_never_regresses_below_start():
    plate = Plate()
    parts = load_parts(_SET["medium"])
    res = simulated_annealing(parts, plate, seed=1, iterations=500)
    assert res.best_utilization >= res.initial_utilization - 1e-9


def test_sa_result_is_valid_packing():
    plate = Plate()
    parts = load_parts(_SET["stress"])
    res = simulated_annealing(parts, plate, seed=7, iterations=200)
    _no_overlaps(res.placements, plate)
    # utilization recomputed from placements matches the reported best
    assert utilization_pct(res.placements, plate) == pytest.approx(
        res.best_utilization, abs=1e-6
    )


def test_sa_improves_on_constrained_set():
    """On medium (demand 111% of plate) ordering matters → SA should help."""
    plate = Plate()
    parts = load_parts(_SET["medium"])
    res = simulated_annealing(parts, plate, seed=42, iterations=2000)
    assert res.best_utilization >= res.initial_utilization
    # Expect a real (non-trivial) gain on this set.
    assert res.best_utilization > res.initial_utilization + 0.5


def test_small_set_is_already_full():
    """All small-set parts fit, so utilization equals total-area ratio and SA
    cannot exceed it."""
    plate = Plate()
    parts = load_parts(_SET["small"])
    total_area = sum(p.width_mm * p.height_mm for p in parts)
    max_possible = 100.0 * total_area / (plate.width_mm * plate.height_mm)
    res = simulated_annealing(parts, plate, seed=42, iterations=200)
    assert res.best_utilization == pytest.approx(max_possible, abs=1e-6)
    assert len(res.unplaced) == 0
