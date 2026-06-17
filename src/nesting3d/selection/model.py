"""selection/model.py — AlgorithmSelector (kazanan cozucu tahmini).

Yontem — 1-NN prototip siniflandiricisi + yorumlanabilir kural:
  Egitim verisi sinirli (telemetri biriktikce artar; 2026-06-17 itibariyle ~69
  instance) -> kara kutu yasak, sklearn yasak. 1-NN (en yakin egitim ornegi)
  yorumlanabilir: "bu ornege en cok benzeyen gozlemde X kazanmisti" -> kural
  olarak anlasilabilir. Overfit kapisi LOO-CV tabanlidir (bkz selection/gengap.py).

Bu dosyada ayrica DecisionTreeSelector tanimlidir:
  Basit CART-benzeri karar agaci (sadece stdlib, sklearn yok). Gini safligi
  ile en iyi (ozellik, esik) boluyor; max_depth + min_samples_leaf ile
  asiri uyumu onluyor. Yaprakta cogunluk winner + safligi = guven.
  explain() okunabilir kural metni uretir.

Guven metrigi (her iki sinif):
  - Egitim verisi < MIN_DATA_THRESHOLD ise -> dusuk guven (<= 0.5) doner.
  - 1-NN guven = 1 / (1 + mesafe). Mesafe 0 -> guven 1.0; buyuk mesafe -> kucuk.
  - Karar agaci guven = yaprak safligi (cogunluk sinif orani).
  - Guven < CONFIDENCE_THRESHOLD ise selector tam portfoye dusar (bkz selector.py).

sklearn YOK — sadece standart kutuphane.
Kara kutu YOK — explain() okunabilir prototip/kural referansi verir.
Determinizm: esitlikte alfabetik secim.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Optional, Tuple

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
# Yardimci (AlgorithmSelector icin)
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


# ===========================================================================
# DecisionTreeSelector — yorumlanabilir CART-benzeri karar agaci
# ===========================================================================

class _DTNode:
    """Karar agacinin tek dugumu (ic dugum veya yaprak).

    Ic dugum: feature_idx ve threshold ile sol/sag alt dugume bolunur.
      - sol: feature_vector[feature_idx] <= threshold
      - sag: feature_vector[feature_idx] > threshold

    Yaprak: winner (cogunluk sinif, esitte alfabetik) ve confidence (safligi).
    """

    __slots__ = (
        "feature_idx",
        "threshold",
        "left",
        "right",
        "winner",
        "confidence",
        "n_samples",
    )

    def __init__(self) -> None:
        self.feature_idx: Optional[int] = None
        self.threshold: Optional[float] = None
        self.left: Optional["_DTNode"] = None
        self.right: Optional["_DTNode"] = None
        self.winner: Optional[str] = None
        self.confidence: float = 0.0
        self.n_samples: int = 0

    def is_leaf(self) -> bool:
        return self.winner is not None


def _gini(labels: List[str]) -> float:
    """Gini safsizligi: 1 - sum(p_i^2). Bos liste -> 0.0."""
    n = len(labels)
    if n == 0:
        return 0.0
    counts = Counter(labels)
    return 1.0 - sum((c / n) ** 2 for c in counts.values())


def _majority_winner(labels: List[str]) -> Tuple[str, float]:
    """Cogunluk sinif ve safligi (orani). Esitte alfabetik secim."""
    if not labels:
        return ("dblf", 0.0)
    counts = Counter(labels)
    total = len(labels)
    # Esitte alfabetik: key=(count azalan, isim artan)
    best = max(counts.keys(), key=lambda s: (counts[s], [-ord(c) for c in s]))
    # Alfabetik cozum: ayni count'ta isim alfabetik kucuge git
    max_count = counts[best]
    candidates = [s for s, c in counts.items() if c == max_count]
    winner = min(candidates)  # alfabetik kucuk
    confidence = counts[winner] / total
    return (winner, confidence)


def _best_split(
    rows: List[TrainingRow],
    feature_names: List[str],
    min_samples_leaf: int,
) -> Tuple[Optional[int], Optional[float], float]:
    """Gini kazancini maksimize eden (ozellik_idx, esik) bul.

    Tum ozellikler ve tum ara noktalar denenir (brute-force; n kucuk).
    Determinizm: esit kazancta kucuk ozellik indexi, sonra kucuk esik.

    Returns:
        (best_feature_idx, best_threshold, best_gain)
        Gecerli bolme bulunamazsa (None, None, 0.0).
    """
    n = len(rows)
    if n < 2 * min_samples_leaf:
        return (None, None, 0.0)

    labels = [r.winner for r in rows]
    parent_gini = _gini(labels)

    n_features = len(rows[0].feature_vector) if rows else 0
    if n_features == 0:
        return (None, None, 0.0)

    best_gain = 0.0
    best_feat: Optional[int] = None
    best_thresh: Optional[float] = None

    for feat_idx in range(n_features):
        # Kopyalama olmadan siralama: sadece degerler
        values = sorted(set(r.feature_vector[feat_idx] for r in rows))
        # Ara nokta esikleri
        thresholds = [
            (values[i] + values[i + 1]) / 2.0
            for i in range(len(values) - 1)
        ]
        for thresh in thresholds:
            left_labels = [
                r.winner for r in rows if r.feature_vector[feat_idx] <= thresh
            ]
            right_labels = [
                r.winner for r in rows if r.feature_vector[feat_idx] > thresh
            ]
            if (
                len(left_labels) < min_samples_leaf
                or len(right_labels) < min_samples_leaf
            ):
                continue
            gain = parent_gini - (
                len(left_labels) / n * _gini(left_labels)
                + len(right_labels) / n * _gini(right_labels)
            )
            # Deterministik: daha iyi kazanc VEYA ayni kazancta (kucuk feat, kucuk esik)
            if gain > best_gain or (
                math.isclose(gain, best_gain, rel_tol=1e-9)
                and best_feat is not None
                and (
                    feat_idx < best_feat
                    or (feat_idx == best_feat and thresh < (best_thresh or math.inf))
                )
            ):
                best_gain = gain
                best_feat = feat_idx
                best_thresh = thresh

    return (best_feat, best_thresh, best_gain)


def _build_tree(
    rows: List[TrainingRow],
    feature_names: List[str],
    max_depth: int,
    min_samples_leaf: int,
    depth: int,
) -> _DTNode:
    """Ozgursuz CART agac insa (recursive). Maksimum maks_derinlik."""
    node = _DTNode()
    node.n_samples = len(rows)

    labels = [r.winner for r in rows]
    winner, confidence = _majority_winner(labels)

    # Yaprak durumu: max_depth asil di, az ornek, homojen sinif
    if depth >= max_depth or len(rows) < 2 * min_samples_leaf or confidence == 1.0:
        node.winner = winner
        node.confidence = confidence
        return node

    feat_idx, thresh, gain = _best_split(rows, feature_names, min_samples_leaf)

    # Gecerli bolme yok: yaprak yap
    if feat_idx is None or gain <= 0.0:
        node.winner = winner
        node.confidence = confidence
        return node

    left_rows = [r for r in rows if r.feature_vector[feat_idx] <= thresh]
    right_rows = [r for r in rows if r.feature_vector[feat_idx] > thresh]

    # Bolme sonucu bos taraf: yaprak yap
    if not left_rows or not right_rows:
        node.winner = winner
        node.confidence = confidence
        return node

    node.feature_idx = feat_idx
    node.threshold = thresh
    node.left = _build_tree(
        left_rows, feature_names, max_depth, min_samples_leaf, depth + 1
    )
    node.right = _build_tree(
        right_rows, feature_names, max_depth, min_samples_leaf, depth + 1
    )
    return node


def _predict_node(node: _DTNode, features: List[float]) -> Tuple[str, float]:
    """Tek bir vektoru agacta yukle, yaprak tahminini don."""
    current = node
    while not current.is_leaf():
        assert current.feature_idx is not None
        assert current.threshold is not None
        if features[current.feature_idx] <= current.threshold:
            assert current.left is not None
            current = current.left
        else:
            assert current.right is not None
            current = current.right
    assert current.winner is not None
    return (current.winner, current.confidence)


def _tree_depth(node: Optional[_DTNode]) -> int:
    """Agacin maksimum derinligi (yaprak=0)."""
    if node is None or node.is_leaf():
        return 0
    return 1 + max(
        _tree_depth(node.left),
        _tree_depth(node.right),
    )


def _leaf_sample_counts(node: Optional[_DTNode], result: List[int]) -> None:
    """Tum yapraklardaki ornek sayilarini result listesine ekle."""
    if node is None:
        return
    if node.is_leaf():
        result.append(node.n_samples)
        return
    _leaf_sample_counts(node.left, result)
    _leaf_sample_counts(node.right, result)


def _explain_node(
    node: _DTNode,
    feature_names: List[str],
    prefix: str,
    lines: List[str],
    depth: int,
) -> None:
    """Agac kurallarini okunabilir satirlar olarak topla (recursive)."""
    indent = "  " * depth
    if node.is_leaf():
        lines.append(
            f"{indent}{prefix}=> {node.winner} "
            f"(guven={node.confidence:.2f}, n={node.n_samples})"
        )
        return
    fname = (
        feature_names[node.feature_idx]
        if node.feature_idx is not None and node.feature_idx < len(feature_names)
        else f"f{node.feature_idx}"
    )
    thresh = node.threshold
    lines.append(f"{indent}{prefix}eger {fname} <= {thresh:.4f}:")
    if node.left:
        _explain_node(node.left, feature_names, "", lines, depth + 1)
    lines.append(f"{indent}aksi halde ({fname} > {thresh:.4f}):")
    if node.right:
        _explain_node(node.right, feature_names, "", lines, depth + 1)


class DecisionTreeSelector:
    """Kazanan cozucu tahmincisi (yorumlanabilir CART-benzeri karar agaci).

    AlgorithmSelector ile AYNI dis arayuz: fit / predict / explain.
    sklearn YASAK — sadece stdlib (math, collections). Kara kutu YASAK.

    Algoritma:
      - Gini kazanci ile en iyi (ozellik, esik) bolme.
      - max_depth ve min_samples_leaf ile asiri uyum onlenir.
      - Yaprakta cogunluk winner; esitte alfabetik secim (determinizm).
      - Guven = yaprak safligi (cogunluk sinif orani).
      - Guven < CONFIDENCE_THRESHOLD ise selector portfoye duser.

    Kullanim::

        sel = DecisionTreeSelector(max_depth=2, min_samples_leaf=2)
        sel.fit(training_rows)
        solver_name, confidence = sel.predict(feature_vector)
        print(sel.explain())
    """

    MIN_DATA_THRESHOLD: int = 4
    CONFIDENCE_THRESHOLD: float = 0.6
    LOW_CONF_CEILING: float = 0.49

    def __init__(
        self,
        max_depth: int = 2,
        min_samples_leaf: int = 2,
    ) -> None:
        """
        Args:
            max_depth:         Agac maksimum derinligi (varsayilan 2).
                               Az veriyle (69 instance) derin agac asiri uyuma girer;
                               LOO-CV taramasinda max_depth=2 en yuksek genellemeyi verir.
            min_samples_leaf:  Yaprakta minimum ornek sayisi (varsayilan 2).
        """
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self._fitted: bool = False
        self._root: Optional[_DTNode] = None
        self._feature_names: List[str] = []
        self._solver_counts: Dict[str, int] = {}
        self.n_train: int = 0

    # ------------------------------------------------------------------
    # fit
    # ------------------------------------------------------------------

    def fit(self, rows: List[TrainingRow]) -> None:
        """Egitim verisiyle karar agaci kur.

        Args:
            rows: TrainingRow listesi (bos olabilir).
        """
        self._fitted = True
        self.n_train = len(rows)
        self._solver_counts = {}
        for r in rows:
            self._solver_counts[r.winner] = (
                self._solver_counts.get(r.winner, 0) + 1
            )

        if not rows:
            self._root = None
            self._feature_names = []
            return

        # Ozellik isimlerini ilk satirdan al (tum satirlar ayni olmali)
        self._feature_names = list(rows[0].feature_names)

        # Egitim verisi yetersizse agac kurma, kok=yaprak yap
        if self.n_train < self.MIN_DATA_THRESHOLD:
            node = _DTNode()
            winner, confidence = _majority_winner([r.winner for r in rows])
            node.winner = winner
            node.confidence = min(confidence, self.LOW_CONF_CEILING)
            node.n_samples = self.n_train
            self._root = node
            return

        self._root = _build_tree(
            rows,
            self._feature_names,
            max_depth=self.max_depth,
            min_samples_leaf=self.min_samples_leaf,
            depth=0,
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
                "DecisionTreeSelector.predict(): once fit() cagirilmali."
            )

        if self._root is None:
            # Bos egitim: fallback
            return ("dblf", 0.0)

        name, conf = _predict_node(self._root, features)

        # Az veri durumunda guven tavani uygula
        if self.n_train < self.MIN_DATA_THRESHOLD:
            conf = min(conf, self.LOW_CONF_CEILING)

        return (name, conf)

    # ------------------------------------------------------------------
    # explain
    # ------------------------------------------------------------------

    def explain(self) -> str:
        """Agac kurallarini okunabilir metin olarak ver.

        Returns:
            Girintili kural listesi ("eger f0 <= 0.5: ..." bicimiyle).
        """
        if not self._fitted:
            return "Henuz egitilmedi."

        if self._root is None:
            return "Egitim verisi bos; fallback: dblf, guven=0.0."

        header = (
            f"DecisionTreeSelector | derinlik={self.tree_depth()} | "
            f"egitim={self.n_train} | max_depth={self.max_depth} | "
            f"min_samples_leaf={self.min_samples_leaf}\n"
            f"Cozucu dagilimi: "
            + ", ".join(
                f"{s}:{c}"
                for s, c in sorted(
                    self._solver_counts.items(),
                    key=lambda x: (-x[1], x[0]),
                )
            )
        )
        lines: List[str] = []
        _explain_node(self._root, self._feature_names, "", lines, depth=0)
        return header + "\nKurallar:\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # Yardimci introspeksiyon (test + debug icin)
    # ------------------------------------------------------------------

    def tree_depth(self) -> int:
        """Agacin maksimum derinligi (yaprak dugum=0)."""
        return _tree_depth(self._root)

    def leaf_sample_counts(self) -> List[int]:
        """Tum yapraklardaki ornek sayilarini liste olarak ver."""
        result: List[int] = []
        _leaf_sample_counts(self._root, result)
        return result
