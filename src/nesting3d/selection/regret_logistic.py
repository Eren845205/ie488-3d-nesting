"""regret_logistic.py — regret-agirlikli multinominal lojistik (C2-ii).

Standart siniflandirma her satiri esit sayar; oysa yanlis secimin bedeli
satirdan satira 0.5mm-192mm arasi degisiyor (Faz B olcumu). Bu varyant her
egitim satirini mm-SPREAD'iyle (max-min per_solver_heights) agirliklar —
yuksek bedelli satirlar loss'ta agir basar (Y-6 regret metrigiyle hizali).

Implementasyon: deterministik TAMSAYI REPLIKASYON (satir, spread'ine orantili
1..1+MAX_EK kez kopyalanir) — LogisticSelector'in GD dongusune dokunmadan
agirlik etkisi verir; stdlib + miras (sicaklik kalibrasyonu dahil) korunur.
"""
from __future__ import annotations

from typing import List

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.model import LogisticSelector

MAX_EK_KOPYA = 3


class RegretWeightedLogistic(LogisticSelector):
    """Spread-agirlikli LogisticSelector (deterministik replikasyonla)."""

    def fit(self, rows: List[TrainingRow]) -> None:
        spreadler = []
        for r in rows:
            hs = list((r.per_solver_heights or {}).values())
            spreadler.append((max(hs) - min(hs)) if len(hs) >= 2 else 0.0)
        maks = max(spreadler) if spreadler else 0.0
        genis: List[TrainingRow] = []
        for r, s in zip(rows, spreadler):
            ek = int(round(MAX_EK_KOPYA * (s / maks))) if maks > 0 else 0
            genis.extend([r] * (1 + ek))
        super().fit(genis)
        self.n_train = len(rows)  # rapor gercek satir sayisini gorsun

    def explain(self) -> str:
        return ("RegretWeightedLogistic | spread-agirlikli (tamsayi "
                f"replikasyon, maks +{MAX_EK_KOPYA}) | n_train={self.n_train}")
