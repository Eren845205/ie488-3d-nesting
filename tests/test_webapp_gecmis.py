"""test_webapp_gecmis.py — /gecmis sayfasi + is-gecmisi entegrasyonu (Faz 2) TDD.

- GET /gecmis 200 + nav sekmesi
- Bos gecmis zarif mesaj
- Otonom is sonrasi kayit /gecmis'te gorunur (senkron yol gecmise yazar)
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


class TestGecmisSayfasi:
    def test_gecmis_rota_var(self, client_no_llm):
        resp = client_no_llm.get("/gecmis")
        assert resp.status_code == 200

    def test_gecmis_bos_zarif_mesaj(self, client_no_llm):
        html = client_no_llm.get("/gecmis").data.decode("utf-8")
        assert "Henüz işlenmiş" in html or "Boş" in html

    def test_nav_gecmis_sekmesi(self, client_no_llm):
        html = client_no_llm.get("/gecmis").data.decode("utf-8")
        assert "/gecmis" in html
        assert "İş Geçmişi" in html


class TestGecmisEntegrasyon:
    def test_otonom_sonrasi_gecmiste_gorunur(self, client_llm):
        # Senkron otonom calistir -> gecmise yazilmali
        r = client_llm.post("/otonom", json={})
        assert r.status_code == 200
        html = client_llm.get("/gecmis").data.decode("utf-8")
        # Tamamlanan is satiri: durum rozeti + bir musteri/metrik gorunur
        assert "Tamamlandı" in html
        assert "İşlenen İşler" in html

    def test_otonom_iki_kez_iki_kayit(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        assert len(store.liste()) == 2

    def test_gecmis_kaydinda_asama_ozeti_var(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kayit = app_with_llm.config["OTONOM_GECMIS"].liste()[0]
        assert isinstance(kayit.get("asamalar"), list)
        assert any(a.get("ad") == "Mail-Cek" for a in kayit["asamalar"])


class TestGecmisDetay:
    def test_satir_detay_linki_iceriyor(self, client_llm):
        client_llm.post("/otonom", json={})
        html = client_llm.get("/gecmis").data.decode("utf-8")
        assert "/gecmis/" in html  # satir onclick -> detay sayfasi

    def test_detay_sayfasi_acilir(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kid = app_with_llm.config["OTONOM_GECMIS"].liste()[0]["id"]
        resp = client_llm.get(f"/gecmis/{kid}")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "İş Geçmişine Dön" in html              # geri linki
        assert "İşlem Hattı Aşamaları" in html          # asama ozeti bolumu
        assert "Sonuç Metrikleri" in html               # metrik kartlari

    def test_bilinmeyen_id_listeye_yonlendirir(self, client_no_llm):
        resp = client_no_llm.get("/gecmis/yokboyle")
        assert resp.status_code == 302
        assert "/gecmis" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# Downstream dedup — _gecmis_kaydet app-katmani testleri
# ---------------------------------------------------------------------------

class TestGecmisDedupOtomatik:
    """Downstream dedup: kaynak=otomatik ayni order_ids -> tek kayit."""

    def _make_fake_result(self, order_ids):
        """order_id tasiyan Order stub'larla minimal pipeline_result."""
        from datetime import date
        from src.scheduling.models import Order
        orders = [
            Order(
                order_id=oid,
                customer="TESTMUST",
                parts_ref="test",
                total_quantity=1,
                total_volume_cm3=0.0,
                deadline=str(date.today()),
                priority_class=1,
            )
            for oid in order_ids
        ]
        return {
            "ranked_orders": orders,
            "batches": [],
            "nesting_results": {},
            "pricing_results": {},
            "elapsed_sec": 0.0,
        }

    def test_gecmis_kaydinda_order_ids_alani_var(self, app_with_llm):
        """Gecmis kaydinda order_ids listesi olmali."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        result = self._make_fake_result(["ZIP-AABB1122"])
        fn(result, mod="auto", kaynak="otomatik")
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        assert "order_ids" in kayit
        assert kayit["order_ids"] == ["ZIP-AABB1122"]

    def test_otomatik_ayni_order_ids_tek_kayit(self, app_with_llm):
        """kaynak=otomatik, ayni order_ids ile iki cagri -> tek kayit."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        result = self._make_fake_result(["ZIP-AABB1122"])
        fn(result, mod="auto", kaynak="otomatik")
        fn(result, mod="auto", kaynak="otomatik")
        store = app_with_llm.config["OTONOM_GECMIS"]
        assert len(store.liste()) == 1

    def test_manuel_iki_cagri_iki_kayit(self, app_with_llm):
        """kaynak=manuel, iki cagri -> iki kayit (dedup uygulanmaz)."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        result = self._make_fake_result(["ZIP-AABB1122"])
        fn(result, mod="auto", kaynak="manuel")
        fn(result, mod="auto", kaynak="manuel")
        store = app_with_llm.config["OTONOM_GECMIS"]
        assert len(store.liste()) == 2
