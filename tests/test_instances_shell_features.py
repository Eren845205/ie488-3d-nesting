"""test_instances_shell_features.py — F1 PartSpec alanları + loader ölçümü +
uzatılmış özellikler (wall_est/true_fill_mean/shell_score).
"""

from __future__ import annotations

import pytest
import trimesh

from src.nesting3d.instances.features import (
    EXTENDED_FEATURE_NAMES,
    FAMILY_FEATURE_NAMES,
    FEATURE_NAMES,
    FULL_FEATURE_NAMES,
    M5_FEATURE_NAMES,
    extract_family_features,
    extract_features,
    extract_features_extended,
    extract_features_full,
    extract_m5_features,
)
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.synthetic import (
    hollow_tubes,
    random_boxes,
    shell_bells,
)


def _tube_stl(r_out=10.0, wall=1.5, length=80.0) -> bytes:
    m = trimesh.creation.annulus(r_min=r_out - wall, r_max=r_out, height=length)
    return m.export(file_type="stl")


# ---------------------------------------------------------------------------
# PartSpec — yeni opsiyonel alanlar, geriye uyumlu round-trip
# ---------------------------------------------------------------------------

class TestPartSpecNewFields:
    def test_shell_fields_round_trip(self):
        p = PartSpec(id="s", name="s", qty=1, source="box",
                     width_mm=60.0, depth_mm=60.0, height_mm=30.0,
                     wall_mm=1.4, family="thin_shell", true_fill=0.07)
        restored = PartSpec.from_dict(p.to_dict())
        assert restored == p

    def test_old_dict_without_new_fields_still_loads(self):
        """F1 öncesi kaydedilmiş dict (yeni alanlar yok) kırılmadan okunur."""
        old = {"id": "p1", "name": "cube", "qty": 3, "source": "box",
               "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0}
        restored = PartSpec.from_dict(old)
        assert restored.wall_mm is None
        assert restored.family is None
        assert restored.true_fill is None

    def test_box_dict_omits_none_shell_fields(self):
        p = PartSpec(id="p", name="x", qty=1, source="box",
                     width_mm=5.0, depth_mm=5.0, height_mm=5.0)
        d = p.to_dict()
        assert "wall_mm" not in d
        assert "family" not in d
        assert "true_fill" not in d

    def test_shell_fields_written_only_when_set(self):
        p = PartSpec(id="p", name="x", qty=1, source="box",
                     width_mm=5.0, depth_mm=5.0, height_mm=5.0,
                     true_fill=0.3)
        d = p.to_dict()
        assert d["true_fill"] == 0.3
        assert "wall_mm" not in d


# ---------------------------------------------------------------------------
# Loader — hacim/yüzey ölçümü -> wall_mm / true_fill
# ---------------------------------------------------------------------------

class TestLoaderMeasurement:
    def test_solid_box_true_fill_near_one_wall_none(self):
        m = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
        stl = m.export(file_type="stl")
        result = build_instance_from_order({"kutu": stl}, {"kutu": 1})
        part = result.instance.parts[0]
        assert part.true_fill is not None
        assert abs(part.true_fill - 1.0) < 0.02
        assert part.wall_mm is None  # kati -> shell değil

    def test_hollow_tube_low_true_fill_and_wall(self):
        result = build_instance_from_order({"boru": _tube_stl()}, {"boru": 1})
        part = result.instance.parts[0]
        assert part.true_fill is not None
        assert part.true_fill < 0.5
        assert part.wall_mm is not None
        assert abs(part.wall_mm - 1.5) < 0.4  # 2V/A ~ cidar

    def test_measurement_does_not_break_existing_bbox(self):
        m = trimesh.creation.box(extents=(10.0, 20.0, 30.0))
        stl = m.export(file_type="stl")
        result = build_instance_from_order({"kutu": stl}, {"kutu": 2})
        part = result.instance.parts[0]
        dims = sorted([part.width_mm, part.depth_mm, part.height_mm])
        for actual, exp in zip(dims, [10.0, 20.0, 30.0]):
            assert abs(actual - exp) < 1.0
        assert part.qty == 2


# ---------------------------------------------------------------------------
# extract_features — DONMUŞ 20-vektör sözleşmesi korunur (regresyon)
# ---------------------------------------------------------------------------

class TestBaseVectorFrozen:
    def test_base_feature_names_still_20(self):
        assert len(FEATURE_NAMES) == 20

    def test_base_vector_length_20(self):
        inst = random_boxes(n_parts=5, seed=0)
        fv = extract_features(inst)
        assert len(fv.values) == 20

    def test_extended_prefix_equals_base(self):
        inst = random_boxes(n_parts=6, seed=3)
        base = extract_features(inst)
        ext = extract_features_extended(inst)
        assert ext.values[:20] == base.values


# ---------------------------------------------------------------------------
# Uzatılmış aile özellikleri
# ---------------------------------------------------------------------------

class TestFamilyFeatures:
    def test_extended_names_count_23(self):
        assert len(EXTENDED_FEATURE_NAMES) == 23
        assert EXTENDED_FEATURE_NAMES[20:] == FAMILY_FEATURE_NAMES

    def test_family_feature_keys(self):
        inst = random_boxes(n_parts=4, seed=0)
        d = extract_family_features(inst)
        assert set(d.keys()) == {"wall_est", "true_fill_mean", "shell_score"}

    def test_solid_boxes_shell_score_zero(self):
        inst = random_boxes(n_parts=8, min_dim=40.0, max_dim=80.0, seed=0)
        d = extract_family_features(inst)
        assert d["shell_score"] == 0.0
        assert d["wall_est"] == 0.0
        assert abs(d["true_fill_mean"] - 1.0) < 1e-9

    def test_shell_bells_high_shell_score(self):
        inst = shell_bells(n_parts=6, seed=0)
        d = extract_family_features(inst)
        assert d["shell_score"] > 0.5
        assert d["wall_est"] > 0.0
        assert d["true_fill_mean"] < 0.5

    def test_hollow_tubes_positive_shell_signals(self):
        inst = hollow_tubes(n_parts=6, seed=0)
        d = extract_family_features(inst)
        assert d["shell_score"] > 0.0
        assert d["wall_est"] > 0.0
        assert d["true_fill_mean"] < 0.5

    def test_extended_values_all_finite(self):
        import math
        inst = shell_bells(n_parts=4, seed=1)
        ext = extract_features_extended(inst)
        for v in ext.values:
            assert math.isfinite(v)

    def test_deterministic(self):
        inst = shell_bells(n_parts=5, seed=9)
        assert extract_family_features(inst) == extract_family_features(inst)


# ---------------------------------------------------------------------------
# M5 özellik ekleri (plaka_asan_ratio / log_n_total / solidity_proxy)
# STRATEJI/ML_YENIDEN_YAPILANMA_PLANI_2026-08-18 §3.2/§6 M5 — ADDITIVE
# ---------------------------------------------------------------------------

class TestM5FrozenVectorsUnaffected:
    """M5 eklerinin 20-temel ve 23-uzatılmış vektörleri BOZMADIĞI regresyonu."""

    def test_base_still_20_after_m5_addition(self):
        assert len(FEATURE_NAMES) == 20

    def test_extended_still_23_after_m5_addition(self):
        assert len(EXTENDED_FEATURE_NAMES) == 23

    def test_full_prefix_equals_extended(self):
        inst = random_boxes(n_parts=6, seed=3)
        ext = extract_features_extended(inst)
        full = extract_features_full(inst)
        assert full.values[:23] == ext.values

    def test_full_prefix_equals_base(self):
        inst = random_boxes(n_parts=5, seed=1)
        base = extract_features(inst)
        full = extract_features_full(inst)
        assert full.values[:20] == base.values


class TestM5FeatureNames:
    def test_m5_names_count_3(self):
        assert len(M5_FEATURE_NAMES) == 3
        assert M5_FEATURE_NAMES == [
            "plaka_asan_ratio", "log_n_total", "solidity_proxy",
        ]

    def test_full_names_count_26(self):
        assert len(FULL_FEATURE_NAMES) == 26
        assert FULL_FEATURE_NAMES[23:] == M5_FEATURE_NAMES

    def test_no_duplicates_in_full_names(self):
        assert len(set(FULL_FEATURE_NAMES)) == len(FULL_FEATURE_NAMES)

    def test_m5_feature_keys(self):
        inst = random_boxes(n_parts=4, seed=0)
        d = extract_m5_features(inst)
        assert set(d.keys()) == {
            "plaka_asan_ratio", "log_n_total", "solidity_proxy",
        }

    def test_full_values_all_finite(self):
        import math
        inst = shell_bells(n_parts=4, seed=1)
        full = extract_features_full(inst)
        for v in full.values:
            assert math.isfinite(v)

    def test_deterministic(self):
        inst = random_boxes(n_parts=5, seed=7)
        assert extract_m5_features(inst) == extract_m5_features(inst)


class TestPlakaAsanRatio:
    def test_all_parts_fit_ratio_zero(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
            parts=[
                PartSpec(id="p", name="p", qty=5, source="box",
                         width_mm=50.0, depth_mm=40.0, height_mm=30.0),
            ],
        )
        d = extract_m5_features(inst)
        assert d["plaka_asan_ratio"] == 0.0

    def test_oversized_rod_ratio_one(self):
        """Konteynerden büyük çubuk (buyuk+orta ikisi de sığmıyor) -> oran 1.0."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
            parts=[
                PartSpec(id="rod", name="rod", qty=3, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=500.0),
            ],
        )
        d = extract_m5_features(inst)
        # dims sorted: (10, 10, 500) -> orta=10, buyuk=500; 500 > 100 (pw) ve
        # 500 > 100 (pd) -> hicbir eksende sigmiyor -> asan
        assert d["plaka_asan_ratio"] == 1.0

    def test_mixed_qty_weighted_ratio(self):
        """3 sigan + 2 asan (qty agirlikli) -> oran 2/5."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
            parts=[
                PartSpec(id="fit", name="fit", qty=3, source="box",
                         width_mm=20.0, depth_mm=20.0, height_mm=20.0),
                PartSpec(id="over", name="over", qty=2, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=500.0),
            ],
        )
        d = extract_m5_features(inst)
        assert d["plaka_asan_ratio"] == pytest.approx(2.0 / 5.0)

    def test_diagonal_fit_not_flagged_as_oversized(self):
        """buyuk<=pd ve orta<=pw eksen-hizali kombinasyonuyla sigan parca asan sayilmaz."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=50.0, depth_mm=200.0),
            parts=[
                PartSpec(id="p", name="p", qty=1, source="box",
                         width_mm=40.0, depth_mm=150.0, height_mm=10.0),
            ],
        )
        d = extract_m5_features(inst)
        # dims sorted: (10, 40, 150) -> orta=40, buyuk=150
        # (150<=pw=50? no) and (150<=pd=200 and 40<=pw=50) -> True -> sigar
        assert d["plaka_asan_ratio"] == 0.0

    def test_missing_container_dims_returns_zero(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=0.0, depth_mm=0.0),
            parts=[
                PartSpec(id="rod", name="rod", qty=1, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=500.0),
            ],
        )
        d = extract_m5_features(inst)
        assert d["plaka_asan_ratio"] == 0.0

    def test_empty_instance_ratio_zero(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        d = extract_m5_features(inst)
        assert d["plaka_asan_ratio"] == 0.0


class TestLogNTotal:
    def test_zero_parts_log_zero(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        d = extract_m5_features(inst)
        assert d["log_n_total"] == pytest.approx(0.0, abs=1e-9)  # log10(1+0)=0

    def test_known_value_9_parts(self):
        import math
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="p", name="p", qty=9, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0),
            ],
        )
        d = extract_m5_features(inst)
        assert d["log_n_total"] == pytest.approx(math.log10(10.0))  # log10(1+9)=1.0

    def test_monotonic_with_more_parts(self):
        small = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[PartSpec(id="p", name="p", qty=5, source="box",
                            width_mm=10.0, depth_mm=10.0, height_mm=10.0)],
        )
        large = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[PartSpec(id="p", name="p", qty=500, source="box",
                            width_mm=10.0, depth_mm=10.0, height_mm=10.0)],
        )
        d_small = extract_m5_features(small)["log_n_total"]
        d_large = extract_m5_features(large)["log_n_total"]
        assert d_large > d_small


class TestSolidityProxy:
    def test_solid_box_solidity_near_one(self):
        inst = random_boxes(n_parts=6, min_dim=40.0, max_dim=80.0, seed=0)
        d = extract_m5_features(inst)
        assert abs(d["solidity_proxy"] - 1.0) < 1e-9

    def test_matches_true_fill_mean_family_feature(self):
        """solidity_proxy = FAMILY grubundaki true_fill_mean ile birebir (ayni tanim)."""
        inst = shell_bells(n_parts=6, seed=0)
        fam = extract_family_features(inst)
        m5 = extract_m5_features(inst)
        assert m5["solidity_proxy"] == pytest.approx(fam["true_fill_mean"])

    def test_hollow_tubes_low_solidity(self):
        inst = hollow_tubes(n_parts=6, seed=0)
        d = extract_m5_features(inst)
        assert d["solidity_proxy"] < 0.5

    def test_solidity_uses_measured_true_fill_field(self):
        """PartSpec.true_fill dolu geldiginde solidity_proxy onu kullanir (ham
        hacim alani yok; K-62 delikli parca sinyali icin var olan alan yeterli)."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="hollow", name="hollow", qty=4, source="box",
                         width_mm=20.0, depth_mm=20.0, height_mm=20.0,
                         true_fill=0.1),
            ],
        )
        d = extract_m5_features(inst)
        assert d["solidity_proxy"] == pytest.approx(0.1)
