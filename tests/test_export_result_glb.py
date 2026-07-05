"""Tests for build_result_scene and scene_to_glb_bytes in export_stl.

Covers:
- build_result_scene returns a trimesh.Scene with correct geometry count
- scene_to_glb_bytes returns valid GLB bytes (magic 'glTF', non-empty)
- Part names are present in the scene geometry dict
"""

import struct

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.export_stl import build_result_scene, scene_to_glb_bytes
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
PLATE = 60.0


def _box_part(part_id: str, dims=(10.0, 10.0, 10.0)):
    """Create a simple box VoxelPart for testing."""
    mesh = trimesh.creation.box(extents=dims)
    mesh.apply_translation(-mesh.bounds[0])
    vp = voxelize_part(part_id, mesh, PITCH, n_orientations=1)
    vp.id = part_id
    return vp


def _make_nesting(n: int = 3):
    """Run a small DBLF nesting and return (parts_by_id, placements, pitch)."""
    parts = [_box_part(f"part_{i:02d}") for i in range(n)]
    placements, _ = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH))
    parts_by_id = {p.id: p for p in parts}
    return parts_by_id, placements


# ---------------------------------------------------------------------------
# TDD tests
# ---------------------------------------------------------------------------


def test_build_result_scene_returns_trimesh_scene():
    """build_result_scene must return a trimesh.Scene instance."""
    parts_by_id, placements = _make_nesting(3)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    assert isinstance(scene, trimesh.Scene)


def test_build_result_scene_geometry_count():
    """Scene must contain exactly one geometry entry per placement."""
    n = 3
    parts_by_id, placements = _make_nesting(n)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    assert len(scene.geometry) == n, (
        f"Expected {n} geometries, got {len(scene.geometry)}"
    )


def test_build_result_scene_geometry_names_contain_part_ids():
    """Each geometry name in the scene must reference a known part id."""
    parts_by_id, placements = _make_nesting(3)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    known_ids = set(parts_by_id.keys())
    for geo_name in scene.geometry:
        # geometry key must start with or exactly match a part id
        assert any(pid in geo_name for pid in known_ids), (
            f"Geometry name '{geo_name}' does not reference any known part id"
        )


def test_build_result_scene_meshes_are_trimesh():
    """Every geometry in the scene must be a trimesh.Trimesh (real mesh, not voxel)."""
    parts_by_id, placements = _make_nesting(3)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    for geo_name, geo in scene.geometry.items():
        assert isinstance(geo, trimesh.Trimesh), (
            f"Geometry '{geo_name}' is {type(geo).__name__}, expected Trimesh"
        )
        assert len(geo.faces) > 0, f"Geometry '{geo_name}' has no faces"


def test_scene_to_glb_bytes_returns_bytes():
    """scene_to_glb_bytes must return a bytes object."""
    parts_by_id, placements = _make_nesting(2)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    glb = scene_to_glb_bytes(scene)
    assert isinstance(glb, bytes)


def test_scene_to_glb_bytes_non_empty():
    """GLB output must be non-empty."""
    parts_by_id, placements = _make_nesting(2)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    glb = scene_to_glb_bytes(scene)
    assert len(glb) > 0


def test_scene_to_glb_bytes_valid_magic():
    """GLB must start with 'glTF' magic bytes (bytes 0-3)."""
    parts_by_id, placements = _make_nesting(2)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    glb = scene_to_glb_bytes(scene)
    # GLB header: magic (4 bytes) = 0x46546C67 = b'glTF'
    assert glb[:4] == b"glTF", (
        f"Invalid GLB magic: {glb[:4]!r} — expected b'glTF'"
    )


def test_scene_to_glb_bytes_valid_version():
    """GLB version field (bytes 4-7) must be 2 (glTF 2.0)."""
    parts_by_id, placements = _make_nesting(2)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    glb = scene_to_glb_bytes(scene)
    version = struct.unpack_from("<I", glb, 4)[0]
    assert version == 2, f"GLB version {version} — expected 2 (glTF 2.0)"


def test_glb_length_matches_header():
    """GLB header total length field must match actual bytes length."""
    parts_by_id, placements = _make_nesting(2)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    glb = scene_to_glb_bytes(scene)
    declared_length = struct.unpack_from("<I", glb, 8)[0]
    assert declared_length == len(glb), (
        f"Header length {declared_length} != actual length {len(glb)}"
    )


# ---------------------------------------------------------------------------
# merge_by_type: tip basina TEK geometri (viewer performansi)
# ---------------------------------------------------------------------------


def _make_typed_nesting():
    """2 tip x 2 kopya = 4 placement (uretimdeki expand_quantities benzeri:
    ayni tipin kopyalari ayni .name'i paylasir, id'ler ayrik)."""
    parts = []
    for tip in ("typeA", "typeB"):
        for kopya in (1, 2):
            mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
            mesh.apply_translation(-mesh.bounds[0])
            vp = voxelize_part(tip, mesh, PITCH, n_orientations=1)
            vp.id = f"{tip}_{kopya}"
            parts.append(vp)
    placements, _ = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH))
    return {p.id: p for p in parts}, placements


def test_merge_by_type_tip_basina_tek_geometri():
    parts_by_id, placements = _make_typed_nesting()
    assert len(placements) == 4
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH,
                               merge_by_type=True)
    assert set(scene.geometry.keys()) == {"typeA", "typeB"}


def test_merge_by_type_gorunum_birebir():
    """Instancing gorunumu degistirmez: dugum-matrisleriyle acilmis sahne
    (dump) placement-basina sahneyle AYNI toplam ucgen sayisini ve AYNI
    dunya bbox'ini verir (matris zinciri placed_meshes ile esdeger)."""
    import numpy as np
    parts_by_id, placements = _make_typed_nesting()
    ayrik = build_result_scene(placements, parts_by_id, pitch=PITCH)
    birlesik = build_result_scene(placements, parts_by_id, pitch=PITCH,
                                  merge_by_type=True)
    d_ayrik = ayrik.dump(concatenate=True)
    d_birlesik = birlesik.dump(concatenate=True)
    assert len(d_ayrik.faces) == len(d_birlesik.faces)
    assert np.allclose(d_ayrik.bounds, d_birlesik.bounds, atol=1e-6)


def test_merge_by_type_glb_gecerli():
    parts_by_id, placements = _make_typed_nesting()
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH,
                               merge_by_type=True)
    glb = scene_to_glb_bytes(scene)
    assert glb[:4] == b"glTF"


def test_max_faces_total_onizleme_sadelesir():
    """Ucgen butcesi asilirsa kanonik mesh'ler sadelesir (acilmis toplam
    ~butceye iner); butce verilmezse tam detay korunur."""
    parts = []
    for tip in ("kureA", "kureB"):
        for kopya in (1, 2, 3):
            mesh = trimesh.creation.icosphere(subdivisions=3, radius=5.0)  # 1280 yuz
            mesh.apply_translation(-mesh.bounds[0])
            vp = voxelize_part(tip, mesh, PITCH, n_orientations=1)
            vp.id = f"{tip}_{kopya}"
            parts.append(vp)
    placements, _ = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH))
    assert len(placements) == 6  # acilmis toplam = 6 x 1280 = 7680 ucgen

    tam = build_result_scene(placements, {p.id: p for p in parts},
                             pitch=PITCH, merge_by_type=True)
    onizleme = build_result_scene(placements, {p.id: p for p in parts},
                                  pitch=PITCH, merge_by_type=True,
                                  max_faces_total=2000)
    tam_yuz = {n: len(g.faces) for n, g in tam.geometry.items()}
    on_yuz = {n: len(g.faces) for n, g in onizleme.geometry.items()}
    # Sadelesme gerceklesti; tam detay korunmus durumda
    assert sum(on_yuz.values()) < sum(tam_yuz.values())
    for n in tam_yuz:
        assert on_yuz[n] < tam_yuz[n]
        assert on_yuz[n] >= 200  # asiri sadelesme freni


def test_merge_by_type_default_kapali_davranis_birebir():
    """Parametresiz cagri eski davranis: placement basina geometri."""
    parts_by_id, placements = _make_typed_nesting()
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    assert len(scene.geometry) == 4


def test_build_result_scene_single_part():
    """Works correctly with a single-part nesting result."""
    parts_by_id, placements = _make_nesting(1)
    scene = build_result_scene(placements, parts_by_id, pitch=PITCH)
    assert len(scene.geometry) == 1
    glb = scene_to_glb_bytes(scene)
    assert glb[:4] == b"glTF"


def test_build_result_scene_empty_placements():
    """Empty placement list must return an empty scene without error."""
    parts_by_id = {}
    scene = build_result_scene([], parts_by_id, pitch=PITCH)
    assert isinstance(scene, trimesh.Scene)
    assert len(scene.geometry) == 0
