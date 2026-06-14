"""selection/gengap.py -- Generalization gap (overfit) detector.

Tracks the gap between in-sample train accuracy and out-of-sample holdout
accuracy as a cheap overfit signal.  Also computes prequential
(rolling test-then-train) accuracy to detect data leakage and temporal drift.

Public API
----------
    GenGapReport           -- result dataclass
    compute_generalization_gap(table) -> GenGapReport
    compute_from_telemetry(telemetry_path) -> GenGapReport

Motor purity: this module ONLY touches selection/ meta-layer.
No imports from bin3d, sa3d, dblf, voxelize.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Union

from src.nesting3d.selection.dataset import TrainingRow, build_training_table
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.telemetry import load_telemetry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERFIT_GAP_THRESHOLD: float = 0.2
"""gap > this value -> overfit_flag = True."""

MIN_INSTANCES: int = 6
"""Minimum rows for meaningful statistics.  Below this: early return."""


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class GenGapReport:
    """Result of generalization gap analysis."""

    train_acc: float
    """In-sample accuracy (model trained and evaluated on same train set)."""

    holdout_acc: float
    """Out-of-sample accuracy (model trained on train, evaluated on holdout)."""

    gap: float
    """train_acc - holdout_acc.  High value signals overfitting."""

    prequential_acc: float
    """Prequential (rolling test-then-train) accuracy across all test positions."""

    prequential_gap: float
    """train_acc - prequential_acc."""

    n_train: int
    """Number of instances in the train split."""

    n_holdout: int
    """Number of instances in the holdout split."""

    overfit_flag: bool
    """True if gap > OVERFIT_GAP_THRESHOLD or prequential_gap > OVERFIT_GAP_THRESHOLD."""

    reason: str
    """Human-readable explanation of the verdict."""

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary."""
        return {
            "train_acc": self.train_acc,
            "holdout_acc": self.holdout_acc,
            "gap": self.gap,
            "prequential_acc": self.prequential_acc,
            "prequential_gap": self.prequential_gap,
            "n_train": self.n_train,
            "n_holdout": self.n_holdout,
            "overfit_flag": self.overfit_flag,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split(
    table: List[TrainingRow],
    holdout_ratio: float = 0.2,
):
    """Deterministic split: last holdout_ratio fraction becomes holdout.

    Mirrors scripts/build_selection_model.py::_split exactly.
    """
    n = len(table)
    if n == 0:
        return [], []
    n_holdout = max(1, round(n * holdout_ratio))
    train = table[: n - n_holdout]
    holdout = table[n - n_holdout :]
    return train, holdout


def _accuracy(
    model: AlgorithmSelector,
    rows: List[TrainingRow],
) -> float:
    """Fraction of rows where model.predict gives the correct winner."""
    if not rows:
        return 0.0
    correct = 0
    for row in rows:
        predicted_solver, _conf = model.predict(row.feature_vector)
        if predicted_solver == row.winner:
            correct += 1
    return correct / len(rows)


def _prequential_accuracy(
    table: List[TrainingRow],
) -> float:
    """Compute prequential (rolling test-then-train) accuracy.

    Protocol:
      - First MIN_INSTANCES rows: seed only (added to train, NOT tested).
      - For each subsequent row i:
          1. Fit a fresh AlgorithmSelector on rows[0..i-1].
          2. Predict row[i].winner.
          3. Record correct/wrong.
          4. Add row[i] to the running train set (test-then-train).
      - Return fraction correct over all tested rows.

    If no rows are tested (table length <= MIN_INSTANCES) return 0.0.
    """
    if len(table) <= MIN_INSTANCES:
        return 0.0

    n_correct = 0
    n_tested = 0

    for i in range(MIN_INSTANCES, len(table)):
        train_slice = table[:i]   # rows 0..i-1 (does NOT include row i)
        model = AlgorithmSelector()
        model.fit(train_slice)
        predicted, _conf = model.predict(table[i].feature_vector)
        if predicted == table[i].winner:
            n_correct += 1
        n_tested += 1

    if n_tested == 0:
        return 0.0
    return n_correct / n_tested


# ---------------------------------------------------------------------------
# Main compute function
# ---------------------------------------------------------------------------

def compute_generalization_gap(
    table: List[TrainingRow],
) -> GenGapReport:
    """Compute generalization gap report for a training table.

    Steps:
      1. If n < MIN_INSTANCES: return insufficient-data report.
      2. Split into train / holdout with _split(holdout_ratio=0.2).
      3. Fit AlgorithmSelector on train.
      4. Evaluate train_acc (in-sample) and holdout_acc (out-of-sample).
      5. Compute gap = train_acc - holdout_acc.
      6. Compute prequential_acc and prequential_gap.
      7. Set overfit_flag = gap > threshold OR prequential_gap > threshold.
      8. Build reason string.

    Args:
        table: List of TrainingRow instances (order matters for split).

    Returns:
        GenGapReport with all fields populated.
    """
    n = len(table)

    # ------------------------------------------------------------------
    # Early return: insufficient data
    # ------------------------------------------------------------------
    if n < MIN_INSTANCES:
        return GenGapReport(
            train_acc=0.0,
            holdout_acc=0.0,
            gap=0.0,
            prequential_acc=0.0,
            prequential_gap=0.0,
            n_train=n,
            n_holdout=0,
            overfit_flag=False,
            reason=(
                f"veri yetersiz: {n} instance < MIN_INSTANCES={MIN_INSTANCES}; "
                "istatistik anlamsiz, flag=False."
            ),
        )

    # ------------------------------------------------------------------
    # Train / holdout split
    # ------------------------------------------------------------------
    train, holdout = _split(table, holdout_ratio=0.2)
    n_train = len(train)
    n_holdout = len(holdout)

    # ------------------------------------------------------------------
    # Fit model on train
    # ------------------------------------------------------------------
    model = AlgorithmSelector()
    model.fit(train)

    # ------------------------------------------------------------------
    # In-sample and out-of-sample accuracy
    # ------------------------------------------------------------------
    train_acc = _accuracy(model, train)
    holdout_acc = _accuracy(model, holdout)
    gap = train_acc - holdout_acc

    # ------------------------------------------------------------------
    # Prequential accuracy (uses full table sequence)
    # ------------------------------------------------------------------
    prequential_acc = _prequential_accuracy(table)
    prequential_gap = train_acc - prequential_acc

    # ------------------------------------------------------------------
    # Overfit flag and reason
    # ------------------------------------------------------------------
    gap_overfit = gap > OVERFIT_GAP_THRESHOLD
    preq_overfit = prequential_gap > OVERFIT_GAP_THRESHOLD
    overfit_flag = gap_overfit or preq_overfit

    if overfit_flag:
        parts = []
        if gap_overfit:
            parts.append(
                f"train_acc={train_acc:.3f} holdout_acc={holdout_acc:.3f} "
                f"gap={gap:.3f}; esik {OVERFIT_GAP_THRESHOLD} asildi -> overfit"
            )
        if preq_overfit:
            parts.append(
                f"prequential_acc={prequential_acc:.3f} "
                f"prequential_gap={prequential_gap:.3f}; esik asildi -> overfit"
            )
        reason = "; ".join(parts)
    else:
        reason = (
            f"train_acc={train_acc:.3f} holdout_acc={holdout_acc:.3f} "
            f"gap={gap:.3f}; esik {OVERFIT_GAP_THRESHOLD} altinda, overfit yok. "
            f"prequential_acc={prequential_acc:.3f} prequential_gap={prequential_gap:.3f}."
        )

    return GenGapReport(
        train_acc=train_acc,
        holdout_acc=holdout_acc,
        gap=gap,
        prequential_acc=prequential_acc,
        prequential_gap=prequential_gap,
        n_train=n_train,
        n_holdout=n_holdout,
        overfit_flag=overfit_flag,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Convenience wrapper: telemetry path -> report
# ---------------------------------------------------------------------------

def compute_from_telemetry(
    telemetry_path: Union[str, Path],
) -> GenGapReport:
    """Load telemetry JSONL, build training table, compute generalization gap.

    Args:
        telemetry_path: Path to JSONL telemetry file.
                        Missing file -> empty telemetry -> insufficient data.

    Returns:
        GenGapReport.
    """
    rows = load_telemetry(telemetry_path)
    table = build_training_table(rows, epsilon_mm=0.5)
    return compute_generalization_gap(table)
