"""selection/model.py — AlgorithmSelector (kazanan cozucu tahmini).

Yontem — 1-NN prototip siniflandiricisi + yorumlanabilir kural:
  Egitim verisi az (su an 17 instance) -> kara kutu yasak, sklearn yasak.
  1-NN (en yakin egitim ornegi) yorumlanabilir: "bu ornege en cok benzeyen
  gozlemde X kazanmisti" -> kural olarak anlasilabilir.

Guven metrigi:
  - Egitim verisi < MIN_DATA_THRESHOLD ise -> dusuk guven (<= 0.5) doner.
  - 1-NN guven = 1 / (1 + mesafe). Mesafe 0 -> guven 1.0; buyuk mesafe -> kucuk.
  - Guven < CONFIDENCE_THRESHOLD ise selector tam portfoye dusar (bkz selector.py).

sklearn YOK — sadece standart kutuphane.
Kara kutu YOK — explain() okunabilir prototip referansi verir.
Determinizm: mesafe esitinde alfabetik secim.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from src.nesting3d.selection.dataset import TrainingRow


class AlgorithmSelector:
    """Kazanan cozucu tahmincisi (1-NN prototip + yorumlanabilir).

    Kullanim::

        sel = AlgorithmSelector()
        sel.fit(training_rows)
        solver_name, confidence = sel.predict(feature_vector)
        print(sel.explain())
    """

    MIN_DATA_THRESHOLD: int = 4      # bu sayinin altinda veri yetersiz
    CONFIDENCE_THRESHOLD: float = 0.6  # esik altinda selector portfoye duser
    LOW_CONF_CEILING: float = 0.49    # yetersiz veri durumunda max guven

    def __init__(self) -> None:
        self._fitted: bool = False
        self._training: List[TrainingRow] = []
        self.n_train: int = 0
        self._solver_counts: dict = {}

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------

    def fit(self, rows: List[TrainingRow]) -> None:
        """Egitim verisiyle modeli egit (1-NN: satirlari sakla)."""
        self._fitted = True
        self._training = list(rows)
        self.n_train = len(rows)

        # Cozucu frekanslarini say (explain icin)
        self._solver_counts = {}
        for r in rows:
            self._solver_counts[r.winner] = (
                self._solver_counts.get(r.winner, 0) + 1
            )

    # ------------------------------------------------------------------
    # predict
    # ------------------------------------------------------------------

    def predict(self, features: List[float]) -> Tuple[str, float]:
        """Ozellik vektorune gore kazanan cozucu tahmin et.

        Returns:
            (solver_name: str, confidence: float)
            confidence < CONFIDENCE_THRESHOLD ise selector portfoye duser.

        Raises:
            RuntimeError: fit() cagrilmamissa.
        """
        if not self._fitted:
            raise RuntimeError(
                "AlgorithmSelector.predict(): once fit() cagirilmali."
            )

        if not self._training:
            return ("dblf", 0.0)

        # Veri yetersiz: en sik cozucuyu dondur ama dusuk guven
        if self.n_train < self.MIN_DATA_THRESHOLD:
            best_solver = max(
                self._solver_counts, key=lambda s: (self._solver_counts[s], s)
            )
            return (best_solver, self.LOW_CONF_CEILING)

        # 1-NN: normalize edilmis Oklid mesafesi
        best_dist = math.inf
        best_row: Optional[TrainingRow] = None

        for row in self._training:
            dist = _euclidean(features, row.feature_vector)
            if dist < best_dist or (
                dist == best_dist
                and best_row is not None
                and row.winner < best_row.winner
            ):
                best_dist = dist
                best_row = row

        assert best_row is not None
        confidence = 1.0 / (1.0 + best_dist)
        return (best_row.winner, confidence)

    # ------------------------------------------------------------------
    # explain
    # ------------------------------------------------------------------

    def explain(self) -> str:
        """Ogrenilenin aciklamasi (okunabilir metin)."""
        if not self._fitted:
            return "Henuz egitilmedi."

        if not self._training:
            return "Egitim verisi bos; fallback: dblf, guven=0.0."

        solver_str = ", ".join(
            f"{s}:{c}"
            for s, c in sorted(
                self._solver_counts.items(),
                key=lambda x: (-x[1], x[0]),
            )
        )
        yontem = (
            "1-NN (en-yakin prototip, normalize Oklid mesafesi)"
            if self.n_train >= self.MIN_DATA_THRESHOLD
            else f"Cok-az-veri fallback (n={self.n_train} < {self.MIN_DATA_THRESHOLD})"
        )
        return (
            f"Yontem: {yontem}. "
            f"Egitim: {self.n_train} instance. "
            f"Cozucu dagilimi: {solver_str}."
        )


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def _euclidean(a: List[float], b: List[float]) -> float:
    """Iki vektoru arasindaki Oklid mesafesi (uzunluk uyusmadiginda 0 padler)."""
    n = max(len(a), len(b))
    dist_sq = 0.0
    for i in range(n):
        ai = a[i] if i < len(a) else 0.0
        bi = b[i] if i < len(b) else 0.0
        dist_sq += (ai - bi) ** 2
    return math.sqrt(dist_sq)
