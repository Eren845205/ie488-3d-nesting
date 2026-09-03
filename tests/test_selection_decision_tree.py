"""tests/test_selection_decision_tree.py — DecisionTreeSelector birim testleri.

TDD yaklasimiyla yazildi: once testler, sonra implementasyon.
Kapsam: fit/predict sozlesmesi, determinizm, explain okunabilirligi,
        bos/az veri guardi, asiri-derin olmama (overfit panzehiri).
"""
from __future__ import annotations

import pytest

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.model import DecisionTreeSelector


# ---------------------------------------------------------------------------
# Yardimci: hizli TrainingRow fabrikasi
# ---------------------------------------------------------------------------

def _row(
    instance_id: str,
    winner: str,
    fv: list | None = None,
    aile: str = "test",
    is_easy: bool = False,
) -> TrainingRow:
    """Test icin minimal TrainingRow olustur."""
    if fv is None:
        fv = [0.0] * 5
    return TrainingRow(
        instance_id=instance_id,
        is_easy=is_easy,
        winner=winner,
        dblf_height=100.0,
        best_height=80.0 if not is_easy else 100.0,
        feature_vector=fv,
        feature_names=[f"f{i}" for i in range(len(fv))],
        aile=aile,
    )


def _ayirt_edici_egitim() -> list[TrainingRow]:
    """Ayirt edici iki bolge: f0 dusuk=sa3d, f0 yuksek=dblf (6+6 ornek)."""
    rows = []
    for i in range(6):
        rows.append(_row(f"s{i}", "sa3d", fv=[0.1, float(i) * 0.01, 0.5, 0.3, 0.2]))
    for i in range(6):
        rows.append(_row(f"d{i}", "dblf", fv=[0.9, float(i) * 0.01, 0.5, 0.3, 0.2]))
    return rows


# ---------------------------------------------------------------------------
# fit sozlesmesi
# ---------------------------------------------------------------------------

class TestDecisionTreeSelectorFit:
    def test_fit_bos_hata_vermez(self):
        """Bos liste ile fit() cagrilinca RuntimeError veya diger hata OLMAMALI."""
        sel = DecisionTreeSelector()
        sel.fit([])  # hata vermemeli

    def test_fit_sonrasi_n_train_dogru(self):
        sel = DecisionTreeSelector()
        rows = _ayirt_edici_egitim()
        sel.fit(rows)
        assert sel.n_train == len(rows)

    def test_fit_az_veri_hata_vermez(self):
        """1-2 ornek ile bile fit() calismali."""
        sel = DecisionTreeSelector()
        sel.fit([_row("a", "sa3d")])
        sel.fit([_row("a", "sa3d"), _row("b", "dblf")])

    def test_fit_tekrar_cagirilabilir(self):
        """fit() iki kez cagirilinca ikinci veriye gore ezber yapilmali."""
        sel = DecisionTreeSelector()
        sel.fit([_row("a", "sa3d")])
        rows2 = _ayirt_edici_egitim()
        sel.fit(rows2)
        assert sel.n_train == len(rows2)


# ---------------------------------------------------------------------------
# predict sozlesmesi
# ---------------------------------------------------------------------------

class TestDecisionTreeSelectorPredict:
    def test_predict_egitilmeden_hata_verir(self):
        sel = DecisionTreeSelector()
        with pytest.raises(RuntimeError):
            sel.predict([0.0] * 5)

    def test_predict_tuple_doner(self):
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        result = sel.predict([0.1, 0.0, 0.5, 0.3, 0.2])
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_predict_isim_str_guven_float(self):
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        name, conf = sel.predict([0.1, 0.0, 0.5, 0.3, 0.2])
        assert isinstance(name, str)
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0

    def test_predict_ayirt_edici_bolge_dogru_cozucu(self):
        """f0=0.1 bolgesinde sa3d, f0=0.9 bolgesinde dblf gelmeli."""
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        name_sa, _ = sel.predict([0.1, 0.0, 0.5, 0.3, 0.2])
        name_db, _ = sel.predict([0.9, 0.0, 0.5, 0.3, 0.2])
        assert name_sa == "sa3d"
        assert name_db == "dblf"

    def test_predict_bos_egitim_sonrasi_dusuk_guven(self):
        """Bos egitim sonrasi guven dusuk (< CONFIDENCE_THRESHOLD) olmali."""
        sel = DecisionTreeSelector()
        sel.fit([])
        _, conf = sel.predict([0.5] * 5)
        assert conf < DecisionTreeSelector.CONFIDENCE_THRESHOLD

    def test_predict_az_veri_dusuk_guven(self):
        """MIN_DATA_THRESHOLD altinda veri varsa guven dusuk olmali."""
        sel = DecisionTreeSelector()
        sel.fit([_row("a", "sa3d", fv=[0.1] * 5)])
        _, conf = sel.predict([0.1] * 5)
        assert conf <= DecisionTreeSelector.LOW_CONF_CEILING

    def test_predict_saf_yaprak_yuksek_guven(self):
        """Tamamen saf yaprakta guven 1.0 olmali."""
        # Tek cozucu: tum egitim ornekleri sa3d, yaprak tamamen saf
        rows = [_row(f"s{i}", "sa3d", fv=[0.1] * 5) for i in range(6)]
        sel = DecisionTreeSelector()
        sel.fit(rows)
        _, conf = sel.predict([0.1] * 5)
        assert conf == pytest.approx(1.0)

    def test_predict_karisik_yaprak_dusuk_guven(self):
        """Karisik yaprakta (50/50 dagilim) guven < CONFIDENCE_THRESHOLD olmali."""
        rows = (
            [_row(f"s{i}", "sa3d", fv=[0.5] * 5) for i in range(3)]
            + [_row(f"d{i}", "dblf", fv=[0.5] * 5) for i in range(3)]
        )
        sel = DecisionTreeSelector()
        sel.fit(rows)
        _, conf = sel.predict([0.5] * 5)
        assert conf < DecisionTreeSelector.CONFIDENCE_THRESHOLD

    def test_predict_gecerli_cozucu_adi_doner(self):
        """Tahmin her zaman egitim setindeki bir cozucu adini icermeli."""
        rows = _ayirt_edici_egitim()
        bilinen_cozucular = {r.winner for r in rows}
        sel = DecisionTreeSelector()
        sel.fit(rows)
        name, _ = sel.predict([0.5] * 5)
        assert name in bilinen_cozucular


# ---------------------------------------------------------------------------
# Determinizm
# ---------------------------------------------------------------------------

class TestDecisionTreeSelectorDeterminism:
    def test_ayni_girdi_ayni_cikti(self):
        """Ayni egitim + ayni sorgu -> ayni (name, conf) iki ayri ornekten."""
        rows = _ayirt_edici_egitim()
        sel1 = DecisionTreeSelector()
        sel1.fit(rows)
        sel2 = DecisionTreeSelector()
        sel2.fit(rows)
        fv = [0.5, 0.0, 0.5, 0.3, 0.2]
        assert sel1.predict(fv) == sel2.predict(fv)

    def test_alfabetik_esitlik_cozumu(self):
        """Esit frekansli cozucular arasinda alfabetik ilk secilmeli."""
        # Tam karisik yaprak: 3 dblf, 3 sa3d -- dblf alfabetik once gelir
        rows = (
            [_row(f"d{i}", "dblf", fv=[0.5] * 5) for i in range(3)]
            + [_row(f"s{i}", "sa3d", fv=[0.5] * 5) for i in range(3)]
        )
        sel = DecisionTreeSelector()
        sel.fit(rows)
        name, _ = sel.predict([0.5] * 5)
        # Coklugun dblf veya sa3d (3=3) oldugu durumda alfabetik -> dblf
        assert name == "dblf"

    def test_farkli_fv_sirasinin_sonucu_degistirmemesi(self):
        """Egitim satirlarinin sirasi degismeden, tahmin degismemeli."""
        rows = _ayirt_edici_egitim()
        rows_ters = list(reversed(rows))  # ters sira

        sel1 = DecisionTreeSelector()
        sel1.fit(rows)
        sel2 = DecisionTreeSelector()
        sel2.fit(rows_ters)  # ters sirali egitim

        fv = [0.1, 0.0, 0.5, 0.3, 0.2]
        # Her iki model de ayni tahmini vermeli (deterministik bolme)
        name1, conf1 = sel1.predict(fv)
        name2, conf2 = sel2.predict(fv)
        assert name1 == name2


# ---------------------------------------------------------------------------
# explain() okunabilirligi
# ---------------------------------------------------------------------------

class TestDecisionTreeSelectorExplain:
    def test_explain_string_doner(self):
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        text = sel.explain()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_explain_egitilmeden_uyari_verir(self):
        sel = DecisionTreeSelector()
        text = sel.explain()
        assert "egitilmedi" in text.lower() or "henuz" in text.lower()

    def test_explain_kural_ifadesi_icerir(self):
        """Egitilmis modelde explain() 'eger' veya 'if' gibi kural ifadesi icermeli."""
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        text = sel.explain().lower()
        # Turkce 'eger' veya genel kural ifadeleri
        assert any(kw in text for kw in ["eger", "if", "<=", ">", "derinlik", "depth"])

    def test_explain_cozucu_adini_icerir(self):
        """explain() ciktisi en az bir cozucu adini icermeli."""
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        text = sel.explain()
        assert "sa3d" in text or "dblf" in text

    def test_explain_ozellik_adini_icerir(self):
        """explain() ciktisi en az bir ozellik adini icermeli (f0, f1, ...)."""
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        text = sel.explain()
        # Ozellik adlari f0..f4 veya gercek isimler olabilir
        assert any(f"f{i}" in text for i in range(5))


# ---------------------------------------------------------------------------
# Asiri derinlik guardi (overfit panzehiri)
# ---------------------------------------------------------------------------

class TestDecisionTreeSelectorOverfitGuard:
    def test_max_depth_asil_maz(self):
        """Agac derinligi max_depth parametresini asmamali."""
        sel = DecisionTreeSelector(max_depth=3)
        sel.fit(_ayirt_edici_egitim())
        assert sel.tree_depth() <= 3

    def test_varsayilan_max_depth_kucuk(self):
        """Varsayilan max_depth makul (<=4) olmali — kara kutu kacisini onler."""
        sel = DecisionTreeSelector()
        sel.fit(_ayirt_edici_egitim())
        assert sel.tree_depth() <= 4

    def test_min_samples_leaf_korunur(self):
        """Yapraklarda min_samples_leaf'ten az ornek olmamali."""
        sel = DecisionTreeSelector(min_samples_leaf=2)
        rows = _ayirt_edici_egitim()
        sel.fit(rows)
        leaf_counts = sel.leaf_sample_counts()
        assert all(c >= 2 for c in leaf_counts), (
            f"min_samples_leaf=2 ihlali: {leaf_counts}"
        )

    def test_tek_ornek_agac_derinlik_sifir(self):
        """Tek egitim ornegi ile agac derinligi 0 (sadece kok yaprak) olmali."""
        sel = DecisionTreeSelector()
        sel.fit([_row("a", "sa3d", fv=[0.5] * 5)])
        assert sel.tree_depth() == 0

    def test_buyuk_veri_derinlik_sinirli(self):
        """100 ornek ile bile max_depth asil maz."""
        rows = (
            [_row(f"s{i}", "sa3d", fv=[float(i) / 100] * 5) for i in range(50)]
            + [_row(f"d{i}", "dblf", fv=[1.0 - float(i) / 100] * 5) for i in range(50)]
        )
        sel = DecisionTreeSelector(max_depth=3)
        sel.fit(rows)
        assert sel.tree_depth() <= 3
