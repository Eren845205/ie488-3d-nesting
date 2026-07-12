"""bagging.py — mini-bagging (deterministik bootstrap + sig agaclar) (C2-iv).

Tek CART'in varyansini dusurur. 03_SECIM_MODELI §3 verdikti KORUNUR: yalniz
LOO-kapili DENEY adayi — promote listesine girmez; yarismada kazanamazsa
uretime hic dokunmaz. sklearn YOK: bootstrap deterministik LCG ile,
agaclar mevcut DecisionTreeSelector.
"""
from __future__ import annotations

from typing import List, Tuple

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.model import DecisionTreeSelector


def _lcg(seed: int):
    durum = seed & 0x7FFFFFFF
    while True:
        durum = (1103515245 * durum + 12345) & 0x7FFFFFFF
        yield durum


class MiniBaggingSelector:
    """n_trees x DecisionTreeSelector, bootstrap + cogunluk oyu."""

    MIN_DATA_THRESHOLD = 4

    def __init__(self, n_trees: int = 7, max_depth: int = 2,
                 min_samples_leaf: int = 2, seed: int = 0):
        self.n_trees = int(n_trees)
        self.max_depth = int(max_depth)
        self.min_samples_leaf = int(min_samples_leaf)
        self.seed = int(seed)
        self._agaclar: List[DecisionTreeSelector] = []
        self._fitted = False
        self.n_train = 0

    def fit(self, rows: List[TrainingRow]) -> None:
        self._agaclar = []
        n = len(rows)
        rnd = _lcg(self.seed)
        for _ in range(self.n_trees):
            orneklem = [rows[next(rnd) % n] for _ in range(n)] if n else []
            agac = DecisionTreeSelector(max_depth=self.max_depth,
                                        min_samples_leaf=self.min_samples_leaf)
            agac.fit(orneklem)
            self._agaclar.append(agac)
        self.n_train = n
        self._fitted = True

    def predict(self, features) -> Tuple[str, float]:
        if not self._fitted:
            raise RuntimeError("MiniBaggingSelector.predict(): once fit().")
        if not self._agaclar or self.n_train == 0:
            return ("heightmap", 0.0)
        oylar: dict = {}
        for agac in self._agaclar:
            ad, _ = agac.predict(features)
            oylar[ad] = oylar.get(ad, 0) + 1
        kazanan = min((a for a, o in oylar.items()
                       if o == max(oylar.values())))       # esitlik: alfabetik
        conf = oylar[kazanan] / len(self._agaclar)
        if self.n_train < self.MIN_DATA_THRESHOLD:
            conf = min(conf, 0.49)
        return (kazanan, conf)

    def explain(self) -> str:
        return (f"MiniBaggingSelector | {self.n_trees} agac x depth<="
                f"{self.max_depth} | seed={self.seed} | n_train={self.n_train}")
