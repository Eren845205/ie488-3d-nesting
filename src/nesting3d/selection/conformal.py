"""conformal.py — LOO-conformal guven kumeleri (C2-iii).

Kucuk N'de "guven=0.6" gibi keyfi esikler kalibre degildir. Conformal
prediction DAGILIMSIZ kapsama garantisi verir: prediction_set(x), dogru arm'i
>= 1-alpha olasilikla icerir (degistirilebilirlik varsayimiyla; N kucukken
kume genisleyerek durustlesir). URETIM KURALI (plan C4): kume TEKIL ise model
konusur, degilse kural — "emin degilsen sus" yapisal hale gelir.

Kalibrasyon: LOO artiklari (her satir icin satir-disi egitilmis temel modelin
DOGRU arm'a verdigi skorun tumleyeni). Split-conformal'in LOO varyanti —
20-30 satirlik tabloda veri israfi olmaz. stdlib-only, deterministik.

Temel modelin arm-skoru: predict_proba varsa o (Logistic ailesi);
predict_heights varsa softmax(-yukseklik) (Argmin ailesi); yoksa predict'in
(ad, conf) ciftinden dejenere dagilim.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Set, Tuple

from src.nesting3d.selection.dataset import TrainingRow


def _arm_skorlari(model, features) -> Dict[str, float]:
    if hasattr(model, "predict_proba"):
        return dict(model.predict_proba(features))
    if hasattr(model, "predict_heights"):
        hs = model.predict_heights(features)
        if not hs:
            return {}
        z = [-h / max(1.0, min(abs(v) for v in hs.values())) for h in hs.values()]
        m = max(z)
        e = [math.exp(v - m) for v in z]
        t = sum(e)
        return {a: ei / t for a, ei in zip(hs.keys(), e)}
    ad, conf = model.predict(features)
    return {ad: float(conf)}


class ConformalSelector:
    """Herhangi bir temel seciciyi conformal guven katmaniyla sarar."""

    def __init__(self, base_factory, alpha: float = 0.1):
        self._base_factory = base_factory
        self.alpha = float(alpha)
        self._base = None
        self._skorlar: List[float] = []   # nonconformity = 1 - p(dogru arm)
        self._armlar: Set[str] = set()
        self._fitted = False
        self.n_train = 0

    def fit(self, rows: List[TrainingRow]) -> None:
        self._base = self._base_factory()
        self._base.fit(rows)
        self._skorlar = []
        self._armlar = {r.winner for r in rows}
        for i, r in enumerate(rows):
            digerleri = rows[:i] + rows[i + 1:]
            if not digerleri:
                self._skorlar.append(1.0)
                continue
            m = self._base_factory()
            m.fit(digerleri)
            p = _arm_skorlari(m, r.feature_vector).get(r.winner, 0.0)
            self._skorlar.append(1.0 - float(p))
        self._skorlar.sort()
        self.n_train = len(rows)
        self._fitted = True

    def _esik(self) -> float:
        n = len(self._skorlar)
        if n == 0:
            return 1.0
        k = min(n, math.ceil((n + 1) * (1.0 - self.alpha)))
        return self._skorlar[k - 1]

    def prediction_set(self, features: Sequence[float]) -> Set[str]:
        if not self._fitted:
            raise RuntimeError("ConformalSelector: once fit().")
        q = self._esik()
        p = _arm_skorlari(self._base, features)
        kume = {a for a in self._armlar if 1.0 - p.get(a, 0.0) <= q}
        if not kume:   # bos kume yerine en olasi arm (kapsama guvenli yonde)
            kume = {max(p, key=p.get)} if p else set()
        return kume

    def predict(self, features: Sequence[float]) -> Tuple[str, float]:
        if not self._fitted:
            raise RuntimeError("ConformalSelector: once fit().")
        ad, conf = self._base.predict(features)
        kume = self.prediction_set(features)
        # tekil kume = conformal-onaylı yuksek guven; genis kume = dusuk
        return (ad, conf if kume == {ad} else min(conf, 0.49))

    def explain(self) -> str:
        return (f"ConformalSelector(alpha={self.alpha}) | temel="
                f"{type(self._base).__name__} | n_train={self.n_train} | "
                f"esik={self._esik():.3f} | kural: kume TEKILse model konusur")
