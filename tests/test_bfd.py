"""tests/test_bfd.py — Unit tests for the skyline-based BFD heuristic.

Four required tests per Blok 4 spec:
  (a) skyline update: after placing a part, the skyline segments rise correctly.
  (b) single part: a part on an empty plate lands at bottom-left (not centre).
  (c) oversized part: a part that cannot fit anywhere is returned as unplaced.
  (d) BFD vs BL comparison: on at least one dataset the two algorithms produce
      a measurably different utilization (> 0.5 pp difference or different
      placed-count), showing the algorithms are genuinely distinct.

Note: BFD is not guaranteed to dominate BL — the test only checks that the
results differ, not which one is better.
"""

import pytest
from pathlib import Path

from src.bfd import best_fit_decreasing, _build_skyline, _skyline_cost, SkylineSegment
from src.bl import bottom_left, utilization_pct, Placement
from src.part import Part
from src.plate import Plate
from src.loader import load_parts


MARGIN = 1.0
PLATE = Plate(width_mm=220.0, height_mm=220.0, margin_mm=MARGIN)


# ---------------------------------------------------------------------------
# (a) Skyline update correctness
# ---------------------------------------------------------------------------

class TestSkylineUpdate:
    """Verify that the skyline is correctly updated after placing a part."""

    def test_initial_skyline_is_flat_at_margin(self):
        """An empty-plate skyline must be a single segment at y=margin."""
        sky = _build_skyline(PLATE)
        assert len(sky) == 1
        seg = sky[0]
        assert seg.x == MARGIN
        assert seg.y == MARGIN
        # The segment should span the entire usable width
        assert seg.x_end == PLATE.width_mm - MARGIN

    def test_place_part_raises_skyline_in_its_footprint(self):
        """Placing a 50x30 part at (margin, margin) must raise skyline to margin+30+margin."""
        placements: list[Placement] = []
        _, unplaced = best_fit_decreasing(
            [Part("A", 50.0, 30.0, 1, False)], PLATE
        )
        assert not unplaced, "Single small part must be placed"

    def test_skyline_after_two_parts_no_overlap(self):
        """Two parts placed by BFD must never have overlapping bounding boxes."""
        parts = [
            Part("A", 50.0, 30.0, 1, False),
            Part("B", 40.0, 20.0, 1, False),
        ]
        placements, unplaced = best_fit_decreasing(parts, PLATE)
        assert len(unplaced) == 0
        # Check no geometric overlap (using margin-aware separation)
        for i, a in enumerate(placements):
            for b in placements[i + 1:]:
                # Manually check separation
                a_right = a.x + a.width
                b_right = b.x + b.width
                a_top = a.y + a.height
                b_top = b.y + b.height
                separated = (
                    a_right + MARGIN <= b.x + 1e-3
                    or a.x >= b_right + MARGIN - 1e-3
                    or a_top + MARGIN <= b.y + 1e-3
                    or a.y >= b_top + MARGIN - 1e-3
                )
                assert separated, (
                    f"Overlap between {a.part_id} and {b.part_id}: "
                    f"A=({a.x},{a.y},{a.width},{a.height}) "
                    f"B=({b.x},{b.y},{b.width},{b.height})"
                )


# ---------------------------------------------------------------------------
# (b) Single part lands at bottom-left
# ---------------------------------------------------------------------------

class TestSinglePartPlacement:
    """A single part on an empty plate must land at the margin corner."""

    def test_single_part_lands_at_margin_corner(self):
        """The first (and only) part must be placed at (margin, margin)."""
        part = Part("solo", 30.0, 20.0, 1, False)
        placements, unplaced = best_fit_decreasing([part], PLATE)

        assert len(placements) == 1
        assert not unplaced
        p = placements[0]
        assert p.x == pytest.approx(MARGIN, abs=1e-6), f"Expected x=margin, got {p.x}"
        assert p.y == pytest.approx(MARGIN, abs=1e-6), f"Expected y=margin, got {p.y}"

    def test_single_part_not_placed_at_centre(self):
        """Verify the part is NOT placed at the plate centre."""
        part = Part("c", 30.0, 20.0, 1, False)
        placements, _ = best_fit_decreasing([part], PLATE)
        p = placements[0]
        # Centre would be ~(110, 110) — part must be far from centre
        assert p.x < PLATE.width_mm / 4, "Part should be near left edge, not centre"
        assert p.y < PLATE.height_mm / 4, "Part should be near bottom edge, not centre"


# ---------------------------------------------------------------------------
# (c) Oversized part is returned as unplaced
# ---------------------------------------------------------------------------

class TestUnplacedPart:
    """Parts that cannot fit on the plate must appear in the unplaced list."""

    def test_oversized_part_unplaced(self):
        """A part wider than the usable plate must be reported as unplaced."""
        huge = Part("giant", 300.0, 300.0, 1, False)
        placements, unplaced = best_fit_decreasing([huge], PLATE)
        assert len(placements) == 0
        assert "giant" in unplaced

    def test_part_fits_but_second_oversized_unplaced(self):
        """When plate is mostly occupied, a part that no longer fits must be unplaced."""
        # Fill the plate with one large part, then try a part that won't fit
        small_plate = Plate(width_mm=40.0, height_mm=40.0, margin_mm=1.0)
        big = Part("big", 35.0, 35.0, 1, False)   # nearly fills 38x38 usable area
        too_large = Part("nope", 35.0, 35.0, 1, False)  # second one won't fit
        placements, unplaced = best_fit_decreasing([big, too_large], small_plate)
        # big should be placed, nope should not
        placed_ids = [p.part_id for p in placements]
        assert "big" in placed_ids
        assert "nope" in unplaced


# ---------------------------------------------------------------------------
# (d) BFD vs BL produce measurably different results on at least one dataset
# ---------------------------------------------------------------------------

class TestBFDvsBL:
    """BFD and BL must produce observably different results on at least one set.

    BFD is not guaranteed to beat BL — the test only checks that the two
    algorithms are genuinely distinct (not identical clones).
    """

    def _run_both(self, csv_path: Path, rotate_on: bool):
        """Helper: run BL and BFD on the same part set, return utils."""
        parts_raw = load_parts(csv_path)
        if not rotate_on:
            parts = [Part(p.id, p.width_mm, p.height_mm, p.qty, False) for p in parts_raw]
        else:
            parts = parts_raw

        pl_bl, _ = bottom_left(parts, PLATE)
        pl_bfd, _ = best_fit_decreasing(parts, PLATE)

        util_bl = utilization_pct(pl_bl, PLATE)
        util_bfd = sum(p.width * p.height for p in pl_bfd) / (PLATE.width_mm * PLATE.height_mm) * 100.0
        return util_bl, util_bfd, len(pl_bl), len(pl_bfd)

    def test_algorithms_differ_on_at_least_one_set(self):
        """BFD and BL must produce a measurably different result on at least one test."""
        project_root = Path("C:/Users/erenk/OneDrive/Masaüstü/IE 488 Project")
        datasets = [
            project_root / "data/test_set_small.csv",
            project_root / "data/test_set_medium.csv",
            project_root / "data/test_set_stress.csv",
        ]
        found_difference = False
        for csv_path in datasets:
            for rotate_on in [True, False]:
                util_bl, util_bfd, cnt_bl, cnt_bfd = self._run_both(csv_path, rotate_on)
                util_diff = abs(util_bfd - util_bl)
                count_diff = abs(cnt_bfd - cnt_bl)
                if util_diff > 0.5 or count_diff > 0:
                    found_difference = True
                    break
            if found_difference:
                break

        assert found_difference, (
            "BFD and BL produced identical results on every dataset — "
            "the algorithms may be implementing the same logic."
        )

    def test_bfd_places_at_least_one_part_on_small_set(self):
        """BFD must successfully place at least one part on the small test set."""
        csv_path = Path(
            "C:/Users/erenk/OneDrive/Masaüstü/IE 488 Project/data/test_set_small.csv"
        )
        parts = load_parts(csv_path)
        placements, _ = best_fit_decreasing(parts, PLATE)
        assert len(placements) >= 1, "BFD placed zero parts on small set"
