"""test_kosu_ilerleme.py — P6 koşu ilerleme + hata bildirimi (2026-08-18).

Kapsam:
    - KosuIlerleme deposu: baslat/asama/bitti/hata yasam dongusu
    - Yuzde tahmini: tavana doyar (97), bitti=100, negatif olmaz
    - EWMA parca-basi katsayisi guncellenir
    - Biten kosu TTL sonrasi listeden duser
    - Hata listesi limitli
    - GET /api/kosu-ilerleme endpoint sozlesmesi

Kosus: pytest tests/test_kosu_ilerleme.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.webapp.kosu_ilerleme import KosuIlerleme, _YUZDE_TAVAN


class SahteSaat:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# Depo yasam dongusu
# ---------------------------------------------------------------------------


class TestYasamDongusu:

    def test_baslat_aktif_listede_gorunur(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        d.baslat("SIP-1", 100, kaynak="mail")
        aktif = d.aktifler()
        assert len(aktif) == 1
        k = aktif[0]
        assert k["order_id"] == "SIP-1"
        assert k["kaynak"] == "mail"
        assert k["durum"] == "kosuyor"
        assert 1 <= k["yuzde"] <= _YUZDE_TAVAN

    def test_asama_guncellenir(self):
        d = KosuIlerleme(now=SahteSaat())
        d.baslat("SIP-1", 10)
        d.asama("SIP-1", "yerlesim hesaplaniyor")
        assert d.aktifler()[0]["asama"] == "yerlesim hesaplaniyor"

    def test_bilinmeyen_order_asama_sessiz(self):
        d = KosuIlerleme(now=SahteSaat())
        d.asama("YOK", "x")  # firlatmamali
        assert d.aktifler() == []

    def test_bitti_yuz_yuzde(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        d.baslat("SIP-1", 10)
        saat.t += 5
        d.bitti("SIP-1")
        k = d.aktifler()[0]
        assert k["durum"] == "bitti"
        assert k["yuzde"] == 100

    def test_hata_kosudan_cikar_hatalara_girer(self):
        d = KosuIlerleme(now=SahteSaat())
        d.baslat("SIP-1", 10, kaynak="manuel")
        d.hata("SIP-1", "pipeline")
        assert d.aktifler() == []
        h = d.son_hatalar()
        assert len(h) == 1
        assert h[0]["order_id"] == "SIP-1"
        assert h[0]["kod"] == "pipeline"
        assert h[0]["kaynak"] == "manuel"


# ---------------------------------------------------------------------------
# Yuzde tahmini
# ---------------------------------------------------------------------------


class TestYuzde:

    def test_yuzde_tavana_doyar(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        d.baslat("SIP-1", 1)
        saat.t += 100000  # beklenenin cok otesi
        assert d.aktifler()[0]["yuzde"] == _YUZDE_TAVAN

    def test_yuzde_zamanla_artar(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        d.baslat("SIP-1", 1000)
        y0 = d.aktifler()[0]["yuzde"]
        saat.t += 30
        y1 = d.aktifler()[0]["yuzde"]
        assert y1 > y0

    def test_ewma_bitiste_guncellenir(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        once = d._parca_basi
        d.baslat("SIP-1", 100)
        saat.t += 500  # taban 30s'nin cok ustunde gercek sure
        d.bitti("SIP-1")
        assert d._parca_basi != once

    def test_biten_ttl_sonrasi_duser(self):
        saat = SahteSaat()
        d = KosuIlerleme(now=saat)
        d.baslat("SIP-1", 10)
        d.bitti("SIP-1")
        assert len(d.aktifler()) == 1  # taze bitti gorunur
        saat.t += 120  # TTL (30s) gecti
        assert d.aktifler() == []

    def test_hata_limiti(self):
        d = KosuIlerleme(now=SahteSaat())
        for i in range(40):
            d.hata(f"SIP-{i}", "kod")
        assert len(d.son_hatalar()) <= 20


# ---------------------------------------------------------------------------
# Endpoint sozlesmesi
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=None,
                      llm_enabled=False)


@pytest.fixture
def client(app):
    return app.test_client()


class TestEndpoint:

    def test_bos_durum_sozlesme(self, client):
        r = client.get("/api/kosu-ilerleme")
        assert r.status_code == 200
        v = r.get_json()
        assert v["aktif"] == []
        assert v["hatalar"] == []

    def test_aktif_kosu_yansir(self, app, client):
        store = app.config["KOSU_ILERLEME"]
        store.baslat("SIP-9", 50, kaynak="mail")
        store.asama("SIP-9", "yerlesim hesaplaniyor")
        v = client.get("/api/kosu-ilerleme").get_json()
        assert len(v["aktif"]) == 1
        k = v["aktif"][0]
        assert k["order_id"] == "SIP-9"
        assert k["asama"] == "yerlesim hesaplaniyor"
        assert "yuzde" in k and "gecen_s" in k

    def test_hata_yansir(self, app, client):
        store = app.config["KOSU_ILERLEME"]
        store.baslat("SIP-8", 5)
        store.hata("SIP-8", "nesting")
        v = client.get("/api/kosu-ilerleme").get_json()
        assert v["aktif"] == []
        assert v["hatalar"][0]["kod"] == "nesting"
