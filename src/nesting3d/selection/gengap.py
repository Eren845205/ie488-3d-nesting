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
from src.nesting3d.selection.splits import stratified_holdout_split
from src.nesting3d.telemetry import load_telemetry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OVERFIT_GAP_THRESHOLD: float = 0.2
"""gap > this value -> overfit_flag = True."""

MIN_INSTANCES: int = 6
"""Minimum rows for meaningful statistics.  Below this: early return."""

# ---------------------------------------------------------------------------
# 1-NN ozel not (overfit dongusu sertlestirme, 2026-06-17)
# ---------------------------------------------------------------------------
# AlgorithmSelector 1-NN tabanli: egitim noktalarini saklar, her noktanin kendine
# en yakini KENDISIDIR (mesafe 0). Bu yuzden in-sample `train_acc` 1-NN icin
# YAPISAL olarak ~1.0'dir -- "ezber" degil, algoritmanin dogasi. Eski kapida
# overfit_flag = (train_acc - holdout_acc) > esik idi; bu, train_acc=1.0 sabiti
# yuzunden 1-NN'de SUREKLI yanlis-pozitif uretiyordu (gercek cesitli veride
# holdout_acc nadiren >= 0.8 olur -> model ASLA promote edilemezdi).
#
# Cozum: overfit_flag artik LEAVE-ONE-OUT cross-validation dogrulugu (`cv_acc`)
# ile hold-out dogrulugu (`holdout_acc`) arasindaki acik (`cv_gap`) uzerinden
# hesaplanir. LOO in-sample ezberi ICERMEZ (her nokta kendi disindaki komsuya
# bakar) -> 1-NN icin DOGRU genelleme tahmini. `train_acc`/`gap`/`prequential`
# alanlari raporda BILGI olarak kalir (geriye-uyum), ama flag'i artik cv_gap
# (ve veri-sizintisi sentineli olarak prequential) belirler.


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
    """True if cv_gap > OVERFIT_GAP_THRESHOLD or prequential_gap > OVERFIT_GAP_THRESHOLD.

    NOT: artik train_acc-tabanli `gap` DEGIL, LOO-CV tabanli `cv_gap` birincil
    sinyaldir (1-NN yapisal train_acc=1.0 yanlis-pozitifini onler)."""

    reason: str
    """Human-readable explanation of the verdict."""

    cv_acc: float = 0.0
    """Leave-one-out cross-validation accuracy (split-bagimsiz genelleme tahmini).
    1-NN icin in-sample ezberi ICERMEZ -> dogru overfit metrigi."""

    cv_gap: float = 0.0
    """cv_acc - holdout_acc.  overfit_flag'in birincil belirleyicisi."""

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
            "cv_acc": self.cv_acc,
            "cv_gap": self.cv_gap,
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


def _loo_cv_accuracy(
    table: List[TrainingRow],
) -> float:
    """Leave-one-out cross-validation dogrulugu (1-NN icin dogru genelleme metrigi).

    Her satir SIRAYLA test edilir: o satir CIKARILIR, kalan tum satirlarla
    AlgorithmSelector egitilir, cikarilan satir tahmin edilir. In-sample ezberi
    (1-NN'in kendine-mesafe-0 dogasi) ICERMEZ -> train_acc=1.0 yanlis-pozitifini
    onler.

    Bos veya tek satir -> 0.0 (anlamsiz).
    Determinizm: sira sabit, rastgelelik yok.
    """
    n = len(table)
    if n < 2:
        return 0.0
    n_correct = 0
    for i in range(n):
        train_slice = table[:i] + table[i + 1:]
        model = AlgorithmSelector()
        model.fit(train_slice)
        predicted, _conf = model.predict(table[i].feature_vector)
        if predicted == table[i].winner:
            n_correct += 1
    return n_correct / n


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
    # Train / holdout split -- STRATIFIED (aile-dengeli, isim-bagimsiz).
    # Tek aile + sirali tabloda eski _split ile ozdes (geriye-uyum).
    # ------------------------------------------------------------------
    train, holdout = stratified_holdout_split(table, holdout_ratio=0.2)
    n_train = len(train)
    n_holdout = len(holdout)

    # ------------------------------------------------------------------
    # Fit model on train
    # ------------------------------------------------------------------
    model = AlgorithmSelector()
    model.fit(train)

    # ------------------------------------------------------------------
    # In-sample (train_acc) -- 1-NN'de YAPISAL ~1.0 (bilgi amacli, flag'de DEGIL).
    # Out-of-sample (holdout_acc) -- stratified hold-out genelleme tahmini.
    # ------------------------------------------------------------------
    train_acc = _accuracy(model, train)
    holdout_acc = _accuracy(model, holdout)
    gap = train_acc - holdout_acc

    # ------------------------------------------------------------------
    # LOO-CV (cv_acc) -- split-bagimsiz, in-sample ezberi ICERMEYEN genelleme.
    # overfit_flag'in BIRINCIL belirleyicisi (1-NN icin dogru metrik).
    # ------------------------------------------------------------------
    cv_acc = _loo_cv_accuracy(table)
    cv_gap = cv_acc - holdout_acc

    # ------------------------------------------------------------------
    # Prequential accuracy (uses full table sequence) -- veri-sizintisi senteneli
    # ------------------------------------------------------------------
    prequential_acc = _prequential_accuracy(table)
    prequential_gap = train_acc - prequential_acc

    # ------------------------------------------------------------------
    # Overfit flag and reason
    #
    # Birincil: cv_gap (LOO vs hold-out) -- iki bagimsiz genelleme tahmini
    # arasinda buyuk acik = veri/aile sizintisi veya gercek overfit.
    # Ikincil: prequential_gap -- yine LOO-benzeri test-then-train; in-sample
    # train_acc'a gore degil, dusuk mutlak deger + cv_acc'tan kopus suphesi.
    # train_acc-tabanli `gap` artik flag'i BELIRLEMEZ (1-NN yapisal 1.0).
    # ------------------------------------------------------------------
    cv_overfit = cv_gap > OVERFIT_GAP_THRESHOLD
    preq_overfit = (cv_acc - prequential_acc) > OVERFIT_GAP_THRESHOLD
    overfit_flag = cv_overfit or preq_overfit

    if overfit_flag:
        parts = []
        if cv_overfit:
            parts.append(
                f"cv_acc(LOO)={cv_acc:.3f} holdout_acc={holdout_acc:.3f} "
                f"cv_gap={cv_gap:.3f}; esik {OVERFIT_GAP_THRESHOLD} asildi -> overfit"
            )
        if preq_overfit:
            parts.append(
                f"cv_acc(LOO)={cv_acc:.3f} prequential_acc={prequential_acc:.3f}; "
                f"esik asildi -> overfit (sizinti/drift suphesi)"
            )
        reason = "; ".join(parts)
    else:
        reason = (
            f"cv_acc(LOO)={cv_acc:.3f} holdout_acc={holdout_acc:.3f} "
            f"cv_gap={cv_gap:.3f}; esik {OVERFIT_GAP_THRESHOLD} altinda, overfit yok. "
            f"(bilgi: train_acc={train_acc:.3f} gap={gap:.3f} 1-NN yapisal; "
            f"prequential_acc={prequential_acc:.3f})."
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
        cv_acc=cv_acc,
        cv_gap=cv_gap,
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
