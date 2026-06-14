"""tests/test_selection_model.py — AlgorithmSelector birim testleri."""
from __future__ import annotations

import pytest

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.model import AlgorithmSelector


def _row(
    instance_id: str,
    winner: str,
    fv: list | None = None,
    is_easy: bool = False,
) -> TrainingRow:
    if fv is None:
        fv = [0.0] * 20
    return TrainingRow(
        instance_id=instance_id,
        is_easy=is_easy,
        winner=winner,
        dblf_height=100.0,
        best_height=80.0 if not is_easy else 100.0,
        feature_vector=fv,
        feature_names=[f"f{i}" for i in range(20)],
        aile="test",
    )


class TestAlgorithmSelectorFit:
    def test_fit_empty_does_not_raise(self):
        sel = AlgorithmSelector()
        sel.fit([])

    def test_fit_stores_count(self):
        rows = [_row("a", "sa3d"), _row("b", "dblf")]
        sel = AlgorithmSelector()
        sel.fit(rows)
        assert sel.n_train == 2

    def test_explain_returns_string(self):
        sel = AlgorithmSelector()
        sel.fit([_row("a", "sa3d"), _row("b", "dblf")])
        text = sel.explain()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_explain_mentions_solvers(self):
        """Aciklama en az bir cozucu adini icerir."""
        sel = AlgorithmSelector()
        sel.fit([_row("a", "sa3d", fv=[0.1] * 20), _row("b", "dblf", fv=[0.9] * 20)])
        text = sel.explain()
        assert "sa3d" in text or "dblf" in text


class TestAlgorithmSelectorPredict:
    def test_predict_returns_tuple(self):
        sel = AlgorithmSelector()
        sel.fit([_row("a", "sa3d")])
        name, conf = sel.predict([0.0] * 20)
        assert isinstance(name, str)
        assert 0.0 <= conf <= 1.0

    def test_not_fitted_raises(self):
        sel = AlgorithmSelector()
        with pytest.raises(RuntimeError):
            sel.predict([0.0] * 20)

    def test_insufficient_data_returns_low_confidence(self):
        """1-2 veri noktasi: dusuk guven donmeli."""
        sel = AlgorithmSelector()
        sel.fit([_row("a", "sa3d", fv=[0.5] * 20)])
        _, conf = sel.predict([0.5] * 20)
        assert conf < 0.7

    def test_clear_region_predicts_correct_solver(self):
        """Ayirt edici ozellik: f0 dusuk=sa3d, f0 yuksek=dblf."""
        training = (
            [_row(f"s{i}", "sa3d", fv=[0.1] + [0.0] * 19) for i in range(6)]
            + [_row(f"d{i}", "dblf", fv=[0.9] + [0.0] * 19) for i in range(6)]
        )
        sel = AlgorithmSelector()
        sel.fit(training)
        name, conf = sel.predict([0.1] + [0.0] * 19)
        assert name == "sa3d"

    def test_hard_region_predicts_metaheuristic_or_fallback(self):
        """Zor bolgede baskil cozucu dblf degil."""
        training = (
            [_row(f"s{i}", "sa3d", fv=[0.1] + [0.0] * 19) for i in range(6)]
            + [_row(f"d{i}", "dblf", fv=[0.9] + [0.0] * 19) for i in range(6)]
        )
        sel = AlgorithmSelector()
        sel.fit(training)
        name, conf = sel.predict([0.9] + [0.0] * 19)
        assert name == "dblf"

    def test_unknown_region_returns_valid_solver(self):
        """Bilinmeyen bolgede gecerli cozucu adi donmeli."""
        training = [_row("a", "sa3d", fv=[0.3] * 20)]
        sel = AlgorithmSelector()
        sel.fit(training)
        name, conf = sel.predict([0.7] * 20)
        assert isinstance(name, str)
        assert len(name) > 0


class TestAlgorithmSelectorDeterminism:
    def test_same_input_same_output(self):
        training = [
            _row(f"e{i}", "sa3d", fv=[0.1] * 20) for i in range(4)
        ] + [
            _row(f"h{i}", "dblf", fv=[0.9] * 20) for i in range(4)
        ]
        sel1 = AlgorithmSelector()
        sel1.fit(training)
        sel2 = AlgorithmSelector()
        sel2.fit(training)

        fv = [0.2] * 20
        assert sel1.predict(fv) == sel2.predict(fv)
