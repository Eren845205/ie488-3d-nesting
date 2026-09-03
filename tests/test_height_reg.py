"""C2-i — height_reg: arm-basina yukseklik regresyonu + argmin secici."""
from __future__ import annotations

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.gengap import loo_regret
from src.nesting3d.selection.height_reg import (
    ArgminModeSelector,
    KNNHeightRegressor,
    RidgeGDRegressor,
)


def _rows():
    """Ayrılabilir tablo: f0 kucukse nfv kazanir (50<100), buyukse heightmap (40<90)."""
    out = []
    for i, f0 in enumerate([0.1, 0.15, 0.2, 0.8, 0.85, 0.9]):
        nfv_iyi = f0 < 0.5
        hs = {"nfv_ham@2": 50.0 + i if nfv_iyi else 90.0 + i,
              "heightmap": 100.0 + i if nfv_iyi else 40.0 + i}
        w = min(a for a, h in hs.items() if h == min(hs.values()))
        out.append(TrainingRow(
            instance_id=f"s{i}", is_easy=False, winner=w,
            dblf_height=hs["heightmap"], best_height=min(hs.values()),
            feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
            aile="A" if nfv_iyi else "B", per_solver_heights=hs))
    return out


def test_knn_reg_trivial():
    r = KNNHeightRegressor(k=1)
    r.fit([[0.0], [1.0]], [10.0, 20.0])
    assert abs(r.predict([0.0]) - 10.0) < 1e-6
    assert abs(r.predict([1.0]) - 20.0) < 1e-6


def test_ridge_ogrenir():
    r = RidgeGDRegressor(l2=0.01, lr=0.2, iters=800)
    X = [[x] for x in (0.0, 0.25, 0.5, 0.75, 1.0)]
    r.fit(X, [10.0, 12.5, 15.0, 17.5, 20.0])   # y = 10 + 10x
    assert abs(r.predict([0.5]) - 15.0) < 0.5


def test_argmin_dogru_arm():
    m = ArgminModeSelector()
    m.fit(_rows())
    arm_a, conf_a = m.predict([0.12, 0.88])
    arm_b, _ = m.predict([0.88, 0.12])
    assert arm_a == "nfv_ham@2" and conf_a >= 0.5
    assert arm_b == "heightmap"
    assert "ArgminModeSelector" in m.explain()


def test_determinizm_ve_loo_entegrasyon():
    m1, m2 = ArgminModeSelector(), ArgminModeSelector()
    m1.fit(_rows()); m2.fit(_rows())
    assert m1.predict([0.3, 0.7]) == m2.predict([0.3, 0.7])
    rapor = loo_regret(_rows(), model_factory=ArgminModeSelector)
    assert rapor is not None   # mevcut gengap makinesiyle uyum
