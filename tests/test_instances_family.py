"""test_instances_family.py — F1 aile taksonomisi (classify_family) testleri.

Tüm sentetik parçalar hızlı/deterministik üretilir (dev STL yok).
"""

from __future__ import annotations

import trimesh

from src.nesting3d.instances.family import (
    FAMILY_NAMES,
    LONG_ROD,
    MIXED_SCALE,
    SOLID_BULK,
    THIN_PLATE,
    THIN_SHELL,
    TUBE,
    UNKNOWN,
    classify_confirmed,
    classify_family,
    classify_prelim,
)
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.synthetic import (
    hollow_tubes,
    long_rods,
    random_boxes,
    shell_bells,
    thin_plates,
)


# ---------------------------------------------------------------------------
# Sentetik aile -> beklenen etiket (kapılar)
# ---------------------------------------------------------------------------

class TestSyntheticFamilyGates:
    def test_shell_bells_is_thin_shell(self):
        inst = shell_bells(n_parts=6, seed=0)
        fam, conf = classify_family(inst)
        assert fam == THIN_SHELL
        assert conf > 0.5

    def test_hollow_tubes_is_tube(self):
        inst = hollow_tubes(n_parts=6, seed=0)
        fam, conf = classify_family(inst)
        assert fam == TUBE
        assert conf > 0.5

    def test_thin_plates_is_thin_plate(self):
        inst = thin_plates(n_parts=8, xy_min=80.0, xy_max=150.0,
                           thickness_min=2.0, thickness_max=6.0, seed=0)
        fam, conf = classify_family(inst)
        assert fam == THIN_PLATE
        assert conf > 0.5

    def test_long_rods_is_long_rod(self):
        inst = long_rods(n_parts=8, cross_min=5.0, cross_max=12.0,
                         length_min=150.0, length_max=250.0, seed=0)
        fam, conf = classify_family(inst)
        assert fam == LONG_ROD
        assert conf > 0.5

    def test_random_boxes_is_solid_bulk(self):
        inst = random_boxes(n_parts=10, min_dim=45.0, max_dim=80.0, seed=0)
        fam, conf = classify_family(inst)
        assert fam == SOLID_BULK
        assert conf > 0.5


# ---------------------------------------------------------------------------
# Belirsiz / ölçülemeyen -> unknown (satılabilirlik çekirdeği)
# ---------------------------------------------------------------------------

class TestUnknownFallback:
    def test_broken_nonwatertight_cube_is_unknown(self):
        """Watertight-olmayan kübik mesh -> wall_mm None -> unknown."""
        m = trimesh.creation.box(extents=(20.0, 20.0, 20.0))
        open_mesh = trimesh.Trimesh(
            vertices=m.vertices, faces=m.faces[:-2], process=False
        )
        assert not open_mesh.is_watertight
        stl = open_mesh.export(file_type="stl")

        result = build_instance_from_order({"kirik": stl}, {"kirik": 1})
        assert len(result.instance.parts) == 1
        part = result.instance.parts[0]
        assert part.wall_mm is None
        assert part.true_fill is None

        fam, conf = classify_family(result.instance)
        assert fam == UNKNOWN
        assert 0.0 <= conf <= 1.0

    def test_empty_instance_is_unknown(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        fam, conf = classify_family(inst)
        assert fam == UNKNOWN
        assert conf == 0.0

    def test_unmeasured_cube_part_is_unknown(self):
        """stl-source, ölçüm yok, kübik bbox -> belirsiz -> unknown."""
        part = PartSpec(id="x", name="x", qty=1, source="stl",
                        stl_path="x.stl", width_mm=20.0, depth_mm=22.0,
                        height_mm=18.0)  # wall/true_fill None
        fam, conf = classify_family([part])
        assert fam == UNKNOWN


# ---------------------------------------------------------------------------
# API sözleşmesi
# ---------------------------------------------------------------------------

class TestApiContract:
    def test_confidence_in_unit_range_all_families(self):
        for builder in (
            lambda: shell_bells(n_parts=4, seed=1),
            lambda: hollow_tubes(n_parts=4, seed=1),
            lambda: thin_plates(n_parts=4, xy_min=80.0, xy_max=150.0,
                                thickness_min=2.0, thickness_max=6.0, seed=1),
            lambda: long_rods(n_parts=4, cross_min=5.0, cross_max=12.0,
                              length_min=150.0, length_max=250.0, seed=1),
            lambda: random_boxes(n_parts=4, min_dim=45.0, max_dim=80.0, seed=1),
        ):
            fam, conf = classify_family(builder())
            assert fam in FAMILY_NAMES
            assert 0.0 <= conf <= 1.0

    def test_accepts_instance_and_part_list(self):
        inst = random_boxes(n_parts=5, min_dim=45.0, max_dim=80.0, seed=0)
        fam_inst, _ = classify_family(inst)
        fam_list, _ = classify_family(inst.parts)
        assert fam_inst == fam_list

    def test_classify_prelim_alias_of_classify_family(self):
        inst = shell_bells(n_parts=4, seed=2)
        assert classify_family(inst) == classify_prelim(inst)

    def test_deterministic(self):
        inst = hollow_tubes(n_parts=5, seed=7)
        assert classify_family(inst) == classify_family(inst)


# ---------------------------------------------------------------------------
# classify_confirmed — voxel-sonrası rafinasyon (saf fonksiyon)
# ---------------------------------------------------------------------------

class TestClassifyConfirmed:
    def test_none_voxel_fill_passthrough(self):
        prelim = (SOLID_BULK, 0.7)
        assert classify_confirmed(prelim, None) == prelim

    def test_solid_prelim_but_hollow_voxel_becomes_shell(self):
        fam, conf = classify_confirmed((SOLID_BULK, 0.6), voxel_fill=0.1)
        assert fam == THIN_SHELL
        assert 0.0 <= conf <= 1.0

    def test_unknown_prelim_but_hollow_voxel_becomes_shell(self):
        fam, _ = classify_confirmed((UNKNOWN, 0.3), voxel_fill=0.2)
        assert fam == THIN_SHELL

    def test_shell_prelim_but_solid_voxel_becomes_bulk(self):
        fam, _ = classify_confirmed((THIN_SHELL, 0.8), voxel_fill=0.9)
        assert fam == SOLID_BULK

    def test_tube_prelim_but_solid_voxel_becomes_bulk(self):
        fam, _ = classify_confirmed((TUBE, 0.8), voxel_fill=0.85)
        assert fam == SOLID_BULK

    def test_shell_prelim_hollow_voxel_confidence_boost(self):
        _, conf0 = (THIN_SHELL, 0.7)
        fam, conf = classify_confirmed((THIN_SHELL, 0.7), voxel_fill=0.1)
        assert fam == THIN_SHELL
        assert conf >= conf0

    def test_shape_decisive_families_unchanged_by_hollow(self):
        # thin_plate şekil-kesin: hollow voxel bile aileyi değiştirmemeli
        fam, _ = classify_confirmed((THIN_PLATE, 0.8), voxel_fill=0.2)
        assert fam == THIN_PLATE
