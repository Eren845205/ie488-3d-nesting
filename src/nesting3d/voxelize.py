"""voxelize.py — mesh -> VoxelPart (PLAN_3D.md §2.4, §3).

Each part is voxelized once per allowed axis-aligned orientation.  For every
orientation we precompute the column profiles the heightmap placement needs:

  grid    : bool (nx, ny, nz) — filled voxels, mesh min-corner at index (0,0,0)
  filled  : bool (nx, ny)     — columns that contain at least one voxel
  bottom  : int  (nx, ny)     — lowest filled z index per column (0 where empty)
  top     : int  (nx, ny)     — highest filled z index + 1 per column (0 where empty)

Heightmap drop rule (PLAN_3D.md §2.4):
  z(x, y) = max over filled columns (i, j) of  H[x+i, y+j] - bottom[i, j]

Orientations (PLAN_3D.md §2.5): 4 axis-aligned poses — z-rotation {0°, 90°}
x {upright, tipped on side (Rx 90°)}.  Not all 24 rotations: AM part stability
+ small search space.
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import trimesh

try:
    from shapely import contains_xy as _contains_xy
except ImportError:  # slice yöntemi shapely ister; subdivide onsuz çalışır
    _contains_xy = None


def rotation_matrices(n_orientations: int = 4) -> List[np.ndarray]:
    """The allowed pose set, as 4x4 homogeneous matrices.

    Order: upright 0°, upright 90°, side 0°, side 90°.  n_orientations=1
    keeps only the original pose (PLAN_3D.md atılma sırası #1).
    """
    rz = trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1))
    rx = trimesh.transformations.rotation_matrix(math.pi / 2, (1, 0, 0))
    mats = [np.eye(4), rz, rx, rz @ rx]
    return mats[: max(1, min(n_orientations, len(mats)))]


@dataclass
class Orientation:
    """Voxel data for one axis-aligned pose of a part."""

    rot_matrix: np.ndarray          # 4x4 — applied to the mesh for this pose
    voxel_origin: np.ndarray        # world xyz of voxel index (0,0,0) centre
    grid: np.ndarray                # bool (nx, ny, nz)
    filled: np.ndarray              # bool (nx, ny)
    bottom: np.ndarray              # int (nx, ny)
    top: np.ndarray                 # int (nx, ny)
    voxel_count: int = 0

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.grid.shape


@dataclass
class VoxelPart:
    """One placeable part instance (qty-expanded; orientation data is shared
    between instances of the same model — read-only)."""

    id: str
    name: str
    mesh: trimesh.Trimesh           # scaled original (for STL export)
    orientations: List[Orientation]
    volume_voxels: int = 0
    qty_of_model: int = 1
    extra: dict = field(default_factory=dict)


def _dilate(grid: np.ndarray, times: int) -> np.ndarray:
    """6-neighbour binary dilation, `times` voxels of inter-part margin
    (PLAN_3D.md §2.8).  Pads the array so the dilation never clips."""
    g = np.pad(grid, times)
    for _ in range(times):
        out = g.copy()
        for axis in range(3):
            out |= np.roll(g, 1, axis=axis)
            out |= np.roll(g, -1, axis=axis)
        g = out
    return g


def _slice_voxelize(mesh: trimesh.Trimesh, pitch: float) -> np.ndarray:
    """Watertight mesh -> bool grid via z-slicing at voxel centres.

    Her z-katmanında mesh kesiti alınır (section_multiplane) ve voxel
    MERKEZLERİ kesit poligonlarının içinde mi diye işaretlenir.  Yüksek
    yüz sayılı gerçek parçalarda subdivide yönteminden ~100x hızlı ve
    hacim-doğru: subdivide yüzeye değen her voxeli doldurur, ince plakaları
    ~2x şişirir (numune kalibrasyonu 2026-06-10).  Mesh min-köşesi origin'de
    olmalı (voxelize_part bunu garanti eder).
    """
    if _contains_xy is None:
        raise ImportError("slice voxelization için shapely gerekli")
    ext = mesh.extents
    n = np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1)
    # son dilim parçadan dışarı taşmasın (kalınlık < pitch/2 kalan tepe katmanı)
    zs = np.minimum((np.arange(n[2]) + 0.5) * pitch, ext[2] - 1e-6)
    sections = mesh.section_multiplane(
        plane_origin=[0.0, 0.0, 0.0], plane_normal=[0.0, 0.0, 1.0], heights=zs
    )
    xs = (np.arange(n[0]) + 0.5) * pitch
    ys = (np.arange(n[1]) + 0.5) * pitch
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    px, py = XX.ravel(), YY.ravel()

    grid = np.zeros((n[0], n[1], n[2]), dtype=bool)
    for k, sec in enumerate(sections):
        if sec is None:
            continue
        mask = np.zeros(px.shape, dtype=bool)
        for poly in sec.polygons_full:
            mask |= _contains_xy(poly, px, py)
        grid[:, :, k] = mask.reshape(n[0], n[1])
    assert grid.any(), "slice voxelization boş grid üretti — pitch/mesh hatası"
    return grid


def _column_profiles(grid: np.ndarray):
    """(filled, bottom, top) column profiles of a bool (nx, ny, nz) grid."""
    nz = grid.shape[2]
    filled = grid.any(axis=2)
    bottom = np.where(filled, np.argmax(grid, axis=2), 0).astype(np.int32)
    top = np.where(filled, nz - np.argmax(grid[:, :, ::-1], axis=2), 0).astype(
        np.int32
    )
    return filled, bottom, top


def voxelize_part(
    name: str,
    mesh: trimesh.Trimesh,
    pitch: float,
    *,
    n_orientations: int = 4,
    margin: int = 0,
    method: str = "subdivide",
    display_mesh: Optional[trimesh.Trimesh] = None,
) -> VoxelPart:
    """Voxelize one model into a VoxelPart with per-orientation profiles.

    fill() is essential: surface-only grids would break both volume metrics
    and the bottom/top profiles (PLAN_3D.md risk #1).

    method="slice" yüksek yüz sayılı gerçek STL'ler için hızlı yol (bkz.
    _slice_voxelize).  display_mesh verilirse VoxelPart.mesh olarak o saklanır
    (görsel + STL export hafif decimated kopyayı kullanır; packing orijinal
    geometriden hesaplanır).
    """
    orientations: List[Orientation] = []
    for rot in rotation_matrices(n_orientations):
        m = mesh.copy()
        m.apply_transform(rot)
        m.apply_translation(-m.bounds[0])

        if method == "slice":
            grid = _slice_voxelize(m, pitch)
            origin = np.full(3, pitch / 2.0)
        else:
            vg = m.voxelized(pitch).fill()
            grid = np.asarray(vg.matrix, dtype=bool)
            origin = vg.indices_to_points(np.array([[0, 0, 0]]))[0]

        if margin > 0:
            grid = _dilate(grid, margin)
            origin = origin - margin * pitch

        filled, bottom, top = _column_profiles(grid)
        orientations.append(
            Orientation(
                rot_matrix=rot,
                voxel_origin=np.asarray(origin, dtype=float),
                grid=grid,
                filled=filled,
                bottom=bottom,
                top=top,
                voxel_count=int(grid.sum()),
            )
        )

    return VoxelPart(
        id=name,
        name=name,
        mesh=display_mesh if display_mesh is not None else mesh,
        orientations=orientations,
        volume_voxels=orientations[0].voxel_count,
    )


def expand_quantities(
    model_set: List[tuple],
    pitch: float,
    *,
    n_orientations: int = 4,
    margin: int = 0,
    method: str = "subdivide",
) -> List[VoxelPart]:
    """Voxelize each model ONCE, then expand to qty part instances.

    Instances share the (read-only) orientation data, so 30 parts cost
    3 voxelizations.  IDs follow the 2D loader suffix convention: name_01..

    model_set girdileri 3'lü (name, mesh, qty) veya 4'lü
    (name, mesh, qty, display_mesh) olabilir.
    """
    parts: List[VoxelPart] = []
    for entry in model_set:
        name, mesh, qty = entry[:3]
        display = entry[3] if len(entry) > 3 else None
        template = voxelize_part(
            name, mesh, pitch, n_orientations=n_orientations, margin=margin,
            method=method, display_mesh=display,
        )
        width = max(2, len(str(qty)))
        for k in range(1, qty + 1):
            parts.append(
                VoxelPart(
                    id=f"{name}_{k:0{width}d}",
                    name=name,
                    mesh=template.mesh,
                    orientations=template.orientations,
                    volume_voxels=template.volume_voxels,
                    qty_of_model=qty,
                )
            )
    return parts
