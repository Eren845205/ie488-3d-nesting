"""tests/test_selection_prefilter.py — EasyInstancePrefilter birim testleri."""
from __future__ import annotations

import pytest

from src.nesting3d.selection.dataset import TrainingRow, build_training_table
from src.nesting3d.selection.prefilter import EasyInstancePrefilter


def _row(
    instance_id: str,
    is_easy: bool,
    fv: list | None = None,
    winner: str = "dblf",
    dblf_height: float = 100.0,
    best_height: float = 100.0,
) -> TrainingRow:
    if fv is None:
        fv = [0.0] * 20
    return TrainingRow(
        instance_id=instance_id,
        is_easy=is_easy,
        winner=winner,
        dblf_height=dblf_height,
        best_height=best_height,
        feature_vector=fv,
        feature_names=[f"f{i}" for i in range(20)],
        aile="test",
    )


class TestEasyInstancePrefilterFit:
    def test_fit_with_empty_data_does_not_raise(self):
        pf = EasyInstancePrefilter()
        pf.fit([])

    def test_fit_stores_rows(self):
        rows = [_row("a", True), _row("b", False)]
        pf = EasyInstancePrefilter()
        pf.fit(rows)
        assert pf.n_train == 2

    def test_explain_returns_string(self):
        pf = EasyInstancePrefilter()
        pf.fit([_row("a", True), _row("b", False)])
        text = pf.explain()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_explain_is_readable(self):
        """Aciklama en az bir okunabilir kural icerir (rakam veya kelime)."""
        pf = EasyInstancePrefilter()
        rows = [
            _row("a", True, fv=[0.1] + [0.0] * 19),
            _row("b", False, fv=[0.9] + [0.0] * 19),
        ]
        pf.fit(rows)
        text = pf.explain()
        assert any(c.isdigit() or c.isalpha() for c in text)


class TestEasyInstancePrefilterPredict:
    def test_predict_returns_tuple(self):
        pf = EasyInstancePrefilter()
        pf.fit([_row("a", True)])
        result = pf.predict([0.0] * 20)
        assert isinstance(result, tuple)
        assert len(result) == 2
        is_easy, confidence = result
        assert isinstance(is_easy, bool)
        assert 0.0 <= confidence <= 1.0

    def test_not_fitted_raises(self):
        pf = EasyInstancePrefilter()
        with pytest.raises(RuntimeError):
            pf.predict([0.0] * 20)

    def test_no_easy_data_returns_false(self):
        """Hic kolay ornek yoksa konservatif: is_easy=False."""
        pf = EasyInstancePrefilter()
        pf.fit([_row("a", False, fv=[0.5] * 20)])
        is_easy, conf = pf.predict([0.5] * 20)
        assert is_easy is False

    def test_conservative_uncertain_returns_false(self):
        """Sinir bolgede konservatif davranir: soz konusu easy olmamali."""
        pf = EasyInstancePrefilter()
        # 1 kolay, 1 zor — esit dagitim — sinir bolgede kolay deme
        easy_fv = [0.1] * 20
        hard_fv = [0.9] * 20
        pf.fit([
            _row("easy", True, fv=easy_fv),
            _row("hard", False, fv=hard_fv),
        ])
        # Orta noktayi sor; konservatif: False donemeli (veya dusuk guven)
        mid_fv = [0.5] * 20
        is_easy, conf = pf.predict(mid_fv)
        # Konservatif kural: eger is_easy=True donduruyorsa guven yuksek olmali
        if is_easy:
            assert conf >= 0.7, "Kolay tahmininde guven en az 0.7 olmali"

    def test_clear_easy_region(self):
        """Ozellikleri kolay bolgeye acikca dusen ornekler icin True donmeli."""
        easy_fv = [0.1] + [0.0] * 19   # f0 dusuk = kolay
        hard_fv = [0.9] + [0.0] * 19   # f0 yuksek = zor
        pf = EasyInstancePrefilter()
        training = (
            [_row(f"e{i}", True, fv=[0.1] + [0.0] * 19) for i in range(5)]
            + [_row(f"h{i}", False, fv=[0.9] + [0.0] * 19) for i in range(5)]
        )
        pf.fit(training)
        is_easy, conf = pf.predict(easy_fv)
        assert is_easy is True
        assert conf >= 0.7

    def test_clear_hard_region(self):
        """Ozellikleri zor bolgeye dusen ornekler icin False donmeli."""
        easy_fv = [0.1] + [0.0] * 19
        hard_fv = [0.9] + [0.0] * 19
        pf = EasyInstancePrefilter()
        training = (
            [_row(f"e{i}", True, fv=easy_fv) for i in range(5)]
            + [_row(f"h{i}", False, fv=hard_fv) for i in range(5)]
        )
        pf.fit(training)
        is_easy, conf = pf.predict(hard_fv)
        assert is_easy is False


class TestEasyInstancePrefilterDeterminism:
    def test_same_input_same_output(self):
        rows = [
            _row("a", True, fv=[0.2] * 20),
            _row("b", False, fv=[0.8] * 20),
        ]
        pf1 = EasyInstancePrefilter()
        pf1.fit(rows)
        pf2 = EasyInstancePrefilter()
        pf2.fit(rows)

        fv = [0.3] * 20
        r1 = pf1.predict(fv)
        r2 = pf2.predict(fv)
        assert r1 == r2
