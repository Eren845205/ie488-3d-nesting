"""test_gecmis_detay_tam.py — Gecmis kayitlarindan TAM detay gorunumu.

Kapsam:
- OtonomGecmisStore detay/GLB kalicilastirma + sil temizligi + traversal reddi
- _gecmis_kaydet detay JSON icerigi (agir alanlar haric) + GLB magic + dedup
  ezilmemesi + persist hatasinin ozet kaydi OLDURMEMESI + dict donusu
- Route'lar: zengin detay sayfasi, eski-kayit geriye uyumu, kalici GLB servisi,
  /gecmis/<id>/teklif, /poll/durum last_gecmis_id, CSRF
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.otonom_gecmis import OtonomGecmisStore
from tests.test_webapp_otonom import _make_full_fake_provider


def _make_provider_with_teklif():
    """Tam fake provider + teklif-v1 fixture'i (gecmisten-teklif testleri)."""
    provider = _make_full_fake_provider()
    provider._fixtures[("teklif-v1", "_any_")] = [json.dumps({
        "konu": "Siparis Teklifiniz",
        "mail_govde_md": "Sayin Musterimiz, teklifimiz ekte bilginize sunulmustur.",
        "kullanilan_kaynaklar": ["teklif#ozet"],
        "topraklama_uyarisi": False,
    }, ensure_ascii=False)] * 3
    return provider


@pytest.fixture
def store(tmp_path):
    return OtonomGecmisStore(tmp_path)


@pytest.fixture
def app_with_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=_make_provider_with_teklif())


@pytest.fixture
def client_llm(app_with_llm):
    return app_with_llm.test_client()


# ---------------------------------------------------------------------------
# Store katmani
# ---------------------------------------------------------------------------

class TestStoreDetay:
    def test_detay_round_trip(self, store):
        store.detay_kaydet("abc123", {"nesting_results": {"B001": {"height_mm": 42.0}}})
        d = store.detay_get("abc123")
        assert d is not None
        assert d["nesting_results"]["B001"]["height_mm"] == 42.0

    def test_detay_yoksa_none(self, store):
        assert store.detay_get("yokboyle") is None

    def test_detay_bozuk_json_none(self, store, tmp_path):
        detay_dir = tmp_path / "detay"
        detay_dir.mkdir(exist_ok=True)
        (detay_dir / "bozuk1.json").write_text("{bozuk json", encoding="utf-8")
        assert store.detay_get("bozuk1") is None

    def test_detay_atomik_tmp_dosya_kalmaz(self, store, tmp_path):
        store.detay_kaydet("abc123", {"a": 1})
        kalanlar = list((tmp_path / "detay").glob("*.tmp"))
        assert kalanlar == []


class TestStoreGlb:
    def test_glb_round_trip(self, store):
        store.glb_kaydet("abc123", "B001", b"glTF-test-bytes")
        p = store.glb_path("abc123", "B001")
        assert p is not None
        assert p.read_bytes() == b"glTF-test-bytes"

    def test_glb_yoksa_none(self, store):
        assert store.glb_path("abc123", "YOK") is None

    def test_glb_batch_id_traversal_sanitize(self, store, tmp_path):
        # Ayirici/parent kacislari sanitize edilir — dosya store koku ICINDE kalir
        store.glb_kaydet("abc123", "../../evil/batch", b"glTF-x")
        glb_dir = (tmp_path / "glb").resolve()
        dosyalar = list(glb_dir.glob("abc123_*.glb"))
        assert len(dosyalar) == 1
        assert str(dosyalar[0].resolve()).startswith(str(glb_dir))
        # Traversal'li sorgu da ayni sanitize yola gider (kok disina cikamaz)
        p = store.glb_path("abc123", "../../evil/batch")
        assert p is not None
        assert str(p.resolve()).startswith(str(glb_dir))

    def test_sil_detay_ve_glb_temizler(self, store):
        kayit = store.kaydet({"musteri": "X"})
        kid = kayit["id"]
        store.detay_kaydet(kid, {"a": 1})
        store.glb_kaydet(kid, "B001", b"glTF-y")
        assert store.detay_get(kid) is not None
        assert store.glb_path(kid, "B001") is not None
        store.sil(kid)
        assert store.detay_get(kid) is None
        assert store.glb_path(kid, "B001") is None

    def test_sil_baska_kaydin_artifactina_dokunmaz(self, store):
        k1 = store.kaydet({"musteri": "A"})["id"]
        k2 = store.kaydet({"musteri": "B"})["id"]
        store.detay_kaydet(k1, {"a": 1})
        store.detay_kaydet(k2, {"b": 2})
        store.sil(k1)
        assert store.detay_get(k1) is None
        assert store.detay_get(k2) is not None


# ---------------------------------------------------------------------------
# _gecmis_kaydet — detay kalicilastirma entegrasyonu
# ---------------------------------------------------------------------------

class TestGecmisKaydetDetay:
    def test_otonom_kosu_detay_json_uretir(self, client_llm, app_with_llm):
        r = client_llm.post("/otonom", json={})
        assert r.status_code == 200
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        detay = store.detay_get(kayit["id"])
        assert detay is not None
        assert "nesting_results" in detay
        assert "pricing_results" in detay
        assert "glb" in detay
        # Agir alanlar detaya YAZILMAZ
        for nr in detay["nesting_results"].values():
            assert "placements" not in nr
            assert "voxel_parts" not in nr

    def test_detay_json_serilestirilebilir(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        detay = store.detay_get(kayit["id"])
        json.dumps(detay)  # tam JSON-guvenli olmali (default=str'siz)

    def test_glb_dosyasi_magic_gltf(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        detay = store.detay_get(kayit["id"])
        glb_olan = [b for b, v in (detay.get("glb") or {}).items() if v]
        if not glb_olan:
            pytest.skip("bu kosuda GLB uretilmedi (placements yok)")
        p = store.glb_path(kayit["id"], glb_olan[0])
        assert p is not None
        assert p.read_bytes()[:4] == b"glTF"

    def test_kaydet_fn_kayit_listesi_dondurur(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        sonuc = fn(
            {"ranked_orders": [], "batches": [], "nesting_results": {},
             "pricing_results": {}, "elapsed_sec": 0.0},
            mod="auto", kaynak="manuel",
        )
        assert isinstance(sonuc, list) and len(sonuc) == 1
        assert sonuc[0].get("id")

    def test_detay_hatasi_ozet_kaydi_oldurmez(self, app_with_llm, monkeypatch):
        store = app_with_llm.config["OTONOM_GECMIS"]
        monkeypatch.setattr(
            store, "detay_kaydet",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disk dolu")),
        )
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        sonuc = fn(
            {"ranked_orders": [], "batches": [], "nesting_results": {},
             "pricing_results": {}, "elapsed_sec": 0.0},
            mod="auto", kaynak="manuel",
        )
        assert sonuc  # ozet kayit YASIYOR
        assert store.get(sonuc[0]["id"]) is not None

    def test_dedup_isabeti_detayi_ezmez(self, app_with_llm):
        from datetime import date
        from src.scheduling.models import Order
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        store = app_with_llm.config["OTONOM_GECMIS"]
        orders = [Order(order_id="ZIP-DEDUP01", customer="M", parts_ref="t",
                        total_quantity=1, total_volume_cm3=0.0,
                        deadline=str(date.today()), priority_class=1)]
        result = {"ranked_orders": orders, "batches": [],
                  "nesting_results": {"B001": {"height_mm": 10.0, "density": 0.5,
                                               "n_parts": 1, "pitch_mm": 2.0}},
                  "pricing_results": {}, "elapsed_sec": 0.0}
        k1 = fn(result, mod="auto", kaynak="otomatik")[0]
        # Ilk detayi isaretle
        d1 = store.detay_get(k1["id"])
        d1["_marker"] = "ilk-kosu"
        store.detay_kaydet(k1["id"], d1)
        # Ayni order_ids -> dedup isabeti (ayni kayit doner), detay EZILMEZ
        k2 = fn(result, mod="auto", kaynak="otomatik")[0]
        assert k2["id"] == k1["id"]
        assert store.detay_get(k1["id"]).get("_marker") == "ilk-kosu"


# ---------------------------------------------------------------------------
# Route'lar
# ---------------------------------------------------------------------------

class TestRunGecmiseYazar:
    def test_run_kosusu_gecmise_tam_detayla_duser(self, client_llm, app_with_llm):
        """Ana ekrandaki manuel 'calistir' (/run) da kalici gecmise yazmali."""
        r = client_llm.post("/run", data={"scenario_type": "rich"})
        assert r.status_code == 302  # /sonuc'a redirect
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayitlar = store.liste()
        assert len(kayitlar) >= 1
        kayit = kayitlar[0]
        assert kayit.get("kaynak") == "manuel"
        detay = store.detay_get(kayit["id"])
        assert detay is not None
        assert detay.get("nesting_results")
        # Detay sayfasi zengin bolumlerle acilir
        html = client_llm.get(f"/gecmis/{kayit['id']}").data.decode("utf-8")
        assert "Toplam Fiyat Onerisi" in html


class TestDetaySayfasi:
    def test_zengin_detay_bolumleri_render(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kid = app_with_llm.config["OTONOM_GECMIS"].liste()[0]["id"]
        html = client_llm.get(f"/gecmis/{kid}").data.decode("utf-8")
        assert "Parti " in html                       # parti-bazli bolum
        assert "Toplam Fiyat Onerisi" in html          # fiyat kirilimi
        assert "Tam kayıt" in html                     # kalicilik rozeti
        assert "Musteri Yanit Taslagi" in html         # teklif karti

    def test_eski_kayit_geriye_uyum(self, client_llm, app_with_llm):
        # detay JSON'suz + EKSIK-ALANLI kayit (cok eski sema — orn.
        # hacim_doluluk_pct alanindan onceki kayitlar) sayfayi KIRMAZ.
        # Gercek 500 vakasi: k.X Jinja Undefined donduruyor, "is not none"
        # kontrolu geciyor ve format() patliyordu — template k.get(...) kullanir.
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.kaydet({"musteri": "ESKI", "durum": "bitti", "kaynak": "manuel"})
        resp = client_llm.get(f"/gecmis/{kayit['id']}")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "önce" in html and "oluşturulmuş" in html  # eski-kayit notu
        assert "Toplam Fiyat Onerisi" not in html


class TestGecmisGeometri:
    def test_kalici_glb_servisi(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        detay = store.detay_get(kayit["id"])
        glb_olan = [b for b, v in (detay.get("glb") or {}).items() if v]
        if not glb_olan:
            pytest.skip("bu kosuda GLB uretilmedi")
        resp = client_llm.get(f"/gecmis/{kayit['id']}/geometri/{glb_olan[0]}")
        assert resp.status_code == 200
        assert resp.mimetype == "model/gltf-binary"
        assert resp.data[:4] == b"glTF"

    def test_olmayan_glb_404(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kid = app_with_llm.config["OTONOM_GECMIS"].liste()[0]["id"]
        resp = client_llm.get(f"/gecmis/{kid}/geometri/YOKBOYLE")
        assert resp.status_code == 404

    def test_gecersiz_kayit_id_formati_404(self, client_llm):
        resp = client_llm.get("/gecmis/..%2F..%2Fetc/geometri/B001")
        assert resp.status_code == 404

    def test_restart_sonrasi_glb_hala_erisilir(self, client_llm, app_with_llm):
        """Kalicilik kaniti: ayni store koku ile YENI app kur -> GLB durur."""
        client_llm.post("/otonom", json={})
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.liste()[0]
        detay = store.detay_get(kayit["id"])
        glb_olan = [b for b, v in (detay.get("glb") or {}).items() if v]
        if not glb_olan:
            pytest.skip("bu kosuda GLB uretilmedi")
        # "Restart": ayni root'tan taze store — dosya diskte kalici
        taze = OtonomGecmisStore(store._root)
        assert taze.detay_get(kayit["id"]) is not None
        p = taze.glb_path(kayit["id"], glb_olan[0])
        assert p is not None and p.read_bytes()[:4] == b"glTF"


class TestGecmisTeklif:
    def test_kalici_detaydan_taslak(self, client_llm, app_with_llm):
        client_llm.post("/otonom", json={})
        kid = app_with_llm.config["OTONOM_GECMIS"].liste()[0]["id"]
        # LAST_RESULT'i temizle — taslak YALNIZ kalici detaydan uretilebilmeli
        app_with_llm.config["LAST_RESULT"] = None
        resp = client_llm.post(f"/gecmis/{kid}/teklif")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("taslak")

    def test_detaysiz_kayit_404(self, client_llm, app_with_llm):
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayit = store.kaydet({"musteri": "ESKI"})
        resp = client_llm.post(f"/gecmis/{kayit['id']}/teklif")
        assert resp.status_code == 404

    def test_csrf_tokensiz_post_reddedilir(self, monkeypatch):
        # CSRF yalniz testing=False'ta aktif (guvenlik test deseniyle ayni)
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        from src.webapp.app import create_app
        app = create_app(testing=False, llm_enabled=False, load_env=False)
        c = app.test_client()
        r = c.post("/gecmis/abc123/teklif")
        assert r.status_code == 403


class TestSilSecenekleri:
    """Silme secenekleri (kullanici karari 2026-07-05): varsayilan = mail
    yeniden islenebilir; idem_birak=1 = kayit silinir ama mail islenmis
    sayilmaya devam eder."""

    def _otomatik_kayit(self, app_with_llm, idem_key, order_id):
        from datetime import date
        from src.scheduling.models import Order
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        idem_store.register(idem_key)
        orders = [Order(order_id=order_id, customer="M", parts_ref="t",
                        total_quantity=1, total_volume_cm3=0.0,
                        deadline=str(date.today()), priority_class=1)]
        result = {"ranked_orders": orders, "batches": [], "nesting_results": {},
                  "pricing_results": {}, "elapsed_sec": 0.0,
                  "_idem_keys": [idem_key]}
        return fn(result, mod="auto", kaynak="otomatik")[0]

    def test_varsayilan_sil_yeniden_islenebilir(self, client_llm, app_with_llm):
        kayit = self._otomatik_kayit(app_with_llm, "hash-sil-1", "ZIP-SIL0001")
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        r = client_llm.post(f"/gecmis/{kayit['id']}/sil", data={})
        assert r.status_code == 302
        assert idem_store.is_registered("hash-sil-1") is False  # yeniden islenir

    def test_idem_birak_ile_sil_islenmis_kalir(self, client_llm, app_with_llm):
        kayit = self._otomatik_kayit(app_with_llm, "hash-sil-2", "ZIP-SIL0002")
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        r = client_llm.post(f"/gecmis/{kayit['id']}/sil", data={"idem_birak": "1"})
        assert r.status_code == 302
        store = app_with_llm.config["OTONOM_GECMIS"]
        assert store.get(kayit["id"]) is None                    # kayit silindi
        assert idem_store.is_registered("hash-sil-2") is True    # mail islenmis kalir


class TestMailFarkindaliDedup:
    """Ayni paket FARKLI mail ile yeniden gelirse yeni kayit yazilmali;
    ayni mailin retry'i (ayni idem key) dedup'lanmali."""

    def _result(self, order_id, idem_keys):
        from datetime import date
        from src.scheduling.models import Order
        orders = [Order(order_id=order_id, customer="M", parts_ref="t",
                        total_quantity=1, total_volume_cm3=0.0,
                        deadline=str(date.today()), priority_class=1)]
        return {"ranked_orders": orders, "batches": [], "nesting_results": {},
                "pricing_results": {}, "elapsed_sec": 0.0,
                "_idem_keys": idem_keys}

    def test_farkli_mail_ayni_paket_yeni_kayit(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        k1 = fn(self._result("ORD-AYNI", ["mail-hash-A"]), mod="auto", kaynak="otomatik")[0]
        k2 = fn(self._result("ORD-AYNI", ["mail-hash-B"]), mod="auto", kaynak="otomatik")[0]
        assert k1["id"] != k2["id"]  # farkli mail -> yeniden islendi, yeni kayit

    def test_ayni_mail_retry_dedup(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        k1 = fn(self._result("ORD-RETRY", ["mail-hash-C"]), mod="auto", kaynak="otomatik")[0]
        k2 = fn(self._result("ORD-RETRY", ["mail-hash-C"]), mod="auto", kaynak="otomatik")[0]
        assert k1["id"] == k2["id"]  # ayni mail retry -> tek kayit


class TestSiparisBazliKayit:
    """Ayni kosuda islenen her siparis AYRI gecmis kaydi olur (kullanici
    karari 2026-07-05); ayni partiyi paylasan siparisler bolunmez."""

    def _order(self, oid, musteri="M"):
        from datetime import date
        from src.scheduling.models import Order
        return Order(order_id=oid, customer=musteri, parts_ref="t",
                     total_quantity=1, total_volume_cm3=0.0,
                     deadline=str(date.today()), priority_class=1)

    def _batch(self, bid, orders):
        from src.scheduling.batcher import Batch
        return Batch(batch_id=bid, orders=orders, total_volume_cm3=0.0,
                     customer=orders[0].customer if orders else "")

    def _iki_plan_result(self):
        o1 = self._order("PLAN-1", "HOCA")
        o3 = self._order("PLAN-3", "HOCA")
        b1 = self._batch("B001", [o1])
        b3 = self._batch("B002", [o3])
        return {
            "ranked_orders": [o1, o3],
            "batches": [b1, b3],
            "nesting_results": {
                "B001": {"height_mm": 100.0, "density": 0.4, "n_parts": 5,
                         "pitch_mm": 2.0, "plate_w_mm": 300.0, "plate_d_mm": 300.0},
                "B002": {"height_mm": 200.0, "density": 0.5, "n_parts": 9,
                         "pitch_mm": 2.0, "plate_w_mm": 300.0, "plate_d_mm": 300.0},
            },
            "pricing_results": {
                "B001": {"total_price": 111.0, "breakdown": ["a"]},
                "B002": {"total_price": 333.0, "breakdown": ["b"]},
            },
            "warnings": [],
            "elapsed_sec": 42.0,
            "_idem_keys": ["mail-p1", "mail-p3"],
            "_idem_key_map": {"PLAN-1": "mail-p1", "PLAN-3": "mail-p3"},
        }

    def test_iki_siparis_iki_kayit(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        kayitlar = fn(self._iki_plan_result(), mod="auto", kaynak="otomatik")
        assert isinstance(kayitlar, list) and len(kayitlar) == 2
        ids = {tuple(k["order_ids"]) for k in kayitlar}
        assert ids == {("PLAN-1",), ("PLAN-3",)}
        # Kosu baglantisi her kayitta
        assert all(k.get("kosu_id") for k in kayitlar)
        assert all(k.get("kosu_siparis_sayisi") == 2 for k in kayitlar)
        assert len({k["kosu_id"] for k in kayitlar}) == 1  # ayni kosu

    def test_kayitlar_kendi_parti_ve_fiyatini_tasir(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        store = app_with_llm.config["OTONOM_GECMIS"]
        kayitlar = fn(self._iki_plan_result(), mod="auto", kaynak="otomatik")
        k_p1 = next(k for k in kayitlar if k["order_ids"] == ["PLAN-1"])
        k_p3 = next(k for k in kayitlar if k["order_ids"] == ["PLAN-3"])
        assert k_p1["toplam_fiyat"] == 111.0
        assert k_p3["toplam_fiyat"] == 333.0
        assert k_p1["min_yukseklik_mm"] == 100.0
        assert k_p3["min_yukseklik_mm"] == 200.0
        d_p1 = store.detay_get(k_p1["id"])
        assert set(d_p1["nesting_results"].keys()) == {"B001"}
        d_p3 = store.detay_get(k_p3["id"])
        assert set(d_p3["nesting_results"].keys()) == {"B002"}

    def test_sil_yalniz_kendi_mailini_acar(self, client_llm, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        idem_store = app_with_llm.config["SHARED_IDEM_STORE"]
        idem_store.register("mail-p1")
        idem_store.register("mail-p3")
        kayitlar = fn(self._iki_plan_result(), mod="auto", kaynak="otomatik")
        k_p1 = next(k for k in kayitlar if k["order_ids"] == ["PLAN-1"])
        r = client_llm.post(f"/gecmis/{k_p1['id']}/sil", data={})
        assert r.status_code == 302
        assert idem_store.is_registered("mail-p1") is False  # PLAN-1 yeniden islenir
        assert idem_store.is_registered("mail-p3") is True   # PLAN-3'e DOKUNULMAZ

    def test_ayni_partiyi_paylasan_siparisler_bolunmez(self, app_with_llm):
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        o1 = self._order("ORT-1", "X")
        o2 = self._order("ORT-2", "X")
        ortak = self._batch("B001", [o1, o2])  # batching birlestirmis
        result = {
            "ranked_orders": [o1, o2], "batches": [ortak],
            "nesting_results": {"B001": {"height_mm": 50.0, "density": 0.3,
                                         "n_parts": 2, "pitch_mm": 2.0}},
            "pricing_results": {"B001": {"total_price": 10.0, "breakdown": []}},
            "warnings": [], "elapsed_sec": 1.0,
        }
        kayitlar = fn(result, mod="auto", kaynak="otomatik")
        assert len(kayitlar) == 1  # parti bolunemez -> tek kayit
        assert kayitlar[0]["order_ids"] == ["ORT-1", "ORT-2"]


class TestPollDurumDetayLinki:
    def test_last_gecmis_id_alani_var(self, client_llm):
        data = client_llm.get("/poll/durum").get_json()
        assert "last_gecmis_id" in data
        assert "last_gecmis_kayitlar" in data

    def test_coklu_siparis_her_kayit_icin_link_verisi(self, app_with_llm):
        """Coklu siparis kosusunda /poll/durum HER kaydin id+etiketini tasir
        (gozcu panosu siparis basina ayri 'detaylari gor' linki basar)."""
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        yardimci = TestSiparisBazliKayit()
        kayitlar = fn(yardimci._iki_plan_result(), mod="auto", kaynak="otomatik")
        # _poll_on_result'un yaptigi atama:
        app_with_llm.config["SON_GECMIS_ID"] = kayitlar[-1]["id"]
        app_with_llm.config["SON_GECMIS_KAYITLAR"] = [
            {"id": k["id"], "musteri": k.get("musteri"),
             "order_ids": k.get("order_ids") or []}
            for k in kayitlar
        ]
        data = app_with_llm.test_client().get("/poll/durum").get_json()
        assert len(data["last_gecmis_kayitlar"]) == 2
        oidler = {tuple(k["order_ids"]) for k in data["last_gecmis_kayitlar"]}
        assert oidler == {("PLAN-1",), ("PLAN-3",)}

    def test_poll_on_result_son_id_yazar(self, app_with_llm):
        # _poll_on_result semantigi: basarili kayit -> SON_GECMIS_ID guncellenir.
        # Dogrudan fn ile ayni yol: kaydet dict dondurur, id config'e yazilir.
        fn = app_with_llm.config["GECMIS_KAYDET_FN"]
        sonuc = fn(
            {"ranked_orders": [], "batches": [], "nesting_results": {},
             "pricing_results": {}, "elapsed_sec": 0.0},
            mod="auto", kaynak="manuel",
        )
        app_with_llm.config["SON_GECMIS_ID"] = sonuc[-1]["id"]
        client = app_with_llm.test_client()
        data = client.get("/poll/durum").get_json()
        assert data["last_gecmis_id"] == sonuc[-1]["id"]
