"""C2-ii — regret_logistic: spread-agirlikli lojistik."""
from __future__ import annotations

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.gengap import loo_regret
from src.nesting3d.selection.regret_logistic import RegretWeightedLogistic


def _row(i, f0, winner, hs, aile="A"):
    return TrainingRow(instance_id=f"s{i}", is_easy=False, winner=winner,
                       dblf_height=hs.get("heightmap"),
                       best_height=min(hs.values()),
                       feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
                       aile=aile, per_solver_heights=hs)


def _rows():
    out = []
    for i, f0 in enumerate([0.1, 0.2, 0.3, 0.7, 0.8, 0.9]):
        nfv_iyi = f0 < 0.5
        spread = 150.0 if nfv_iyi else 5.0    # dusuk-f0 satirlar YUKSEK bedelli
        hs = ({"nfv_ham@2": 50.0, "heightmap": 50.0 + spread} if nfv_iyi
              else {"nfv_ham@2": 45.0 + spread, "heightmap": 45.0})
        out.append(_row(i, f0, min(a for a, h in hs.items()
                                   if h == min(hs.values())), hs))
    return out


def test_ogrenir_ve_n_train_gercek():
    m = RegretWeightedLogistic(iters=300)
    rows = _rows()
    m.fit(rows)
    assert m.n_train == len(rows)              # replikasyon rapora sizmaz
    assert m.predict([0.15, 0.85])[0] == "nfv_ham@2"
    assert m.predict([0.85, 0.15])[0] == "heightmap"
    assert "RegretWeighted" in m.explain()


def test_determinizm_ve_loo():
    a, b = RegretWeightedLogistic(iters=200), RegretWeightedLogistic(iters=200)
    a.fit(_rows()); b.fit(_rows())
    assert a.predict([0.4, 0.6]) == b.predict([0.4, 0.6])
    assert loo_regret(_rows(), model_factory=RegretWeightedLogistic) is not None
