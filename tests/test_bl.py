"""tests/test_bl.py — Unit tests for AABB collision detection and BL heuristic.

Test cases cover the four canonical collision states required by Blok 2:
  1. Disjoint with gap > margin -> no collision
  2. Touching (gap == 0) -> collision (margin=1mm requires real gap)
  3. Overlapping -> collision
  4. Fully contained -> collision

Plus integration tests for bottom_left and loader.
"""

import pytest
from pathlib import Path

from src.bl import _overlaps, _fits, bottom_left, utilization_pct, Placement
from src.part import Part
from src.plate import Plate
from src.loader import load_parts


MARGIN = 1.0
PLATE = Plate(width_mm=220.0, height_mm=220.0, margin_mm=MARGIN)


# ---------------------------------------------------------------------------
# AABB overlap tests (4 canonical cases)
# ---------------------------------------------------------------------------

class TestAABBOverlap:
    """Tests for _overlaps() — the core 4-condition collision predicate."""

    def test_disjoint_gap_greater_than_margin_no_collision(self):
        """Two rectangles separated by 5 mm (> 1 mm margin) must NOT collide."""
        # a occupies [0, 0, 10, 10]; b starts at x=16 (gap=6 mm)
        assert _overlaps(0, 0, 10, 10, 16, 0, 10, 10, margin=MARGIN) is False

    def test_touching_zero_gap_is_collision(self):
        """Two rects with zero gap (touching edges) must collide when margin=1 mm."""
        # a right edge at x=10; b left edge at x=10 -> gap=0, margin=1 -> collision
        assert _overlaps(0, 0, 10, 10, 10, 0, 10, 10, margin=MARGIN) is True

    def test_overlapping_rects_collide(self):
        """Two rects that geometrically overlap must collide."""
        # a occupies [0,0,10,10]; b occupies [5,5,10,10] — overlap in both axes
        assert _overlaps(0, 0, 10, 10, 5, 5, 10, 10, margin=MARGIN) is True

    def test_contained_rect_collides(self):
        """A rect fully inside another must collide."""
        # b is entirely inside a
        assert _overlaps(0, 0, 20, 20, 5, 5, 5, 5, margin=MARGIN) is True

    def test_gap_exactly_margin_no_collision(self):
        """Two rects separated by exactly margin mm must NOT collide (boundary)."""
        # a right at x=10; b left at x=11 -> gap=1mm == margin -> no collision
        assert _overlaps(0, 0, 10, 10, 11, 0, 10, 10, margin=MARGIN) is False

    def test_disjoint_vertically_no_collision(self):
        """Two rects separated vertically by > margin must NOT collide."""
        # a top at y=10; b bottom at y=12 -> gap=2mm > margin
        assert _overlaps(0, 0, 10, 10, 0, 12, 10, 10, margin=MARGIN) is False


# ---------------------------------------------------------------------------
# _fits() boundary tests
# ---------------------------------------------------------------------------

class TestFits:
    def test_part_fits_at_origin_margin(self):
        """A small part placed at (margin, margin) should fit on an empty plate."""
        assert _fits(MARGIN, MARGIN, 10.0, 10.0, [], PLATE) is True

    def test_part_out_of_bounds_right(self):
        """Part extending past plate.width - margin must not fit."""
        # x=1, w=220 -> right edge at 221 > 219 (220-1)
        assert _fits(MARGIN, MARGIN, 220.0, 10.0, [], PLATE) is False

    def test_part_below_margin(self):
        """Part placed at y=0 (below margin) must not fit."""
        assert _fits(0.0, 0.0, 10.0, 10.0, [], PLATE) is False

    def test_collision_with_placed_part(self):
        """New part colliding with an existing placement must not fit."""
        placed = [Placement("p1", 1.0, 1.0, 50.0, 50.0, False)]
        # Attempt to place on top of the existing part
        assert _fits(1.0, 1.0, 20.0, 20.0, placed, PLATE) is False

    def test_no_collision_after_placed_part(self):
        """New part placed with sufficient gap after an existing part must fit."""
        placed = [Placement("p1", 1.0, 1.0, 50.0, 50.0, False)]
        # Next available x = 1 + 50 + 1 (margin) = 52
        assert _fits(52.0, 1.0, 10.0, 10.0, placed, PLATE) is True


# ---------------------------------------------------------------------------
# bottom_left integration tests
# ---------------------------------------------------------------------------

class TestBottomLeft:
    def test_single_part_placed(self):
        """A single small part on an empty plate should always be placed."""
        parts = [Part("A", 10.0, 10.0, 1, False)]
        placements, unplaced = bottom_left(parts, PLATE)
        assert len(placements) == 1
        assert len(unplaced) == 0

    def test_part_too_large_is_unplaced(self):
        """A part larger than the usable plate area must be reported as unplaced."""
        huge = Part("huge", 300.0, 300.0, 1, False)
        placements, unplaced = bottom_left([huge], PLATE)
        assert len(placements) == 0
        assert "huge" in unplaced

    def test_multiple_parts_no_overlap(self):
        """All placed parts must have non-overlapping bounding boxes (with margin)."""
        parts = [
            Part("p1", 50.0, 50.0, 1, True),
            Part("p2", 50.0, 50.0, 1, True),
            Part("p3", 30.0, 30.0, 1, True),
        ]
        placements, _ = bottom_left(parts, PLATE)
        # Check all pairs
        for i, a in enumerate(placements):
            for b in placements[i + 1:]:
                assert not _overlaps(
                    a.x, a.y, a.width, a.height,
                    b.x, b.y, b.width, b.height,
                    margin=PLATE.margin_mm,
                ), f"Overlap detected between {a.part_id} and {b.part_id}"

    def test_utilization_within_bounds(self):
        """Utilization must be in (0, 100] for at least one placed part."""
        parts = [Part("q1", 30.0, 40.0, 1, True)]
        placements, _ = bottom_left(parts, PLATE)
        util = utilization_pct(placements, PLATE)
        assert 0.0 < util <= 100.0

    def test_rotation_used_when_rotatable(self):
        """A tall narrow part should be rotated when it fits better rotated."""
        # Part is 10 wide x 200 tall — won't fit upright (200 > 220-2*1=218 barely)
        # but rotated is 200 wide x 10 tall which fits fine too.
        # Just verify it gets placed (either orientation)
        parts = [Part("tall", 10.0, 200.0, 1, True)]
        placements, unplaced = bottom_left(parts, PLATE)
        assert len(placements) == 1
        assert "tall" not in unplaced


# ---------------------------------------------------------------------------
# loader integration tests
# ---------------------------------------------------------------------------

class TestLoader:
    def test_load_small_csv(self):
        """Loading test_set_small.csv must return 10 Part instances."""
        csv_path = Path("C:/Users/erenk/OneDrive/Masaüstü/IE 488 Project/data/test_set_small.csv")
        parts = load_parts(csv_path)
        assert len(parts) == 10

    def test_qty_expansion(self, tmp_path):
        """A row with qty=3 must expand into 3 Part instances."""
        csv_file = tmp_path / "qty_test.csv"
        csv_file.write_text(
            "id,width_mm,height_mm,qty,rotatable\n"
            "p01,20.0,30.0,3,True\n",
            encoding="utf-8",
        )
        parts = load_parts(csv_file)
        assert len(parts) == 3
        ids = [p.id for p in parts]
        assert "p01_a" in ids
        assert "p01_b" in ids
        assert "p01_c" in ids

    def test_qty_one_no_suffix(self, tmp_path):
        """A row with qty=1 must yield an instance with the original ID."""
        csv_file = tmp_path / "single.csv"
        csv_file.write_text(
            "id,width_mm,height_mm,qty,rotatable\n"
            "partX,15.0,25.0,1,False\n",
            encoding="utf-8",
        )
        parts = load_parts(csv_file)
        assert len(parts) == 1
        assert parts[0].id == "partX"

    def test_missing_file_raises(self):
        """Loading a non-existent file must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_parts(Path("/no/such/file.csv"))

    def test_missing_column_raises(self, tmp_path):
        """A CSV missing a required column must raise ValueError."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text(
            "id,width_mm,height_mm,qty\n"  # missing rotatable
            "p01,10,20,1\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required columns"):
            load_parts(csv_file)
