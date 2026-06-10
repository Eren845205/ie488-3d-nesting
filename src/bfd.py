"""bfd.py — Best-Fit Decreasing (BFD) nesting heuristic, skyline-based.

Implementation follows PLAN.md §11 Blok 4 skyline decision (overrides §8.2
maximal-rectangles pseudo-code).  Spec conflict noted: §8.2 describes a
free_rects / maximal-rectangles approach, while §11 and the Blok 4 brief
explicitly mandate skyline.  This file implements skyline.

Skyline representation
----------------------
The skyline is a sorted list of SkylineSegment objects, each covering a
contiguous x-range [x, x_end) at a fixed height y.  Together they tile the
full usable width [margin, plate_w - margin] exactly (no gaps, no overlaps).

Initial state: a single segment spanning the full usable width at y = margin.

After placing a part at (px, py) with size (pw, ph):
  - The skyline is raised to py + ph + margin over the interval [px, px+pw].
  - Existing segments that the part footprint crosses are split/trimmed and the
    covered portion is replaced by the new raised segment.

Placement scoring (Best-Fit)
----------------------------
For each part (sorted area-descending) and each allowed orientation:
  For each skyline segment start position (the left edge aligns with a segment
  boundary):
    - Compute y_top = max skyline height over the interval [px, px+pw].
    - If y_top + ph > plate_h - margin: position is infeasible, skip.
    - Score (waste below part) = sum of (y_top - skyline_i.y) * overlap_width
      for each segment i that the part footprint covers.
    - Track best (lowest score; tie-break: lower y_top, then lower px).

Margin convention (matches bl.py)
----------------------------------
- Usable area: [margin, W-margin] x [margin, H-margin].
- After placing a part whose top is at y_top = py + ph, the skyline in that
  region rises to y_top + margin so the next part keeps the required gap.
- Plate-edge margin is absorbed by the usable area limits (skyline starts at
  y=margin, feasibility check uses plate_h - margin as ceiling).

This is consistent with bl.py's `_fits()` which applies `margin` as a gap
between any two placed bounding boxes (including part-to-plate-edge).

Reuse
-----
`Placement` is imported from src.bl so that src.visualize.render() works
without modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.bl import Placement
from src.part import Part
from src.plate import Plate

_EPSILON = 1e-3  # mm — floating-point guard


@dataclass
class SkylineSegment:
    """One horizontal segment of the skyline.

    Covers x in [x, x_end) at height y (the lowest available y for a new part
    above this segment, including the margin already baked in).
    """
    x: float
    x_end: float
    y: float


def _build_skyline(plate: Plate) -> List[SkylineSegment]:
    """Create the initial flat skyline for an empty plate."""
    m = plate.margin_mm
    return [SkylineSegment(x=m, x_end=plate.width_mm - m, y=m)]


def _query_max_y(skyline: List[SkylineSegment], px: float, px_end: float) -> float:
    """Return max skyline height over the x-interval [px, px_end)."""
    max_y = 0.0
    for seg in skyline:
        if seg.x_end <= px + _EPSILON:
            continue
        if seg.x >= px_end - _EPSILON:
            break
        max_y = max(max_y, seg.y)
    return max_y


def _query_waste(
    skyline: List[SkylineSegment], px: float, px_end: float, y_floor: float
) -> float:
    """Return total wasted area between y_floor and the skyline over [px, px_end).

    Waste = sum over covered segments of (y_floor - seg.y) * overlap_width.
    (y_floor is the bottom of the part; segments below it create waste.)
    """
    waste = 0.0
    for seg in skyline:
        if seg.x_end <= px + _EPSILON:
            continue
        if seg.x >= px_end - _EPSILON:
            break
        overlap_left = max(seg.x, px)
        overlap_right = min(seg.x_end, px_end)
        overlap_width = overlap_right - overlap_left
        if overlap_width > _EPSILON:
            waste += (y_floor - seg.y) * overlap_width
    return waste


def _update_skyline(
    skyline: List[SkylineSegment],
    px: float,
    px_end: float,
    new_y: float,
    margin: float = 0.0,
) -> List[SkylineSegment]:
    """Raise the skyline to new_y over [px, px_end + margin).

    The horizontal margin is absorbed into the raised segment so that the next
    part's candidate x-positions are naturally at least `margin` away from the
    placed part's right edge.  Specifically, the raised region covers
    [px, px_end + margin) at height new_y — the +margin zone is raised to the
    same height as the part-top + vertical-margin already baked into new_y,
    making it a 'blocked' zone that any feasibility check will reject unless a
    part is wide enough to land on top of it or to the right of it.

    Left boundary: existing segments to the left of px are trimmed at px (their
    right edge stays at px, i.e. right-adjacent to the new part's x without the
    horizontal margin already baked in via candidate_xs >= margin from plate edge).

    Returns a new sorted list of segments with no gaps.
    """
    # We raise the zone [px, px_end + margin) to new_y.  This collapses the
    # horizontal gap zone into the raised-skyline region.
    blocked_end = min(px_end + margin, skyline[-1].x_end if skyline else px_end + margin)

    result: List[SkylineSegment] = []
    new_seg_added = False

    for seg in skyline:
        # Segment entirely left of the blocked zone — keep unchanged
        if seg.x_end <= px + _EPSILON:
            result.append(seg)
            continue
        # Segment entirely right of the blocked zone — keep unchanged
        if seg.x >= blocked_end - _EPSILON:
            if not new_seg_added:
                result.append(SkylineSegment(x=px, x_end=blocked_end, y=new_y))
                new_seg_added = True
            result.append(seg)
            continue

        # Segment partially or fully overlaps the blocked zone
        # Left tail (before blocked zone starts)
        if seg.x < px - _EPSILON:
            result.append(SkylineSegment(x=seg.x, x_end=px, y=seg.y))

        # The blocked zone contribution (added once)
        if not new_seg_added:
            result.append(SkylineSegment(x=px, x_end=blocked_end, y=new_y))
            new_seg_added = True

        # Right tail (after blocked zone ends)
        if seg.x_end > blocked_end + _EPSILON:
            result.append(SkylineSegment(x=blocked_end, x_end=seg.x_end, y=seg.y))

    # Guard: if part footprint extends beyond all existing segments
    if not new_seg_added:
        result.append(SkylineSegment(x=px, x_end=blocked_end, y=new_y))

    return result


def _collides_with_placed(
    px: float,
    py: float,
    pw: float,
    ph: float,
    placements: List[Placement],
    margin: float,
) -> bool:
    """Return True if (px,py,pw,ph) is too close to any already-placed part.

    Uses the same 4-condition AABB separation test as bl._overlaps, with the
    given margin enforced as minimum gap.
    """
    for p in placements:
        a_right = px + pw
        a_top = py + ph
        b_right = p.x + p.width
        b_top = p.y + p.height
        separated = (
            a_right + margin <= p.x + _EPSILON
            or px >= b_right + margin - _EPSILON
            or a_top + margin <= p.y + _EPSILON
            or py >= b_top + margin - _EPSILON
        )
        if not separated:
            return True
    return False


def _skyline_cost(
    skyline: List[SkylineSegment],
    px: float,
    pw: float,
    ph: float,
    plate: Plate,
    placements: List[Placement],
) -> Optional[Tuple[float, float, float]]:
    """Compute the placement cost (waste) of placing part at (px, y_top-ph).

    Returns (score, y_top, px) if feasible, else None.

    y_top = max skyline height over [px, px+pw] — this is the bottom of the
    part (since the part sits on top of the skyline).
    Score = waste area below the part bottom (y_top) within the part's footprint.
    """
    m = plate.margin_mm
    px_end = px + pw

    # Usable width boundary
    if px < m - _EPSILON or px_end > plate.width_mm - m + _EPSILON:
        return None

    y_floor = _query_max_y(skyline, px, px_end)
    # Part top must not exceed usable height ceiling
    if y_floor + ph > plate.height_mm - m + _EPSILON:
        return None

    # Margin-aware collision check against all already-placed parts
    if _collides_with_placed(px, y_floor, pw, ph, placements, m):
        return None

    waste = _query_waste(skyline, px, px_end, y_floor)
    return (waste, y_floor, px)


def _allowed_orientations(part: Part) -> List[Tuple[float, float, bool]]:
    """Return list of (width, height, rotated) for allowed orientations."""
    orientations: List[Tuple[float, float, bool]] = [
        (part.width_mm, part.height_mm, False)
    ]
    if part.rotatable and abs(part.width_mm - part.height_mm) > _EPSILON:
        orientations.append((part.height_mm, part.width_mm, True))
    return orientations


def best_fit_decreasing(
    parts: List[Part],
    plate: Plate,
) -> Tuple[List[Placement], List[str]]:
    """Run the Best-Fit Decreasing nesting heuristic (skyline-based).

    Parts are sorted by area descending (PLAN §8.2 + §11).  For each part,
    every candidate x-position (aligned with skyline segment boundaries) is
    evaluated for both allowed orientations.  The position and orientation with
    the lowest waste (gap between part bottom and skyline below it) wins.
    Tie-break: lower y_top, then lower px.

    Args:
        parts: list of Part instances to place.
        plate: Plate defining dimensions and margin.

    Returns:
        (placements, unplaced_ids): placed Placement list and list of unplaced IDs.
    """
    # Sort by area descending (BFD rule — differs from BL's max-edge sort)
    sorted_parts = sorted(
        parts,
        key=lambda p: p.width_mm * p.height_mm,
        reverse=True,
    )

    skyline = _build_skyline(plate)
    placements: List[Placement] = []
    unplaced_ids: List[str] = []

    for part in sorted_parts:
        best_cost: Optional[float] = None
        best_y_floor: Optional[float] = None
        best_px: Optional[float] = None
        best_pw: Optional[float] = None
        best_ph: Optional[float] = None
        best_rotated: Optional[bool] = None

        # Candidate x positions: left edge of each skyline segment
        candidate_xs = [seg.x for seg in skyline]

        for pw, ph, rotated in _allowed_orientations(part):
            for px in candidate_xs:
                result = _skyline_cost(skyline, px, pw, ph, plate, placements)
                if result is None:
                    continue
                waste, y_floor, _ = result
                # Tie-break: lower y_floor, then lower px
                if (
                    best_cost is None
                    or waste < best_cost - _EPSILON
                    or (
                        abs(waste - best_cost) <= _EPSILON
                        and (
                            y_floor < best_y_floor - _EPSILON
                            or (
                                abs(y_floor - best_y_floor) <= _EPSILON
                                and px < best_px - _EPSILON
                            )
                        )
                    )
                ):
                    best_cost = waste
                    best_y_floor = y_floor
                    best_px = px
                    best_pw = pw
                    best_ph = ph
                    best_rotated = rotated

        if best_px is None:
            unplaced_ids.append(part.id)
            continue

        # Place the part: record placement, update skyline
        placements.append(
            Placement(
                part_id=part.id,
                x=best_px,
                y=best_y_floor,
                width=best_pw,
                height=best_ph,
                rotated=best_rotated,
            )
        )
        new_y = best_y_floor + best_ph + plate.margin_mm
        skyline = _update_skyline(
            skyline, best_px, best_px + best_pw, new_y, plate.margin_mm
        )

    return placements, unplaced_ids
