"""tests/test_gengap.py — TDD tests for gengap.py (generalization gap detector).

Test strategy:
  - All fixtures use in-memory TrainingRow lists (no disk I/O except telemetry test).
  - Scenarios explicitly constructed so overfit/healthy outcomes are deterministic.
  - No imports from bin3d/sa3d/dblf/voxelize (motor purity check via import).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import List

import pytest

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.gengap import (
    OVERFIT_GAP_THRESHOLD,
    MIN_INSTANCES,
    GenGapReport,
    compute_generalization_gap,
    compute_from_telemetry,
    _loo_cv_accuracy,
)
from src.nesting3d.selection.model import AlgorithmSelector


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_row(
    instance_id: str,
    winner: str,
    feature_val: float,
    *,
    is_easy: bool = False,
) -> TrainingRow:
    """Create a minimal TrainingRow for testing."""
    return TrainingRow(
        instance_id=instance_id,
        is_easy=is_easy,
        winner=winner,
        dblf_height=100.0,
        best_height=100.0,
        feature_vector=[feature_val],
        feature_names=["f0"],
        aile="test",
    )


def _make_table_uniform(n: int, winner: str = "sa3d") -> List[TrainingRow]:
    """Uniform table: all rows same winner, features spread evenly."""
    return [_make_row(f"inst_{i:03d}", winner, float(i)) for i in range(n)]


# ---------------------------------------------------------------------------
# SCENARIO 1: overfit
#
# Design: 1-NN memorises train. Train = 8 rows all labeled "sa3d" with
# clustered features [0..7]. Holdout = 2 rows labeled "dblf" with
# features [0.05, 0.06] (very close to train cluster -> 1-NN predicts "sa3d"
# which is WRONG for holdout).
# => train_acc = 1.0 (perfect in-sample), holdout_acc = 0.0, gap = 1.0 > 0.2
# ---------------------------------------------------------------------------

def _make_overfit_table() -> List[TrainingRow]:
    """
    8 train rows: winner='sa3d', features 10..17  (cluster A)
    2 holdout rows: winner='dblf', features 10.05, 10.06
      (nearest neighbour -> 'sa3d' -> wrong)
    Total 10 rows.  _split(holdout_ratio=0.2) -> train[:8], holdout[8:10]
    """
    rows = []
    # train cluster
    for i in range(8):
        rows.append(_make_row(f"train_{i:03d}", "sa3d", 10.0 + float(i)))
    # holdout: labeled dblf, features close to train cluster
    rows.append(_make_row("hold_000", "dblf", 10.05))
    rows.append(_make_row("hold_001", "dblf", 10.06))
    return rows


# ---------------------------------------------------------------------------
# SCENARIO 2: healthy (no overfit)
#
# Design: 10 rows all labeled 'sa3d', features spread uniformly.
# 1-NN will predict 'sa3d' for everyone including holdout.
# => train_acc = 1.0, holdout_acc = 1.0, gap = 0.0 <= 0.2
# ---------------------------------------------------------------------------

def _make_healthy_table() -> List[TrainingRow]:
    return _make_table_uniform(10, winner="sa3d")


# ---------------------------------------------------------------------------
# Basic contract tests
# ---------------------------------------------------------------------------

class TestGenGapReportDataclass:
    """GenGapReport dataclass contract."""

    def test_fields_present(self):
        r = GenGapReport(
            train_acc=0.9,
            holdout_acc=0.7,
            gap=0.2,
            prequential_acc=0.75,
            prequential_gap=0.15,
            n_train=8,
            n_holdout=2,
            overfit_flag=False,
            reason="ok",
        )
        assert r.train_acc == 0.9
        assert r.holdout_acc == 0.7
        assert r.gap == pytest.approx(0.2)
        assert r.prequential_acc == 0.75
        assert r.prequential_gap == 0.15
        assert r.n_train == 8
        assert r.n_holdout == 2
        assert r.overfit_flag is False
        assert r.reason == "ok"

    def test_to_dict_returns_dict(self):
        r = GenGapReport(
            train_acc=0.8,
            holdout_acc=0.6,
            gap=0.2,
            prequential_acc=0.65,
            prequential_gap=0.15,
            n_train=6,
            n_holdout=2,
            overfit_flag=False,
            reason="test",
        )
        d = r.to_dict()
        assert isinstance(d, dict)
        assert set(d.keys()) >= {
            "train_acc", "holdout_acc", "gap",
            "prequential_acc", "prequential_gap",
            "n_train", "n_holdout", "overfit_flag", "reason",
        }

    def test_to_dict_json_serializable(self):
        r = GenGapReport(
            train_acc=1.0,
            holdout_acc=0.5,
            gap=0.5,
            prequential_acc=0.6,
            prequential_gap=0.4,
            n_train=8,
            n_holdout=2,
            overfit_flag=True,
            reason="gap asildi",
        )
        # Must not raise
        serialized = json.dumps(r.to_dict())
        assert isinstance(serialized, str)

    def test_gap_field_equals_train_minus_holdout(self):
        r = GenGapReport(
            train_acc=0.9,
            holdout_acc=0.7,
            gap=0.2,
            prequential_acc=0.75,
            prequential_gap=0.15,
            n_train=8,
            n_holdout=2,
            overfit_flag=False,
            reason="ok",
        )
        assert r.gap == pytest.approx(r.train_acc - r.holdout_acc)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_overfit_threshold_is_0_2(self):
        assert OVERFIT_GAP_THRESHOLD == pytest.approx(0.2)

    def test_min_instances_is_6(self):
        assert MIN_INSTANCES == 6


# ---------------------------------------------------------------------------
# Insufficient data guard
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """n < MIN_INSTANCES -> early return, no crash, flag=False."""

    @pytest.mark.parametrize("n", [0, 1, 3, 5])
    def test_insufficient_n_returns_flag_false(self, n: int):
        table = _make_table_uniform(n)
        report = compute_generalization_gap(table)
        assert report.overfit_flag is False

    @pytest.mark.parametrize("n", [0, 1, 3, 5])
    def test_insufficient_n_reason_mentions_insufficient(self, n: int):
        table = _make_table_uniform(n)
        report = compute_generalization_gap(table)
        reason_lower = report.reason.lower()
        # Reason must communicate data shortage in some form
        assert any(
            kw in reason_lower
            for kw in ["yetersiz", "insufficient", "veri", "data", "az"]
        ), f"reason did not mention insufficient data: {report.reason!r}"

    @pytest.mark.parametrize("n", [0, 1, 3, 5])
    def test_insufficient_n_accs_are_zero(self, n: int):
        table = _make_table_uniform(n)
        report = compute_generalization_gap(table)
        assert report.train_acc == pytest.approx(0.0)
        assert report.holdout_acc == pytest.approx(0.0)
        assert report.prequential_acc == pytest.approx(0.0)

    def test_empty_table_does_not_crash(self):
        report = compute_generalization_gap([])
        assert isinstance(report, GenGapReport)
        assert report.overfit_flag is False


# ---------------------------------------------------------------------------
# SCENARIO 1: Overfit detection
# ---------------------------------------------------------------------------

class TestOverfitScenario:
    """Large gap (train=perfect, holdout=poor) -> overfit_flag=True."""

    def test_overfit_flag_is_true(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.overfit_flag is True, (
            f"Expected overfit_flag=True, got report={report}"
        )

    def test_train_acc_is_high(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.train_acc > 0.8, (
            f"Expected high train_acc, got {report.train_acc}"
        )

    def test_holdout_acc_is_low(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.holdout_acc < 0.5, (
            f"Expected low holdout_acc, got {report.holdout_acc}"
        )

    def test_gap_exceeds_threshold(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.gap > OVERFIT_GAP_THRESHOLD, (
            f"Expected gap > {OVERFIT_GAP_THRESHOLD}, got {report.gap}"
        )

    def test_reason_mentions_overfit(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        reason_lower = report.reason.lower()
        assert any(
            kw in reason_lower
            for kw in ["overfit", "ezber", "asild", "esik"]
        ), f"reason does not mention overfit: {report.reason!r}"

    def test_n_train_and_n_holdout_correct(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        # _split(10, 0.2) -> 8 train, 2 holdout
        assert report.n_train == 8
        assert report.n_holdout == 2

    def test_gap_equals_train_minus_holdout(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.gap == pytest.approx(report.train_acc - report.holdout_acc, abs=1e-9)


# ---------------------------------------------------------------------------
# SCENARIO 2: Healthy (no overfit)
# ---------------------------------------------------------------------------

class TestHealthyScenario:
    """Small gap -> overfit_flag=False."""

    def test_overfit_flag_is_false(self):
        table = _make_healthy_table()
        report = compute_generalization_gap(table)
        assert report.overfit_flag is False, (
            f"Expected overfit_flag=False, got report={report}"
        )

    def test_gap_within_threshold(self):
        table = _make_healthy_table()
        report = compute_generalization_gap(table)
        assert report.gap <= OVERFIT_GAP_THRESHOLD, (
            f"Expected gap <= {OVERFIT_GAP_THRESHOLD}, got {report.gap}"
        )

    def test_train_acc_high(self):
        table = _make_healthy_table()
        report = compute_generalization_gap(table)
        assert report.train_acc > 0.5

    def test_reason_says_no_overfit(self):
        table = _make_healthy_table()
        report = compute_generalization_gap(table)
        reason_lower = report.reason.lower()
        # Reason must NOT claim overfit
        assert "overfit yok" in reason_lower or "dar" in reason_lower or "no overfit" in reason_lower or "esik" in reason_lower, (
            f"reason unclear for healthy case: {report.reason!r}"
        )


# ---------------------------------------------------------------------------
# Prequential: no data leakage
# ---------------------------------------------------------------------------

class TestPrequential:
    """
    Test-then-train: a row must NOT be in training set when it is predicted.
    Concretely: prequential_acc should be < train_acc when model memorises.
    """

    def test_prequential_acc_below_train_acc_on_overfit(self):
        """
        In overfit scenario train is perfect (1.0).
        Prequential (rolling held-out) should yield < 1.0 because early
        instances have seen little data and face harder unseen patterns.
        """
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        # prequential_acc must be strictly less than train_acc
        # (in-sample perfect, but rolling test-then-train is not in-sample)
        assert report.prequential_acc < report.train_acc, (
            f"Expected prequential_acc < train_acc; "
            f"prequential={report.prequential_acc}, train={report.train_acc}"
        )

    def test_prequential_gap_equals_train_minus_prequential(self):
        table = _make_overfit_table()
        report = compute_generalization_gap(table)
        assert report.prequential_gap == pytest.approx(
            report.train_acc - report.prequential_acc, abs=1e-9
        )

    def test_prequential_seeds_not_tested(self):
        """
        First MIN_INSTANCES rows are seed-only (no test recorded for them).
        prequential_acc is computed only from rows after position MIN_INSTANCES.
        With exactly MIN_INSTANCES rows, no test is possible -> prequential_acc=0.0
        """
        table = _make_table_uniform(MIN_INSTANCES, winner="sa3d")
        report = compute_generalization_gap(table)
        # No instances tested in prequential (all are seed)
        assert report.prequential_acc == pytest.approx(0.0)

    def test_prequential_has_test_instances_beyond_seed(self):
        """With n > MIN_INSTANCES we must have at least one tested instance."""
        table = _make_table_uniform(MIN_INSTANCES + 2, winner="sa3d")
        report = compute_generalization_gap(table)
        # prequential_acc should be defined (0 or 1, not a sentinel)
        assert 0.0 <= report.prequential_acc <= 1.0

    def test_prequential_no_leakage_explicit(self):
        """
        Leakage test: create a table where first 6 rows all labeled 'sa3d'
        and row 7 labeled 'dblf' with a DIFFERENT feature cluster.
        If there were leakage (row 7 in train when predicted), 1-NN would
        trivially predict 'dblf' for row 7.  Without leakage it must predict
        from the prior 6 rows only -> 'sa3d' -> wrong.

        We verify prequential_acc < 1.0 for this table.
        """
        rows = []
        for i in range(6):
            # cluster A: feature=0..5, label=sa3d
            rows.append(_make_row(f"seed_{i}", "sa3d", float(i)))
        # row 7: feature=100 (far from cluster A), label=dblf
        # Without leakage: nearest in seed is 'sa3d' -> wrong prediction
        rows.append(_make_row("test_0", "dblf", 100.0))
        # Add a few more to ensure split is triggered
        rows.append(_make_row("test_1", "sa3d", 1.0))
        rows.append(_make_row("test_2", "sa3d", 2.0))

        report = compute_generalization_gap(rows)
        # prequential_acc must be < 1.0 because row "test_0" should be wrong
        assert report.prequential_acc < 1.0, (
            f"Possible leakage: prequential_acc={report.prequential_acc} "
            f"is perfect despite mismatched label in test_0"
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same table -> same report (no randomness)."""

    def test_same_table_same_report_healthy(self):
        table = _make_healthy_table()
        r1 = compute_generalization_gap(table)
        r2 = compute_generalization_gap(table)
        assert r1.train_acc == pytest.approx(r2.train_acc)
        assert r1.holdout_acc == pytest.approx(r2.holdout_acc)
        assert r1.gap == pytest.approx(r2.gap)
        assert r1.prequential_acc == pytest.approx(r2.prequential_acc)
        assert r1.overfit_flag == r2.overfit_flag

    def test_same_table_same_report_overfit(self):
        table = _make_overfit_table()
        r1 = compute_generalization_gap(table)
        r2 = compute_generalization_gap(table)
        assert r1.train_acc == pytest.approx(r2.train_acc)
        assert r1.holdout_acc == pytest.approx(r2.holdout_acc)
        assert r1.overfit_flag == r2.overfit_flag


# ---------------------------------------------------------------------------
# Motor purity: no forbidden imports
# ---------------------------------------------------------------------------

class TestMotorPurity:
    """gengap must not import bin3d/sa3d/dblf/voxelize."""

    def test_no_forbidden_imports(self):
        import importlib
        import ast
        import pathlib

        gengap_path = pathlib.Path(
            "C:/Users/erenk/OneDrive/Masaüstü/IE 488 Project/src/nesting3d/selection/gengap.py"
        )
        source = gengap_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden = {"bin3d", "sa3d", "dblf", "voxelize"}
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                else:
                    module = ""
                    for alias in node.names:
                        module += alias.name + " "
                for kw in forbidden:
                    if kw in module:
                        violations.append(module)

        assert not violations, f"Forbidden imports found: {violations}"


# ---------------------------------------------------------------------------
# compute_from_telemetry convenience wrapper
# ---------------------------------------------------------------------------

class TestComputeFromTelemetry:
    """compute_from_telemetry: load_telemetry -> build_training_table -> compute."""

    def _make_jsonl(self, tmp_path: Path, n_instances: int = 10) -> Path:
        """Write a minimal valid JSONL telemetry file."""
        from src.nesting3d.instances.features import FEATURE_NAMES

        p = tmp_path / "runs.jsonl"
        lines = []
        for i in range(n_instances):
            iid = f"inst_{i:03d}"
            # Two solvers per instance; sa3d always wins (lower height)
            for cozucu, height, winner_flag in [
                ("dblf", 110.0, False),
                ("sa3d", 100.0, True),
            ]:
                row = {
                    "ts": 1.0,
                    "kaynak": "benchmark",
                    "instance_id": iid,
                    "aile": "test",
                    "feature_names": list(FEATURE_NAMES),
                    "feature_vector": [float(i)] + [0.0] * (len(FEATURE_NAMES) - 1),
                    "cozucu": cozucu,
                    "pitch": 5.0,
                    "budget": 100,
                    "seed": 42,
                    "height_mm": height,
                    "density": 0.5,
                    "time_s": 1.0,
                    "winner_flag": winner_flag,
                }
                lines.append(json.dumps(row))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_returns_gen_gap_report(self, tmp_path: Path):
        p = self._make_jsonl(tmp_path, n_instances=10)
        report = compute_from_telemetry(p)
        assert isinstance(report, GenGapReport)

    def test_sufficient_data_gives_valid_accs(self, tmp_path: Path):
        p = self._make_jsonl(tmp_path, n_instances=10)
        report = compute_from_telemetry(p)
        assert 0.0 <= report.train_acc <= 1.0
        assert 0.0 <= report.holdout_acc <= 1.0
        assert 0.0 <= report.prequential_acc <= 1.0

    def test_nonexistent_file_gives_insufficient_data(self, tmp_path: Path):
        p = tmp_path / "nonexistent.jsonl"
        report = compute_from_telemetry(p)
        # load_telemetry returns [] for missing file -> insufficient data path
        assert report.overfit_flag is False
        reason_lower = report.reason.lower()
        assert any(
            kw in reason_lower
            for kw in ["yetersiz", "insufficient", "veri", "data", "az"]
        )

    def test_to_dict_json_serializable_from_telemetry(self, tmp_path: Path):
        p = self._make_jsonl(tmp_path, n_instances=10)
        report = compute_from_telemetry(p)
        serialized = json.dumps(report.to_dict())
        assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# Edge: exactly MIN_INSTANCES rows (boundary)
# ---------------------------------------------------------------------------

class TestBoundaryMinInstances:
    def test_exactly_min_instances_does_not_crash(self):
        table = _make_table_uniform(MIN_INSTANCES, winner="sa3d")
        report = compute_generalization_gap(table)
        assert isinstance(report, GenGapReport)

    def test_exactly_min_instances_flag_and_accs_sane(self):
        table = _make_table_uniform(MIN_INSTANCES, winner="sa3d")
        report = compute_generalization_gap(table)
        # With exactly MIN_INSTANCES: _split gives train and holdout
        # flag may be True or False, but accs must be in [0,1]
        assert 0.0 <= report.train_acc <= 1.0
        assert 0.0 <= report.holdout_acc <= 1.0

    def test_min_instances_minus_one_is_insufficient(self):
        table = _make_table_uniform(MIN_INSTANCES - 1)
        report = compute_generalization_gap(table)
        assert report.overfit_flag is False
        assert report.train_acc == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# model_factory parametrization (M2, EGITIM_EL_KITABI.md backlog #2)
#
# Kanit iki yonlu:
#   1. Ozel bir fake factory verilince ONUN kullanildigi (kayitli cagri +
#      farkli sonuc) kanitlanir.
#   2. model_factory verilmeyince (default) davranis eski davranisla
#      (explicit AlgorithmSelector ile) BIREBIR ayni kalir.
# ---------------------------------------------------------------------------

def _make_never_matching_factory():
    """Fake model_factory: her predict() cagrisinda hicbir winner ile
    eslesmeyecek sabit bir etiket doner. Cagri sayisini da kaydeder --
    boylece factory'nin gercekten kullanildigi (yok sayilmadigi) kanitlanir.
    """
    counter = {"n": 0}

    class _NeverMatchingModel:
        def fit(self, rows):  # noqa: D401 -- fake fit, no-op
            self._rows = rows

        def predict(self, feature_vector):
            return ("__FAKE_WINNER_ASLA_ESLESMEZ__", 0.0)

    def factory():
        counter["n"] += 1
        return _NeverMatchingModel()

    return factory, counter


class TestModelFactoryParametrization:
    """_loo_cv_accuracy / compute_generalization_gap model-parametrik mi?"""

    def test_loo_cv_accuracy_uses_custom_factory(self):
        table = _make_healthy_table()  # default 1-NN LOO acc yuksek olur
        default_acc = _loo_cv_accuracy(table)

        fake_factory, counter = _make_never_matching_factory()
        fake_acc = _loo_cv_accuracy(table, model_factory=fake_factory)

        assert counter["n"] > 0, "fake factory hic cagrilmadi -- parametre yok sayildi"
        assert fake_acc == pytest.approx(0.0), (
            "fake factory hicbir zaman dogru tahmin uretmemeli -> LOO acc 0.0"
        )
        assert fake_acc != pytest.approx(default_acc), (
            "fake factory kullanildiginin kaniti: sonuc default'tan farkli olmali"
        )

    def test_loo_cv_accuracy_default_matches_explicit_algorithmselector(self):
        """model_factory verilmezse davranis explicit AlgorithmSelector ile
        BIREBIR (bit-ozdes) ayni olmali -- geriye-uyum garantisi."""
        table = _make_overfit_table()
        acc_default = _loo_cv_accuracy(table)
        acc_explicit = _loo_cv_accuracy(table, model_factory=AlgorithmSelector)
        assert acc_default == pytest.approx(acc_explicit, abs=0.0)

    def test_compute_generalization_gap_uses_custom_factory(self):
        table = _make_healthy_table()
        report_default = compute_generalization_gap(table)

        fake_factory, counter = _make_never_matching_factory()
        report_fake = compute_generalization_gap(table, model_factory=fake_factory)

        assert counter["n"] > 0, "fake factory hic cagrilmadi -- parametre yok sayildi"
        assert report_fake.cv_acc == pytest.approx(0.0)
        assert report_fake.train_acc == pytest.approx(0.0)
        assert report_fake.cv_acc != pytest.approx(report_default.cv_acc)

    def test_compute_generalization_gap_default_bit_identical_to_explicit(self):
        """Eski davranis (parametre yokken) ile yeni parametreli cagrinin
        explicit AlgorithmSelector ile sonucu BIREBIR (bit-ozdes) ayni olmali."""
        for table in (_make_overfit_table(), _make_healthy_table()):
            r_default = compute_generalization_gap(table)
            r_explicit = compute_generalization_gap(table, model_factory=AlgorithmSelector)
            assert r_default.to_dict() == r_explicit.to_dict()

    def test_compute_from_telemetry_still_uses_default_factory(self, tmp_path: Path):
        """compute_from_telemetry additive wrapper -- model_factory parametresi
        eklenmedigi icin default (AlgorithmSelector) yolunu kullanmaya devam
        etmeli (geriye-uyum, public sozlesme kirilmadi)."""
        from src.nesting3d.instances.features import FEATURE_NAMES

        p = tmp_path / "runs.jsonl"
        lines = []
        for i in range(10):
            iid = f"inst_{i:03d}"
            for cozucu, height, winner_flag in [
                ("dblf", 110.0, False),
                ("sa3d", 100.0, True),
            ]:
                row = {
                    "ts": 1.0,
                    "kaynak": "benchmark",
                    "instance_id": iid,
                    "aile": "test",
                    "feature_names": list(FEATURE_NAMES),
                    "feature_vector": [float(i)] + [0.0] * (len(FEATURE_NAMES) - 1),
                    "cozucu": cozucu,
                    "pitch": 5.0,
                    "budget": 100,
                    "seed": 42,
                    "height_mm": height,
                    "density": 0.5,
                    "time_s": 1.0,
                    "winner_flag": winner_flag,
                }
                lines.append(json.dumps(row))
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

        report = compute_from_telemetry(p)
        assert isinstance(report, GenGapReport)
        assert 0.0 <= report.cv_acc <= 1.0
