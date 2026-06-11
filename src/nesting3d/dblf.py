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

from functools import lru_cache
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

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


def plates_first_key(plate_names: FrozenSet[str]) -> Callable[[VoxelPart], tuple]:
    """Sıra anahtarı: plakalar önce (aynı tip ARDIŞIK), kalanlar hacim-azalan.

    Gerekçe (2026-06-11, hedef z <= 170): 335 tabana aynı anda tek plaka
    sığar (228x180 footprint) — ardışık gelen aynı-tip plakayı _best_position
    z_top kuralı bir öncekinin üstüne EN İYİ geçişme hizasında (çıkıntı ->
    delik) oturtmak zorunda kalır.  Hacim-azalan sıra tipleri karıştırıp bu
    eşleşmeyi bozuyordu (farklı tip plakalar geçişmez).
    """
    def key(p: VoxelPart):
        return (p.name not in plate_names, -p.volume_voxels, p.name, p.id)
    return key


def tower_order_key(
    parts: List[VoxelPart],
    plate_names: FrozenSet[str],
    bin_factory: Callable[[], Bin3D],
) -> Callable[[VoxelPart], tuple]:
    """DP-optimal plaka istif sırası (çapraz-tip geçişme matrisi üzerinden).

    335 tabana iki plaka yan yana sığmadığından tüm plakalar tek kolonda
    kesişir (Helly) -> plaka kulesi yerleşimin ALT SINIRIDIR.  Kuleyi
    minimize eden istif sırası: tip çifti başına geçişme (çıkıntı -> delik)
    drop_map ile ölçülür, 'kalan adetler x son tip' DP'si toplam geçişmeyi
    maksimize eden diziyi verir (probe 2026-06-11: p1.0'da zigzag dizi
    aynı-tip gruplamadan 30 mm daha iyi — n3->n6/n8 7'şer mm geçişiyor).
    Kalan parçalar hacim-azalan sona gider.
    """
    by_name: Dict[str, List[VoxelPart]] = {}
    for p in parts:
        if p.name in plate_names:
            by_name.setdefault(p.name, []).append(p)
    names = sorted(by_name)
    if not names:
        return plates_first_key(plate_names)

    # tip çifti geçişme matrisi: alt plaka orijinde, üstün en derin drop'u
    nest: Dict[Tuple[int, int], int] = {}
    for ai, a in enumerate(names):
        b = bin_factory()
        b.place(by_name[a][0], 0, 0, 0, 0)
        no_nest = b.max_height_voxels() + b.z_clearance
        for ui, u in enumerate(names):
            zs = [int(Z.min()) for o in by_name[u][0].orientations
                  if (Z := b.drop_map(o)) is not None]
            nest[(ai, ui)] = no_nest - min(zs) if zs else 0

    counts0 = tuple(len(by_name[n]) for n in names)

    @lru_cache(maxsize=None)
    def dp(counts: tuple, last: int) -> int:
        if sum(counts) == 0:
            return 0
        return max(
            (nest[(last, t)] if last >= 0 else 0)
            + dp(tuple(c - 1 if i == t else c for i, c in enumerate(counts)), t)
            for t, ct in enumerate(counts) if ct
        )

    seq: List[str] = []
    counts, last = counts0, -1
    while sum(counts):
        for t, ct in enumerate(counts):
            if not ct:
                continue
            nxt = tuple(c - 1 if i == t else c for i, c in enumerate(counts))
            gain = nest[(last, t)] if last >= 0 else 0
            if gain + dp(nxt, t) == dp(counts, last):
                seq.append(names[t])
                counts, last = nxt, t
                break

    # diziye somut parça örnekleri ata (tip içinde id sırası — determinizm)
    pos: Dict[str, int] = {}
    queues = {n: sorted(by_name[n], key=lambda p: p.id) for n in names}
    for i, n in enumerate(seq):
        pos[queues[n].pop(0).id] = i

    def key(p: VoxelPart):
        return ((0, pos[p.id], 0, "") if p.id in pos
                else (1, 0, -p.volume_voxels, p.id))
    return key


def dblf(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    order_key: Optional[Callable[[VoxelPart], tuple]] = None,
) -> Tuple[List[Placement3D], Bin3D]:
    """DBLF baseline: volume-descending order (or `order_key`), all orientations."""
    key = order_key or (lambda p: (-p.volume_voxels,))
    order = sorted(parts, key=key)
    bin3d = bin_factory()
    placements = place_in_order(
        order, bin3d, lambda _i, part: range(len(part.orientations))
    )
    return placements, bin3d
