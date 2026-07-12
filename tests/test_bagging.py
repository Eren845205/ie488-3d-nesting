"""C2-iv — bagging: mini-bagging (deterministik bootstrap, deney adayi)."""
from __future__ import annotations

from src.nesting3d.selection.bagging import MiniBaggingSelector
from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.gengap import loo_regret


def _rows(n=10):
    out = []
    for i in range(n):
        f0 = 0.05 + 0.9 * i / (n - 1)
        nfv_iyi = f0 < 0.5
        hs = ({"nfv_ham@2": 50.0, "heightmap": 100.0} if nfv_iyi
              else {"nfv_ham@2": 90.0, "heightmap": 40.0})
        out.append(TrainingRow(
            instance_id=f"s{i}", is_easy=False,
            winner="nfv_ham@2" if nfv_iyi else "heightmap",
            dblf_height=hs["heightmap"], best_height=min(hs.values()),
            feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
            aile="A" if nfv_iyi else "B", per_solver_heights=hs))
    return out


def test_ayrilabilir_veride_dogru():
    m = MiniBaggingSelector(n_trees=7, seed=0)
    m.fit(_rows())
    assert m.predict([0.1, 0.9])[0] == "nfv_ham@2"
    assert m.predict([0.9, 0.1])[0] == "heightmap"
    assert "MiniBagging" in m.explain()


def test_determinizm():
    a, b = MiniBaggingSelector(seed=3), MiniBaggingSelector(seed=3)
    a.fit(_rows()); b.fit(_rows())
    for fv in ([0.2, 0.8], [0.6, 0.4], [0.5, 0.5]):
        assert a.predict(fv) == b.predict(fv)


def test_kucuk_veride_dusuk_guven_ve_loo():
    m = MiniBaggingSelector()
    m.fit(_rows(3))
    assert m.predict([0.1, 0.9])[1] <= 0.49
    assert loo_regret(_rows(), model_factory=MiniBaggingSelector) is not None
