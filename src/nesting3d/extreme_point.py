"""extreme_point.py — Extreme-Point constructive 3D packer (R5 fix, fast v2).

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

Performance (fast v2):
  is_feasible uses a 2D column_top array (nx x ny) that tracks the highest
  occupied z+1 per column.  For the common "place on top" case — where the
  candidate z is >= all column tops in the footprint — no 3D voxel-AND is
  needed; the function returns True immediately.  Only sub-top (cavity)
  candidates pay the full 3D AND cost.  This mirrors bin3d.py's drop_map
  fast-path pattern and is provably result-identical: the fast path triggers
  only when z >= local column top, which is a sufficient condition for zero
  overlap (all occupancy in the footprint is strictly below z).
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
    nx, ny       : bin footprint in voxels (fixed)
    nz_limit     : initial z-axis allocation (auto-expands as needed)
    pitch        : mm per voxel (for mm-unit reporting only)
    occupancy    : bool array (nx, ny, nz_alloc) — True = occupied
    column_top   : int array (nx, ny) — per-column topmost occupied z+1 (0=empty)
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
        # column_top[i, j] = first free z above the topmost occupied voxel in
        # column (i, j).  0 means the column is entirely empty.
        self.column_top: np.ndarray = np.zeros((self.nx, self.ny), dtype=np.int32)
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
    # Feasibility check (fast v2 with heightmap short-circuit)
    # ------------------------------------------------------------------

    def is_feasible(self, orient: Orientation,
                    x: int, y: int, z: int) -> bool:
        """Return True iff placing *orient* at (x, y, z) is valid.

        Conditions:
          1. x + fw <= nx  and  y + fd <= ny  (footprint fits base)
          2. No voxel overlap with occupancy  (3D collision-free)
          z upper-bound is handled by auto-expand; we only check (1) and (2).

        Fast path (heightmap short-circuit):
          column_top[i, j] stores the first-free-z above the topmost occupied
          voxel in column (i, j).  If z >= max(column_top[x:x+fw, y:y+fd]),
          then ALL occupied voxels in the footprint columns are strictly below
          z — the part placement cannot overlap any of them regardless of the
          part's own voxel pattern.  Return True without the 3D AND.

          This is a SOUND shortcut (never wrong): when the condition holds,
          the 3D AND would also return True.  When z < local max column_top
          (sub-top / cavity candidate), we fall through to the full 3D AND,
          paying the exact same cost as before — so correctness is fully
          preserved for the cavity case.

          Result is bit-identical to the full-3D version on every input.
        """
        fw, fd, fh = orient.grid.shape
        if x + fw > self.nx or y + fd > self.ny:
            return False
        z_top = z + fh

        # --- Fast path: entire part is above all occupancy in its footprint ---
        local_max_top = int(self.column_top[x:x + fw, y:y + fd].max())
        if z >= local_max_top:
            # The first occupied voxel (if any) in every footprint column is at
            # index < local_max_top <= z.  The part voxels start at index z.
            # Disjoint z-ranges → no overlap possible.
            return True

        # --- Slow path: sub-top candidate (cavity / overhang) — full 3D AND ---
        self._ensure_z_capacity(z_top)
        occ_slice = self.occupancy[x:x + fw, y:y + fd, z:z_top]
        return not bool(np.any(orient.grid & occ_slice))

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------

    def place(self, orient: Orientation, x: int, y: int, z: int) -> None:
        """Commit *orient* at (x, y, z): update occupancy, column_top, and EPs.

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

        # Update column_top for each footprint column that the part actually
        # occupies (columns where orient.filled is True — i.e., the part has
        # at least one voxel in that column).
        # top[i, j] is the highest z-index occupied in that column + 1.
        # After placing at z, new column top = z + orient.top[i, j].
        # We take the element-wise max to handle stacking.
        fw2, fd2 = orient.filled.shape  # same as fw, fd
        new_col_top = self.column_top[x:x + fw2, y:y + fd2].copy()
        part_col_top = np.where(orient.filled, z + orient.top, 0).astype(np.int32)
        np.maximum(new_col_top, part_col_top, out=new_col_top)
        self.column_top[x:x + fw2, y:y + fd2] = new_col_top

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

    def _rebuild_column_top(self) -> None:
        """Recompute column_top from scratch from current occupancy.

        Used after manual occupancy manipulation (e.g., in tests and
        _rebuild_extreme_points).
        """
        occ = self.occupancy
        nz = occ.shape[2]
        # For each column (i, j), find the highest z that is True.
        # np.max along axis 2 of the z-index where occ is True, +1.
        # Efficient: flip z-axis, argmax gives first True from the top.
        # But simpler and still fast: use cumsum trick or just argmax on flip.
        # For correctness, compute: column_top[i,j] = max z+1 where occ[i,j,z]=True
        # = 0 if no True in column.
        col_any = occ.any(axis=2)  # (nx, ny) bool
        # np.argmax on reversed z finds highest True index
        flipped = occ[:, :, ::-1]
        argmax_from_top = np.argmax(flipped, axis=2)  # index from top
        highest_z = (nz - 1) - argmax_from_top        # actual z index of highest True
        self.column_top = np.where(col_any, highest_z + 1, 0).astype(np.int32)

    def _rebuild_extreme_points(self) -> None:
        """Rebuild EP set from scratch based on current occupancy.

        Used in tests that manually modify occupancy without calling place().
        """
        # Rebuild column_top as well since occupancy was modified directly.
        self._rebuild_column_top()

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
