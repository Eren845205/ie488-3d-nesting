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


def _dz_dogrula(dz, n: int):
    """dz listesini dogrula (K-50/R11 kablosu): None -> None, aksi halde
    uzunluk == yerlesim sayisi olmali. Sessiz hizasizlik illegal STL uretir —
    fail-loud sart."""
    if dz is None:
        return None
    if len(dz) != n:
        raise ValueError(
            f"dz uzunlugu ({len(dz)}) yerlesim sayisiyla ({n}) eslesmiyor — "
            "R11 dz listesi placements ile ayni sirali/uzunlukta olmali")
    return [float(d) for d in dz]


def placed_meshes(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    pitch: float,
    dz=None,
) -> List[trimesh.Trimesh]:
    """The original meshes, transformed to their placed poses (mm frame).

    dz (K-50 R11 kablosu): parca-basina mm cinsinden EK asagi otelenme
    (continuous_settle.apply_dz semantigi: yalniz d>0 uygulanir). None ->
    bugunku davranis birebir. Uzunluk uyusmazligi ValueError."""
    dz = _dz_dogrula(dz, len(placements))
    out = []
    for i, pl in enumerate(placements):
        part = parts_by_id[pl.part_id]
        orient = part.orientations[pl.orientation_idx]
        m = part.mesh.copy()
        m.apply_transform(orient.rot_matrix)
        m.apply_translation(-m.bounds[0])
        cell_centre = (np.array([pl.x, pl.y, pl.z], dtype=float) + 0.5) * pitch
        m.apply_translation(cell_centre - orient.voxel_origin)
        if dz is not None and dz[i] > 0.0:
            m.apply_translation([0.0, 0.0, -dz[i]])
        out.append(m)
    return out


def build_result_scene(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    *,
    pitch: float,
    merge_by_type: bool = False,
    max_faces_total: int | None = None,
    dz=None,
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

    merge_by_type=True: her parca TIPININ mesh'i sahneye BIR kez konur;
    yerlesimler ayni geometriye referans veren DUGUMLER olur (tam donusum
    matrisi dugumde tasinir).  GLB'de geometri buffer'i tip basina tek kez
    yazilir -> dosya 588-kopyali sahnede ~30x kuculur; three.js tarafi
    paylasilan BufferGeometry'yi gorup InstancedMesh'e cevirebilir (draw
    call sayisi tip sayisina iner).  Gorunum birebir: dugum matrisi
    placed_meshes'in uyguladigi zincirin (R -> min-kose -> hucre) aynisidir.
    Default False, tarihsel placement-basina-geometri yerlesimini korur
    (testler + STL araclari).

    dz (K-50 R11 kablosu): parca-basina ek asagi otelenme; placed_meshes ile
    ayni sozlesme. Instanced yolda dugum matrisine islenir (geometri paylasimi
    bozulmaz).

    Returns an empty Scene for an empty placements list.
    """
    dz = _dz_dogrula(dz, len(placements))
    scene = trimesh.Scene()
    if not placements:
        return scene

    if merge_by_type:
        return _build_instanced_scene(placements, parts_by_id, pitch,
                                      max_faces_total=max_faces_total, dz=dz)

    # Assign one colour index per unique part name (model type).
    name_colour_idx: Dict[str, int] = {}
    # Count occurrences to build unique geometry keys.
    name_counter: Dict[str, int] = {}

    # Reuse placed_meshes for the transform — single source of truth.
    meshes = placed_meshes(placements, parts_by_id, pitch, dz=dz)

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


def _build_instanced_scene(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    pitch: float,
    max_faces_total: int | None = None,
    dz=None,
) -> trimesh.Scene:
    """Tip basina TEK geometri + yerlesim basina dugum-matrisi (instancing).

    Dugum matrisi placed_meshes zincirinin kompozisyonu (saga carpim sirasi:
    once R, sonra min-kose otelenmesi, sonra hucre-merkezi):
        M = T(cell_centre - voxel_origin) @ T(-rotated_bounds_min) @ R
    rotated_bounds_min tip+oryantasyon basina BIR kez hesaplanir (cache).

    max_faces_total: verilirse ONIZLEME modu — sahnenin ACILMIS toplam ucgen
    sayisi (tip ucgeni x kopya adedi) bu butceyi asarsa her tipin kanonik
    mesh'i oransal olarak sadelestirilir (quadric decimation). WebGL'de 5M+
    ucgen kasar; onizleme ~budget ucgenle akici olur. STL indirme/tam-dogruluk
    yolu bu parametreyi VERMEZ (geometri birebir kalir).
    """
    scene = trimesh.Scene()
    name_colour_idx: Dict[str, int] = {}
    canon_added: Dict[str, str] = {}       # part name -> geom adi
    bmin_cache: Dict[tuple, np.ndarray] = {}  # (name, orient_idx) -> bounds[0]

    # -- Onizleme butcesi: tip basina sadelestirme orani hesapla -----------
    decim_keep: Dict[str, float] = {}
    if max_faces_total:
        sayim: Dict[str, int] = {}
        for pl in placements:
            sayim[parts_by_id[pl.part_id].name] = sayim.get(
                parts_by_id[pl.part_id].name, 0) + 1
        toplam = 0
        for name, adet in sayim.items():
            ornek = next(p for p in parts_by_id.values() if p.name == name)
            toplam += len(ornek.mesh.faces) * adet
        if toplam > max_faces_total:
            oran = max_faces_total / float(toplam)
            for name in sayim:
                decim_keep[name] = max(oran, 0.02)  # asiri sadelesme freni

    def _kanonik_mesh(part) -> trimesh.Trimesh:
        mesh = part.mesh.copy()
        keep = decim_keep.get(part.name)
        if keep is not None and keep < 1.0 and len(mesh.faces) > 500:
            try:
                hedef_kalan = max(int(len(mesh.faces) * keep), 200)
                azalt = 1.0 - (hedef_kalan / float(len(mesh.faces)))
                if azalt > 0.05:
                    mesh = mesh.simplify_quadric_decimation(azalt)
            except Exception:
                pass  # sadelestirme yoksa/patlarsa tam mesh kullan (dogruluk-notr)
        return mesh

    for i, pl in enumerate(placements):
        part = parts_by_id[pl.part_id]
        part_name = part.name
        orient = part.orientations[pl.orientation_idx]

        key = (part_name, pl.orientation_idx)
        if key not in bmin_cache:
            rotated = part.mesh.copy()
            rotated.apply_transform(orient.rot_matrix)
            bmin_cache[key] = rotated.bounds[0].copy()
        bmin = bmin_cache[key]

        cell_centre = (np.array([pl.x, pl.y, pl.z], dtype=float) + 0.5) * pitch
        t_top = np.eye(4)
        t_top[:3, 3] = (cell_centre - orient.voxel_origin) - bmin
        if dz is not None and dz[i] > 0.0:
            t_top[2, 3] -= dz[i]  # R11 dusmesi dugum matrisinde (placed_meshes paritesi)
        matrix = t_top @ np.asarray(orient.rot_matrix, dtype=float)
        node_name = f"{pl.part_id}#{i:04d}"

        if part_name not in canon_added:
            mesh = _kanonik_mesh(part)
            if part_name not in name_colour_idx:
                name_colour_idx[part_name] = len(name_colour_idx) % len(_PART_COLOURS)
            colour = _PART_COLOURS[name_colour_idx[part_name]]
            mesh.visual = trimesh.visual.ColorVisuals(
                mesh=mesh,
                face_colors=np.tile(
                    np.array([int(c * 255) for c in colour], dtype=np.uint8),
                    (len(mesh.faces), 1),
                ),
            )
            # Ilk yerlesim dugumu geometriyle birlikte eklenir (orijinde
            # fazladan kimlik-donusumlu kopya OLUSMAZ).
            scene.add_geometry(
                mesh, geom_name=part_name, node_name=node_name, transform=matrix,
            )
            canon_added[part_name] = part_name
        else:
            scene.graph.update(
                frame_to=node_name,
                matrix=matrix,
                geometry=canon_added[part_name],
            )

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
    dz=None,
) -> Path:
    """Write all placed parts as a single STL file; returns the path.

    dz: bkz. placed_meshes (K-50 R11 kablosu)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scene = trimesh.util.concatenate(
        placed_meshes(placements, parts_by_id, pitch, dz=dz))
    scene.export(out_path)
    return out_path
