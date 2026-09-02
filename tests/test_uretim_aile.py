"""tests/test_uretim_aile.py — AC-10: egitim satiri -> uretim ailesi + uretim
kurali; kapili-karar LOO; guvenli-aile secimi; karar-probu (olu promote).
Hafif: instance/classify/kural stub'lanir (gercek STL yok)."""
from __future__ import annotations

from types import SimpleNamespace

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.uretim_aile import (
    URETIM_AILELERI, guvenli_aileler_sec, instance_kur, kapili_loo,
    karar_probu, mode_decision_kolu, satir_uretim_bilgisi)


# --- yardimcilar -----------------------------------------------------------

def _row(iid, aile, fv, winner, hs):
    return TrainingRow(instance_id=iid, is_easy=False, winner=winner,
                       dblf_height=hs.get("heightmap"), best_height=min(hs.values()),
                       feature_vector=list(fv), feature_names=["a", "b"],
                       aile=aile, per_solver_heights=dict(hs))


class _Sabit:
    """Taban secici stub: fit no-op; predict_proba = sabit dagilim."""
    def __init__(self, dagilim):
        self._d = dict(dagilim)

    def fit(self, rows):
        pass

    def predict_proba(self, fv):
        return dict(self._d)

    def predict(self, fv):
        a = max(self._d, key=self._d.get)
        return a, self._d[a]


class _Conf:
    """Conformal stub: esik sabit; armlar tablodan."""
    esik = 0.5

    def __init__(self, base_factory, alpha=0.1):
        self.alpha = alpha
        self._armlar = set()

    def fit(self, rows):
        self._armlar = {r.winner for r in rows}

    def _esik(self):
        return self.esik


# --- mode_decision_kolu ----------------------------------------------------

def test_mode_decision_kolu_cevrimi():
    assert mode_decision_kolu(SimpleNamespace(mode="heightmap")) == "heightmap"
    assert mode_decision_kolu(SimpleNamespace(mode="nfv", nfv_quality="max")) == "nfv_max"
    assert mode_decision_kolu(SimpleNamespace(mode="nfv", nfv_quality="fast")) == "nfv_kalite"
    assert mode_decision_kolu(SimpleNamespace(mode="nfv", nfv_quality=None)) == "nfv_kalite"


# --- instance_kur ----------------------------------------------------------

def test_instance_kur_m4_devset_telemetri():
    cagri = []
    builders = {"thin_plates": lambda s, sc, d: cagri.append(("m4", s, sc)) or "I1",
                "fsm610_gercek": lambda s, sc, d: cagri.append(("fsm", s, sc)) or "I3"}

    def devset(ad):
        return lambda s, sc, d: cagri.append(("dev", ad, s, sc)) or "I2"

    assert instance_kur("m4_thin_plates_s2@kucuk", "thin_plates", builders, devset) == "I1"
    assert instance_kur("devset_plan3@gercek", "devset_plan3", builders, devset) == "I2"
    assert instance_kur("plan3", "thin_shell", builders, devset) == "I2"   # telemetri satiri
    assert instance_kur("fsm610@gercek", "fsm610_gercek", builders, devset) == "I3"
    assert instance_kur("B001", "mixed_scale", builders, devset) is None
    assert cagri[0] == ("m4", 2, "kucuk") and cagri[1] == ("dev", "plan3", 42, "gercek")


# --- satir_uretim_bilgisi --------------------------------------------------

def test_satir_uretim_bilgisi_kaynaklari():
    rows = [
        _row("m4_x_s0@kucuk", "x", [0, 0], "nfv_max", {"heightmap": 10, "nfv_max": 8}),
        _row("tel1", "thin_shell", [0, 0], "heightmap", {"heightmap": 5, "nfv_max": 9}),
        _row("tel2", "garip", [0, 0], "heightmap", {"heightmap": 5}),
    ]
    builders = {"x": lambda s, sc, d: "INST"}
    bilgi = satir_uretim_bilgisi(
        rows, builders=builders, devset_builder=lambda ad: None,
        classify=lambda inst: ("long_rod", 0.9),
        kural_fn=lambda inst: SimpleNamespace(mode="nfv", nfv_quality="max"),
        kural_map={"tel1": "heightmap"}, log=lambda *a: None)
    assert bilgi["m4_x_s0@kucuk"] == {"uretim_aile": "long_rod", "kural_arm": "nfv_max",
                                      "kaynak": "instance"}
    assert bilgi["tel1"]["uretim_aile"] == "thin_shell"
    assert bilgi["tel1"]["kural_arm"] == "heightmap"
    assert bilgi["tel2"] == {"uretim_aile": None, "kural_arm": None, "kaynak": "yok"}


def test_satir_uretim_bilgisi_hata_yutar():
    rows = [_row("m4_x_s0@kucuk", "x", [0, 0], "nfv_max", {"heightmap": 10, "nfv_max": 8})]

    def patlar(s, sc, d):
        raise RuntimeError("stl yok")
    uyari = []
    bilgi = satir_uretim_bilgisi(
        rows, builders={"x": patlar}, devset_builder=lambda ad: None,
        classify=lambda i: ("tube", 1.0), kural_fn=lambda i: None,
        log=uyari.append)
    assert bilgi["m4_x_s0@kucuk"]["uretim_aile"] is None and uyari


# --- kapili_loo + guvenli_aileler_sec --------------------------------------

def _tablo():
    # long_rod: model (nfv_max) dogru, kural (heightmap) 10mm kotu  -> guvenli
    # thin_shell: model (nfv_max) yanlis, kural (heightmap) dogru   -> zararli
    rows = []
    for i in range(3):
        rows.append(_row(f"lr{i}", "long_rods", [1, i], "nfv_max",
                         {"heightmap": 20.0, "nfv_max": 10.0}))
        rows.append(_row(f"ts{i}", "thin_shell", [2, i], "heightmap",
                         {"heightmap": 10.0, "nfv_max": 25.0}))
    bilgi = {f"lr{i}": {"uretim_aile": "long_rod", "kural_arm": "heightmap"} for i in range(3)}
    bilgi.update({f"ts{i}": {"uretim_aile": "thin_shell", "kural_arm": "heightmap"} for i in range(3)})
    return rows, bilgi


def test_kapili_loo_konusma_ve_regret():
    rows, bilgi = _tablo()
    fab = lambda: _Sabit({"nfv_max": 0.9, "heightmap": 0.1})   # tekil kume (esik 0,5)
    rap = kapili_loo(rows, bilgi, fab, 0.25, allow={"long_rod"}, conformal_cls=_Conf)
    assert rap["n"] == 6 and rap["konustu"] == 3 and rap["isabet"] == 3
    assert rap["aile"]["long_rod"]["model_ort"] == 0.0
    assert rap["aile"]["long_rod"]["kural_ort"] == 10.0
    assert rap["aile"]["thin_shell"]["model_ort"] == 0.0   # allow disi -> kural (dogru)
    assert rap["regret_model"] < rap["regret_kural"]


def test_kapili_loo_kural_bilinmeyen_kiyas_disi():
    rows, bilgi = _tablo()
    bilgi["lr0"]["kural_arm"] = None
    rap = kapili_loo(rows, bilgi, lambda: _Sabit({"nfv_max": 1.0}), 0.25,
                     allow=URETIM_AILELERI, conformal_cls=_Conf)
    assert rap["kural_bilinmeyen"] == 1 and rap["n"] == 5


def test_guvenli_aileler_sec_zararli_aileyi_disarida_birakir():
    rows, bilgi = _tablo()
    fab = lambda: _Sabit({"nfv_max": 0.9, "heightmap": 0.1})
    guvenli, rap = guvenli_aileler_sec(rows, bilgi, fab, 0.25, min_n=3, conformal_cls=_Conf)
    assert guvenli == {"long_rod"}
    assert rap["aile"]["thin_shell"]["model_ort"] == 15.0   # allowlist'siz: model zarar


def test_guvenli_aileler_sec_esitlik_guvenli_degil():
    # model konusmasin (kume tekil degil) -> model_ort == kural_ort -> guvenli DEGIL
    rows, bilgi = _tablo()
    fab = lambda: _Sabit({"nfv_max": 0.6, "heightmap": 0.6})   # iki kol da esik altinda
    guvenli, rap = guvenli_aileler_sec(rows, bilgi, fab, 0.25, min_n=3, conformal_cls=_Conf)
    assert rap["aile"]["long_rod"]["model_ort"] == rap["aile"]["long_rod"]["kural_ort"]
    assert guvenli == set()


def test_guvenli_aileler_sec_min_n():
    rows, bilgi = _tablo()
    fab = lambda: _Sabit({"nfv_max": 0.9, "heightmap": 0.1})
    guvenli, _ = guvenli_aileler_sec(rows, bilgi, fab, 0.25, min_n=4, conformal_cls=_Conf)
    assert guvenli == set()


# --- karar_probu -----------------------------------------------------------

class _Model:
    def __init__(self, konusan_aileler):
        self._a = set(konusan_aileler)

    def karar(self, fv, aile):
        return ("nfv_max", "gerekce") if aile in self._a else None


def test_karar_probu_olu_ve_canli():
    rows, bilgi = _tablo()
    olu = karar_probu(_Model(set()), rows, bilgi)
    assert olu["olu"] and olu["konustu"] == 0 and olu["n"] == 6
    canli = karar_probu(_Model({"long_rod"}), rows, bilgi)
    assert not canli["olu"] and canli["konustu"] == 3 and canli["isabet"] == 3
    assert canli["aileler"] == {"long_rod": 3}
