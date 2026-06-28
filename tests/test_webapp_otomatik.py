"""test_webapp_otomatik.py — Otomatik mod (poller) UI + gecmis entegrasyonu TDD.

- Otomatik islenen is kalici GECMISE dusen (kaynak=otomatik)
- /poll/baslat aralik (interval_s) parametresi
- Ana sayfada Otomatik Mod karti (LLM aktifken)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tests.test_webapp_otonom import _make_full_fake_provider


@pytest.fixture
def app_with_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=_make_full_fake_provider())


@pytest.fixture
def client_llm(app_with_llm):
    return app_with_llm.test_client()


@pytest.fixture
def client_no_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_enabled=False).test_client()


class TestOtomatikGecmis:
    def test_poller_islenen_isi_gecmise_yazar(self, app_with_llm):
        poller = app_with_llm.config["MAIL_POLLER"]
        gecmis = app_with_llm.config["OTONOM_GECMIS"]
        assert gecmis.liste() == []
        poller.poll_once()  # FakeMailbox -> siparis -> on_result -> gecmis
        kayitlar = gecmis.liste()
        assert len(kayitlar) >= 1, "Otomatik islenen is gecmise yazilmali"
        assert kayitlar[0]["kaynak"] == "otomatik"

    def test_manuel_kaynak_etiketi(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kayit = app_with_llm.config["OTONOM_GECMIS"].liste()[0]
        assert kayit["kaynak"] == "manuel"


class TestPollAralik:
    def test_poll_baslat_interval_uygular(self, client_llm, app_with_llm):
        resp = client_llm.post("/poll/baslat", json={"interval_s": 600})
        assert resp.status_code == 200
        try:
            assert app_with_llm.config["MAIL_POLLER"].state.interval_s == 600
        finally:
            client_llm.post("/poll/durdur")  # daemon thread temizligi

    def test_poll_baslat_cok_kucuk_interval_yoksayilir(self, client_llm, app_with_llm):
        onceki = app_with_llm.config["MAIL_POLLER"].state.interval_s
        try:
            client_llm.post("/poll/baslat", json={"interval_s": 5})  # <30 -> yoksay
            assert app_with_llm.config["MAIL_POLLER"].state.interval_s == onceki
        finally:
            client_llm.post("/poll/durdur")

    def test_poll_durum_snapshot(self, client_llm):
        resp = client_llm.get("/poll/durum")
        assert resp.status_code == 200
        d = resp.get_json()
        for key in ("enabled", "interval_s", "total_processed", "runs"):
            assert key in d


class TestOtomatikUI:
    def test_otomatik_karti_render(self, client_llm):
        html = client_llm.get("/").data.decode("utf-8")
        assert "Otomatik Mod" in html
        assert 'id="otomatik-toggle"' in html

    def test_llm_yoksa_otomatik_karti_yok(self, client_no_llm):
        # Otomatik mod parse=LLM gerektirir; LLM yoksa kart gosterilmez
        html = client_no_llm.get("/").data.decode("utf-8")
        assert 'id="otomatik-toggle"' not in html
