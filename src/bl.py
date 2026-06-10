"""bl.py — Bottom-Left (BL) nesting heuristic.

Follows PLAN.md §8.1 pseudo-code.  Image mapping: AABB (bounding box).
Collision detection: 4-condition AABB overlap test with margin.
Rotation: {0, 90} degrees when Part.rotatable is True.

Architectural decision (not in PLAN.md, flagged in summary):
  Margin applies to BOTH part-to-part gaps AND plate edges.
  Usable plate area is [margin, W-margin] x [margin, H-margin].
  Collision check inflates each placed bounding box by `margin` on all sides
  before testing separation — this is equivalent but avoids double-counting.

Epsilon: 1e-3 mm (PLAN.md §12) applied in fit boundary checks to handle
floating-point edge cases at plate boundaries.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.part import Part
from src.plate import Plate

_EPSILON = 1e-3  # mm — floating-point guard at boundary


@dataclass
class Placement:
    """A successfully placed part instance."""

    part_id: str
    x: float          # left edge of bounding box (mm)
    y: float          # bottom edge of bounding box (mm)
    width: float      # effective width after orientation (mm)
    height: float     # effective height after orientation (mm)
    rotated: bool     # True if placed at 90-degree rotation


def _overlaps(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
    margin: float,
) -> bool:
    """Return True when two axis-aligned rectangles are closer than `margin`.

    Two rects are separated (non-overlapping, respecting margin) iff at least
    one of the four separation conditions holds:
      a is fully left of b  OR  a is fully right of b  OR
      a is fully below b   OR  a is fully above b

    "Fully left" means a's right edge + margin <= b's left edge (no gap smaller
    than margin allowed).  Touching (gap == 0) counts as a collision because
    margin > 0 requires a real gap.
    """
    a_right = ax + aw
    a_top = ay + ah
    b_right = bx + bw
    b_top = by + bh

    separated = (
        a_right + margin <= bx + _EPSILON
        or ax >= b_right + margin - _EPSILON
        or a_top + margin <= by + _EPSILON
        or ay >= b_top + margin - _EPSILON
    )
    return not separated


def _fits(
    x: float,
    y: float,
    w: float,
    h: float,
    placed: List[Placement],
    plate: Plate,
) -> bool:
    """Return True if a part at (x, y) with size (w, h) fits on the plate.

    Conditions:
    1. The bounding box stays within [margin, plate_dim - margin] on each axis.
    2. The bounding box does not overlap (or get too close to) any placed part.
    """
    m = plate.margin_mm
    # Boundary check — must fit inside usable area
    if x < m - _EPSILON:
        return False
    if y < m - _EPSILON:
        return False
    if x + w > plate.width_mm - m + _EPSILON:
        return False
    if y + h > plate.height_mm - m + _EPSILON:
        return False

    # Collision check against every already-placed part
    for p in placed:
        if _overlaps(x, y, w, h, p.x, p.y, p.width, p.height, m):
            return False

    return True


def _candidate_points(placed: List[Placement], plate: Plate) -> List[Tuple[float, float]]:
    """Generate candidate (x, y) positions for the next part.

    Candidates = (margin, margin) plus the right-bottom and left-top corners of
    every placed part.  These are the only positions where a new part can land
    optimally in the BL heuristic.
    """
    m = plate.margin_mm
    points: List[Tuple[float, float]] = [(m, m)]

    for p in placed:
        # Right edge of this part, bottom-aligned
        points.append((p.x + p.width + m, p.y))
        # Left edge of this part, top-aligned
        points.append((p.x, p.y + p.height + m))

    return points


def _allowed_orientations(part: Part) -> List[Tuple[float, float, bool]]:
    """Return list of (width, height, rotated) tuples for allowed orientations."""
    orientations = [(part.width_mm, part.height_mm, False)]
    if part.rotatable and part.width_mm != part.height_mm:
        orientations.append((part.height_mm, part.width_mm, True))
    return orientations


def bottom_left(
    parts: List[Part],
    plate: Plate,
) -> Tuple[List[Placement], List[str]]:
    """Run the Bottom-Left nesting heuristic.

    Parts are sorted by max(width, height) descending before placement (PLAN §8.1).
    For each part, candidate positions are tried in (y asc, x asc) order.
    First orientation that fits is used; if neither fits, the part is unplaced.

    Args:
        parts: list of Part instances to place.
        plate: Plate defining dimensions and margin.

    Returns:
        (placements, unplaced_ids): placed Placement list and list of unplaced IDs.
    """
    sorted_parts = sorted(
        parts,
        key=lambda p: max(p.width_mm, p.height_mm),
        reverse=True,
    )

    placements: List[Placement] = []
    unplaced_ids: List[str] = []

    for part in sorted_parts:
        placed_this = False
        candidates = _candidate_points(placements, plate)
        # Sort by y ascending, then x ascending (bottom-left preference)
        candidates.sort(key=lambda c: (c[1], c[0]))

        for orientation in _allowed_orientations(part):
            w, h, rotated = orientation
            for cx, cy in candidates:
                if _fits(cx, cy, w, h, placements, plate):
                    placements.append(
                        Placement(
                            part_id=part.id,
                            x=cx,
                            y=cy,
                            width=w,
                            height=h,
                            rotated=rotated,
                        )
                    )
                    placed_this = True
                    break
            if placed_this:
                break
        else:
            unplaced_ids.append(part.id)

    return placements, unplaced_ids


def utilization_pct(placements: List[Placement], plate: Plate) -> float:
    """Compute utilization as placed-area / full-plate-area * 100.

    Denominator is full plate area (PLAN §9 metric definition).
    """
    placed_area = sum(p.width * p.height for p in placements)
    plate_area = plate.width_mm * plate.height_mm
    return 100.0 * placed_area / plate_area
