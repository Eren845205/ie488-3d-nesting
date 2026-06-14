"""export_stl.py — turn a placement list back into real geometry (PLAN_3D.md §3).

The voxel solver works on grids; the export applies each placement's pose to
the ORIGINAL (scaled) mesh and writes one combined STL scene — the final
arrow of the hoca pipeline (... -> Order -> .STL).

Alignment: each Orientation stores voxel_origin = the world position of voxel
index (0,0,0)'s CENTRE in the rotated, min-corner-at-origin mesh frame.  The
placed mesh is translated so that this point lands on the centre of bin cell
(x, y, z) — mesh and voxel grid agree to within voxelization rounding.
"""

from pathlib import Path
from typing import Dict, List

import numpy as np
import trimesh

from src.nesting3d.bin3d import Placement3D
from src.nesting3d.voxelize import VoxelPart

# Distinct colours for up to 20 part types; cycles after that.
_PART_COLOURS = [
    [0.902, 0.224, 0.208, 1.0],  # red
    [0.208, 0.518, 0.894, 1.0],  # blue
    [0.204, 0.710, 0.290, 1.0],  # green
    [0.988, 0.733, 0.012, 1.0],  # amber
    [0.612, 0.153, 0.690, 1.0],  # purple
    [0.012, 0.663, 0.957, 1.0],  # cyan
    [1.000, 0.596, 0.000, 1.0],  # orange
    [0.620, 0.004, 0.259, 1.0],  # crimson
    [0.004, 0.455, 0.420, 1.0],  # teal
    [0.949, 0.502, 0.502, 1.0],  # pink
    [0.565, 0.933, 0.565, 1.0],  # light-green
    [0.373, 0.620, 0.627, 1.0],  # slate-blue
    [0.741, 0.718, 0.420, 1.0],  # khaki
    [0.855, 0.439, 0.839, 1.0],  # violet
    [0.824, 0.706, 0.549, 1.0],  # tan
    [0.502, 0.502, 0.000, 1.0],  # olive
    [0.000, 0.502, 0.502, 1.0],  # dark-teal
    [0.502, 0.000, 0.502, 1.0],  # dark-purple
    [0.502, 0.502, 0.502, 1.0],  # grey
    [0.184, 0.310, 0.310, 1.0],  # dark-slate
]


def placed_meshes(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    pitch: float,
) -> List[trimesh.Trimesh]:
    """The original meshes, transformed to their placed poses (mm frame)."""
    out = []
    for pl in placements:
        part = parts_by_id[pl.part_id]
        orient = part.orientations[pl.orientation_idx]
        m = part.mesh.copy()
        m.apply_transform(orient.rot_matrix)
        m.apply_translation(-m.bounds[0])
        cell_centre = (np.array([pl.x, pl.y, pl.z], dtype=float) + 0.5) * pitch
        m.apply_translation(cell_centre - orient.voxel_origin)
        out.append(m)
    return out


def build_result_scene(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    *,
    pitch: float,
) -> trimesh.Scene:
    """Build a trimesh.Scene of the nesting result using REAL part geometry.

    Each placement's original mesh (VoxelPart.mesh — NOT voxel cubes) is
    rotated by its orientation's rot_matrix and translated to its placed
    position (voxel indices -> mm via pitch + voxel_origin offset).  The
    result is identical to the STL export geometry but returned as a named
    multi-mesh Scene suitable for GLB export.

    Transform chain (mirrors placed_meshes exactly, reuses its logic):
      1. apply rot_matrix          — pose rotation in mesh-local frame
      2. translate to min-corner   — shift rotated mesh so AABB min = origin
      3. translate to cell centre  — place at (x+0.5, y+0.5, z+0.5)*pitch
      4. subtract voxel_origin     — undo the half-voxel offset added at
                                     voxelization time so mesh and voxel grid align

    Part names appear as geometry keys; duplicate part names get a
    sequential suffix (_01, _02 …) so every key is unique.  A distinct
    colour is applied per unique part name for visual differentiation.

    Returns an empty Scene for an empty placements list.
    """
    scene = trimesh.Scene()
    if not placements:
        return scene

    # Assign one colour index per unique part name (model type).
    name_colour_idx: Dict[str, int] = {}
    # Count occurrences to build unique geometry keys.
    name_counter: Dict[str, int] = {}

    # Reuse placed_meshes for the transform — single source of truth.
    meshes = placed_meshes(placements, parts_by_id, pitch)

    for pl, mesh in zip(placements, meshes):
        part_name = parts_by_id[pl.part_id].name

        # Assign colour per model name.
        if part_name not in name_colour_idx:
            name_colour_idx[part_name] = len(name_colour_idx) % len(_PART_COLOURS)
        colour = _PART_COLOURS[name_colour_idx[part_name]]

        # Apply colour to mesh material.
        mesh.visual = trimesh.visual.ColorVisuals(
            mesh=mesh,
            face_colors=np.tile(
                np.array([int(c * 255) for c in colour], dtype=np.uint8),
                (len(mesh.faces), 1),
            ),
        )

        # Build a unique geometry key: part_id already unique per placement.
        geo_key = pl.part_id
        name_counter[geo_key] = name_counter.get(geo_key, 0) + 1
        if name_counter[geo_key] > 1:
            geo_key = f"{geo_key}_{name_counter[geo_key]:02d}"

        scene.add_geometry(mesh, geom_name=geo_key)

    return scene


def scene_to_glb_bytes(scene: trimesh.Scene) -> bytes:
    """Export a trimesh.Scene to GLB format (three.js-compatible).

    Returns raw GLB bytes.  The GLB header starts with magic b'glTF' and
    version 2 (glTF 2.0) as required by the three.js GLTFLoader.
    """
    return scene.export(file_type="glb")


def export_scene(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    pitch: float,
    out_path: Path | str,
) -> Path:
    """Write all placed parts as a single STL file; returns the path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.util.concatenate(placed_meshes(placements, parts_by_id, pitch))
    scene.export(out_path)
    return out_path
