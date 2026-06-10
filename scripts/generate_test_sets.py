"""generate_test_sets.py — Deterministic CSV generator for medium and stress test sets.

PLAN.md §9:
  small  = 10 parts  (already exists, produced manually)
  medium = 25 parts
  stress = 50 parts
  Geometry: rectangles, dimensions in [10, 80] mm.

Seed: 42 (numpy.random.default_rng(42)).
Run once; outputs data/test_set_medium.csv and data/test_set_stress.csv.
"""

import csv
import sys
from pathlib import Path

import numpy as np

# ---- Seed (documented here as source of truth) ----
_SEED = 42
_DIM_LOW = 10.0   # mm — minimum part dimension (PLAN §9)
_DIM_HIGH = 80.0  # mm — maximum part dimension (PLAN §9)

_SETS = {
    "medium": 25,
    "stress": 50,
}

_PROJECT_ROOT = Path(__file__).parent.parent
_DATA_DIR = _PROJECT_ROOT / "data"


def _generate_csv(name: str, n_parts: int, rng: np.random.Generator) -> Path:
    """Generate a CSV with n_parts unique rectangular parts.

    Each part has qty=1 and rotatable=True.
    Dimensions are rounded to 1 decimal place.
    """
    out_path = _DATA_DIR / f"test_set_{name}.csv"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    widths = rng.uniform(_DIM_LOW, _DIM_HIGH, size=n_parts).round(1)
    heights = rng.uniform(_DIM_LOW, _DIM_HIGH, size=n_parts).round(1)

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "width_mm", "height_mm", "qty", "rotatable"])
        for i, (w, h) in enumerate(zip(widths, heights), start=1):
            part_id = f"p{i:02d}"
            writer.writerow([part_id, w, h, 1, "True"])

    return out_path


def main() -> None:
    rng = np.random.default_rng(_SEED)

    for name, n_parts in _SETS.items():
        path = _generate_csv(name, n_parts, rng)
        print(f"Generated: {path}  ({n_parts} parts, seed={_SEED})")


if __name__ == "__main__":
    main()
