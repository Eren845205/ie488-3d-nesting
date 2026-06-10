"""tests/test_loader.py — Tests for medium and stress CSV sets (Blok 3).

Tests are intentionally written before the CSV files exist (TDD RED).
They will pass once generate_test_sets.py is run and the CSVs are in data/.

PLAN.md §9:
  small  = 10 parts
  medium = 25 parts
  stress = 50 parts
  Geometry: rectangles, dimensions in [10, 80] mm.
"""

from pathlib import Path
import pytest

from src.loader import load_parts

_DATA_DIR = Path("C:/Users/erenk/OneDrive/Masaüstü/IE 488 Project/data")
_MEDIUM_CSV = _DATA_DIR / "test_set_medium.csv"
_STRESS_CSV = _DATA_DIR / "test_set_stress.csv"


class TestMediumCSV:
    def test_medium_csv_exists(self):
        """test_set_medium.csv must exist in data/ directory."""
        assert _MEDIUM_CSV.exists(), f"Missing: {_MEDIUM_CSV}"

    def test_medium_loads_25_parts(self):
        """Loading test_set_medium.csv must yield exactly 25 Part instances."""
        parts = load_parts(_MEDIUM_CSV)
        assert len(parts) == 25

    def test_medium_dimensions_in_range(self):
        """All medium parts must have dimensions in [10, 80] mm (PLAN §9)."""
        parts = load_parts(_MEDIUM_CSV)
        for p in parts:
            assert 10.0 <= p.width_mm <= 80.0, (
                f"{p.id}: width_mm={p.width_mm} out of [10, 80]"
            )
            assert 10.0 <= p.height_mm <= 80.0, (
                f"{p.id}: height_mm={p.height_mm} out of [10, 80]"
            )

    def test_medium_all_ids_unique(self):
        """All Part IDs in medium set must be unique."""
        parts = load_parts(_MEDIUM_CSV)
        ids = [p.id for p in parts]
        assert len(ids) == len(set(ids)), "Duplicate IDs found in medium set"


class TestStressCSV:
    def test_stress_csv_exists(self):
        """test_set_stress.csv must exist in data/ directory."""
        assert _STRESS_CSV.exists(), f"Missing: {_STRESS_CSV}"

    def test_stress_loads_50_parts(self):
        """Loading test_set_stress.csv must yield exactly 50 Part instances."""
        parts = load_parts(_STRESS_CSV)
        assert len(parts) == 50

    def test_stress_dimensions_in_range(self):
        """All stress parts must have dimensions in [10, 80] mm (PLAN §9)."""
        parts = load_parts(_STRESS_CSV)
        for p in parts:
            assert 10.0 <= p.width_mm <= 80.0, (
                f"{p.id}: width_mm={p.width_mm} out of [10, 80]"
            )
            assert 10.0 <= p.height_mm <= 80.0, (
                f"{p.id}: height_mm={p.height_mm} out of [10, 80]"
            )

    def test_stress_all_ids_unique(self):
        """All Part IDs in stress set must be unique."""
        parts = load_parts(_STRESS_CSV)
        ids = [p.id for p in parts]
        assert len(ids) == len(set(ids)), "Duplicate IDs found in stress set"
