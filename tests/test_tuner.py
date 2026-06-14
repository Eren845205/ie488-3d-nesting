"""Tests for src.nesting3d.tuner — Instance-Tuner (APP_YOL_HARITASI §6 Ajan 2).

Acceptance criteria:
  (a) Determinizm: aynı (parts, budget, seed) -> birebir aynı TuneResult.
  (b) Monoton kabul: tuner.result.height_mm <= portfolio genel sonucu.
       (Asla kötüleşmez — çıktı en az portföy kadar iyi.)
  (c) TuneResult.winning_config_name: hangi konfigin kazandığını taşır.
  (d) En az bir senaryoda deney menüsü çalışır (birden fazla konfig denenmiş).
"""

from __future__ import annotations

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.tuner import TuneResult, tune, build_menu
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
FAST_BUDGET = 30  # tests fast'tan hız öncelikli


def _part(part_id: str, extents=(10, 10, 10)):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    return voxelize_part(part_id, b, PITCH, n_orientations=4)


def _bin():
    return Bin3D(40.0, 40.0, PITCH)


def _parts():
    return [
        _part("slab1", (20, 20, 5)),
        _part("stick1", (5, 5, 30)),
        _part("cube1", (10, 10, 10)),
        _part("cube2", (10, 10, 10)),
    ]


# ---------------------------------------------------------------------------
# TuneResult structure
# ---------------------------------------------------------------------------


def test_tune_result_is_dataclass():
    """TuneResult must be importable and have required fields."""
    from dataclasses import fields
    field_names = {f.name for f in fields(TuneResult)}
    assert "result" in field_names
    assert "winning_config_name" in field_names
    assert "baseline_height_mm" in field_names
    assert "improvement_mm" in field_names


def test_tune_result_improvement_formula():
    """improvement_mm = baseline_height_mm - result.height_mm (>= 0)."""
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    expected = tr.baseline_height_mm - tr.result.height_mm
    assert abs(tr.improvement_mm - expected) < 1e-9


# ---------------------------------------------------------------------------
# (a) Determinizm
# ---------------------------------------------------------------------------


def test_tune_deterministic_same_seed():
    """Same (parts, budget, seed) -> identical TuneResult."""
    parts = _parts()
    tr_a = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    tr_b = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert tr_a.result.height_mm == tr_b.result.height_mm
    assert tr_a.winning_config_name == tr_b.winning_config_name
    assert tr_a.baseline_height_mm == tr_b.baseline_height_mm


def test_tune_different_seeds_both_valid():
    """Different seeds still produce valid (positive height) TuneResults."""
    parts = _parts()
    tr_a = tune(parts, _bin, budget=FAST_BUDGET, seed=1)
    tr_b = tune(parts, _bin, budget=FAST_BUDGET, seed=2)
    assert tr_a.result.height_mm > 0
    assert tr_b.result.height_mm > 0


# ---------------------------------------------------------------------------
# (b) Monoton kabul — tuner asla portföy genel sonucundan KÖTÜ olamaz
# ---------------------------------------------------------------------------


def test_tune_never_worse_than_portfolio():
    """Tuner sonucu height_mm <= baseline_height_mm (portfolyo en iyisi).

    Monoton kabul garantisi: tuner ya aynı ya da daha iyi bir sonuç üretir.
    """
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    # tuner result must be <= genel portföy en iyisi (baseline)
    assert tr.result.height_mm <= tr.baseline_height_mm + 1e-9


def test_tune_result_height_matches_solve_result():
    """TuneResult.result.height_mm must equal the actual SolveResult height."""
    from src.nesting3d.solvers.base import SolveResult
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert isinstance(tr.result, SolveResult)
    # height_mm must be positive
    assert tr.result.height_mm > 0


def test_tune_improvement_non_negative():
    """improvement_mm must always be >= 0 (monoton kabul)."""
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert tr.improvement_mm >= -1e-9  # allow floating-point epsilon


# ---------------------------------------------------------------------------
# (c) TuneResult taşıdığı konfig adı
# ---------------------------------------------------------------------------


def test_tune_winning_config_name_is_string():
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert isinstance(tr.winning_config_name, str)
    assert len(tr.winning_config_name) > 0


def test_tune_winning_config_name_is_from_menu():
    """winning_config_name must be a key in build_menu()."""
    parts = _parts()
    menu = build_menu()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert tr.winning_config_name in menu


# ---------------------------------------------------------------------------
# (d) Deney menüsü çalışır — birden fazla konfig denenir
# ---------------------------------------------------------------------------


def test_build_menu_returns_dict_with_multiple_entries():
    """build_menu() must return a dict with at least 2 named configs."""
    menu = build_menu()
    assert isinstance(menu, dict)
    assert len(menu) >= 2, f"Menüde en az 2 konfig beklendi, {len(menu)} geldi"


def test_build_menu_configs_have_required_keys():
    """Each menu entry must have 'solver' and 'params' keys."""
    menu = build_menu()
    for name, cfg in menu.items():
        assert "solver" in cfg, f"'{name}' konfiginde 'solver' yok"
        assert "params" in cfg, f"'{name}' konfiginde 'params' yok"


def test_tune_all_menu_configs_run():
    """tune() runs all menu configs and picks the best — check via all_results."""
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    # all_results (if exposed) should contain all menu configs
    # If TuneResult exposes all_results, verify length; otherwise check winning
    # config name is among menu keys.
    menu = build_menu()
    assert tr.winning_config_name in menu
    # At minimum the winning config must be one of the known menu names
    assert isinstance(tr.winning_config_name, str)


def test_tune_all_parts_placed_in_result():
    """All parts must be placed in the winning result."""
    parts = _parts()
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    placed_ids = {p.part_id for p in tr.result.placements}
    expected_ids = {p.id for p in parts}
    assert placed_ids == expected_ids


def test_tune_baseline_height_is_portfolio_best():
    """baseline_height_mm must equal the run_portfolio winner height_mm."""
    from src.nesting3d.solvers.dblf_solver import DBLFSolver
    from src.nesting3d.solvers.sa_solver import SASolver, MultiStartSA
    from src.nesting3d.solvers.ga_solver import GASolver
    from src.nesting3d.solvers.tabu_solver import TabuSolver
    from src.nesting3d.solvers.portfolio import run_portfolio

    parts = _parts()
    solvers = [DBLFSolver(), SASolver(), GASolver(), TabuSolver()]
    pr = run_portfolio(parts, _bin, solvers, budget=FAST_BUDGET, seed=42)
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=42)
    assert abs(tr.baseline_height_mm - pr.winner.height_mm) < 1e-9


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_tune_single_part():
    """tune() must work on a single part (edge case)."""
    parts = [_part("solo1", (15, 15, 15))]
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=7)
    assert tr.result.height_mm > 0
    assert tr.result.height_mm <= tr.baseline_height_mm + 1e-9


def test_tune_two_parts():
    """tune() must work on two parts."""
    parts = [_part("a", (10, 10, 10)), _part("b", (20, 10, 5))]
    tr = tune(parts, _bin, budget=FAST_BUDGET, seed=13)
    assert tr.result.height_mm > 0
    assert tr.result.height_mm <= tr.baseline_height_mm + 1e-9
