"""selection/prefilter.py — Kolay-instance on-filtresi (Renau & Hart 2024).

EasyInstancePrefilter: egitim verisinden KONSERVATIF yorumlanabilir kural
ogrenir.

Yontem — esiksiz 1-boyutlu esik arama:
  1. Hangi ozelligin kolay/zor ayrimini en iyi yaptigi aranir
     (her ozellik icin bilgi kazanimi hesabi — saf entropi gini).
  2. En ayirt edici ozellikte bir esik secilir.
  3. Esik: "kolay" tarafi tamamen kolay ise ve yeterli ornekle destekleniyorsa
     gecerli; aksi halde "hic kolay tahmin etme" (konservatif fallback).

Konservatif garanti:
  - Egitim setinde hic kolay ornek yoksa: hep False.
  - Sinir bolgede (kesintisiz kolay bolge yok): hep False.
  - Guven = kolay bolgedeki kolay orani (1.0 = o bolgedeki hepsi kolay).
  - Emin degilse (guven < min_confidence=0.9) is_easy=False doner.

sklearn YOK — sadece standart kutuphane (math, collections).
Kara kutu YOK — explain() okunabilir kural metni uretir.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

from src.nesting3d.selection.dataset import TrainingRow


_UNSET = object()  # sentinel


class EasyInstancePrefilter:
    """Kolay-instance on-filtresi.

    Kullanim::

        pf = EasyInstancePrefilter()
        pf.fit(training_rows)
        is_easy, confidence = pf.predict(feature_vector)
        print(pf.explain())
    """

    # Konservatif esikler
    MIN_CONFIDENCE: float = 0.9     # easy diyebilmek icin minimum saflık
    MIN_EASY_SUPPORT: int = 2       # easy tahmin icin en az kac kolay ornek
    FALLBACK_CONFIDENCE: float = 0.0

    def __init__(self) -> None:
        self._fitted: bool = False
        self._rule_feature_idx: Optional[int] = None
        self._rule_feature_name: Optional[str] = None
        self._rule_threshold: Optional[float] = None
        self._rule_side: Optional[str] = None   # "below" | "above"
        self._rule_confidence: float = 0.0
        self._n_easy: int = 0
        self._n_total: int = 0
        self.n_train: int = 0

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------

    def fit(self, rows: List[TrainingRow]) -> None:
        """Egitim verisinden konservatif kural ogren."""
        self.n_train = len(rows)
        self._fitted = True

        if not rows:
            self._n_easy = 0
            self._n_total = 0
            self._rule_feature_idx = None
            return

        self._n_total = len(rows)
        self._n_easy = sum(1 for r in rows if r.is_easy)

        if self._n_easy < self.MIN_EASY_SUPPORT:
            # Yetersiz kolay ornek -> kural ogrenemez, hep False
            self._rule_feature_idx = None
            return

        n_features = len(rows[0].feature_vector)
        feature_names = rows[0].feature_names

        best_score = -1.0
        best_idx = None
        best_threshold = None
        best_side = None
        best_conf = 0.0

        for fi in range(n_features):
            vals = [r.feature_vector[fi] for r in rows]
            labels = [r.is_easy for r in rows]

            # Benzersiz deger esikleri (sirali)
            uniq = sorted(set(vals))
            if len(uniq) < 2:
                continue

            # Her esik adayini dene
            for tidx in range(len(uniq) - 1):
                threshold = (uniq[tidx] + uniq[tidx + 1]) / 2.0

                for side in ("below", "above"):
                    if side == "below":
                        in_group = [i for i, v in enumerate(vals) if v <= threshold]
                        out_group = [i for i, v in enumerate(vals) if v > threshold]
                    else:
                        in_group = [i for i, v in enumerate(vals) if v > threshold]
                        out_group = [i for i, v in enumerate(vals) if v <= threshold]

                    if len(in_group) < self.MIN_EASY_SUPPORT:
                        continue

                    easy_in = sum(1 for i in in_group if labels[i])
                    conf = easy_in / len(in_group)

                    if conf < self.MIN_CONFIDENCE:
                        continue

                    # Bilgi kazanimi (gini azalmasi): in_group safligi
                    # Skor: (in_group buyuklugu / toplam) * saflık
                    score = (len(in_group) / len(rows)) * conf

                    if score > best_score:
                        best_score = score
                        best_idx = fi
                        best_threshold = threshold
                        best_side = side
                        best_conf = conf

        self._rule_feature_idx = best_idx
        self._rule_threshold = best_threshold
        self._rule_side = best_side
        self._rule_confidence = best_conf
        self._rule_feature_name = (
            feature_names[best_idx] if best_idx is not None else None
        )

    # ------------------------------------------------------------------
    # predict
    # ------------------------------------------------------------------

    def predict(self, features: List[float]) -> Tuple[bool, float]:
        """Ozellik vektorune gore kolay tahmin yap.

        Returns:
            (is_easy: bool, confidence: float)
            Konservatif: emin degilse (False, 0.0).

        Raises:
            RuntimeError: fit() cagrilmamissa.
        """
        if not self._fitted:
            raise RuntimeError(
                "EasyInstancePrefilter.predict(): once fit() cagirilmali."
            )

        if self._rule_feature_idx is None:
            return (False, self.FALLBACK_CONFIDENCE)

        fi = self._rule_feature_idx
        val = features[fi]
        threshold = self._rule_threshold
        side = self._rule_side

        if side == "below":
            in_group = val <= threshold
        else:
            in_group = val > threshold

        if in_group:
            return (True, self._rule_confidence)
        return (False, self.FALLBACK_CONFIDENCE)

    # ------------------------------------------------------------------
    # explain
    # ------------------------------------------------------------------

    def explain(self) -> str:
        """Ogrenilenkulral aciklamasi (okunabilir metin)."""
        if not self._fitted:
            return "Henuz egitilmedi."

        if self._rule_feature_idx is None:
            return (
                f"Kural: hic kolay tahmin yapilmaz "
                f"(egitim kolay ornegi: {self._n_easy}/{self._n_total}, "
                f"min_support={self.MIN_EASY_SUPPORT}, "
                f"min_confidence={self.MIN_CONFIDENCE:.0%})."
            )

        side_tr = "altinda veya esitinde" if self._rule_side == "below" else "ustunde"
        return (
            f"Kural: {self._rule_feature_name} {side_tr} {self._rule_threshold:.4g} "
            f"ise KOLAY (guven={self._rule_confidence:.2%}, "
            f"egitim kolay={self._n_easy}/{self._n_total})."
        )
