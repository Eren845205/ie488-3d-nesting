"""Hoca feedback 2026-06-11 testleri: devoxelization + clearance + makine limitleri.

1. STL export ORİJİNAL mesh'ten gitmeli (display_mesh decimation kabartma
   yazıları siliyordu) — VoxelPart.mesh asla decimated kopya olmamalı.
2. Parça arası min 1 mm boşluk: margin dilation + clearance ölçümü.
3. Numune senaryo default'ları: taban 335x335, pitch 2.5, margin 1, max z 600.
"""

import argparse

import numpy as np
import pytest
import trimesh

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.clearance import min_clearance
from src.nesting3d.dblf import dblf
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.run3d import MAX_Z_MM, SCENARIO_DEFAULTS, resolve_params
from src.nesting3d.voxelize import expand_quantities, voxelize_part

PITCH = 5.0


def _box(w=20.0, d=20.0, h=20.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


def _sphere(r=10.0, subdivisions=3):
    s = trimesh.creation.icosphere(subdivisions=subdivisions, radius=r)
    s.apply_translation(-s.bounds[0])
    return s


# -- 1. devoxelization: export orijinal mesh'ten ----------------------------

def test_voxelpart_keeps_original_mesh_when_display_given():
    orig = _sphere(subdivisions=3)          # 1280 yüz
    display = _sphere(subdivisions=1)       # 80 yüz — "decimated" vekili
    vp = voxelize_part("s", orig, PITCH, n_orientations=1, display_mesh=display)
    assert vp.mesh is orig
    assert vp.display_mesh is display
    assert len(vp.mesh.faces) > len(vp.display_mesh.faces)


def test_expand_quantities_propagates_both_meshes():
    orig, display = _sphere(subdivisions=3), _sphere(subdivisions=1)
    parts = expand_quantities([("s", orig, 3, display)], PITCH, n_orientations=1)
    assert len(parts) == 3
    for p in parts:
        assert p.mesh is orig
        assert p.display_mesh is display


def test_placed_meshes_use_original_resolution():
    """Export edilen mesh'in yüz sayısı = orijinal (decimated değil)."""
    orig, display = _sphere(subdivisions=3), _sphere(subdivisions=1)
    parts = expand_quantities([("s", orig, 1, display)], PITCH, n_orientations=1)
    pl = [Placement3D(parts[0].id, "s", 0, 0, 0, 0)]
    out = placed_meshes(pl, {parts[0].id: parts[0]}, PITCH)
    assert len(out[0].faces) == len(orig.faces)


# -- 2. clearance ------------------------------------------------------------

def test_min_clearance_two_boxes_known_gap():
    a = _box()
    b = _box()
    b.apply_translation((23.0, 0, 0))  # x'te 3 mm boşluk
    rep = min_clearance([a, b], samples_per_mesh=4000, seed=1)
    assert rep.ok(1.0)
    assert rep.min_mm == pytest.approx(3.0, abs=0.3)
    assert rep.worst_pair == (0, 1)


def test_min_clearance_flags_violation():
    a = _box()
    b = _box()
    b.apply_translation((20.4, 0, 0))  # 0.4 mm — ihlal
    rep = min_clearance([a, b], samples_per_mesh=4000, seed=1)
    assert not rep.ok(1.0)
    assert rep.min_mm < 1.0


def test_min_clearance_skips_far_pairs():
    a = _box()
    b = _box()
    b.apply_translation((200.0, 0, 0))
    rep = min_clearance([a, b], aabb_pad_mm=15.0)
    assert rep.n_pairs_checked == 0
    assert rep.min_mm == float("inf")
    assert rep.ok(1.0)  # temas adayı yok = ihlal yok


def test_margin_dilation_guarantees_real_gap():
    """margin=1 ile DBLF'in yan yana koyduğu iki küpün GERÇEK mesafesi >= 1 mm.

    Garanti zinciri: konservatif grid (yüzey hücreleri işaretli) + yatay
    dilation 1 voxel -> yan yana hull'lar arası >= 2 boş hücre = 2 x pitch.
    """
    parts = expand_quantities(
        [("box", _box(), 2)], PITCH, n_orientations=1, margin=1, method="slice",
    )
    placements, bin3d = dblf(parts, lambda: Bin3D(100.0, 100.0, PITCH,
                                                  z_clearance=1))
    assert len(placements) == 2
    assert all(p.z == 0 for p in placements), "küpler yan yana sığmalıydı"
    meshes = placed_meshes(placements, {p.id: p for p in parts}, PITCH)
    rep = min_clearance(meshes, samples_per_mesh=4000, seed=1)
    assert rep.ok(1.0), f"margin=1 gerçek boşluğu sağlamadı: {rep.min_mm:.2f} mm"


def test_z_clearance_guarantees_vertical_gap():
    """Dar tabanda üst üste istiflenen iki küp arasında >= 1 hücre dikey boşluk.

    z_clearance tek taraflıdır: istif arayüzü başına maliyet 1 x pitch
    (çift taraflı z-dilation'ın yarısı) ama hull'lar konservatif olduğundan
    gerçek mesafe >= pitch >= 1 mm.
    """
    parts = expand_quantities(
        [("box", _box(), 2)], PITCH, n_orientations=1, margin=1, method="slice",
    )
    # 30 mm taban: dilated footprint (6 hücre = 30 mm) tek küp alır -> istif
    placements, bin3d = dblf(parts, lambda: Bin3D(30.0, 30.0, PITCH,
                                                  z_clearance=1))
    assert len(placements) == 2
    zs = sorted(p.z for p in placements)
    assert zs[0] == 0
    assert zs[1] >= 4 + 1  # küp 4 hücre + 1 hücre clearance
    meshes = placed_meshes(placements, {p.id: p for p in parts}, PITCH)
    rep = min_clearance(meshes, samples_per_mesh=4000, seed=1)
    assert rep.ok(1.0), f"dikey boşluk yetersiz: {rep.min_mm:.2f} mm"
    assert rep.min_mm == pytest.approx(PITCH, abs=0.6)


def test_slice_grid_covers_thin_features():
    """Pitch'ten ince duvar grid'de görünmeli (konservatif sarma).

    Merkez-içi slice testi tek başına 1 mm'lik fini ıskalar (hiçbir hücre
    merkezi fin içinde değil) -> collision koruması sıfır olur (2026-06-11
    kalibrasyonunda ölçülen 0.77 mm ihlalin kök nedeni).  _surface_cells
    birleşimi fin hücrelerini işaretlemeli.
    """
    body = _box(20, 20, 20)
    fin = trimesh.creation.box(extents=(1, 20, 20))
    fin.apply_translation((20.5, 10, 10))  # x: [20, 21] — gövdeye yapışık fin
    part = trimesh.util.concatenate([body, fin])
    vp = voxelize_part("finli", part, PITCH, n_orientations=1, method="slice")
    grid = vp.orientations[0].grid
    assert grid.shape[0] == 5  # ceil(21/5)
    assert grid[4, :, :].any(), "ince fin voxel grid'de görünmüyor"


# -- 3. makine parametreleri (hoca 2026-06-11) --------------------------------

def _args(**over):
    base = dict(plate=None, pitch=None, margin=None, voxel_method=None)
    base.update(over)
    return argparse.Namespace(**base)


def test_numune_scenario_defaults_match_hoca_machine():
    prm = resolve_params(_args(), "numune")
    assert prm == {"plate": 335.0, "pitch": 2.5, "margin": 1,
                   "voxel_method": "slice"}
    assert MAX_Z_MM == 600.0


def test_default_scenario_keeps_legacy_params():
    prm = resolve_params(_args(), "default")
    assert prm["plate"] == 220.0
    assert prm["pitch"] == pytest.approx(220.0 / 64)
    assert prm["margin"] == 0
    assert prm["voxel_method"] == "subdivide"


def test_cli_overrides_beat_scenario_defaults():
    prm = resolve_params(_args(plate=400.0, margin=2), "numune")
    assert prm["plate"] == 400.0
    assert prm["margin"] == 2
    assert prm["pitch"] == 2.5  # verilmeyen alanlar senaryo default'unda kalır


def test_numune_largest_part_fits_new_plate():
    """n4 = 304.8 mm — 335 mm tabana sığmalı (350'den küçülmenin ön şartı)."""
    assert 304.8 + 2 * SCENARIO_DEFAULTS["numune"]["pitch"] < 335.0


def test_allowed_orientations_restrict_poses():
    """Poz kısıtı: dikdörtgen prizma yalnız yatay pozlarda kalmalı.

    Plaka vekili 40x30x5: dik pozlarda z-yüksekliği 30 veya 40 olur;
    (0,1,4,5) kısıtı tüm pozlarda z = 5 garanti etmeli (dik plaka yasağı).
    """
    plate_like = trimesh.creation.box(extents=(40, 30, 5))
    plate_like.apply_translation(-plate_like.bounds[0])
    vp = voxelize_part("plk", plate_like, PITCH, n_orientations=4,
                       allowed_orientations=(0, 1, 4, 5), method="slice")
    assert len(vp.orientations) == 4
    for o in vp.orientations:
        assert o.shape[2] == 1  # 5 mm / pitch 5 = 1 hücre — hep yatay


def test_expand_quantities_orientation_overrides():
    box = _box()
    parts = expand_quantities(
        [("plk", box, 1), ("serbest", box, 1)], PITCH, n_orientations=4,
        orientation_overrides={"plk": (0, 1)},
    )
    by_name = {p.name: p for p in parts}
    assert len(by_name["plk"].orientations) == 2
    assert len(by_name["serbest"].orientations) == 4
