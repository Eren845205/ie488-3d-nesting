"""Tests for src.nesting3d.instances.format (PLAN_DEMO1.md 2.1 + 2.4)."""

import json
import tempfile
from pathlib import Path

import pytest

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
    to_voxel_parts,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=200.0, depth_mm=200.0, height_mm=None),
        parts=[
            PartSpec(
                id="box_01", name="box_01", qty=2,
                source="box", width_mm=20.0, depth_mm=15.0, height_mm=10.0,
            ),
            PartSpec(
                id="box_02", name="box_02", qty=1,
                source="box", width_mm=50.0, depth_mm=30.0, height_mm=25.0,
            ),
        ],
        meta={"test": True},
    )


# ---------------------------------------------------------------------------
# ContainerSpec
# ---------------------------------------------------------------------------

class TestContainerSpec:
    def test_round_trip_dict(self):
        c = ContainerSpec(width_mm=300.0, depth_mm=200.0, height_mm=150.0)
        assert ContainerSpec.from_dict(c.to_dict()) == c

    def test_round_trip_open_dimension(self):
        c = ContainerSpec(width_mm=300.0, depth_mm=200.0, height_mm=None)
        restored = ContainerSpec.from_dict(c.to_dict())
        assert restored.height_mm is None
        assert restored.width_mm == 300.0

    def test_dict_keys(self):
        d = ContainerSpec(width_mm=10.0, depth_mm=20.0, height_mm=30.0).to_dict()
        assert set(d.keys()) == {"width_mm", "depth_mm", "height_mm"}


# ---------------------------------------------------------------------------
# PartSpec
# ---------------------------------------------------------------------------

class TestPartSpec:
    def test_box_round_trip(self):
        p = PartSpec(
            id="p1", name="cube", qty=3, source="box",
            width_mm=10.0, depth_mm=10.0, height_mm=10.0,
        )
        assert PartSpec.from_dict(p.to_dict()) == p

    def test_stl_round_trip(self):
        p = PartSpec(
            id="p2", name="bracket", qty=1, source="stl",
            stl_path="/some/path/bracket.stl",
        )
        restored = PartSpec.from_dict(p.to_dict())
        assert restored.stl_path == "/some/path/bracket.stl"
        assert restored.width_mm is None

    def test_box_dict_has_no_stl_path(self):
        p = PartSpec(id="p3", name="x", qty=1, source="box",
                     width_mm=5.0, depth_mm=5.0, height_mm=5.0)
        d = p.to_dict()
        assert "stl_path" not in d
        assert "width_mm" in d

    def test_stl_dict_has_no_box_dims(self):
        p = PartSpec(id="p4", name="x", qty=1, source="stl", stl_path="a.stl")
        d = p.to_dict()
        assert "stl_path" in d
        assert "width_mm" not in d


# ---------------------------------------------------------------------------
# NestingInstance — JSON round-trip
# ---------------------------------------------------------------------------

class TestNestingInstanceJSON:
    def test_to_dict_structure(self):
        inst = _simple_instance()
        d = inst.to_dict()
        assert "version" in d
        assert "container" in d
        assert "parts" in d
        assert len(d["parts"]) == 2

    def test_round_trip_dict(self):
        inst = _simple_instance()
        restored = NestingInstance.from_dict(inst.to_dict())
        assert restored.container.width_mm == 200.0
        assert len(restored.parts) == 2
        assert restored.parts[0].qty == 2
        assert restored.meta == {"test": True}

    def test_round_trip_json_file(self, tmp_path):
        inst = _simple_instance()
        p = tmp_path / "test_instance.json"
        inst.to_json(p)
        restored = NestingInstance.from_json(p)
        assert restored.container == inst.container
        assert len(restored.parts) == len(inst.parts)
        assert restored.parts[1].height_mm == 25.0

    def test_json_is_valid_json(self, tmp_path):
        inst = _simple_instance()
        p = tmp_path / "inst.json"
        inst.to_json(p)
        # Must parse without error
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert raw["version"] == "1.0"

    def test_version_field(self):
        inst = _simple_instance()
        assert inst.version == "1.0"
        d = inst.to_dict()
        assert d["version"] == "1.0"

    def test_meta_preserved(self):
        inst = _simple_instance()
        inst.meta["extra"] = 42
        restored = NestingInstance.from_dict(inst.to_dict())
        assert restored.meta["extra"] == 42

    def test_open_dimension_preserved_in_json(self, tmp_path):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None),
            parts=[
                PartSpec(id="b", name="b", qty=1, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0)
            ],
        )
        p = tmp_path / "open.json"
        inst.to_json(p)
        restored = NestingInstance.from_json(p)
        assert restored.container.height_mm is None


# ---------------------------------------------------------------------------
# to_voxel_parts — 2.4 kabulü: 20mm kutu @ pitch=5 -> 64 voxel
# ---------------------------------------------------------------------------

class TestToVoxelParts:
    def test_20mm_box_at_pitch5_is_64_voxels(self):
        """Plan 2.4 kabul kriteri: 20mm kutu @ pitch=5 -> 64 voxel (slice method).

        slice method: ceil(20/5) = 4 per side -> 4*4*4 = 64.
        subdivide method does not satisfy this criterion (surface voxels -> 5x5x5=125).
        """
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
            parts=[
                PartSpec(id="cube", name="cube", qty=1, source="box",
                         width_mm=20.0, depth_mm=20.0, height_mm=20.0)
            ],
        )
        vp_list = to_voxel_parts(inst, pitch=5.0, n_orientations=1, method="slice")
        assert len(vp_list) == 1
        # 20/5 = 4 voxel per side -> 4*4*4 = 64
        assert vp_list[0].volume_voxels == 64

    def test_qty_expansion(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="p", name="cube", qty=5, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0)
            ],
        )
        parts = to_voxel_parts(inst, pitch=5.0, n_orientations=1)
        assert len(parts) == 5

    def test_multiple_models(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
            parts=[
                PartSpec(id="a", name="a", qty=2, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0),
                PartSpec(id="b", name="b", qty=3, source="box",
                         width_mm=20.0, depth_mm=10.0, height_mm=10.0),
            ],
        )
        parts = to_voxel_parts(inst, pitch=5.0, n_orientations=1)
        assert len(parts) == 5  # 2 + 3

    def test_part_ids_are_unique(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="x", name="x", qty=4, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0)
            ],
        )
        parts = to_voxel_parts(inst, pitch=5.0, n_orientations=1)
        ids = [p.id for p in parts]
        assert len(set(ids)) == 4

    def test_unknown_source_raises(self):
        part = PartSpec(id="bad", name="bad", qty=1, source="unknown")
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
            parts=[part],
        )
        with pytest.raises(ValueError, match="bilinmeyen source"):
            to_voxel_parts(inst, pitch=5.0)


# ---------------------------------------------------------------------------
# F8 — from_dict eksik alan hata mesajları
# ---------------------------------------------------------------------------

class TestFromDictMissingFieldErrors:
    def test_partspec_missing_required_field_raises_valueerror(self):
        """Eksik 'qty' alanı KeyError değil ValueError fırlatmalı."""
        bad = {"id": "p1", "name": "cube", "source": "box",
               "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0}
        with pytest.raises(ValueError, match="qty"):
            PartSpec.from_dict(bad)

    def test_partspec_missing_id_mentions_field_name(self):
        """Eksik 'id' alanı hata mesajında alan adını içermeli."""
        bad = {"name": "cube", "qty": 1, "source": "box",
               "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0}
        with pytest.raises(ValueError, match="id"):
            PartSpec.from_dict(bad)

    def test_nestinginstance_missing_parts_raises_valueerror(self):
        """'parts' anahtarı eksik olduğunda ValueError fırlatmalı."""
        bad = {"version": "1.0",
               "container": {"width_mm": 100.0, "depth_mm": 100.0, "height_mm": None}}
        with pytest.raises(ValueError, match="parts"):
            NestingInstance.from_dict(bad)

    def test_nestinginstance_bad_part_reports_index(self):
        """İkinci parçada eksik alan olduğunda hata mesajı indeksi (parts[1]) içermeli."""
        d = {
            "version": "1.0",
            "container": {"width_mm": 100.0, "depth_mm": 100.0, "height_mm": None},
            "parts": [
                {"id": "ok", "name": "ok", "qty": 1, "source": "box",
                 "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0},
                {"name": "broken", "source": "box"},  # id ve qty eksik
            ],
        }
        with pytest.raises(ValueError, match=r"parts\[1\]"):
            NestingInstance.from_dict(d)
