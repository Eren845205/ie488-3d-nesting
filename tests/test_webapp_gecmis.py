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

    def test_otomatik_idem_keys_gecmis_kaydinda_saklanir(self, app_with_llm):
        """pipeline_result['_idem_keys'] -> gecmis kaydinin ic alani (route icin)."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        result = self._make_fake_result(["ZIP-AABB1122"])
        result["_idem_keys"] = ["hash-1", "hash-2"]
        fn(result, mod="auto", kaynak="otomatik")
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]
        # sil() ic alanlari (route'un okudugu) geri dondurur
        silinen = store.sil(kayit_id)
        assert silinen["_idem_keys"] == ["hash-1", "hash-2"]

    def test_manuel_kayitta_idem_keys_yazilmaz(self, app_with_llm):
        """kaynak=manuel ise _idem_keys asla yazilmaz (yalniz otomatik/poller)."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        result = self._make_fake_result(["ZIP-AABB1122"])
        result["_idem_keys"] = ["hash-1"]
        fn(result, mod="auto", kaynak="manuel")
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]
        silinen = store.sil(kayit_id)
        assert not silinen.get("_idem_keys")


# ---------------------------------------------------------------------------
# Gecmisten sil -> yeniden islenebilir
# ---------------------------------------------------------------------------

class TestGecmisSil:
    def test_sil_rotasi_kaydi_kaldirir_ve_yonlendirir(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]

        resp = client_llm.post(f"/gecmis/{kayit_id}/sil")
        assert resp.status_code == 302
        assert "/gecmis" in resp.headers.get("Location", "")
        assert store.get(kayit_id) is None

    def test_sil_bilinmeyen_id_hata_vermez(self, client_llm):
        resp = client_llm.post("/gecmis/yokboyle/sil")
        assert resp.status_code == 302

    def test_sil_liste_sayfasindan_kayit_kaybolur(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]

        client_llm.post(f"/gecmis/{kayit_id}/sil")
        html = client_llm.get("/gecmis").data.decode("utf-8")
        assert "Henüz işlenmiş" in html or "Boş" in html

    def test_sil_idempotency_anahtarlarini_da_dusurur(self, app_with_llm):
        """_idem_keys tasiyan otomatik kayit silinince paylasimli idempotency
        store'dan da anahtarlar dusurulur -> is_registered False doner."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        idem_store.register("hash-abc")
        result = self._make_fake_result_local()
        result["_idem_keys"] = ["hash-abc"]
        fn(result, mod="auto", kaynak="otomatik")

        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]
        assert idem_store.is_registered("hash-abc") is True

        client = app_with_llm.test_client()
        client.post(f"/gecmis/{kayit_id}/sil")
        assert idem_store.is_registered("hash-abc") is False

    @staticmethod
    def _make_fake_result_local():
        from datetime import date
        from src.scheduling.models import Order
        orders = [
            Order(
                order_id="ZIP-XYZ99900",
                customer="TESTMUST",
                parts_ref="test",
                total_quantity=1,
                total_volume_cm3=0.0,
                deadline=str(date.today()),
                priority_class=1,
            )
        ]
        return {
            "ranked_orders": orders,
            "batches": [],
            "nesting_results": {},
            "pricing_results": {},
            "elapsed_sec": 0.0,
        }

    def test_sil_eski_kayit_idem_keys_yoksa_yalniz_kayit_silinir(self, client_llm, app_with_llm):
        """Eski (gecmis) kayitlarda _idem_keys alani yok -- sil() hata vermeden
        yalniz kaydi kaldirir (geriye uyum, yeniden-isleme garantisi verilmez)."""
        client_llm.post("/otonom", json={})  # manuel kaynak -> _idem_keys yok
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]

        resp = client_llm.post(f"/gecmis/{kayit_id}/sil")
        assert resp.status_code == 302
        assert store.get(kayit_id) is None


# ---------------------------------------------------------------------------
# Uctan uca: isle -> sil -> mail hala pencerede -> yeniden islenir
# ---------------------------------------------------------------------------

class TestGecmisSilIdemUyari:
    """unregister basarisiz olursa kullaniciya /gecmis'te uyari gosterilmeli
    (sessizce yalniz logger.warning ile yutulmamali)."""

    def test_unregister_hata_verirse_redirect_idem_uyari_flag_tasir(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        from datetime import date
        from src.scheduling.models import Order
        orders = [Order(order_id="ZIP-UYARI001", customer="TESTMUST", parts_ref="test",
                         total_quantity=1, total_volume_cm3=0.0,
                         deadline=str(date.today()), priority_class=1)]
        pipeline_result = {
            "ranked_orders": orders, "batches": [], "nesting_results": {},
            "pricing_results": {}, "elapsed_sec": 0.0,
            "_idem_keys": ["hash-fail"],
        }
        fn(pipeline_result, mod="auto", kaynak="otomatik")
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]

        def _patlayan_unregister(key):
            raise RuntimeError("simulasyon: unregister basarisiz")
        idem_store.unregister = _patlayan_unregister

        client = app_with_llm.test_client()
        resp = client.post(f"/gecmis/{kayit_id}/sil")
        assert resp.status_code == 302
        assert "idem_uyari=1" in resp.headers.get("Location", "")

        html = client.get(resp.headers["Location"]).data.decode("utf-8")
        assert "idempotency anahtar" in html.lower()

    def test_unregister_basarili_ise_idem_uyari_yok(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        from datetime import date
        from src.scheduling.models import Order
        orders = [Order(order_id="ZIP-UYARI002", customer="TESTMUST", parts_ref="test",
                         total_quantity=1, total_volume_cm3=0.0,
                         deadline=str(date.today()), priority_class=1)]
        pipeline_result = {
            "ranked_orders": orders, "batches": [], "nesting_results": {},
            "pricing_results": {}, "elapsed_sec": 0.0,
            "_idem_keys": ["hash-ok"],
        }
        fn(pipeline_result, mod="auto", kaynak="otomatik")
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit_id = store.liste()[0]["id"]

        client = app_with_llm.test_client()
        resp = client.post(f"/gecmis/{kayit_id}/sil")
        assert resp.status_code == 302
        assert "idem_uyari" not in resp.headers.get("Location", "")


class TestGecmisSilYenidenIslenebilir:
    """process_inbox_once + gercek shared idempotency store + gecmis_sil route
    ile "gecmisten sil -> yeniden islenebilir" tam zincirini dogrular."""

    class _FakeImapLikeSource:
        """IMAP benzeri: idem_key_for + mark_processed GERCEK paylasimli
        idempotency store'u kullanir; fetch_new pencere-farkindaligini taklit
        eder (kayitli olmayan mailleri dondurur -- gercek ImapMailbox mantigi)."""

        def __init__(self, mails, idem_store):
            self._mails = mails
            self._idem_store = idem_store

        def idem_key_for(self, mail):
            from src.runtime.idempotency import idempotency_key
            return idempotency_key("test-imap", mail.message_id)

        def fetch_new(self):
            return [
                m for m in self._mails
                if not self._idem_store.is_registered(self.idem_key_for(m))
            ]

        def mark_processed(self, mail):
            from src.runtime.idempotency import DuplicateKeyError
            try:
                self._idem_store.register(self.idem_key_for(mail))
            except DuplicateKeyError:
                pass

    @staticmethod
    def _zip_mail(mid="<GECMIS-SIL-1@x>"):
        import io
        import zipfile

        trimesh = pytest.importorskip("trimesh")
        from src.runtime.mail_ingest import Attachment, RawMail

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("braket.stl", trimesh.creation.box(extents=(40, 30, 15)).export(file_type="stl"))
            z.writestr("kapak.stl", trimesh.creation.box(extents=(60, 40, 10)).export(file_type="stl"))
        return RawMail(
            gonderen="uretim@firma.com.tr", konu="Plan1",
            govde="braket 3 adet\nkapak 2 adet",
            tarih="2026-06-14T09:00:00+03:00", message_id=mid,
            ekler=[Attachment("parcalar.zip", buf.getvalue(), "application/zip")],
        )

    def test_isle_sil_pencerede_kalan_mail_yeniden_islenir(self, app_with_llm, tmp_path):
        from scripts.demo_pipeline import RICH_SCENARIO
        from src.runtime.mail_poller import process_inbox_once

        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        gecmis_store = app_with_llm.config["OTONOM_GECMIS"]
        gecmis_kaydet = app_with_llm.config["GECMIS_KAYDET_FN"]
        mail = self._zip_mail()
        source = self._FakeImapLikeSource([mail], idem_store)

        # Tur 1: mail islenir + gecmise kaydedilir (poller'in on_result'i)
        def _on_result(result):
            gecmis_kaydet(result, mod="auto", nfv_quality="fast", kaynak="otomatik")

        r1 = process_inbox_once(
            source, parser_role=None, base_scenario=RICH_SCENARIO,
            persist_root=str(tmp_path), on_result=_on_result,
        )
        assert r1 is not None

        idem_key = source.idem_key_for(mail)
        assert idem_store.is_registered(idem_key) is True  # mark_processed calisti

        # Tur 2 (silmeden ONCE): ayni mail hala "pencerede" ama idempotency
        # kayitli -> fetch_new bos doner (yeniden islenmez)
        r2 = process_inbox_once(
            source, parser_role=None, base_scenario=RICH_SCENARIO,
            persist_root=str(tmp_path), on_result=_on_result,
        )
        assert r2 is None

        # Gecmisten sil -> idempotency anahtari da dusurulur
        kayit_id = gecmis_store.liste()[0]["id"]
        client = app_with_llm.test_client()
        client.post(f"/gecmis/{kayit_id}/sil")
        assert idem_store.is_registered(idem_key) is False

        # Tur 3 (silme sonrasi): mail HALA pencerede (source hala tasiyor) ve
        # artik idempotency kaydi yok -> yeni mail gibi YENIDEN islenir
        r3 = process_inbox_once(
            source, parser_role=None, base_scenario=RICH_SCENARIO,
            persist_root=str(tmp_path), on_result=_on_result,
        )
        assert r3 is not None
        assert r3.get("nesting_results")
        assert len(gecmis_store.liste()) == 1  # yeni gecmis kaydi yazildi
