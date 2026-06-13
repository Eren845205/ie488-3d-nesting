"""Tests for src.nesting3d.instances.synthetic (PLAN_DEMO1.md 2.2)."""

import pytest

from src.nesting3d.instances.synthetic import (
    few_large_many_small,
    high_qty_repeat,
    long_rods,
    random_boxes,
    thin_plates,
)
from src.nesting3d.instances.format import ContainerSpec, NestingInstance


# ---------------------------------------------------------------------------
# Determinizm — aynı seed -> aynı instance
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_random_boxes_same_seed(self):
        a = random_boxes(n_parts=10, seed=42)
        b = random_boxes(n_parts=10, seed=42)
        assert len(a.parts) == len(b.parts)
        for pa, pb in zip(a.parts, b.parts):
            assert pa.width_mm == pb.width_mm
            assert pa.depth_mm == pb.depth_mm
            assert pa.height_mm == pb.height_mm

    def test_random_boxes_different_seeds(self):
        a = random_boxes(n_parts=10, seed=1)
        b = random_boxes(n_parts=10, seed=2)
        dims_a = [(p.width_mm, p.depth_mm, p.height_mm) for p in a.parts]
        dims_b = [(p.width_mm, p.depth_mm, p.height_mm) for p in b.parts]
        assert dims_a != dims_b

    def test_few_large_many_small_same_seed(self):
        a = few_large_many_small(seed=7)
        b = few_large_many_small(seed=7)
        assert [p.width_mm for p in a.parts] == [p.width_mm for p in b.parts]

    def test_high_qty_repeat_same_seed(self):
        a = high_qty_repeat(seed=99)
        b = high_qty_repeat(seed=99)
        assert [p.qty for p in a.parts] == [p.qty for p in b.parts]

    def test_thin_plates_same_seed(self):
        a = thin_plates(seed=3)
        b = thin_plates(seed=3)
        assert [p.height_mm for p in a.parts] == [p.height_mm for p in b.parts]

    def test_long_rods_same_seed(self):
        a = long_rods(seed=5)
        b = long_rods(seed=5)
        assert [p.height_mm for p in a.parts] == [p.height_mm for p in b.parts]


# ---------------------------------------------------------------------------
# random_boxes
# ---------------------------------------------------------------------------

class TestRandomBoxes:
    def test_part_count(self):
        inst = random_boxes(n_parts=15, seed=0)
        assert len(inst.parts) == 15

    def test_all_box_source(self):
        inst = random_boxes(n_parts=5, seed=0)
        assert all(p.source == "box" for p in inst.parts)

    def test_dims_in_range(self):
        inst = random_boxes(n_parts=20, min_dim=10.0, max_dim=50.0, seed=0)
        for p in inst.parts:
            for dim in (p.width_mm, p.depth_mm, p.height_mm):
                assert 10.0 <= dim <= 50.0

    def test_all_qty_one(self):
        inst = random_boxes(n_parts=8, seed=0)
        assert all(p.qty == 1 for p in inst.parts)

    def test_meta_family(self):
        inst = random_boxes(seed=0)
        assert inst.meta["family"] == "random_boxes"

    def test_unique_ids(self):
        inst = random_boxes(n_parts=10, seed=0)
        ids = [p.id for p in inst.parts]
        assert len(set(ids)) == 10

    def test_custom_container(self):
        cnt = ContainerSpec(width_mm=500.0, depth_mm=400.0, height_mm=300.0)
        inst = random_boxes(container=cnt, seed=0)
        assert inst.container.width_mm == 500.0

    def test_default_container_open_dimension(self):
        inst = random_boxes(seed=0)
        assert inst.container.height_mm is None


# ---------------------------------------------------------------------------
# few_large_many_small
# ---------------------------------------------------------------------------

class TestFewLargeManySmall:
    def test_part_count(self):
        inst = few_large_many_small(n_large=3, n_small=10, seed=0)
        assert len(inst.parts) == 13

    def test_large_dims_in_range(self):
        inst = few_large_many_small(
            n_large=5, n_small=0,
            large_min=60.0, large_max=120.0, seed=0
        )
        for p in inst.parts[:5]:
            for dim in (p.width_mm, p.depth_mm, p.height_mm):
                assert 60.0 <= dim <= 120.0

    def test_small_dims_in_range(self):
        inst = few_large_many_small(
            n_large=0, n_small=10,
            small_min=5.0, small_max=20.0, seed=0
        )
        for p in inst.parts:
            for dim in (p.width_mm, p.depth_mm, p.height_mm):
                assert 5.0 <= dim <= 20.0

    def test_meta_family(self):
        inst = few_large_many_small(seed=0)
        assert inst.meta["family"] == "few_large_many_small"


# ---------------------------------------------------------------------------
# high_qty_repeat
# ---------------------------------------------------------------------------

class TestHighQtyRepeat:
    def test_model_count(self):
        inst = high_qty_repeat(n_models=4, qty_per_model=8, seed=0)
        assert len(inst.parts) == 4

    def test_qty_per_model(self):
        inst = high_qty_repeat(n_models=3, qty_per_model=10, seed=0)
        for p in inst.parts:
            assert p.qty == 10

    def test_total_parts(self):
        inst = high_qty_repeat(n_models=4, qty_per_model=5, seed=0)
        total = sum(p.qty for p in inst.parts)
        assert total == 20

    def test_meta_family(self):
        inst = high_qty_repeat(seed=0)
        assert inst.meta["family"] == "high_qty_repeat"

    def test_distinct_model_dims(self):
        # Farklı modeller genellikle farklı boyutlara sahip olmalı (seed bazlı)
        inst = high_qty_repeat(n_models=5, seed=42)
        dims = [(p.width_mm, p.depth_mm, p.height_mm) for p in inst.parts]
        # tüm boyutlar aynı olma ihtimali astronomik derecede düşük
        assert len(set(dims)) > 1


# ---------------------------------------------------------------------------
# thin_plates
# ---------------------------------------------------------------------------

class TestThinPlates:
    def test_part_count(self):
        inst = thin_plates(n_parts=6, seed=0)
        assert len(inst.parts) == 6

    def test_thickness_in_range(self):
        inst = thin_plates(
            n_parts=10,
            xy_min=40.0, xy_max=100.0,
            thickness_min=2.0, thickness_max=8.0,
            seed=0,
        )
        for p in inst.parts:
            # height_mm = kalınlık
            assert 2.0 <= p.height_mm <= 8.0

    def test_xy_in_range(self):
        inst = thin_plates(
            n_parts=10, xy_min=50.0, xy_max=120.0,
            thickness_min=3.0, thickness_max=10.0, seed=0,
        )
        for p in inst.parts:
            assert 50.0 <= p.width_mm <= 120.0
            assert 50.0 <= p.depth_mm <= 120.0

    def test_plates_are_thin(self):
        # kalınlık / xy_max < 0.2 olmalı (parametreler bunu garanti eder)
        inst = thin_plates(
            n_parts=10,
            xy_min=60.0, xy_max=100.0,
            thickness_min=3.0, thickness_max=10.0,
            seed=0,
        )
        for p in inst.parts:
            ratio = p.height_mm / max(p.width_mm, p.depth_mm)
            assert ratio < 0.25, f"Plate not thin: ratio={ratio:.3f}"

    def test_meta_family(self):
        inst = thin_plates(seed=0)
        assert inst.meta["family"] == "thin_plates"


# ---------------------------------------------------------------------------
# long_rods
# ---------------------------------------------------------------------------

class TestLongRods:
    def test_part_count(self):
        inst = long_rods(n_parts=5, seed=0)
        assert len(inst.parts) == 5

    def test_length_in_range(self):
        inst = long_rods(
            n_parts=8, length_min=100.0, length_max=200.0,
            cross_min=5.0, cross_max=15.0, seed=0,
        )
        for p in inst.parts:
            assert 100.0 <= p.height_mm <= 200.0

    def test_cross_section_in_range(self):
        inst = long_rods(
            n_parts=8, cross_min=5.0, cross_max=15.0,
            length_min=100.0, length_max=200.0, seed=0,
        )
        for p in inst.parts:
            assert 5.0 <= p.width_mm <= 15.0
            assert 5.0 <= p.depth_mm <= 15.0

    def test_rods_are_long(self):
        # Eşik features.py long_rod tanımıyla (max_dim/mid_dim > 5.0) tutarlı:
        # length_min=100, cross_max=15 -> ratio >= 100/15 ≈ 6.67 > 5.0
        inst = long_rods(
            n_parts=10,
            cross_min=5.0, cross_max=15.0,
            length_min=100.0, length_max=200.0,
            seed=0,
        )
        for p in inst.parts:
            ratio = p.height_mm / max(p.width_mm, p.depth_mm)
            assert ratio > 5.0, f"Rod not long: ratio={ratio:.2f}"

    def test_meta_family(self):
        inst = long_rods(seed=0)
        assert inst.meta["family"] == "long_rods"


# ---------------------------------------------------------------------------
# Returns NestingInstance type
# ---------------------------------------------------------------------------

class TestReturnTypes:
    @pytest.mark.parametrize("factory,kwargs", [
        (random_boxes, {"n_parts": 5, "seed": 0}),
        (few_large_many_small, {"n_large": 2, "n_small": 5, "seed": 0}),
        (high_qty_repeat, {"n_models": 3, "qty_per_model": 4, "seed": 0}),
        (thin_plates, {"n_parts": 4, "seed": 0}),
        (long_rods, {"n_parts": 4, "seed": 0}),
    ])
    def test_returns_nesting_instance(self, factory, kwargs):
        inst = factory(**kwargs)
        assert isinstance(inst, NestingInstance)


# ---------------------------------------------------------------------------
# Sınır durumları — F9 (n_parts=0 / n_large=0 / n_models=0)
# ---------------------------------------------------------------------------

class TestEdgeCasesZeroParts:
    def test_random_boxes_zero_parts_does_not_raise(self):
        inst = random_boxes(n_parts=0, seed=0)
        assert isinstance(inst, NestingInstance)
        assert len(inst.parts) == 0

    def test_random_boxes_zero_parts_is_nesting_instance(self):
        inst = random_boxes(n_parts=0, seed=0)
        assert inst.container.width_mm > 0

    def test_few_large_many_small_zero_parts_does_not_raise(self):
        inst = few_large_many_small(n_large=0, n_small=0, seed=0)
        assert isinstance(inst, NestingInstance)
        assert len(inst.parts) == 0

    def test_thin_plates_zero_parts_does_not_raise(self):
        inst = thin_plates(n_parts=0, seed=0)
        assert isinstance(inst, NestingInstance)
        assert len(inst.parts) == 0

    def test_long_rods_zero_parts_does_not_raise(self):
        inst = long_rods(n_parts=0, seed=0)
        assert isinstance(inst, NestingInstance)
        assert len(inst.parts) == 0

    def test_high_qty_repeat_zero_models_does_not_raise(self):
        inst = high_qty_repeat(n_models=0, qty_per_model=5, seed=0)
        assert isinstance(inst, NestingInstance)
        assert len(inst.parts) == 0
