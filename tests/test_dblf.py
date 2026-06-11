"""Tests for src.nesting3d.bin3d + dblf (PLAN_3D.md §4)."""

import numpy as np
import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf, plates_first_key, tower_order_key
from src.nesting3d.voxelize import voxelize_part

# trimesh grid size is round(extent/pitch)+1 (vertex-centred, conservative):
# at pitch 5 a 6 mm cube -> 2x2x2 voxels, a 9 mm cube -> 3x3x3.
PITCH = 5.0


def _cube_part(part_id: str, edge_mm: float = 6.0):
    b = trimesh.creation.box(extents=(edge_mm,) * 3)
    b.apply_translation(-b.bounds[0])
    vp = voxelize_part(part_id, b, PITCH, n_orientations=1)
    vp.id = part_id
    return vp


def _bin(base_mm: float = 20.0) -> Bin3D:
    return Bin3D(base_mm, base_mm, PITCH)  # 4x4 voxel base


def test_single_cube_lands_at_origin():
    placements, b = dblf([_cube_part("c1")], _bin)
    assert len(placements) == 1
    p = placements[0]
    assert (p.x, p.y, p.z) == (0, 0, 0)
    assert b.max_height_voxels() == 2


def test_two_cubes_share_the_floor():
    placements, b = dblf([_cube_part("c1"), _cube_part("c2")], _bin)
    assert [p.z for p in placements] == [0, 0]
    assert (placements[0].x, placements[0].y) != (placements[1].x, placements[1].y)
    assert b.max_height_voxels() == 2  # side by side, not stacked


def test_fifth_cube_stacks():
    # 4x4 base holds exactly four 2x2 cubes on the floor; the 5th must stack
    parts = [_cube_part(f"c{i}") for i in range(5)]
    placements, b = dblf(parts, _bin)
    zs = sorted(p.z for p in placements)
    assert zs == [0, 0, 0, 0, 2]
    assert b.max_height_voxels() == 4


def test_no_overlap_heightmap_invariant():
    # cubes are full columns, so sum(H) == total voxels placed; any overlap
    # would make the heightmap sum come up short
    parts = [_cube_part(f"c{i}") for i in range(5)]
    _, b = dblf(parts, _bin)
    assert int(b.height.sum()) == sum(p.volume_voxels for p in parts)


def test_volume_descending_order():
    small = _cube_part("small", edge_mm=6.0)
    big = _cube_part("big", edge_mm=9.0)  # 3x3x3 voxels
    placements, _ = dblf([small, big], _bin)
    assert placements[0].part_id == "big"


def test_plates_first_order():
    # plakalar başa, aynı isimliler ARDIŞIK; plaka-dışılar hacim-azalan sona
    def named(part_id, name, edge):
        vp = _cube_part(part_id, edge_mm=edge)
        vp.name = name
        return vp

    parts = [
        named("small", "small", 6.0),
        named("pA_1", "plateA", 9.0),
        named("big", "big", 9.0),
        named("pB_1", "plateB", 9.0),
        named("pA_2", "plateA", 9.0),
    ]
    key = plates_first_key(frozenset({"plateA", "plateB"}))
    order = [p.id for p in sorted(parts, key=key)]
    assert order[:3] == ["pA_1", "pA_2", "pB_1"]  # plakalar önce, tip-tip
    assert order[3:] == ["big", "small"]          # kalanlar hacim-azalan


def test_dblf_custom_order_key_changes_placement_order():
    small = _cube_part("small", edge_mm=6.0)
    big = _cube_part("big", edge_mm=9.0)
    placements, _ = dblf([small, big], _bin,
                         order_key=lambda p: (p.volume_voxels,))
    assert placements[0].part_id == "small"  # hacim-ARTAN özel sıra uygulanır


def test_tower_order_plates_lead_and_deterministic():
    def named(part_id, name, edge):
        vp = _cube_part(part_id, edge_mm=edge)
        vp.name = name
        return vp

    def build():
        return [
            named("big", "big", 9.0),
            named("pA_1", "plateA", 9.0),
            named("pB_1", "plateB", 9.0),
            named("pA_2", "plateA", 9.0),
            named("small", "small", 6.0),
        ]

    plates = frozenset({"plateA", "plateB"})
    parts = build()
    key = tower_order_key(parts, plates, _bin)
    order = [p.id for p in sorted(parts, key=key)]
    assert set(order[:3]) == {"pA_1", "pA_2", "pB_1"}  # plakalar önde
    assert order[3:] == ["big", "small"]               # kalanlar hacim-azalan
    # determinizm: aynı girdiden aynı sıra
    parts2 = build()
    order2 = [p.id for p in sorted(parts2, key=tower_order_key(parts2, plates, _bin))]
    assert order == order2


def test_deterministic():
    parts = [_cube_part(f"c{i}") for i in range(5)]
    a, _ = dblf(parts, _bin)
    b, _ = dblf(parts, _bin)
    assert a == b


def test_drop_z_matches_drop_map():
    part = _cube_part("c1")
    orient = part.orientations[0]
    b = _bin(40.0)  # 8x8 base
    rng = np.random.default_rng(42)
    b.height[:] = rng.integers(0, 5, size=b.height.shape)
    Z = b.drop_map(orient)
    for x in range(Z.shape[0]):
        for y in range(Z.shape[1]):
            assert Z[x, y] == b.drop_z(orient, x, y)


def test_metrics():
    placements, b = dblf([_cube_part("c1")], _bin)
    # 6mm cube -> 2 voxels = 10mm of heightmap
    assert b.max_height_mm() == 10.0
    # 8 placed voxels x 125 mm3 in a 20x20x10 envelope = 1000/4000
    assert abs(b.packing_density() - 0.25) < 1e-9
