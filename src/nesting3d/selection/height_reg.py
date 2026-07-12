"""height_reg.py — arm-basina YUKSEKLIK regresyonu + argmin mod secici (C2-i).

Siniflandirma kazancin BUYUKLUGUNU atar (0.5mm ile 100mm ayni "dogru/yanlis");
regresyon regret hedefiyle birebir hizali: her arm icin legal_height tahmin
et, argmin'i sec. VERI VERIMI kritigi: her arm o arm'i OLCMUS TUM satirlarla
egitilir (yalniz winner satirlari degil) — kucuk N'de sinyal 3-4 katlanir.

stdlib-only (Y-3); deterministik (sabit baslangic, sirali dolasim).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from src.nesting3d.selection.dataset import TrainingRow

_EPS = 1e-9


def _z_stats(X: Sequence[Sequence[float]]):
    n, d = len(X), len(X[0])
    mu = [sum(x[j] for x in X) / n for j in range(d)]
    sd = [math.sqrt(sum((x[j] - mu[j]) ** 2 for x in X) / n) or 1.0
          for j in range(d)]
    return mu, sd


def _z(x, mu, sd):
    return [(xi - m) / (s + _EPS) for xi, m, s in zip(x, mu, sd)]


class KNNHeightRegressor:
    """k-NN regresyon: z-normalize ozellik uzayinda mesafe-agirlikli ortalama."""

    def __init__(self, k: int = 3):
        self.k = int(k)
        self._X: List[List[float]] = []
        self._y: List[float] = []
        self._mu = self._sd = None

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> None:
        self._X = [list(map(float, x)) for x in X]
        self._y = [float(v) for v in y]
        self._mu, self._sd = _z_stats(self._X)

    def predict(self, x: Sequence[float]) -> float:
        xn = _z(x, self._mu, self._sd)
        skorlar = []
        for xi, yi in zip(self._X, self._y):
            d = math.dist(xn, _z(xi, self._mu, self._sd))
            skorlar.append((d, yi))
        skorlar.sort(key=lambda t: (t[0], t[1]))
        en_yakin = skorlar[:max(1, min(self.k, len(skorlar)))]
        w = [1.0 / (d + _EPS) for d, _ in en_yakin]
        return sum(wi * yi for wi, (_, yi) in zip(w, en_yakin)) / sum(w)


class RidgeGDRegressor:
    """L2'li dogrusal regresyon — standardize girdi, tam-batch GD, 0-baslangic."""

    def __init__(self, l2: float = 1.0, lr: float = 0.1, iters: int = 400):
        self.l2, self.lr, self.iters = float(l2), float(lr), int(iters)
        self._w: List[float] = []
        self._b = 0.0
        self._mu = self._sd = None
        self._y_mu = 0.0

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> None:
        self._mu, self._sd = _z_stats([list(x) for x in X])
        Xn = [_z(x, self._mu, self._sd) for x in X]
        self._y_mu = sum(y) / len(y)
        yc = [v - self._y_mu for v in y]
        n, d = len(Xn), len(Xn[0])
        self._w = [0.0] * d
        self._b = 0.0
        for _ in range(self.iters):
            gw = [0.0] * d
            gb = 0.0
            for xi, yi in zip(Xn, yc):
                hata = (sum(wj * xj for wj, xj in zip(self._w, xi)) + self._b) - yi
                for j in range(d):
                    gw[j] += hata * xi[j]
                gb += hata
            for j in range(d):
                self._w[j] -= self.lr * (gw[j] / n + self.l2 * self._w[j] / n)
            self._b -= self.lr * gb / n

    def predict(self, x: Sequence[float]) -> float:
        xn = _z(x, self._mu, self._sd)
        return sum(wj * xj for wj, xj in zip(self._w, xn)) + self._b + self._y_mu


class ArgminModeSelector:
    """Arm-basina regressorlerin argmin'i; ortak fit/predict/explain arayuzu."""

    MIN_DATA_THRESHOLD = 4  # tablo bu boyutun altindaysa dusuk guven

    def __init__(self, reg_factory=KNNHeightRegressor):
        self._reg_factory = reg_factory
        self._regs: Dict[str, object] = {}
        self._fitted = False
        self.n_train = 0

    def fit(self, rows: List[TrainingRow]) -> None:
        veri: Dict[str, Tuple[list, list]] = {}
        for r in rows:
            for arm, h in (r.per_solver_heights or {}).items():
                X, y = veri.setdefault(arm, ([], []))
                X.append(list(r.feature_vector))
                y.append(float(h))
        self._regs = {}
        for arm in sorted(veri):
            X, y = veri[arm]
            reg = self._reg_factory()
            reg.fit(X, y)
            self._regs[arm] = reg
        self.n_train = len(rows)
        self._fitted = True

    def predict_heights(self, features: Sequence[float]) -> Dict[str, float]:
        if not self._fitted:
            raise RuntimeError("ArgminModeSelector.predict(): once fit().")
        return {arm: reg.predict(features) for arm, reg in self._regs.items()}

    def predict(self, features: Sequence[float]) -> Tuple[str, float]:
        tahmin = self.predict_heights(features)
        if not tahmin:
            return ("heightmap", 0.0)
        sirali = sorted(tahmin.items(), key=lambda t: (t[1], t[0]))
        arm, en_iyi = sirali[0]
        if len(sirali) == 1 or self.n_train < self.MIN_DATA_THRESHOLD:
            return (arm, 0.49)
        marj = sirali[1][1] - en_iyi
        conf = 1.0 / (1.0 + math.exp(-marj / max(abs(en_iyi), 1.0) * 10.0))
        return (arm, min(0.99, max(0.5, conf)))

    def explain(self) -> str:
        return (f"ArgminModeSelector | {self._reg_factory.__name__} | "
                f"armlar={sorted(self._regs)} | n_train={self.n_train} | "
                "karar: arm-basina yukseklik tahmini, argmin secilir")
