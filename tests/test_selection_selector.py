"""tests/test_selection_selector.py — Orkestrateur (selector.py) birim testleri.

Guvenlik degismezleri:
  1. MONOTON: selector sonucu asla DBLF taban baseline'indan daha kotu olamaz.
  2. GUVENSIZLIK -> TAM PORTFOY: dusuk guven / yetersiz veri -> full_portfolio_fallback.
  3. KOLAY: easy_dblf yolu metaheuristigi atlar, sadece DBLF kosar.
  4. DETERMINIZM: ayni giris+seed -> ayni SelectionResult.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.selection.selector import (
    SelectionResult,
    select_and_solve,
    SolvePath,
)


# ---------------------------------------------------------------------------
# Yardimci sahte objeler
# ---------------------------------------------------------------------------

def _fake_solve_result(height: float, solver_name: str = "dblf") -> SolveResult:
    return SolveResult(
        placements=[],
        bin3d=MagicMock(),
        height_mm=height,
        density=0.5,
        time_s=0.01,
        history=[],
        meta={"solver": solver_name, "params": {}},
    )


class FakeSolver:
    def __init__(self, name: str, height: float):
        self._name = name
        self._height = height
        self.call_count = 0

    def solve(self, parts, bin_factory, *, budget, seed, order_key=None):
        self.call_count += 1
        return _fake_solve_result(self._height, self._name)


class FakePrefilter:
    def __init__(self, is_easy: bool, confidence: float = 0.9):
        self._is_easy = is_easy
        self._confidence = confidence
        self.predict_count = 0

    def predict(self, features):
        self.predict_count += 1
        return (self._is_easy, self._confidence)

    def explain(self):
        return f"easy={self._is_easy}"


class FakeModel:
    def __init__(self, solver_name: str, confidence: float = 0.9):
        self._solver = solver_name
        self._confidence = confidence
        self.predict_count = 0

    def predict(self, features):
        self.predict_count += 1
        return (self._solver, self._confidence)

    def explain(self):
        return f"winner={self._solver}"


# ---------------------------------------------------------------------------
# Testler — SelectionResult
# ---------------------------------------------------------------------------

class TestSelectionResult:
    def test_has_required_fields(self):
        sr = SelectionResult(
            solve_result=_fake_solve_result(100.0),
            path=SolvePath.EASY_DBLF,
            reason="test",
            dblf_baseline=100.0,
        )
        assert hasattr(sr, "solve_result")
        assert hasattr(sr, "path")
        assert hasattr(sr, "reason")
        assert hasattr(sr, "dblf_baseline")

    def test_path_values(self):
        """SolvePath enum degerleri dogrula."""
        assert SolvePath.EASY_DBLF is not None
        assert SolvePath.SELECTED is not None
        assert SolvePath.FULL_PORTFOLIO_FALLBACK is not None


# ---------------------------------------------------------------------------
# Testler — MONOTON degismezi
# ---------------------------------------------------------------------------

class TestMonotonicityInvariant:
    def _build_instance_and_parts(self):
        """Minimal sahte instance (extract_features gerekmez — fv inject edilir)."""
        instance = MagicMock()
        parts = []
        bin_factory = lambda: MagicMock()
        return instance, parts, bin_factory

    def test_easy_path_returns_dblf_baseline(self):
        """Kolay yolda DBLF kosulur; sonuc DBLF height'ini tasir."""
        instance, parts, bin_factory = self._build_instance_and_parts()
        dblf_solver = FakeSolver("dblf", 80.0)
        prefilter = FakePrefilter(is_easy=True, confidence=0.95)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=None,
            )

        assert result.path == SolvePath.EASY_DBLF
        assert result.solve_result.height_mm == 80.0
        assert result.dblf_baseline == 80.0

    def test_selected_path_never_worse_than_dblf(self):
        """Secilen cozucu DBLF'den kotu sonuc verirse DBLF sonucu kullanilir."""
        instance, parts, bin_factory = self._build_instance_and_parts()
        dblf_solver = FakeSolver("dblf", 70.0)
        bad_solver = FakeSolver("sa3d", 120.0)  # DBLF'den daha kotu
        prefilter = FakePrefilter(is_easy=False, confidence=0.9)
        model = FakeModel("sa3d", confidence=0.85)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._solver_by_name",
            return_value=bad_solver,
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=model,
            )

        # Sonuc DBLF baseline'indan asla kotu olmamali
        assert result.solve_result.height_mm <= result.dblf_baseline + 1e-9
        assert result.dblf_baseline == 70.0

    def test_full_portfolio_fallback_picks_best(self):
        """Tam portfoy fallback: en iyi sonucu dondurur (en az DBLF kadar iyi)."""
        instance, parts, bin_factory = self._build_instance_and_parts()
        prefilter = FakePrefilter(is_easy=False, confidence=0.3)  # dusuk guven
        model = FakeModel("sa3d", confidence=0.3)

        dblf_solver = FakeSolver("dblf", 90.0)
        sa_solver = FakeSolver("sa3d", 75.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            return_value=[dblf_solver, sa_solver],
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=model,
            )

        assert result.path == SolvePath.FULL_PORTFOLIO_FALLBACK
        assert result.solve_result.height_mm <= result.dblf_baseline + 1e-9


# ---------------------------------------------------------------------------
# Testler — GUVENSIZLIK -> PORTFOY
# ---------------------------------------------------------------------------

class TestFallbackOnLowConfidence:
    def _setup(self):
        instance = MagicMock()
        parts = []
        bin_factory = lambda: MagicMock()
        return instance, parts, bin_factory

    def test_model_none_uses_full_portfolio(self):
        """Model None -> tam portfoy."""
        instance, parts, bin_factory = self._setup()
        prefilter = FakePrefilter(is_easy=False, confidence=0.9)
        dblf_solver = FakeSolver("dblf", 100.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            return_value=[dblf_solver],
        ) as mock_port:
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=None,
            )
        assert result.path == SolvePath.FULL_PORTFOLIO_FALLBACK

    def test_low_confidence_model_uses_full_portfolio(self):
        """Model dusuk guven -> tam portfoy."""
        instance, parts, bin_factory = self._setup()
        prefilter = FakePrefilter(is_easy=False, confidence=0.9)
        model = FakeModel("sa3d", confidence=0.4)  # esik altinda
        dblf_solver = FakeSolver("dblf", 100.0)
        sa_solver = FakeSolver("sa3d", 90.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            return_value=[dblf_solver, sa_solver],
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=model,
            )
        assert result.path == SolvePath.FULL_PORTFOLIO_FALLBACK

    def test_no_prefilter_and_no_model_uses_full_portfolio(self):
        """Ikisi de None -> tam portfoy fallback."""
        instance, parts, bin_factory = self._setup()
        dblf_solver = FakeSolver("dblf", 100.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            return_value=[dblf_solver],
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=None, model=None,
            )
        assert result.path == SolvePath.FULL_PORTFOLIO_FALLBACK


# ---------------------------------------------------------------------------
# Testler — EASY PATH
# ---------------------------------------------------------------------------

class TestEasyPath:
    def test_easy_instance_skips_metaheuristic(self):
        """Kolay tahmin: sadece DBLF kosulur, model predict edilmez."""
        instance = MagicMock()
        parts = []
        bin_factory = lambda: MagicMock()
        prefilter = FakePrefilter(is_easy=True, confidence=0.95)
        model = FakeModel("sa3d", confidence=0.95)
        dblf_solver = FakeSolver("dblf", 60.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=prefilter, model=model,
            )

        assert result.path == SolvePath.EASY_DBLF
        assert model.predict_count == 0  # model hic cagirilmadi


# ---------------------------------------------------------------------------
# Testler — DETERMINIZM
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_same_result(self):
        """Ayni giris+seed -> birebir ayni SelectionResult."""
        instance = MagicMock()
        parts = []
        bin_factory = lambda: MagicMock()
        prefilter = FakePrefilter(is_easy=False, confidence=0.3)
        model = FakeModel("sa3d", confidence=0.3)
        dblf_a = FakeSolver("dblf", 100.0)
        dblf_b = FakeSolver("dblf", 100.0)

        kwargs = dict(budget=30, seed=42, prefilter=prefilter, model=model)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            side_effect=[dblf_a, dblf_b],
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            side_effect=[
                [dblf_a],
                [dblf_b],
            ],
        ):
            r1 = select_and_solve(instance, parts, bin_factory, **kwargs)
            r2 = select_and_solve(instance, parts, bin_factory, **kwargs)

        assert r1.path == r2.path
        assert r1.solve_result.height_mm == r2.solve_result.height_mm


# ---------------------------------------------------------------------------
# Testler — EXPLAIN / reason
# ---------------------------------------------------------------------------

class TestReasonField:
    def test_reason_is_string(self):
        instance = MagicMock()
        parts = []
        bin_factory = lambda: MagicMock()
        dblf_solver = FakeSolver("dblf", 100.0)

        with patch(
            "src.nesting3d.selection.selector.extract_features",
            return_value=MagicMock(values=[0.0] * 20),
        ), patch(
            "src.nesting3d.selection.selector.DBLFSolver",
            return_value=dblf_solver,
        ), patch(
            "src.nesting3d.selection.selector._build_full_portfolio",
            return_value=[dblf_solver],
        ):
            result = select_and_solve(
                instance, parts, bin_factory,
                budget=30, seed=42,
                prefilter=None, model=None,
            )

        assert isinstance(result.reason, str)
        assert len(result.reason) > 0
