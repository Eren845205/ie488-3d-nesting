"""dblf.py — Deepest-Bottom-Left-Fill constructive baseline (PLAN_3D.md §2.4).

3D analogue of the 2D pipeline's constructive step:
  - "Order" (hoca pipeline step 3): parts sorted by voxel volume, descending —
    the 3D counterpart of BFD's area-descending rule.
  - Position rule: among all feasible (orientation, x, y) the placement with
    the lexicographically smallest (z_top, z, y, x) wins, where
    z_top = z + orientation height.  Minimizing the resulting TOP (not just z)
    is what the open-dimension objective actually rewards: an orientation that
    lies flat beats one that stands tall at the same drop z.

Height is unbounded, so every part is always placeable (acceptance criterion
PLAN_3D.md §6.2) — an UNPLACED outcome would indicate a bug, hence the assert.
"""

from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.voxelize import VoxelPart

# (z_top, z, y, x, orientation_idx) — orientation_idx breaks exact ties deterministically
_Best = Tuple[int, int, int, int, int]


def _best_position(
    bin3d: Bin3D, part: VoxelPart, orientation_indices: Sequence[int]
) -> Optional[_Best]:
    """Scan the given orientations; return the winning placement tuple."""
    best: Optional[_Best] = None
    for oi in orientation_indices:
        orient = part.orientations[oi]
        Z = bin3d.drop_map(orient)
        if Z is None:
            continue
        z_top = Z + orient.grid.shape[2]
        # lexicographic argmin over (z_top, z, y, x): scan winners of z_top
        cand_top = int(z_top.min())
        xs, ys = np.nonzero(z_top == cand_top)
        zs = Z[xs, ys]
        k = np.lexsort((xs, ys, zs))[0]
        cand = (cand_top, int(zs[k]), int(ys[k]), int(xs[k]), oi)
        if best is None or cand < best:
            best = cand
    return best


def place_in_order(
    parts: List[VoxelPart],
    bin3d: Bin3D,
    orientation_for: Callable[[int, VoxelPart], Sequence[int]],
) -> List[Placement3D]:
    """Place `parts` in the EXACT given order (the SA decision variable).

    `orientation_for(index, part)` returns which orientation indices to try —
    all of them for the DBLF baseline, exactly one for an SA decode.
    """
    placements: List[Placement3D] = []
    for idx, part in enumerate(parts):
        best = _best_position(bin3d, part, orientation_for(idx, part))
        assert best is not None, (
            f"{part.id} tabana sığmıyor — pitch/ölçek hatası (PLAN_3D.md §6.2)"
        )
        _, z, y, x, oi = best
        placements.append(bin3d.place(part, oi, x, y, z))
    return placements


def dblf(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
) -> Tuple[List[Placement3D], Bin3D]:
    """DBLF baseline: volume-descending order, all orientations considered."""
    order = sorted(parts, key=lambda p: p.volume_voxels, reverse=True)
    bin3d = bin_factory()
    placements = place_in_order(
        order, bin3d, lambda _i, part: range(len(part.orientations))
    )
    return placements, bin3d
