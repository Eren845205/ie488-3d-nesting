"""extreme_point.py — Extreme-Point constructive 3D packer (R5 fix).

Motivation (PLAN_3D.md §2.4 known limitation):
  The heightmap Bin3D drops parts from above and cannot slide them into
  cavities beneath overhangs.  This module replaces the per-column 2D
  heightmap with a full 3D occupancy grid and maintains an *extreme-point*
  (EP) set — candidate placement origins derived from the geometry of already-
  placed parts.  Because collision detection is done voxel-by-voxel in 3D,
  a part can be placed anywhere its voxels do not overlap existing occupancy,
  including inside arch-shaped cavities.

API:
  OccupancyBin3D   — state container (occupancy + EP set)
  place_extreme_point(parts, bin_factory, *, order_key) -> (placements, bin)

Design constraints:
  - Existing heightmap Bin3D / dblf / solvers are NOT touched.
  - This module is a PARALLEL constructive alternative; both can coexist.
  - Deterministic: same input -> same output.
  - Honest cost: 3D occupancy is more expensive than heightmap.  The public
    API exposes timing; the compare script reports it.

Extreme-point generation (Crainic 2008 style, tractable):
  After placing a part at (px, py, pz) with bounding box (fw, fd, fh):
    New EP candidates:
      (px + fw, py,      pz)      — right face
      (px,      py + fd, pz)      — back face
      (px,      py,      pz + fh) — top face
      (0,       py,      pz + fh) — top face projected to x=0 wall
      (px,      0,       pz + fh) — top face projected to y=0 wall
      (0,       0,       pz + fh) — top-corner projected to origin column
  All candidates are then pruned: any EP whose voxel slot is already inside
  the occupancy grid (or out of bin x/y bounds) is discarded.

  The nz_limit parameter is a *soft ceiling* only for the occupancy array
  allocation.  The grid auto-expands if a placement would exceed the current
  z dimension (see _ensure_z_capacity).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Set, Tuple

import numpy as np

from src.nesting3d.bin3d import Placement3D
from src.nesting3d.voxelize import Orientation, VoxelPart


# ---------------------------------------------------------------------------
# OccupancyBin3D
# ---------------------------------------------------------------------------

class OccupancyBin3D:
    """3D occupancy grid bin with extreme-point placement candidate tracking.

    Attributes
    ----------
    nx, ny    : bin footprint in voxels (fixed)
    nz_limit  : initial z-axis allocation (auto-expands as needed)
    pitch     : mm per voxel (for mm-unit reporting only)
    occupancy : bool array (nx, ny, nz_alloc) — True = occupied
    extreme_points : set of (x, y, z) int tuples — placement candidates
    placed_voxels  : cumulative count of placed True cells
    """

    def __init__(self, nx: int, ny: int, nz_limit: int = 200,
                 pitch: float = 5.0) -> None:
        self.nx = int(nx)
        self.ny = int(ny)
        self.nz_limit = int(nz_limit)
        self.pitch = float(pitch)
        self.occupancy: np.ndarray = np.zeros(
            (self.nx, self.ny, self.nz_limit), dtype=bool
        )
        self.extreme_points: Set[Tuple[int, int, int]] = {(0, 0, 0)}
        self.placed_voxels: int = 0
        self._max_z_used: int = 0  # tracks actual max z top seen so far

    # ------------------------------------------------------------------
    # Capacity management
    # ------------------------------------------------------------------

    def _ensure_z_capacity(self, z_top: int) -> None:
        """Grow the z-axis of occupancy if z_top would exceed current size."""
        nz_cur = self.occupancy.shape[2]
        if z_top <= nz_cur:
            return
        new_nz = max(z_top, nz_cur * 2)
        new_occ = np.zeros((self.nx, self.ny, new_nz), dtype=bool)
        new_occ[:, :, :nz_cur] = self.occupancy
        self.occupancy = new_occ

    # ------------------------------------------------------------------
    # Feasibility check
    # ------------------------------------------------------------------

    def is_feasible(self, orient: Orientation,
                    x: int, y: int, z: int) -> bool:
        """Return True iff placing *orient* at (x, y, z) is valid.

        Conditions:
          1. x + fw <= nx  and  y + fd <= ny  (footprint fits base)
          2. No voxel overlap with occupancy  (3D collision-free)
          z upper-bound is handled by auto-expand; we only check (1) and (2).
        """
        fw, fd, fh = orient.grid.shape
        if x + fw > self.nx or y + fd > self.ny:
            return False
        z_top = z + fh
        self._ensure_z_capacity(z_top)
        occ_slice = self.occupancy[x:x + fw, y:y + fd, z:z_top]
        # collision iff any voxel in part grid AND in occupancy
        return not bool(np.any(orient.grid & occ_slice))

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------

    def place(self, orient: Orientation, x: int, y: int, z: int) -> None:
        """Commit *orient* at (x, y, z): update occupancy and extreme-points.

        Raises
        ------
        ValueError
            If the placement is infeasible (out-of-bounds or collision).
        """
        fw, fd, fh = orient.grid.shape
        if x + fw > self.nx or y + fd > self.ny:
            raise ValueError(
                f"Placement out of bounds: part ({fw},{fd},{fh}) at "
                f"({x},{y},{z}) exceeds bin ({self.nx},{self.ny},*)"
            )
        z_top = z + fh
        self._ensure_z_capacity(z_top)
        occ_slice = self.occupancy[x:x + fw, y:y + fd, z:z_top]
        if np.any(orient.grid & occ_slice):
            raise ValueError(
                f"3D collision: part ({fw},{fd},{fh}) at ({x},{y},{z})"
            )
        # Commit
        occ_slice |= orient.grid
        self.placed_voxels += int(orient.grid.sum())
        if z_top > self._max_z_used:
            self._max_z_used = z_top
        self._update_extreme_points(x, y, z, fw, fd, fh)

    def _update_extreme_points(self, px: int, py: int, pz: int,
                                fw: int, fd: int, fh: int) -> None:
        """Generate new EP candidates from the placed part bounding box and prune."""
        candidates = [
            (px + fw, py,      pz),           # right face
            (px,      py + fd, pz),           # back face
            (px,      py,      pz + fh),      # top face (same corner)
            (0,       py,      pz + fh),      # top → project to x=0
            (px,      0,       pz + fh),      # top → project to y=0
            (0,       0,       pz + fh),      # top-corner → origin column
        ]
        for ep in candidates:
            self.extreme_points.add(ep)
        self._prune_extreme_points()

    def _prune_extreme_points(self) -> None:
        """Remove EPs that are out-of-x/y bounds or inside occupancy."""
        nz_cur = self.occupancy.shape[2]
        keep: Set[Tuple[int, int, int]] = set()
        for (ex, ey, ez) in self.extreme_points:
            if ex >= self.nx or ey >= self.ny:
                continue  # outside x/y footprint
            if ez >= nz_cur:
                keep.add((ex, ey, ez))  # above current occ — keep (may expand)
                continue
            if self.occupancy[ex, ey, ez]:
                continue  # inside occupied voxel — discard
            keep.add((ex, ey, ez))
        self.extreme_points = keep

    def _rebuild_extreme_points(self) -> None:
        """Rebuild EP set from scratch based on current occupancy.

        Used in tests that manually modify occupancy without calling place().
        """
        occ = self.occupancy
        nz = occ.shape[2]
        # Start fresh
        self.extreme_points = {(0, 0, 0)}
        # For every occupied voxel, add its 3 outward-facing EPs
        xs, ys, zs = np.nonzero(occ)
        for xi, yi, zi in zip(xs.tolist(), ys.tolist(), zs.tolist()):
            self.extreme_points.add((xi + 1, yi, zi))
            self.extreme_points.add((xi, yi + 1, zi))
            self.extreme_points.add((xi, yi, zi + 1))
            self.extreme_points.add((0, yi, zi + 1))
            self.extreme_points.add((xi, 0, zi + 1))
            self.extreme_points.add((0, 0, zi + 1))
        self._prune_extreme_points()

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def max_height_voxels(self) -> int:
        """Maximum z extent currently occupied (0 if nothing placed)."""
        return self._max_z_used

    def height_mm(self) -> float:
        """max_height in mm."""
        return self._max_z_used * self.pitch

    def fill_ratio(self) -> float:
        """Placed voxels / (base_area_voxels * max_height_voxels)."""
        h = self.max_height_voxels()
        if h <= 0:
            return 0.0
        return self.placed_voxels / (self.nx * self.ny * h)


# ---------------------------------------------------------------------------
# Constructive packer
# ---------------------------------------------------------------------------

@dataclass
class EPPlacement:
    """One placed part record returned by place_extreme_point."""
    part_id: str
    name: str
    x: int
    y: int
    z: int
    orientation_idx: int


def _ep_sort_key(ep: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """Deepest-bottom-left: min z, then min y, then min x."""
    return (ep[2], ep[1], ep[0])


def place_extreme_point(
    parts: List[VoxelPart],
    bin_factory: Callable[[], OccupancyBin3D],
    *,
    order_key: Optional[Callable[[VoxelPart], object]] = None,
) -> Tuple[List[EPPlacement], OccupancyBin3D]:
    """Constructive extreme-point packer — 3D analogue of dblf.place_in_order.

    Parameters
    ----------
    parts       : parts to place (consumed in order after sorting by order_key)
    bin_factory : callable returning a fresh OccupancyBin3D
    order_key   : sort key applied to parts before placement; defaults to
                  volume-descending (largest first, same as DBLF baseline)

    Returns
    -------
    (placements, obin) — list of EPPlacement records and the final bin state.

    Algorithm
    ---------
    For each part (in order):
      1. Sort current EP set by (z, y, x) — deepest-bottom-left first.
      2. For each orientation of the part:
           For each EP (sorted):
             If is_feasible(orient, ep): record as candidate with key
               (z + fh, z, y, x, oi) — minimise top then bottom.
      3. Pick the candidate with the lexicographically smallest key.
      4. Place and update EPs.
    The bin z-axis auto-expands, so every part is always placeable
    (analogous to the unbounded-height guarantee in PLAN_3D.md §6.2).
    """
    key = order_key if order_key is not None else (lambda vp: -vp.volume_voxels)
    ordered = sorted(parts, key=key)

    obin = bin_factory()
    placements: List[EPPlacement] = []

    for part in ordered:
        best_score: Optional[Tuple] = None
        best_ep: Optional[Tuple[int, int, int]] = None
        best_oi: int = 0

        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            # Sort EPs each iteration — set is small after pruning
            for ep in sorted(obin.extreme_points, key=_ep_sort_key):
                ex, ey, ez = ep
                if obin.is_feasible(orient, ex, ey, ez):
                    z_top = ez + fh
                    score = (z_top, ez, ey, ex, oi)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_ep = ep
                        best_oi = oi

        assert best_ep is not None, (
            f"{part.id}: no feasible EP found — increase nz_limit or bin size "
            f"(extreme_point.py §6.2 analogue)"
        )

        ex, ey, ez = best_ep
        orient = part.orientations[best_oi]
        obin.place(orient, ex, ey, ez)
        placements.append(EPPlacement(
            part_id=part.id,
            name=part.name,
            x=ex,
            y=ey,
            z=ez,
            orientation_idx=best_oi,
        ))

    return placements, obin
