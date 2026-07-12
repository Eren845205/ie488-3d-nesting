"""C3 — mod_yarismasi: aday x LOO-regret yarisma cercevesi."""
from __future__ import annotations

from src.nesting3d.selection.dataset import TrainingRow
from scripts.mod_yarismasi import RuleAdapter, _loo_regret_detay, yarisma


def _rows(n=8):
    out = []
    for i in range(n):
        f0 = 0.05 + 0.9 * i / max(1, n - 1)
        nfv_iyi = f0 < 0.5
        hs = ({"nfv_ham@2": 50.0, "heightmap": 150.0} if nfv_iyi
              else {"nfv_ham@2": 90.0, "heightmap": 40.0})
        out.append(TrainingRow(
            instance_id=f"s{i}", is_easy=False,
            winner="nfv_ham@2" if nfv_iyi else "heightmap",
            dblf_height=hs["heightmap"], best_height=min(hs.values()),
            feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
            aile="A" if nfv_iyi else "B", per_solver_heights=hs))
    return out


def test_rule_adapter_sabit_kiyas():
    rows = _rows()
    # kural: hep heightmap (yanlis yari icin buyuk regret beklenir)
    kural = {r.instance_id: "heightmap" for r in rows}
    det = _loo_regret_detay(rows, lambda: RuleAdapter(kural))
    assert det["mean"] == 50.0          # A ailesinde 100 ceza, B'de 0 -> ort 50
    assert det["aile"]["A"]["mean"] == 100.0
    assert det["aile"]["B"]["mean"] == 0.0


def test_yarisma_yapisi_ve_model_kurali_yener():
    rows = _rows()
    kural = {r.instance_id: "heightmap" for r in rows}
    sonuc = yarisma(rows, kural)
    assert sonuc["n_tablo"] == len(rows)
    assert "KURAL(baseline)" in sonuc["adaylar"]
    assert "argmin_knn_reg" in sonuc["adaylar"]
    # ayrilabilir veride ogrenen adaylardan en az biri sabit-yanlis kurali gecer
    kural_regret = sonuc["adaylar"]["KURAL(baseline)"]["mean"]
    en_iyi_model = min(s["mean"] for ad, s in sonuc["adaylar"].items()
                       if ad != "KURAL(baseline)" and s["mean"] is not None)
    assert en_iyi_model < kural_regret
    # her aday satirinda zorunlu alanlar
    for s in sonuc["adaylar"].values():
        assert {"mean", "max", "n", "accuracy", "aile"} <= set(s.keys())


def test_kucuk_tablo_kibarca():
    det = _loo_regret_detay(_rows(1), lambda: RuleAdapter({}))
    assert det["mean"] is None and "not" in det
