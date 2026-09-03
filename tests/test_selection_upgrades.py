# -*- coding: utf-8 -*-
"""STRATEJI Faz-3 secim-modeli yukseltme testleri.

Kapsam: KNNSelector, LogisticSelector(+kalibrasyon), gengap model-parametrik
refactor (default BIT-OZDES), loo_regret, held-out egitim filtresi (A3).
sklearn YOK — hepsi stdlib. Deterministik.
"""
from functools import partial

from src.nesting3d.selection.dataset import (
    TrainingRow, build_training_table, heldout_instance_ids,
)
from src.nesting3d.selection.gengap import (
    _loo_cv_accuracy, compute_generalization_gap, loo_regret,
)
from src.nesting3d.selection.model import (
    AlgorithmSelector, KNNSelector, LogisticSelector, calibrate_temperature,
)

FN = ["f0", "f1"]


def _row(iid, x, winner, heights=None, aile="a"):
    return TrainingRow(
        instance_id=iid, is_easy=False, winner=winner, dblf_height=None,
        best_height=min((heights or {winner: 1.0}).values()),
        feature_vector=list(x), feature_names=FN, aile=aile,
        per_solver_heights=dict(heights or {winner: 1.0}))


def _iki_kume(n_per=6):
    """Ayrik iki kume: sol (0 civari) -> 'dblf', sag (10 civari) -> 'sa3d'."""
    rows = []
    for i in range(n_per):
        rows.append(_row(f"L{i}", [0.0 + i * 0.1, 0.0], "dblf",
                         {"dblf": 100.0, "sa3d": 150.0}))
        rows.append(_row(f"R{i}", [10.0 + i * 0.1, 1.0], "sa3d",
                         {"dblf": 150.0, "sa3d": 100.0}))
    return rows


# --- KNN ---------------------------------------------------------------------

def test_knn_ayrik_kumelerde_dogru_ve_deterministik():
    rows = _iki_kume()
    m = KNNSelector(k=3)
    m.fit(rows)
    w1, c1 = m.predict([0.2, 0.0])
    w2, c2 = m.predict([10.2, 1.0])
    assert (w1, w2) == ("dblf", "sa3d")
    assert 0.0 < c1 <= 1.0
    m2 = KNNSelector(k=3); m2.fit(rows)
    assert m2.predict([0.2, 0.0]) == (w1, c1)  # determinizm


def test_knn_az_veri_dusuk_guven():
    m = KNNSelector(k=3)
    m.fit([_row("a", [0, 0], "dblf")])
    w, c = m.predict([0, 0])
    assert c <= KNNSelector.LOW_CONF_CEILING


def test_knn_loo_regret_1nn_esit_veya_iyi():
    # el kitabi kabul kriteri deseni: LOO-regret(kNN) <= LOO-regret(1-NN) toy'da
    rows = _iki_kume()
    r1 = loo_regret(rows, AlgorithmSelector)
    rk = loo_regret(rows, partial(KNNSelector, k=3))
    assert rk["mean_mm"] <= r1["mean_mm"] + 1e-9


# --- Logistic + kalibrasyon --------------------------------------------------

def test_logistic_ayrilabilir_veride_ogrenir():
    rows = _iki_kume()
    m = LogisticSelector(l2=0.01, lr=0.5, iters=300)
    m.fit(rows)
    assert m.predict([0.0, 0.0])[0] == "dblf"
    assert m.predict([10.0, 1.0])[0] == "sa3d"
    p = m.predict_proba([10.0, 1.0])
    assert p["sa3d"] > 0.8 and abs(sum(p.values()) - 1.0) < 1e-9


def test_logistic_sicaklik_olasiligi_yumusatir():
    rows = _iki_kume()
    keskin = LogisticSelector(l2=0.01, lr=0.5, iters=300, temperature=1.0)
    keskin.fit(rows)
    yumusak = LogisticSelector(l2=0.01, lr=0.5, iters=300, temperature=4.0)
    yumusak.fit(rows)
    pk = keskin.predict_proba([10.0, 1.0])["sa3d"]
    py = yumusak.predict_proba([10.0, 1.0])["sa3d"]
    assert py < pk  # T>1 -> daha az asiri-guven


def test_calibrate_temperature_deterministik_ve_gecerli():
    rows = _iki_kume()
    f = partial(LogisticSelector, l2=0.01, lr=0.5, iters=200)
    t1 = calibrate_temperature(rows, f)
    t2 = calibrate_temperature(rows, f)
    assert t1 == t2 and t1 > 0


# --- gengap refactor: default BIT-OZDES + factory calisiyor -------------------

def test_gengap_default_bit_ozdes():
    rows = _iki_kume()
    # parametresiz (eski) cagri ile acikca AlgorithmSelector gecmek ayni sonucu verir
    assert _loo_cv_accuracy(rows) == _loo_cv_accuracy(rows, AlgorithmSelector)
    r_old = compute_generalization_gap(rows)
    r_new = compute_generalization_gap(rows, AlgorithmSelector)
    assert r_old.to_dict() == r_new.to_dict()


def test_gengap_farkli_factory_kabul_eder():
    rows = _iki_kume()
    acc = _loo_cv_accuracy(rows, partial(KNNSelector, k=3))
    assert 0.0 <= acc <= 1.0


# --- loo_regret ---------------------------------------------------------------

def test_loo_regret_dogru_hesap_ve_aile_kirilimi():
    rows = _iki_kume()
    rep = loo_regret(rows, AlgorithmSelector)
    # ayrik kumelerde 1-NN hep dogru -> regret 0
    assert rep["mean_mm"] == 0.0 and rep["max_mm"] == 0.0
    assert rep["n"] == len(rows) and "a" in rep["per_aile"]


def test_loo_regret_yanlis_secim_mm_cezasi():
    # tek uzak aykiri satir: komsulari 'dblf' der ama gercek kazanani 'sa3d';
    # yanlis secimin bedeli mm cinsinden gorunmeli (accuracy'nin goremedigi).
    rows = _iki_kume()
    rows.append(_row("X", [0.5, 0.0], "sa3d", {"dblf": 300.0, "sa3d": 100.0}))
    rep = loo_regret(rows, AlgorithmSelector)
    assert rep["max_mm"] >= 200.0 - 1e-9


def test_loo_regret_olculmemis_cozucu_kotumser_ceza():
    rows = _iki_kume()
    # 'ga' hicbir satirda olculmemis; onu tahmin eden model cezalanmali —
    # sahte factory ile dogrudan test:
    class _HepGa:
        def fit(self, rows): pass
        def predict(self, x): return ("ga", 1.0)
    rep = loo_regret(rows, _HepGa)
    assert rep["n_missing_pred"] == rep["n"] > 0
    assert rep["mean_mm"] >= 50.0 - 1e-9  # (max-min)=50 ceza


# --- held-out egitim filtresi (A3) --------------------------------------------

def _tele_row(iid, cozucu, h):
    return {"instance_id": iid, "cozucu": cozucu, "height_mm": h,
            "feature_vector": [0.0, 0.0], "feature_names": FN, "aile": "a"}


def test_build_training_table_heldout_dislar():
    rows = [_tele_row("plan1", "dblf", 100.0),
            _tele_row("numune", "dblf", 90.0),
            _tele_row("boxy", "sa3d", 80.0)]
    tam = build_training_table(rows)
    assert {r.instance_id for r in tam} == {"plan1", "numune", "boxy"}
    filtreli = build_training_table(
        rows, exclude_instance_ids={"numune", "boxy"})
    assert {r.instance_id for r in filtreli} == {"plan1"}


def test_heldout_instance_ids_registry_okur(tmp_path):
    reg = tmp_path / "registry.json"
    reg.write_text('{"sets": {"a": {"rol": "dev"}, "b": {"rol": "held-out"}}}',
                   encoding="utf-8")
    assert heldout_instance_ids(reg) == {"b"}
    assert heldout_instance_ids(tmp_path / "yok.json") == set()
