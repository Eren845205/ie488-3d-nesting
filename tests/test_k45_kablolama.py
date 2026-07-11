# -*- coding: utf-8 -*-
"""K-45 kablolama testleri: sampiyon recetesi (solve_nfv_kalite) + no-go
plumbing + 2mm kural sabiti.

Kanit zinciri: K-36/38/41/44 (MOTOR/YONTEM_HARITASI §3). Recete:
  pitch == clearance (K-38 kuantizasyon) · once ham, kilit>0 ise exit_guard
  (K-41/44) · rot denetimi recetede YOK (K-42 maliyet dersi).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.nesting3d.nfv_solve import solve_nfv_kalite


def _fake_result(h):
    return SimpleNamespace(height_mm=float(h), placements=[SimpleNamespace()],
                           fine_voxel_parts={})


class _SolveSpy:
    """solve_nfv imza-uyumlu casus: cagri kayitlari + sirali sonuclar."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, instance, *, plate_w_mm, plate_d_mm, fine_pitch,
                 quality, seed, n_orientations, time_budget_sec,
                 clearance_mm, no_go_bounds, exit_guard=False):
        self.calls.append({"fine_pitch": fine_pitch, "clearance_mm": clearance_mm,
                           "no_go_bounds": no_go_bounds, "exit_guard": exit_guard,
                           "quality": quality, "seed": seed})
        return self.results.pop(0)


def _check_seq(locks):
    seq = list(locks)

    def check(placements, parts):
        return SimpleNamespace(n_locked=seq.pop(0))
    return check


def test_kalite_ham_kilitsiz_guard_odenmez():
    """K-44 deseni: ham kilit 0 -> guard HIC kosulmaz, ham secilir."""
    spy = _SolveSpy([_fake_result(223.5)])
    res, tel = solve_nfv_kalite(
        object(), plate_w_mm=335.0, plate_d_mm=335.0, clearance_mm=2.0,
        no_go_bounds=((152.5, 0.2), (185.5, 45.0)),
        _solve=spy, _check_5dir=_check_seq([0]))
    assert res.height_mm == 223.5
    assert len(spy.calls) == 1  # guard cagrilmadi
    assert tel["secilen"] == "ham" and tel["guard_kosuldu"] is False
    assert tel["ham_n_locked"] == 0


def test_kalite_pitch_clearance_esittir():
    """K-38 kurali: solve'a giden fine_pitch == clearance_mm (tam pencere)."""
    spy = _SolveSpy([_fake_result(100.0)])
    solve_nfv_kalite(object(), plate_w_mm=300.0, plate_d_mm=300.0,
                     clearance_mm=2.0, _solve=spy, _check_5dir=_check_seq([0]))
    assert spy.calls[0]["fine_pitch"] == 2.0
    assert spy.calls[0]["clearance_mm"] == 2.0


def test_kalite_ham_kilitli_guard_kazanir():
    """K-41 deseni: ham kilitli (532/29) -> guard kosulur, kilitsiz guard secilir."""
    spy = _SolveSpy([_fake_result(532.0), _fake_result(544.5)])
    res, tel = solve_nfv_kalite(
        object(), plate_w_mm=335.0, plate_d_mm=335.0, clearance_mm=2.0,
        _solve=spy, _check_5dir=_check_seq([29, 0]))
    assert res.height_mm == 544.5
    assert len(spy.calls) == 2
    assert spy.calls[1]["exit_guard"] is True
    assert tel["secilen"] == "guard" and tel["guard_n_locked"] == 0
    assert tel["ham_n_locked"] == 29


def test_kalite_iki_bacak_da_kilitli_alcak_secilir():
    """Ikisi de kilitliyse dusuk yukseklik secilir (rapor INVALID'i tasir)."""
    spy = _SolveSpy([_fake_result(500.0), _fake_result(520.0)])
    res, tel = solve_nfv_kalite(
        object(), plate_w_mm=335.0, plate_d_mm=335.0, clearance_mm=2.0,
        _solve=spy, _check_5dir=_check_seq([10, 5]))
    assert res.height_mm == 500.0
    assert tel["secilen"] == "ham"


def test_kalite_no_go_iki_bacaga_da_gecer():
    ng = ((152.5, 0.2), (185.5, 45.0))
    spy = _SolveSpy([_fake_result(10.0), _fake_result(11.0)])
    solve_nfv_kalite(object(), plate_w_mm=335.0, plate_d_mm=335.0,
                     clearance_mm=2.0, no_go_bounds=ng,
                     _solve=spy, _check_5dir=_check_seq([3, 0]))
    assert spy.calls[0]["no_go_bounds"] == ng
    assert spy.calls[1]["no_go_bounds"] == ng


def test_web_min_clearance_2mm_politikasi():
    """A2 guncel kural (hoca 2026-07-09 cevap 5): app sabiti 2.0mm."""
    from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
    assert WEB_MIN_CLEARANCE_MM == 2.0


# --- no-go cozumu (plate_config.resolve_no_go) ---

def test_resolve_no_go_json(tmp_path):
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "plate.local.json").write_text(json.dumps({
        "width_mm": 335, "depth_mm": 335,
        "no_go": [[152.5, 0.2], [185.5, 45.0]],
    }), encoding="utf-8")
    from src.runtime.plate_config import resolve_no_go
    assert resolve_no_go(tmp_path) == ((152.5, 0.2), (185.5, 45.0))


def test_resolve_no_go_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATE_NOGO", "152.5,0.2,185.5,45")
    from src.runtime.plate_config import resolve_no_go
    assert resolve_no_go(tmp_path) == ((152.5, 0.2), (185.5, 45.0))


def test_resolve_no_go_yok(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_NOGO", raising=False)
    from src.runtime.plate_config import resolve_no_go
    assert resolve_no_go(tmp_path) is None


def test_resolve_no_go_gecersiz_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATE_NOGO", "bozuk,veri")
    from src.runtime.plate_config import resolve_no_go
    assert resolve_no_go(tmp_path) is None


def test_resolve_no_go_ters_sinir_reddedilir(tmp_path):
    cfg = tmp_path / "configs"
    cfg.mkdir()
    (cfg / "plate.local.json").write_text(json.dumps({
        "no_go": [[185.5, 45.0], [152.5, 0.2]],  # x1>x2 ters
    }), encoding="utf-8")
    from src.runtime.plate_config import resolve_no_go
    assert resolve_no_go(tmp_path) is None


# --- _bin_factory no-go maskesi ---

def test_bin_factory_no_go_maskesi_kurulur():
    from scripts.demo_pipeline import _bin_factory
    container = {"width_mm": 100.0, "depth_mm": 100.0, "height_mm": 200.0}
    b = _bin_factory(container, pitch=5.0, clearance_mm=2.0,
                     no_go_bounds=((10.0, 10.0), (30.0, 30.0)))()
    assert b._no_go is not None and b._no_go.any()
    b2 = _bin_factory(container, pitch=5.0, clearance_mm=2.0)()
    assert b2._no_go is None
