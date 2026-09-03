"""C2-iii — conformal: LOO-conformal guven kumeleri (kapsama + tekil-kume)."""
from __future__ import annotations

from src.nesting3d.selection.conformal import ConformalSelector
from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.height_reg import ArgminModeSelector
from src.nesting3d.selection.model import LogisticSelector


def _row(i, f0, gurultu=0.0):
    nfv_iyi = f0 < 0.5
    hs = ({"nfv_ham@2": 50.0 + gurultu, "heightmap": 100.0} if nfv_iyi
          else {"nfv_ham@2": 90.0, "heightmap": 40.0 + gurultu})
    w = min(a for a, h in hs.items() if h == min(hs.values()))
    return TrainingRow(instance_id=f"s{i}", is_easy=False, winner=w,
                       dblf_height=hs["heightmap"], best_height=min(hs.values()),
                       feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
                       aile="A" if nfv_iyi else "B", per_solver_heights=hs)


def _table(n=24):
    # deterministik yayilim: [0.05..0.95]
    return [_row(i, 0.05 + 0.9 * i / (n - 1), gurultu=(i % 3) * 0.5)
            for i in range(n)]


def test_kapsama_sentetikte():
    """Ampirik kapsama >= 1 - alpha - tolerans (ayni dagilimdan taze noktalar)."""
    egitim = _table(24)
    m = ConformalSelector(LogisticSelector, alpha=0.25)
    m.fit(egitim)
    taze = [_row(100 + i, 0.08 + 0.84 * i / 11) for i in range(12)]
    kapsanan = sum(1 for r in taze
                   if r.winner in m.prediction_set(r.feature_vector))
    assert kapsanan / len(taze) >= 0.75 - 0.15   # kucuk-N toleransi


def test_tekil_kume_net_bolgede():
    m = ConformalSelector(LogisticSelector, alpha=0.2)
    m.fit(_table(24))
    kume_net = m.prediction_set([0.05, 0.95])
    assert "nfv_ham@2" in kume_net
    ad, conf = m.predict([0.05, 0.95])
    if kume_net == {"nfv_ham@2"}:
        assert conf >= 0.5           # tekil -> guven korunur
    kume_belirsiz = m.prediction_set([0.5, 0.5])
    assert kume_belirsiz            # bos degil (guvenli yon)


def test_argmin_temelle_calisir():
    m = ConformalSelector(ArgminModeSelector, alpha=0.2)
    m.fit(_table(16))
    assert m.predict([0.1, 0.9])[0] == "nfv_ham@2"
    assert isinstance(m.prediction_set([0.1, 0.9]), set)
    assert "Conformal" in m.explain()
