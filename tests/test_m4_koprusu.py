"""tests/test_m4_koprusu.py — M4 etiket -> egitim tablosu koprusu testleri.

Kapsam:
  - uretim kollari dogru TrainingRow'a cevrilir (winner/is_easy/per_solver)
  - kafes kollari tabloya GIRMEZ (katalog §C) + sayac
  - invalid kol (invalid_reasons dolu) dusurulur; hepsi invalid -> instance atlanir
  - benzersiz kimlik '@scale' eki (mass kucuk/orta ayni id paylasiyordu)
  - ayni benzersiz-kimlikte SON satir kazanir (append-only en yeni)
  - held-out dislama + mevcut-tablo id cakismasi + ozelliksiz instance atlama
"""

from __future__ import annotations

from src.nesting3d.selection.m4_koprusu import (
    m4_benzersiz_id, m4_training_rows)

FV = ([1.0, 2.0, 3.0], ["a", "b", "c"])


def _resolver(satir):
    return FV


def _satir(iid="m4_thin_plates_s0", aile="thin_plates", scale="kucuk",
           arms=None, invalid=None):
    if arms is None:
        arms = {"heightmap": {"height_mm": 30.0},
                "nfv_fast": {"height_mm": 28.0},
                "nfv_max": {"height_mm": 27.5}}
    return {"instance_id": iid, "aile": aile, "seed": 0, "scale": scale,
            "arms": arms, "invalid_reasons": invalid or {},
            "winner_mode": "kafes"}


class TestCevirim:
    def test_temel_alanlar(self):
        rows = m4_training_rows([_satir()], _resolver)
        assert len(rows) == 1
        r = rows[0]
        assert r.instance_id == "m4_thin_plates_s0@kucuk"
        assert r.winner == "nfv_max"
        assert r.best_height == 27.5
        assert r.dblf_height == 30.0
        assert r.is_easy is False  # 30 - 27.5 = 2.5 > 0.5
        assert r.aile == "thin_plates"
        # nfv_fast uretim esdegeri nfv_kalite adiyla girer (ARM_ESDEGER)
        assert r.per_solver_heights == {
            "heightmap": 30.0, "nfv_kalite": 28.0, "nfv_max": 27.5}
        assert r.feature_vector == FV[0]

    def test_arm_esdeger_haritasi(self):
        """nfv_fast -> nfv_kalite (uretim kalite yolu quality=fast);
        nfv_max kendi adiyla kalir."""
        rows = m4_training_rows([_satir()], _resolver)
        assert "nfv_fast" not in rows[0].per_solver_heights
        assert "nfv_kalite" in rows[0].per_solver_heights
        assert "nfv_max" in rows[0].per_solver_heights

    def test_esitlikte_alfabetik_winner(self):
        arms = {"heightmap": {"height_mm": 28.0},
                "nfv_fast": {"height_mm": 28.0}}
        rows = m4_training_rows([_satir(arms=arms)], _resolver)
        assert rows[0].winner == "heightmap"
        assert rows[0].is_easy is True

    def test_kafes_dahil_bayragi(self):
        """kafes_dahil=True (Eren onayi 2026-08-21): kafes kollari tabloya
        girer, winner kafes olabilir."""
        arms = {"heightmap": {"height_mm": 30.0},
                "nfv_max": {"height_mm": 28.0},
                "kafes": {"height_mm": 20.0},
                "kafes_duruskoru": {"height_mm": 21.0}}
        ist = {}
        rows = m4_training_rows([_satir(arms=arms)], _resolver,
                                kafes_dahil=True, istatistik=ist)
        assert rows[0].winner == "kafes"
        assert rows[0].per_solver_heights["kafes_duruskoru"] == 21.0
        assert ist["m4_n_kafes_kol_atlandi"] == 0

    def test_kafes_kollari_girmez(self):
        """Etiketteki winner kafes olsa bile tablo uretim kollarindan kurulur."""
        arms = {"heightmap": {"height_mm": 30.0},
                "nfv_max": {"height_mm": 28.0},
                "kafes": {"height_mm": 20.0},
                "kafes_duruskoru": {"height_mm": 21.0}}
        ist = {}
        rows = m4_training_rows([_satir(arms=arms)], _resolver, istatistik=ist)
        assert rows[0].winner == "nfv_max"
        assert "kafes" not in rows[0].per_solver_heights
        assert ist["m4_n_kafes_kol_atlandi"] == 2


class TestDusurmeYollari:
    def test_invalid_kol_dusurulur(self):
        inv = {"heightmap": "clearance 0.04<2.0", "nfv_fast": None,
               "nfv_max": None}
        rows = m4_training_rows([_satir(invalid=inv)], _resolver)
        assert "heightmap" not in rows[0].per_solver_heights
        assert rows[0].dblf_height is None

    def test_hepsi_invalid_instance_atlanir(self):
        inv = {"heightmap": "x", "nfv_fast": "x", "nfv_max": "x"}
        ist = {}
        rows = m4_training_rows([_satir(invalid=inv)], _resolver,
                                istatistik=ist)
        assert rows == []
        assert ist["m4_n_legal_armsiz"] == 1

    def test_heldout_dislama(self):
        ist = {}
        rows = m4_training_rows(
            [_satir()], _resolver,
            exclude_instance_ids={"m4_thin_plates_s0"}, istatistik=ist)
        assert rows == []
        assert ist["m4_n_heldout_dislanan"] == 1

    def test_mevcut_id_cakismasi(self):
        ist = {}
        rows = m4_training_rows(
            [_satir()], _resolver,
            mevcut_ids={"m4_thin_plates_s0@kucuk"}, istatistik=ist)
        assert rows == []
        assert ist["m4_n_id_cakisan"] == 1

    def test_ozelliksiz_atlanir(self):
        ist = {}
        rows = m4_training_rows([_satir()], lambda s: None, istatistik=ist)
        assert rows == []
        assert ist["m4_n_ozelliksiz"] == 1


class TestKimlikVeTekrar:
    def test_scale_eki_kimligi_ayirir(self):
        """mass kucuk/orta ayni instance_id'yi paylasir — @scale ayirir."""
        s1 = _satir(iid="m4_mass_plate_rod_mix_s0",
                    aile="mass_plate_rod_mix", scale="kucuk")
        s2 = _satir(iid="m4_mass_plate_rod_mix_s0",
                    aile="mass_plate_rod_mix", scale="orta")
        rows = m4_training_rows([s1, s2], _resolver)
        assert len(rows) == 2
        assert {r.instance_id for r in rows} == {
            "m4_mass_plate_rod_mix_s0@kucuk",
            "m4_mass_plate_rod_mix_s0@orta"}

    def test_ayni_kimlikte_son_satir_kazanir(self):
        s1 = _satir()
        s1["arms"]["nfv_max"]["height_mm"] = 99.0
        s2 = _satir()  # ayni id+scale, yeni kosu
        ist = {}
        rows = m4_training_rows([s1, s2], _resolver, istatistik=ist)
        assert len(rows) == 1
        assert rows[0].per_solver_heights["nfv_max"] == 27.5
        assert ist["m4_n_tekrar_satir"] == 1

    def test_benzersiz_id_fonksiyonu(self):
        assert m4_benzersiz_id(_satir()) == "m4_thin_plates_s0@kucuk"


class TestKarantina:
    """2026-08-31 cozum plani Paket C: AC-08 altinda olculen satirlar
    'karantina' alaniyla egitim-disi birakilir; taze (bayraksiz) satir
    'son satir kazanir' kuraliyla karantinayi otomatik ezer."""

    def test_karantinali_satir_tabloya_girmez(self):
        ist = {}
        rows = m4_training_rows(
            [_satir(arms={"heightmap": {"height_mm": 30.0}},
                    iid="devset_plan3", scale="gercek") | {
                "karantina": "AC-08 NFV kollari olculemedi"}],
            _resolver, istatistik=ist)
        assert rows == []
        assert ist["m4_n_karantina"] == 1

    def test_taze_satir_karantinayi_ezer(self):
        eski = _satir(iid="devset_plan3", scale="gercek",
                      arms={"heightmap": {"height_mm": 811.0}}) | {
            "karantina": "AC-08"}
        taze = _satir(iid="devset_plan3", scale="gercek",
                      arms={"heightmap": {"height_mm": 811.0},
                            "nfv_max": {"height_mm": 607.5}})
        rows = m4_training_rows([eski, taze], _resolver)
        assert len(rows) == 1 and rows[0].winner == "nfv_max"

    def test_karantinasiz_set_bayt_ozdes(self):
        # karantina alani olmayan satirlarda davranis birebir eski
        ist1, ist2 = {}, {}
        r1 = m4_training_rows([_satir()], _resolver, istatistik=ist1)
        assert len(r1) == 1
        assert ist1.get("m4_n_karantina", 0) == 0
