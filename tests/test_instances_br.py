"""Tests for src.nesting3d.instances.br_loader (PLAN_DEMO1.md 2.3)."""

import pytest

from src.nesting3d.instances.br_loader import (
    BR_CLASS_PARAMS,
    BR_CLASSES,
    N_INSTANCES_PER_CLASS,
    generate_br_instance,
    load_br_instance,
)
from src.nesting3d.instances.format import NestingInstance


# ---------------------------------------------------------------------------
# Temel doğrulama
# ---------------------------------------------------------------------------

class TestBRClassRegistry:
    def test_15_classes_defined(self):
        assert len(BR_CLASSES) == 15

    def test_all_classes_in_params(self):
        for cls in BR_CLASSES:
            assert cls in BR_CLASS_PARAMS

    def test_class_names_br1_to_br15(self):
        for i in range(1, 16):
            assert f"BR{i}" in BR_CLASSES


# ---------------------------------------------------------------------------
# generate_br_instance
# ---------------------------------------------------------------------------

class TestGenerateBRInstance:
    def test_returns_nesting_instance(self):
        inst = generate_br_instance("BR1", 0)
        assert isinstance(inst, NestingInstance)

    def test_container_proportional_to_box(self):
        """Konteyner ∝ kutu (2026-06-14): kenar = CONTAINER_DIM_FACTOR × en
        büyük kutu boyutu; kare taban (w == d)."""
        from src.nesting3d.instances.br_loader import CONTAINER_DIM_FACTOR
        for cls in ["BR1", "BR5", "BR12"]:
            inst = generate_br_instance(cls, 0)
            max_box = max(
                max(p.width_mm, p.depth_mm, p.height_mm) for p in inst.parts
            )
            assert inst.container.width_mm == inst.container.depth_mm
            assert inst.container.width_mm == CONTAINER_DIM_FACTOR * max_box

    def test_open_dimension_container(self):
        inst = generate_br_instance("BR1", 0)
        assert inst.container.height_mm is None

    def test_br1_has_parts(self):
        inst = generate_br_instance("BR1", 0)
        assert len(inst.parts) >= 1

    def test_br1_box_source(self):
        inst = generate_br_instance("BR1", 0)
        assert all(p.source == "box" for p in inst.parts)

    def test_br1_box_dims_in_range(self):
        """BR1: boyut aralığı 1-5 birim."""
        params = BR_CLASS_PARAMS["BR1"]
        inst = generate_br_instance("BR1", 0)
        for p in inst.parts:
            assert params.w_range[0] <= p.width_mm <= params.w_range[1]
            assert params.d_range[0] <= p.depth_mm <= params.d_range[1]
            assert params.h_range[0] <= p.height_mm <= params.h_range[1]

    def test_br1_total_qty_in_range(self):
        """BR1: toplam adet 50-150."""
        params = BR_CLASS_PARAMS["BR1"]
        inst = generate_br_instance("BR1", 0)
        total = sum(p.qty for p in inst.parts)
        assert params.qty_range[0] <= total <= params.qty_range[1]

    def test_br1_single_type(self):
        """BR1: tek tip kutu."""
        inst = generate_br_instance("BR1", 0)
        assert len(inst.parts) == 1  # n_types_range = (1,1)

    def test_determinism_same_seed(self):
        a = generate_br_instance("BR3", 2)
        b = generate_br_instance("BR3", 2)
        assert len(a.parts) == len(b.parts)
        for pa, pb in zip(a.parts, b.parts):
            assert pa.qty == pb.qty
            assert pa.width_mm == pb.width_mm

    def test_different_instances_different_results(self):
        a = generate_br_instance("BR3", 0)
        b = generate_br_instance("BR3", 1)
        # Farklı seed -> en azından qty veya boyut farklı olmalı
        total_a = sum(p.qty for p in a.parts)
        total_b = sum(p.qty for p in b.parts)
        # Boyutlar veya toplam farklı olmalı
        dims_a = [(p.width_mm, p.depth_mm, p.height_mm) for p in a.parts]
        dims_b = [(p.width_mm, p.depth_mm, p.height_mm) for p in b.parts]
        assert total_a != total_b or dims_a != dims_b

    def test_meta_has_class_and_method(self):
        inst = generate_br_instance("BR5", 0)
        assert inst.meta["class"] == "BR5"
        assert inst.meta["source_method"] == "seed_regenerated"

    def test_meta_has_reference(self):
        inst = generate_br_instance("BR1", 0)
        assert "Bischoff" in inst.meta["reference"]

    def test_unknown_class_raises(self):
        with pytest.raises(KeyError, match="BR99"):
            generate_br_instance("BR99", 0)

    def test_invalid_index_raises(self):
        with pytest.raises(ValueError):
            generate_br_instance("BR1", N_INSTANCES_PER_CLASS)

    def test_all_classes_generate(self):
        """Tüm BR1-BR15 sınıfları hatasız üretmeli."""
        for cls in BR_CLASSES:
            inst = generate_br_instance(cls, 0)
            assert isinstance(inst, NestingInstance)
            assert len(inst.parts) >= 1

    def test_br12_thin_plate_dims(self):
        """BR12: yükseklik (h) 1-5 birim (ince plaka)."""
        params = BR_CLASS_PARAMS["BR12"]
        for idx in range(N_INSTANCES_PER_CLASS):
            inst = generate_br_instance("BR12", idx)
            for p in inst.parts:
                assert params.h_range[0] <= p.height_mm <= params.h_range[1]

    def test_br13_long_rod_dims(self):
        """BR13: yükseklik (h) 1-20 birim (uzun çubuk), kesit 1-5."""
        params = BR_CLASS_PARAMS["BR13"]
        for idx in range(N_INSTANCES_PER_CLASS):
            inst = generate_br_instance("BR13", idx)
            for p in inst.parts:
                assert params.h_range[0] <= p.height_mm <= params.h_range[1]

    def test_br14_square_base(self):
        """BR14: kare taban — her parçada w == d olmalı."""
        for idx in range(N_INSTANCES_PER_CLASS):
            inst = generate_br_instance("BR14", idx)
            for p in inst.parts:
                assert p.width_mm == p.depth_mm, (
                    f"BR14 idx={idx} part={p.id}: w={p.width_mm} != d={p.depth_mm}"
                )

    def test_make_seed_golden_value(self):
        """_make_seed deterministik — bilinen (class,idx) için sabit değer."""
        from src.nesting3d.instances.br_loader import _make_seed
        # hashlib.sha256("BR1_0".encode()) hesaplanmış golden value:
        assert _make_seed("BR1", 0) == 1886574934

    def test_positive_qty(self):
        for cls in ["BR1", "BR6", "BR10"]:
            inst = generate_br_instance(cls, 0)
            for p in inst.parts:
                assert p.qty >= 1


# ---------------------------------------------------------------------------
# load_br_instance (JSON cache fallback)
# ---------------------------------------------------------------------------

class TestLoadBRInstance:
    def test_load_same_as_generate_when_no_json(self):
        """JSON yoksa generate ile aynı sonuç döner."""
        inst_load = load_br_instance("BR2", 0)
        inst_gen = generate_br_instance("BR2", 0)
        assert len(inst_load.parts) == len(inst_gen.parts)
        for pl, pg in zip(inst_load.parts, inst_gen.parts):
            assert pl.qty == pg.qty
            assert pl.width_mm == pg.width_mm

    def test_load_from_json_file(self, tmp_path):
        """data/br/ altında JSON varsa onu yükler (JSON-var dalı gerçek kodla test edilir)."""
        from pathlib import Path

        orig_inst = generate_br_instance("BR7", 1)
        orig_inst.meta["custom_flag"] = True

        # tmp_path altına sahte JSON cache dizini oluştur
        fake_br_dir = tmp_path / "data" / "br"
        fake_br_dir.mkdir(parents=True)
        json_path = fake_br_dir / "BR7_01.json"
        orig_inst.to_json(json_path)

        # data_dir parametresiyle gerçek load_br_instance çağrılır — JSON-var dalı
        loaded = load_br_instance("BR7", 1, data_dir=str(fake_br_dir))
        assert loaded.meta.get("custom_flag") is True

    def test_load_generates_when_no_json(self, tmp_path):
        """JSON yoksa generate dalı gerçek kodla çalışır."""
        # Boş tmp dizini — JSON yok
        empty_dir = tmp_path / "empty_br"
        empty_dir.mkdir()
        loaded = load_br_instance("BR7", 1, data_dir=str(empty_dir))
        expected = generate_br_instance("BR7", 1)
        assert len(loaded.parts) == len(expected.parts)
        for pl, pe in zip(loaded.parts, expected.parts):
            assert pl.qty == pe.qty
            assert pl.width_mm == pe.width_mm
