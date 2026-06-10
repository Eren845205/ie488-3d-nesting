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
