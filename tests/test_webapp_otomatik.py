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


class TestOtomatikModPolitikasi:
    """Kullanici karari 2026-07-03: gozcu HER ZAMAN NFV kalite modunda kosar.

    Gerekce: auto->heightmap sezgiseli kutu-oranina bakip ince cidarli KABUK
    parcalarda yaniliyordu (Deneme4: 377mm heightmap vs Magics 250mm hedef).
    Heightmap yalniz manuel ekranda bilincli secenek olarak kalir."""

    def test_poller_senaryosu_nfv_quality_max(self, app_with_llm):
        poller = app_with_llm.config["MAIL_POLLER"]
        assert poller._base_scenario.get("nesting_mode") == "nfv"
        assert poller._base_scenario.get("nfv_quality") == "max"

    def test_otomatik_gecmis_kaydi_nfv_etiketli(self, app_with_llm):
        poller = app_with_llm.config["MAIL_POLLER"]
        poller.poll_once()
        kayit = app_with_llm.config["OTONOM_GECMIS"].liste()[0]
        assert kayit["mod"] == "nfv"
        assert kayit["nfv_quality"] == "max"


class TestKesinSonucGecmisKaydi:
    """P0 (2026-07-03): sifir-sonuclu kosu gecmise 'hata' olarak duser,
    hata notu tasir ve BASARILI kaydin dedup anahtarini tuketmez."""

    @staticmethod
    def _fail_result():
        from types import SimpleNamespace
        return {
            "ranked_orders": [SimpleNamespace(customer="FSM", order_id="ZIP-X1")],
            "batches": [1],
            "nesting_results": {"B001": {"height_mm": 0.0,
                                         "note": "Tuner hatasi: voxel bos"}},
            "pricing_results": {},
            "elapsed_sec": 5.0,
        }

    @staticmethod
    def _ok_result():
        from types import SimpleNamespace
        return {
            "ranked_orders": [SimpleNamespace(customer="FSM", order_id="ZIP-X1")],
            "batches": [1],
            "nesting_results": {"B001": {"height_mm": 42.0, "density": 0.5}},
            "pricing_results": {"B001": {"total_price": 200.0}},
            "elapsed_sec": 7.0,
        }

    def test_sifir_sonuc_hata_kaydi_ve_ozet(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        gecmis = app_with_llm.config["OTONOM_GECMIS"]
        fn(self._fail_result(), mod="nfv", kaynak="otomatik")
        kayit = gecmis.liste()[0]
        assert kayit["durum"] == "hata"
        assert "Tuner hatasi" in kayit["hata_ozeti"]

    def test_kismi_basari_kaydi(self, app_with_llm):
        """R1 #3: bazi partiler uretemezse durum='kismi' + basarisiz parti
        notu; sonraki TAM basari kaydi ayri anahtarla YAZILIR."""
        from types import SimpleNamespace
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        gecmis = app_with_llm.config["OTONOM_GECMIS"]
        partial = {
            "ranked_orders": [SimpleNamespace(customer="FSM", order_id="ZIP-X1")],
            "batches": [1, 2],
            "nesting_results": {
                "B001": {"height_mm": 42.0, "density": 0.5},
                "B002": {"height_mm": 0.0, "note": "Tuner hatasi: parti B"},
            },
            "pricing_results": {}, "elapsed_sec": 5.0,
        }
        fn(partial, mod="nfv", kaynak="otomatik")
        fn(partial, mod="nfv", kaynak="otomatik")   # retry — cogalmasin
        fn(self._ok_result(), mod="nfv", kaynak="otomatik")
        kayitlar = gecmis.liste()
        durumlar = [k["durum"] for k in kayitlar]
        assert durumlar.count("kismi") == 1
        assert durumlar.count("bitti") == 1
        kismi = next(k for k in kayitlar if k["durum"] == "kismi")
        assert "parti B" in kismi["hata_ozeti"]

    def test_hata_kaydi_basarili_kaydi_bloklamaz(self, app_with_llm):
        """Bugunku canli olay: hata kaydi dedup anahtarini tuketseydi,
        duzeltme sonrasi basarili kosunun kaydi GORUNMEZ olurdu."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        gecmis = app_with_llm.config["OTONOM_GECMIS"]
        fn(self._fail_result(), mod="nfv", kaynak="otomatik")
        fn(self._fail_result(), mod="nfv", kaynak="otomatik")  # retry ayni hata
        fn(self._ok_result(), mod="nfv", kaynak="otomatik")    # duzeltme sonrasi
        kayitlar = gecmis.liste()
        durumlar = [k["durum"] for k in kayitlar]
        assert durumlar.count("hata") == 1    # retry cogaltmadi (hata-dedup)
        assert durumlar.count("bitti") == 1   # basari kaydi YAZILDI
        bitti = next(k for k in kayitlar if k["durum"] == "bitti")
        assert bitti["min_yukseklik_mm"] == 42.0


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
