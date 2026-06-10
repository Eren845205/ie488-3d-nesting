"""Tests for src.nesting3d.export_stl + visualize3d (PLAN_3D.md §4)."""

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.export_stl import export_scene, placed_meshes
from src.nesting3d.visualize3d import render_convergence, render_layout
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
PLATE = 40.0


def _cube_part(part_id: str, edge_mm: float = 10.0):
    b = trimesh.creation.box(extents=(edge_mm,) * 3)
    b.apply_translation(-b.bounds[0])
    vp = voxelize_part(part_id, b, PITCH, n_orientations=1)
    vp.id = part_id
    return vp


def _placed(n=4):
    parts = [_cube_part(f"c{i}") for i in range(n)]
    placements, b = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH))
    return parts, placements, b


def test_export_writes_loadable_stl(tmp_path):
    parts, placements, b = _placed()
    out = export_scene(placements, {p.id: p for p in parts}, PITCH,
                       tmp_path / "scene.stl")
    assert out.exists()
    scene = trimesh.load(str(out), force="mesh")
    # 4 disjoint 10mm cubes -> total volume ~ 4000 mm^3 (PLAN_3D.md §4, %1)
    assert abs(scene.volume - 4 * 10.0 ** 3) < 0.01 * 4 * 10.0 ** 3


def test_placed_meshes_stay_inside_base():
    parts, placements, b = _placed()
    eps = PITCH  # voxel rounding tolerance
    for m in placed_meshes(placements, {p.id: p for p in parts}, PITCH):
        lo, hi = m.bounds
        assert lo[0] >= -eps and lo[1] >= -eps and lo[2] >= -eps
        assert hi[0] <= PLATE + eps and hi[1] <= PLATE + eps


def test_meshes_do_not_interpenetrate():
    # disjoint placements -> pairwise AABBs must not overlap in 3D
    parts, placements, _ = _placed()
    boxes = [m.bounds for m in placed_meshes(placements,
                                             {p.id: p for p in parts}, PITCH)]
    eps = 1e-6
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (alo, ahi), (blo, bhi) = boxes[i], boxes[j]
            overlap = all(ahi[k] > blo[k] + eps and bhi[k] > alo[k] + eps
                          for k in range(3))
            assert not overlap, f"placements {i} ve {j} çakışıyor"


def test_render_layout_writes_png(tmp_path):
    parts, placements, b = _placed()
    out = render_layout(placements, {p.id: p for p in parts}, b,
                        tmp_path / "layout.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_convergence_writes_png(tmp_path):
    out = render_convergence([30.0, 25.0, 25.0, 20.0], 30.0,
                             tmp_path / "conv.png")
    assert out.exists() and out.stat().st_size > 0
