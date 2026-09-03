"""test_stl_order_loader.py — TDD testleri: build_instance_from_order.

Sahte STL bytes'lari trimesh.creation.box ile uretilir; gercek dosya gerekmez.
"""

from __future__ import annotations

import io

import pytest
import trimesh

from src.nesting3d.instances.stl_order_loader import (
    StlOrderResult,
    build_instance_from_order,
)


# ---------------------------------------------------------------------------
# Yardimci: sahte STL bytes uret
# ---------------------------------------------------------------------------

def _make_stl_bytes(w: float, d: float, h: float) -> bytes:
    """trimesh box mesh'inden STL bytes uret."""
    mesh = trimesh.creation.box(extents=(w, d, h))
    return mesh.export(file_type="stl")


# ---------------------------------------------------------------------------
# Test 1: 2 STL + ikisinin de adeti var
# ---------------------------------------------------------------------------

def test_two_matching_parts():
    stl_map = {
        "parca_a": _make_stl_bytes(10.0, 20.0, 30.0),
        "parca_b": _make_stl_bytes(15.0, 25.0, 5.0),
    }
    quantities = {
        "parca_a": 3,
        "parca_b": 7,
    }

    result = build_instance_from_order(stl_map, quantities)

    assert isinstance(result, StlOrderResult)
    assert result.skipped_no_qty == []
    assert result.skipped_no_stl == []

    instance = result.instance
    assert len(instance.parts) == 2

    ids = {p.id for p in instance.parts}
    assert ids == {"parca_a", "parca_b"}

    by_id = {p.id: p for p in instance.parts}

    assert by_id["parca_a"].qty == 3
    assert by_id["parca_b"].qty == 7

    assert by_id["parca_a"].source == "stl"
    assert by_id["parca_b"].source == "stl"


# ---------------------------------------------------------------------------
# Test 2: STL var ama adeti yok -> skipped_no_qty
# ---------------------------------------------------------------------------

def test_stl_without_qty_is_skipped():
    stl_map = {
        "parca_a": _make_stl_bytes(10.0, 20.0, 30.0),
        "parca_orphan": _make_stl_bytes(5.0, 5.0, 5.0),
    }
    quantities = {
        "parca_a": 2,
        # parca_orphan eksik
    }

    result = build_instance_from_order(stl_map, quantities)

    assert "parca_orphan" in result.skipped_no_qty
    assert "parca_a" not in result.skipped_no_qty
    assert len(result.instance.parts) == 1
    assert result.instance.parts[0].id == "parca_a"


# ---------------------------------------------------------------------------
# Test 3: adet var ama STL yok -> skipped_no_stl
# ---------------------------------------------------------------------------

def test_qty_without_stl_is_skipped():
    stl_map = {
        "parca_a": _make_stl_bytes(10.0, 20.0, 30.0),
        # parca_ghost STL'i yok
    }
    quantities = {
        "parca_a": 1,
        "parca_ghost": 4,
    }

    result = build_instance_from_order(stl_map, quantities)

    assert "parca_ghost" in result.skipped_no_stl
    assert "parca_a" not in result.skipped_no_stl
    assert len(result.instance.parts) == 1


# ---------------------------------------------------------------------------
# Test 4: bbox boyutlari kabaca (10, 20, 30) mertebesinde (eksen-sira toleransi)
# ---------------------------------------------------------------------------

def test_bbox_dimensions_approximately_correct():
    stl_map = {"kutu": _make_stl_bytes(10.0, 20.0, 30.0)}
    quantities = {"kutu": 1}

    result = build_instance_from_order(stl_map, quantities)

    part = result.instance.parts[0]
    dims = sorted([part.width_mm, part.depth_mm, part.height_mm])
    expected = sorted([10.0, 20.0, 30.0])

    for actual, exp in zip(dims, expected):
        assert abs(actual - exp) < 1.0, (
            f"Boyut uyumsuz: beklenen {exp:.1f}, gelen {actual:.1f}"
        )


# ---------------------------------------------------------------------------
# Test 5: Determinizm — ayni girdi ayni sonuc
# ---------------------------------------------------------------------------

def test_determinism():
    stl_bytes = _make_stl_bytes(12.0, 24.0, 36.0)
    stl_map = {"parcam": stl_bytes}
    quantities = {"parcam": 5}

    result1 = build_instance_from_order(stl_map, quantities)
    result2 = build_instance_from_order(stl_map, quantities)

    p1 = result1.instance.parts[0]
    p2 = result2.instance.parts[0]

    assert p1.qty == p2.qty == 5
    assert abs(p1.width_mm - p2.width_mm) < 1e-6
    assert abs(p1.depth_mm - p2.depth_mm) < 1e-6
    assert abs(p1.height_mm - p2.height_mm) < 1e-6


# ---------------------------------------------------------------------------
# Test 6: meta alanlari
# ---------------------------------------------------------------------------

def test_instance_meta():
    stl_map = {
        "a": _make_stl_bytes(5.0, 5.0, 5.0),
        "b": _make_stl_bytes(8.0, 8.0, 8.0),
    }
    quantities = {"a": 2, "b": 3}

    result = build_instance_from_order(stl_map, quantities)
    meta = result.instance.meta

    assert meta["family"] == "mail_order"
    assert meta["n_distinct_parts"] == 2
    assert meta["total_qty"] == 5


# ---------------------------------------------------------------------------
# Test 7: konteyner boyutlari default + override
# ---------------------------------------------------------------------------

def test_container_otomatik_plaka():
    """Plaka verilmezse SABIT default DEGIL — parcalardan otomatik turetilir.

    Pay = max(%2, 10mm taban): kucuk parcada (5 mm) %2 = 0.1 mm pitch icin
    yetersiz kalir -> sabit 10 mm taban uygulanir = 5 + 10 = 15 mm. Boylece
    parca her zaman plakaya sigar (voxel/pitch yuvarlamasi tasmaz).
    Sabit 335 ARTIK kullanilmaz (kullanici karari: sabit default olmamali).
    """
    stl_map = {"p": _make_stl_bytes(5.0, 5.0, 5.0)}
    quantities = {"p": 1}

    result = build_instance_from_order(stl_map, quantities)
    c = result.instance.container
    assert c.width_mm == 15.0
    assert c.depth_mm == 15.0
    assert c.height_mm is None
    # parca taban kenarindan (5) buyuk olmali -> her oryantasyonda sigar
    assert c.width_mm >= 5.0
    assert result.instance.meta.get("plate_auto") is True


def test_container_override():
    stl_map = {"p": _make_stl_bytes(5.0, 5.0, 5.0)}
    quantities = {"p": 1}

    result = build_instance_from_order(
        stl_map, quantities,
        container_w_mm=500.0,
        container_d_mm=400.0,
        container_h_mm=200.0,
    )
    c = result.instance.container
    assert c.width_mm == 500.0
    assert c.depth_mm == 400.0
    assert c.height_mm == 200.0
    # gercek plaka acikca verildi -> otomatik DEGIL
    assert result.instance.meta.get("plate_auto") is False


# ---------------------------------------------------------------------------
# Test 8: bos girdi -> bos instance, her iki skip listesi de bos
# ---------------------------------------------------------------------------

def test_empty_inputs():
    result = build_instance_from_order({}, {})
    assert result.instance.parts == []
    assert result.skipped_no_qty == []
    assert result.skipped_no_stl == []


def test_build_instance_case_insensitive_eslesme():
    """Mail metni 'Braket' (büyük) ile dosya 'braket' (küçük) eşleşmeli."""
    import trimesh
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order
    m = trimesh.creation.box(extents=(10, 20, 30))
    stl_map = {"braket": m.export(file_type="stl")}   # dosya: küçük
    qty = {"Braket": 5}                                # mail: büyük
    res = build_instance_from_order(stl_map, qty)
    assert len(res.instance.parts) == 1
    assert res.instance.parts[0].qty == 5
    assert res.skipped_no_stl == [] and res.skipped_no_qty == []
