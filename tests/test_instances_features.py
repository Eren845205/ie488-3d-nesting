"""Tests for src.nesting3d.instances.features (PLAN_DEMO1.md 2.8)."""

import math

import pytest

from src.nesting3d.instances.features import (
    FEATURE_NAMES,
    FeatureVector,
    extract_features,
)
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.synthetic import (
    few_large_many_small,
    high_qty_repeat,
    long_rods,
    random_boxes,
    thin_plates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inst_one_box(w=20.0, d=20.0, h=20.0, qty=1) -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
        parts=[PartSpec(id="b", name="b", qty=qty, source="box",
                        width_mm=w, depth_mm=d, height_mm=h)],
    )


def _inst_mixed() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
        parts=[
            PartSpec(id="p1", name="p1", qty=2, source="box",
                     width_mm=10.0, depth_mm=10.0, height_mm=10.0),
            PartSpec(id="p2", name="p2", qty=3, source="box",
                     width_mm=50.0, depth_mm=40.0, height_mm=30.0),
            PartSpec(id="p3", name="p3", qty=1, source="box",
                     width_mm=80.0, depth_mm=5.0, height_mm=3.0),   # thin plate
        ],
    )


# ---------------------------------------------------------------------------
# FEATURE_NAMES sabitleri
# ---------------------------------------------------------------------------

class TestFeatureNames:
    def test_count_is_20(self):
        assert len(FEATURE_NAMES) == 20

    def test_no_duplicates(self):
        assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)

    def test_known_names_present(self):
        for name in ("n_distinct_parts", "n_total_parts", "repeat_part_ratio",
                     "mean_volume_norm", "thin_plate_ratio", "long_rod_ratio",
                     "fill_lb", "cv_volume"):
            assert name in FEATURE_NAMES


# ---------------------------------------------------------------------------
# extract_features — temel
# ---------------------------------------------------------------------------

class TestExtractFeaturesBasic:
    def test_returns_feature_vector(self):
        fv = extract_features(_inst_one_box())
        assert isinstance(fv, FeatureVector)

    def test_values_length_matches_names(self):
        fv = extract_features(_inst_one_box())
        assert len(fv.values) == len(FEATURE_NAMES)

    def test_all_floats(self):
        fv = extract_features(_inst_one_box())
        for v in fv.values:
            assert isinstance(v, float)

    def test_no_nan_or_inf(self):
        fv = extract_features(_inst_mixed())
        for v in fv.values:
            assert math.isfinite(v), f"Non-finite value in features: {v}"

    def test_to_dict_keys_match_names(self):
        fv = extract_features(_inst_one_box())
        d = fv.to_dict()
        assert set(d.keys()) == set(FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Determinizm
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_instance_same_features(self):
        inst = random_boxes(n_parts=8, seed=42)
        fv1 = extract_features(inst)
        fv2 = extract_features(inst)
        assert fv1.values == fv2.values

    def test_different_instances_different_features(self):
        a = extract_features(random_boxes(n_parts=8, seed=1))
        b = extract_features(random_boxes(n_parts=8, seed=2))
        assert a.values != b.values


# ---------------------------------------------------------------------------
# Parça sayısı özellikleri
# ---------------------------------------------------------------------------

class TestPartCountFeatures:
    def test_n_distinct_parts(self):
        inst = _inst_mixed()
        fv = extract_features(inst)
        assert fv.to_dict()["n_distinct_parts"] == 3.0

    def test_n_total_parts(self):
        inst = _inst_mixed()  # qty: 2+3+1 = 6
        fv = extract_features(inst)
        assert fv.to_dict()["n_total_parts"] == 6.0

    def test_repeat_part_ratio_zero_when_all_unique(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0)
                for i in range(5)
            ],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["repeat_part_ratio"] == 0.0

    def test_repeat_part_ratio_high_when_few_models_many_parts(self):
        inst = high_qty_repeat(n_models=2, qty_per_model=20, seed=0)
        fv = extract_features(inst)
        # 2 model, 40 parça -> ratio = 1 - 2/40 = 0.95
        assert fv.to_dict()["repeat_part_ratio"] == pytest.approx(1.0 - 2.0 / 40.0)


# ---------------------------------------------------------------------------
# Hacim özellikleri
# ---------------------------------------------------------------------------

class TestVolumeFeatures:
    def test_single_box_volume_norm(self):
        # konteyner: 200x200xNone (open-dim)
        # parça: 10x20x5=1000 mm^3; open-dim cont_vol = 200*200*max(1000/40000, 1.0) = 40000
        inst = _inst_one_box(w=10.0, d=20.0, h=5.0)
        fv = extract_features(inst)
        part_vol = 10.0 * 20.0 * 5.0       # 1000
        cont_vol = 200.0 * 200.0 * 1.0     # 40000  (min_height<1 -> 1.0 kullanılır)
        expected_norm = part_vol / cont_vol  # 0.025
        assert fv.to_dict()["mean_volume_norm"] == pytest.approx(expected_norm, rel=1e-6)

    def test_cv_volume_zero_for_identical_parts(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="a", name="a", qty=5, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0)
            ],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["cv_volume"] == pytest.approx(0.0, abs=1e-9)

    def test_volume_ratio_gte_one(self):
        fv = extract_features(_inst_mixed())
        assert fv.to_dict()["volume_ratio"] >= 1.0

    def test_max_vol_norm_ge_min_vol_norm(self):
        fv = extract_features(_inst_mixed())
        d = fv.to_dict()
        assert d["max_volume_norm"] >= d["min_volume_norm"]


# ---------------------------------------------------------------------------
# Aspect oranı özellikleri
# ---------------------------------------------------------------------------

class TestAspectFeatures:
    def test_cube_aspect_z_near_one(self):
        inst = _inst_one_box(w=20.0, d=20.0, h=20.0)
        fv = extract_features(inst)
        assert fv.to_dict()["mean_aspect_z"] == pytest.approx(1.0, abs=1e-6)

    def test_plate_aspect_z_high(self):
        # 100 x 100 x 5 mm plaka
        inst = _inst_one_box(w=100.0, d=100.0, h=5.0)
        fv = extract_features(inst)
        assert fv.to_dict()["mean_aspect_z"] > 5.0


# ---------------------------------------------------------------------------
# Parça tipi oranları
# ---------------------------------------------------------------------------

class TestPartTypeRatios:
    def test_thin_plate_ratio_for_pure_plates(self):
        # Tüm parçalar ince plaka (h/max < 0.15)
        inst = NestingInstance(
            container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
            parts=[
                PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                         width_mm=100.0, depth_mm=80.0, height_mm=4.0)
                for i in range(5)
            ],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["thin_plate_ratio"] == pytest.approx(1.0)

    def test_thin_plate_ratio_zero_for_cubes(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id=f"c{i}", name=f"c{i}", qty=1, source="box",
                         width_mm=20.0, depth_mm=20.0, height_mm=20.0)
                for i in range(4)
            ],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["thin_plate_ratio"] == pytest.approx(0.0)

    def test_long_rod_ratio_for_pure_rods(self):
        # Tüm parçalar uzun çubuk: cross=5, length=100 -> 100/5 = 20 > 5
        inst = NestingInstance(
            container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
            parts=[
                PartSpec(id=f"r{i}", name=f"r{i}", qty=1, source="box",
                         width_mm=5.0, depth_mm=5.0, height_mm=100.0)
                for i in range(5)
            ],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["long_rod_ratio"] == pytest.approx(1.0)

    def test_cube_like_ratio(self):
        # Küp benzeri parçalar
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="cube", name="cube", qty=4, source="box",
                         width_mm=15.0, depth_mm=15.0, height_mm=15.0),
                PartSpec(id="plate", name="plate", qty=2, source="box",
                         width_mm=100.0, depth_mm=80.0, height_mm=3.0),
            ],
        )
        fv = extract_features(inst)
        # 4 küp / 6 toplam = 0.667
        assert fv.to_dict()["cube_like_ratio"] == pytest.approx(4.0 / 6.0, abs=0.01)

    def test_thin_plate_family_has_high_ratio(self):
        inst = thin_plates(n_parts=10, xy_min=60.0, xy_max=120.0,
                           thickness_min=3.0, thickness_max=8.0, seed=0)
        fv = extract_features(inst)
        assert fv.to_dict()["thin_plate_ratio"] > 0.5

    def test_long_rod_family_has_high_ratio(self):
        inst = long_rods(n_parts=10, cross_min=5.0, cross_max=10.0,
                         length_min=100.0, length_max=200.0, seed=0)
        fv = extract_features(inst)
        assert fv.to_dict()["long_rod_ratio"] > 0.5


# ---------------------------------------------------------------------------
# Doluluk alt sınırı
# ---------------------------------------------------------------------------

class TestFillLB:
    def test_fill_lb_positive(self):
        fv = extract_features(_inst_mixed())
        assert fv.to_dict()["fill_lb"] > 0.0

    def test_fill_lb_with_fixed_height(self):
        # 10x10x10 küp, konteyner 100x100x100 -> fill = 1000/1000000 = 0.001
        inst = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=100.0),
            parts=[PartSpec(id="c", name="c", qty=1, source="box",
                            width_mm=10.0, depth_mm=10.0, height_mm=10.0)],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["fill_lb"] == pytest.approx(1000.0 / 1_000_000.0, rel=1e-6)


# ---------------------------------------------------------------------------
# Konteyner geometrisi
# ---------------------------------------------------------------------------

class TestContainerFeatures:
    def test_square_container_ratio_near_one(self):
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[PartSpec(id="b", name="b", qty=1, source="box",
                            width_mm=10.0, depth_mm=10.0, height_mm=10.0)],
        )
        fv = extract_features(inst)
        assert fv.to_dict()["container_xy_ratio"] == pytest.approx(1.0)

    def test_max_part_fill_xy_le_one_for_small_part(self):
        inst = _inst_one_box(w=10.0, d=10.0, h=10.0)  # 200x200 container
        fv = extract_features(inst)
        # 10*10 / (200*200) = 100/40000 = 0.0025
        assert fv.to_dict()["max_part_fill_xy"] == pytest.approx(0.0025, rel=1e-4)


# ---------------------------------------------------------------------------
# large_part_ratio — Q2: esik = ortalama hacmin 3 kati (feat 20)
# ---------------------------------------------------------------------------

class TestLargePartRatio:
    def test_large_part_ratio_present_in_feature_names(self):
        assert "large_part_ratio" in FEATURE_NAMES

    def test_one_large_many_small(self):
        """1 dev + 9 kucuk parca -> dev, kucuklerin ort. hacminin >> 3 kati."""
        from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec

        # kucuk parcalar: 10x10x10 = 1000 mm^3 (x9)
        # dev parca: 80x80x80 = 512000 mm^3 (~512 kati ortalamadan -> "large")
        # ortalama hacim = (9*1000 + 1*512000) / 10 = 52100
        # esik = 3 * 52100 = 156300; dev (512000 > 156300) -> large
        # kucukler (1000 < 156300) -> normal
        # large_ratio = 1/10 = 0.1
        inst = NestingInstance(
            container=ContainerSpec(width_mm=500.0, depth_mm=500.0),
            parts=[
                PartSpec(id="big", name="big", qty=1, source="box",
                         width_mm=80.0, depth_mm=80.0, height_mm=80.0),
                PartSpec(id="small", name="small", qty=9, source="box",
                         width_mm=10.0, depth_mm=10.0, height_mm=10.0),
            ],
        )
        fv = extract_features(inst)
        d = fv.to_dict()
        assert "large_part_ratio" in d
        # 1 large / 10 total = 0.1
        assert d["large_part_ratio"] == pytest.approx(0.1, abs=1e-9)

    def test_all_identical_parts_zero_large_ratio(self):
        """Tum parcalar ayni boyutta -> ortalama hacmin 3 kati esigi geci yok."""
        from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec

        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                         width_mm=20.0, depth_mm=20.0, height_mm=20.0)
                for i in range(5)
            ],
        )
        fv = extract_features(inst)
        # Tum parcalar esit -> hicbiri 3 * mean > vol olamazyok; ratio=0.0
        assert fv.to_dict()["large_part_ratio"] == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Farklı instance ailelerinde özellikler anlamlı
# ---------------------------------------------------------------------------

class TestFeaturesSensitivity:
    def test_few_large_many_small_higher_cv_than_homogeneous(self):
        homogeneous = high_qty_repeat(n_models=1, qty_per_model=10, seed=0)
        mixed = few_large_many_small(n_large=3, n_small=10, seed=0)
        fv_h = extract_features(homogeneous)
        fv_m = extract_features(mixed)
        # CV hacim: karışık daha yüksek
        assert fv_m.to_dict()["cv_volume"] > fv_h.to_dict()["cv_volume"]


# ---------------------------------------------------------------------------
# Sınır durumları — F9 (0 parça ve tek parça)
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_instance_does_not_raise(self):
        """0 parçalı instance extract_features çağrısında çökmemeli."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        fv = extract_features(inst)
        assert isinstance(fv, FeatureVector)

    def test_empty_instance_returns_finite_values(self):
        """0 parçalı instance özellik vektöründe NaN/Inf olmamalı."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        fv = extract_features(inst)
        for v in fv.values:
            assert math.isfinite(v), f"Non-finite in empty instance features: {v}"

    def test_empty_instance_zero_counts(self):
        """0 parçalı instance: n_distinct_parts=0, n_total_parts=0."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[],
        )
        d = extract_features(inst).to_dict()
        assert d["n_distinct_parts"] == 0.0
        assert d["n_total_parts"] == 0.0

    def test_single_part_does_not_raise(self):
        """Tek parçalı instance çökmemeli."""
        inst = _inst_one_box(w=30.0, d=30.0, h=30.0, qty=1)
        fv = extract_features(inst)
        assert isinstance(fv, FeatureVector)

    def test_single_part_std_volume_norm_zero(self):
        """Tek parça: std_volume_norm sıfır olmalı (varyans yok)."""
        inst = _inst_one_box(w=30.0, d=30.0, h=30.0, qty=1)
        d = extract_features(inst).to_dict()
        assert d["std_volume_norm"] == pytest.approx(0.0, abs=1e-12)

    def test_box_with_none_dim_raises(self):
        """source='box' + None boyut ValueError fırlatmalı."""
        inst = NestingInstance(
            container=ContainerSpec(width_mm=200.0, depth_mm=200.0),
            parts=[
                PartSpec(id="bad", name="bad", qty=1, source="box",
                         width_mm=10.0, depth_mm=None, height_mm=20.0),
            ],
        )
        with pytest.raises(ValueError, match="zorunludur"):
            extract_features(inst)
