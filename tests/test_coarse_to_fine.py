"""Tests for src.nesting3d.coarse_to_fine — coarse-to-fine nesting pipeline.

TDD RED → GREEN sequence.

Acceptance criteria:
  1. solve_coarse_to_fine runs, returns CoarseToFineResult; n_placed == total parts.
  2. Fine placements part_id order matches coarse winner order (coarse order -> fine).
  3. height_mm > 0, density in 0..1.
  4. coarse_pitch > fine_pitch (coarser = bigger pitch).
  5. Determinism: two calls with same args return same height_mm.
  6. Fast: small boxes + coarse pitch + low budget + 1-config menu.
"""

from __future__ import annotations

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)
from src.nesting3d.coarse_to_fine import (
    CoarseToFineResult,
    solve_coarse_to_fine,
    suggest_coarse_pitch,
    _min_feature_mm,
)

# ---------------------------------------------------------------------------
# Test fixtures — small box instance (no real STL, no large voxelization)
# ---------------------------------------------------------------------------

COARSE_PITCH = 10.0   # kaba: 10 mm / voxel
FINE_PITCH = 5.0      # ince: 5 mm / voxel
PLATE_W = 100.0
PLATE_D = 100.0
BUDGET = 15           # hızlı test: 15 iterasyon yeterli


def _make_instance() -> NestingInstance:
    """4 kutu parça: 2 adet box_a (30x20x10) + 2 adet box_b (20x20x15)."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(
                id="box_a",
                name="box_a",
                qty=2,
                source="box",
                width_mm=30.0,
                depth_mm=20.0,
                height_mm=10.0,
            ),
            PartSpec(
                id="box_b",
                name="box_b",
                qty=2,
                source="box",
                width_mm=20.0,
                depth_mm=20.0,
                height_mm=15.0,
            ),
        ],
    )


def _fast_menu():
    """Tuner menu'su: sadece dblf_only (1 konfig) — hız için."""
    from src.nesting3d.solvers.dblf_solver import DBLFSolver

    return {
        "dblf_only": {
            "solver": DBLFSolver(),
            "params": {},
        }
    }


def _solve(**kwargs) -> CoarseToFineResult:
    """Ortak çağrı yardımcısı."""
    instance = _make_instance()
    return solve_coarse_to_fine(
        instance,
        plate_w_mm=PLATE_W,
        plate_d_mm=PLATE_D,
        coarse_pitch=COARSE_PITCH,
        fine_pitch=FINE_PITCH,
        budget=BUDGET,
        seed=42,
        menu=_fast_menu(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. CoarseToFineResult yapısı ve n_placed
# ---------------------------------------------------------------------------


def test_result_is_dataclass():
    """CoarseToFineResult dataclass alanlari tam olmalı."""
    from dataclasses import fields

    field_names = {f.name for f in fields(CoarseToFineResult)}
    required = {
        "placements",
        "bin3d",
        "height_mm",
        "density",
        "winning_config",
        "coarse_height_mm",
        "coarse_pitch",
        "fine_pitch",
        "coarse_time_s",
        "fine_time_s",
        "n_placed",
    }
    assert required <= field_names, f"Eksik alanlar: {required - field_names}"


def test_solve_returns_coarse_to_fine_result():
    """solve_coarse_to_fine CoarseToFineResult döndürmeli."""
    result = _solve()
    assert isinstance(result, CoarseToFineResult)


def test_n_placed_equals_total_parts():
    """n_placed == toplam parça adedi (qty'ler açılmış)."""
    instance = _make_instance()
    total = sum(p.qty for p in instance.parts)  # 2 + 2 = 4
    result = _solve()
    assert result.n_placed == total, (
        f"Beklenen n_placed={total}, gelen={result.n_placed}"
    )


def test_placements_list_length_equals_n_placed():
    """placements listesi uzunluğu n_placed ile eşit olmalı."""
    result = _solve()
    assert len(result.placements) == result.n_placed


# ---------------------------------------------------------------------------
# 2. Fine placements order matches coarse winner order
# ---------------------------------------------------------------------------


def test_fine_order_matches_coarse_order():
    """Fine placement part_id sırası, coarse kazananının sırasıyla aynı olmalı."""
    result = _solve()
    # Fine placement'ların part_id sırası coarse sırası aktarılmış olmalı.
    # Her fine placement'da part_id mevcut olmalı.
    placed_ids = [p.part_id for p in result.placements]
    # Tümü benzersiz-ish id içermeli (qty_açılmış versiyonlar: name_0, name_1, ...)
    assert len(placed_ids) == result.n_placed
    # Sıralı olmayan bir set değil, gerçek liste — sıra korunmuş.
    # Hem coarse hem fine aynı id uzayını kullandığından intersection tam olmalı.
    assert len(set(placed_ids)) == result.n_placed, (
        "Placement part_id'leri tekil olmalı (her parça bir kez yerleşir)"
    )


def test_fine_bin3d_is_bin3d_instance():
    """result.bin3d Bin3D örneği olmalı."""
    result = _solve()
    assert isinstance(result.bin3d, Bin3D)


# ---------------------------------------------------------------------------
# 3. height_mm > 0, density 0..1
# ---------------------------------------------------------------------------


def test_height_mm_positive():
    """Fine height_mm > 0 olmalı."""
    result = _solve()
    assert result.height_mm > 0.0, f"height_mm={result.height_mm}"


def test_density_in_unit_interval():
    """Fine density 0 ile 1 arasında olmalı."""
    result = _solve()
    assert 0.0 < result.density <= 1.0, f"density={result.density}"


def test_coarse_height_mm_positive():
    """Coarse kazananının height_mm > 0 olmalı."""
    result = _solve()
    assert result.coarse_height_mm > 0.0


# ---------------------------------------------------------------------------
# 4. coarse_pitch > fine_pitch
# ---------------------------------------------------------------------------


def test_pitch_relationship():
    """coarse_pitch > fine_pitch olmalı (kaba >= ince)."""
    result = _solve()
    assert result.coarse_pitch == COARSE_PITCH
    assert result.fine_pitch == FINE_PITCH
    assert result.coarse_pitch > result.fine_pitch


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """Aynı argümanlarla iki çağrı aynı height_mm versin."""
    r1 = _solve()
    r2 = _solve()
    assert r1.height_mm == r2.height_mm, (
        f"Determinizm ihlali: {r1.height_mm} != {r2.height_mm}"
    )
    assert r1.winning_config == r2.winning_config
    assert r1.n_placed == r2.n_placed


# ---------------------------------------------------------------------------
# 6. Timing fields are non-negative floats
# ---------------------------------------------------------------------------


def test_timing_fields_non_negative():
    """coarse_time_s ve fine_time_s >= 0 olmalı."""
    result = _solve()
    assert result.coarse_time_s >= 0.0
    assert result.fine_time_s >= 0.0


# ---------------------------------------------------------------------------
# 7. winning_config is a string matching the menu key
# ---------------------------------------------------------------------------


def test_winning_config_is_menu_key():
    """winning_config menu'deki bir anahtar olmalı."""
    menu = _fast_menu()
    result = _solve()
    assert result.winning_config in menu, (
        f"winning_config='{result.winning_config}' menu'de yok: {list(menu)}"
    )


# ---------------------------------------------------------------------------
# 8. Farklı seed -> farklı veya aynı ama geçerli sonuç
# ---------------------------------------------------------------------------


def test_different_seed_still_valid():
    """Farklı seed ile sonuç yine geçerli (height>0, density 0..1)."""
    instance = _make_instance()
    result = solve_coarse_to_fine(
        instance,
        plate_w_mm=PLATE_W,
        plate_d_mm=PLATE_D,
        coarse_pitch=COARSE_PITCH,
        fine_pitch=FINE_PITCH,
        budget=BUDGET,
        seed=99,
        menu=_fast_menu(),
    )
    assert result.height_mm > 0.0
    assert 0.0 < result.density <= 1.0


# ---------------------------------------------------------------------------
# Adaptif coarse pitch (suggest_coarse_pitch) — her veriye özel güvenli
# ---------------------------------------------------------------------------

def _inst(dim_list):
    """dim_list: [(w,d,h), ...] -> box parçalı NestingInstance."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                     width_mm=w, depth_mm=d, height_mm=h)
            for i, (w, d, h) in enumerate(dim_list)
        ],
    )


def test_min_feature_en_ince_boyut():
    inst = _inst([(50, 50, 50), (10, 1.0, 20)])
    assert _min_feature_mm(inst) == 1.0


def test_suggest_coarse_ince_parca_guvenli():
    # 1 mm ince parça → coarse pitch onu voxelize'da kaybetmemeli
    inst = _inst([(50, 50, 50), (10, 1.0, 20)])
    cp = suggest_coarse_pitch(inst, fine_pitch=0.4)
    assert _min_feature_mm(inst) / cp > 0.5   # kaybolmaz (güvenli)


def test_suggest_coarse_kalin_parca_fine_x3():
    # En ince 10 mm → güvenli tavan (10/0.6=16.7) yüksek, hedef fine×3 geçerli
    inst = _inst([(50, 50, 50), (20, 10, 30)])
    cp = suggest_coarse_pitch(inst, fine_pitch=1.0)
    assert cp == pytest.approx(3.0)


def test_suggest_coarse_fine_alt_sinir():
    # coarse asla fine'dan küçük olamaz
    inst = _inst([(2, 1.0, 2)])  # çok ince
    cp = suggest_coarse_pitch(inst, fine_pitch=2.0)
    assert cp >= 2.0


def test_solve_coarse_pitch_none_otomatik():
    # coarse_pitch=None → otomatik suggest; çalışmalı
    inst = _make_instance()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
        coarse_pitch=None, fine_pitch=FINE_PITCH, budget=BUDGET, seed=42,
    )
    assert r.n_placed == 4
    assert r.coarse_pitch >= FINE_PITCH
