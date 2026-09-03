"""test_webapp.py — Flask test client smoke testleri.

Kapsam:
    - GET / -> 200 + kritik metinler
    - POST /run -> 302 (redirect) veya 200
    - GET /sonuc kos sonrasi 200 + "Toplam" metni
    - POST /ozet -> LLM ozet (FakeProvider inject)
    - POST /sor  -> LLM asistan (FakeProvider inject)
    - LLM kapali senaryo: llm_active=False -> LLM rotalar 503

Kosus: pytest tests/test_webapp.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# FakeProvider yardimcisi (webapp testleri icin)
# ---------------------------------------------------------------------------


def _make_fake_llm_provider(
    report_json: str = None,
    assistant_json: str = None,
):
    """webapp LLM rota testleri icin FakeProvider dondurur.

    Her iki rol de ayni provider'i kullanir (template_id'ye gore esleme).
    """
    from src.llm.provider import FakeProvider

    if report_json is None:
        report_json = json.dumps({
            "baslik": "Test Ozeti",
            "govde_md": "Bu test ozetidir.",
            "kullanilan_kaynaklar": [],
            "eksik_bilgi": [],
        }, ensure_ascii=False)

    if assistant_json is None:
        assistant_json = json.dumps({
            "cevap_md": "Test cevabidir.",
            "alintilar": [{"kaynak_id": "yerlesim#B001", "konum": "test"}],
            "onerilen_aksiyonlar": [],
            "ret": False,
            "ret_nedeni": None,
        }, ensure_ascii=False)

    return FakeProvider(
        fixture_map={
            ("report-v1", "_any_"): [report_json],
            ("assistant-v1", "_any_"): [assistant_json],
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Flask uygulamasini test modunda, LLM KAPALI olusturur."""
    from src.webapp.app import create_app
    application = create_app(testing=True, llm_provider_override=None, llm_enabled=False)
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_with_llm():
    """Flask uygulamasini LLM AKTIF (FakeProvider) olusturur."""
    from src.webapp.app import create_app
    provider = _make_fake_llm_provider()
    application = create_app(testing=True, llm_provider_override=provider)
    yield application


@pytest.fixture
def client_llm(app_with_llm):
    return app_with_llm.test_client()


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


class TestIndexRoute:

    def test_index_returns_200(self, client):
        assert client.get("/").status_code == 200

    def test_index_contains_app_title(self, client):
        html = client.get("/").data.decode("utf-8")
        assert "3D Nesting" in html

    def test_index_contains_run_button(self, client):
        html = client.get("/").data.decode("utf-8")
        assert "Calistir" in html or "Pipeline" in html

    def test_index_contains_scenario_info(self, client):
        html = client.get("/").data.decode("utf-8")
        assert any(k in html for k in ["FORD", "ASELSAN", "BAYKAR", "Demo", "Senaryo"])


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------


class TestRunRoute:

    def test_run_post_does_not_crash(self, client):
        response = client.post("/run", follow_redirects=False)
        assert response.status_code in (200, 302, 303)

    def test_run_post_with_follow_redirects(self, client):
        response = client.post("/run", follow_redirects=True)
        assert response.status_code == 200

    def test_run_post_result_contains_toplam(self, client):
        response = client.post("/run", follow_redirects=True)
        html = response.data.decode("utf-8")
        assert "Toplam" in html


# ---------------------------------------------------------------------------
# GET /sonuc
# ---------------------------------------------------------------------------


class TestSonucRoute:

    def test_sonuc_before_run_returns_valid(self, client):
        response = client.get("/sonuc")
        assert response.status_code in (200, 302)

    def test_sonuc_after_run_returns_200(self, client):
        client.post("/run", follow_redirects=True)
        assert client.get("/sonuc").status_code == 200

    def test_sonuc_after_run_contains_toplam(self, client):
        client.post("/run", follow_redirects=True)
        html = client.get("/sonuc").data.decode("utf-8")
        assert "Toplam" in html

    def test_sonuc_after_run_contains_batch_info(self, client):
        client.post("/run", follow_redirects=True)
        html = client.get("/sonuc").data.decode("utf-8")
        assert any(k in html for k in ["Parti", "Musteri", "parti", "B00", "Ciro"])

    def test_sonuc_after_run_contains_nesting_metrics(self, client):
        client.post("/run", follow_redirects=True)
        html = client.get("/sonuc").data.decode("utf-8")
        assert any(k in html for k in ["Yukseklik", "Doluluk", "mm", "yukseklik", "doluluk"])

    def test_sonuc_after_run_contains_pricing(self, client):
        client.post("/run", follow_redirects=True)
        html = client.get("/sonuc").data.decode("utf-8")
        assert any(k in html for k in ["Fiyat", "fiyat", "$", "Ciro"])


# ---------------------------------------------------------------------------
# POST /ozet — LLM kapali -> 503
# ---------------------------------------------------------------------------


class TestOzetRoute:

    def test_ozet_without_llm_returns_503(self, client):
        """LLM aktif degilse /ozet 503 donmeli."""
        client.post("/run", follow_redirects=True)
        response = client.post("/ozet", content_type="application/json")
        assert response.status_code == 503
        data = response.get_json()
        assert data["hata"] is not None

    def test_ozet_without_run_returns_400(self, client_llm):
        """Pipeline kosulmadan /ozet 400 donmeli."""
        response = client_llm.post("/ozet", content_type="application/json")
        assert response.status_code == 400
        data = response.get_json()
        assert data["hata"] is not None

    def test_ozet_with_llm_returns_200(self, client_llm):
        """LLM aktif + pipeline kosulmus -> /ozet 200 + ozet icerigi."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post("/ozet", content_type="application/json")
        assert response.status_code == 200
        data = response.get_json()
        # hata yoksa ozet veya topraklama_uyarisi olmali
        if data.get("hata") is None:
            assert data.get("ozet") is not None or data.get("topraklama_uyarisi") is not None

    def test_ozet_with_llm_json_response_structure(self, client_llm):
        """LLM aktif -> /ozet yanit JSON yapisi dogru."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post("/ozet", content_type="application/json")
        data = response.get_json()
        # "hata" anahtari her zaman olmali
        assert "hata" in data


# ---------------------------------------------------------------------------
# POST /sor — LLM asistan
# ---------------------------------------------------------------------------


class TestSorRoute:

    def test_sor_without_llm_returns_503(self, client):
        """LLM aktif degilse /sor 503 donmeli."""
        client.post("/run", follow_redirects=True)
        response = client.post(
            "/sor",
            data=json.dumps({"soru": "Test sorusu"}),
            content_type="application/json",
        )
        assert response.status_code == 503

    def test_sor_without_run_returns_400(self, client_llm):
        """Pipeline kosulmadan /sor 400 donmeli."""
        response = client_llm.post(
            "/sor",
            data=json.dumps({"soru": "Test sorusu"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_sor_empty_question_returns_400(self, client_llm):
        """Bos soru -> 400."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post(
            "/sor",
            data=json.dumps({"soru": ""}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_sor_with_llm_returns_200(self, client_llm):
        """LLM aktif + pipeline kosulmus -> /sor 200."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post(
            "/sor",
            data=json.dumps({"soru": "B001 yuksekligi nedir?"}),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_sor_response_structure(self, client_llm):
        """LLM aktif -> /sor yanit JSON yapisi dogru."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post(
            "/sor",
            data=json.dumps({"soru": "B001 partisi hakkinda ne biliyorsunuz?"}),
            content_type="application/json",
        )
        data = response.get_json()
        assert "hata" in data

    def test_sor_missing_body_returns_400(self, client_llm):
        """Soru anahtari eksikse 400 donmeli."""
        client_llm.post("/run", follow_redirects=True)
        response = client_llm.post(
            "/sor",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# create_app factory
# ---------------------------------------------------------------------------


class TestAppFactory:

    def test_create_app_returns_flask_app(self):
        from flask import Flask
        from src.webapp.app import create_app
        assert isinstance(create_app(testing=True), Flask)

    def test_testing_flag_set(self, app):
        assert app.testing is True

    def test_create_app_with_fake_provider(self):
        """FakeProvider injection ile app olusturabilmeli."""
        from flask import Flask
        from src.webapp.app import create_app
        provider = _make_fake_llm_provider()
        app = create_app(testing=True, llm_provider_override=provider)
        assert isinstance(app, Flask)


# ---------------------------------------------------------------------------
# /gecmis/arsiv/<dosya> — hoca paketi arsiv HTML servisi (2026-08-16)
# ---------------------------------------------------------------------------


class TestGecmisArsivRoute:

    def test_gecersiz_dosya_adi_404(self, client):
        """Whitelist regex: yol ayraci/encoded traversal reddedilir."""
        assert client.get("/gecmis/arsiv/..%5Cgecmis.jsonl").status_code == 404
        assert client.get("/gecmis/arsiv/a%2Fb.html").status_code == 404

    def test_olmayan_dosya_404(self, client):
        assert client.get("/gecmis/arsiv/olmayan.html").status_code == 404

    def test_mevcut_arsiv_html_servis_edilir(self, app, client):
        store = app.config["OTONOM_GECMIS"]
        arsiv = Path(store._path).parent / "arsiv"
        arsiv.mkdir(parents=True, exist_ok=True)
        (arsiv / "test_ok.html").write_text(
            "<html><body>ARSIV-ICERIK</body></html>", encoding="utf-8")
        r = client.get("/gecmis/arsiv/test_ok.html")
        assert r.status_code == 200
        assert b"ARSIV-ICERIK" in r.data


# ---------------------------------------------------------------------------
# Async not analizi (2026-08-16 "Incele bug" fix)
# ---------------------------------------------------------------------------


def _notlu_siparis_ekle(app, order_id="T-NOT-1", **meta_ekstra):
    ps = app.config["PENDING_STORE"]
    ps.add(
        order_id=order_id, customer="Test Musteri", sender="t@example.com",
        deadline="", priority_class=1, konu="test",
        stl_map={"parca_a": b"solid a\nendsolid a\n"},
        not_adaylari=[{"satir": "parca dik basilsin", "kaynak": "mail",
                       "parca_adaylari": ["parca_a"]}],
    )
    if meta_ekstra:
        ps.update_meta(order_id, **meta_ekstra)
    return order_id


class TestKisitAnalizAsync:

    def test_detay_get_aninda_acilir_analiz_bekliyor(self, app, client):
        """Detay GET artik LLM'i SENKRON cagirmaz — bekleme kutusu basar."""
        oid = _notlu_siparis_ekle(app)
        r = client.get(f"/kisit-onay/{oid}")
        assert r.status_code == 200
        assert b"analiz-bekliyor" in r.data

    def test_detay_get_onerili_metada_form_basar(self, app, client):
        """Meta'da kisit_onerileri varsa form direkt gelir (bekleme yok)."""
        oid = _notlu_siparis_ekle(
            app, kisit_onerileri=[{
                "tip": "orientation_lock", "deger": "dik",
                "parca_adi": "parca_a", "oy": 3, "hakem": "onay",
                "nihai_guven": "yuksek", "gerekce": "test",
                "derleme": "derlendi",
            }], kisit_n_ornekleme=3)
        r = client.get(f"/kisit-onay/{oid}")
        assert r.status_code == 200
        assert b"analiz-bekliyor" not in r.data
        assert b'name="onay_0"' in r.data

    def test_dusuk_guven_ve_derlenmeyen_de_onaylanabilir(self, app, client):
        """Eren istegi 2026-08-16: dusuk guven / derlenemeyen onerilerde de
        onay kutusu bulunur (yalniz yuksek guven varsayilan isaretli)."""
        oid = _notlu_siparis_ekle(
            app, order_id="T-NOT-4", kisit_onerileri=[
                {"tip": "orientation_lock", "deger": "dik",
                 "parca_adi": "parca_a", "oy": 1, "hakem": "ret",
                 "nihai_guven": "dusuk", "gerekce": "t",
                 "derleme": "derlendi"},
                {"tip": "grup_bolme", "parca_adi": "parca_a", "oy": 2,
                 "hakem": "onay", "nihai_guven": "orta", "gerekce": "t",
                 "derleme": "derlenemedi", "derleme_sebep": "sema-disi"},
            ], kisit_n_ornekleme=3)
        r = client.get(f"/kisit-onay/{oid}")
        assert r.status_code == 200
        assert b'name="onay_0"' in r.data  # dusuk guven: kutu var
        assert b'name="onay_1"' in r.data  # derlenemeyen: kutu var
        # hicbiri yuksek degil -> checked yok
        assert b"checked" not in r.data

    def test_analiz_api_llm_kapali_hata_json(self, app, client):
        oid = _notlu_siparis_ekle(app, order_id="T-NOT-2")
        r = client.get(f"/api/kisit-analiz/{oid}")
        assert r.status_code == 200
        assert "LLM aktif degil" in (r.get_json() or {}).get("analiz_hata", "")

    def test_analiz_api_olmayan_siparis_404(self, client):
        assert client.get("/api/kisit-analiz/YOK-1").status_code == 404

    def test_analiz_api_mevcut_onerileri_dondurur(self, app, client):
        """Oneri zaten meta'daysa LLM'e gitmeden ayni listeyi doner."""
        oid = _notlu_siparis_ekle(
            app, order_id="T-NOT-3",
            kisit_onerileri=[{"tip": "orientation_lock"}],
            kisit_n_ornekleme=3)
        v = client.get(f"/api/kisit-analiz/{oid}").get_json()
        assert v["analiz_hata"] is None
        assert v["oneriler"] == [{"tip": "orientation_lock"}]
        assert v["n_ornekleme"] == 3


# ---------------------------------------------------------------------------
# /kisit-onay/<id>/sil — onay beklemesini kaldirma (2026-08-18 operator istegi)
# ---------------------------------------------------------------------------


class TestKisitOnaySil:

    def test_onay_beklemesi_kalkar_siparis_kalir(self, app, client):
        """POST sil -> not/oneri alanlari dusuruldu; siparis + STL DURUYOR."""
        oid = _notlu_siparis_ekle(
            app, order_id="T-SIL-1",
            kisit_onerileri=[{"tip": "orientation_lock"}],
            kisit_n_ornekleme=3)
        r = client.post(f"/kisit-onay/{oid}/sil")
        assert r.status_code == 302
        assert "silindi=1" in r.headers["Location"]
        meta = app.config["PENDING_STORE"].get(oid)
        assert meta is not None                       # siparis silinMEdi
        assert "not_adaylari" not in meta             # kuyruktan cikti
        assert "kisit_onerileri" not in meta
        assert app.config["PENDING_STORE"].load_stl_map(oid)  # STL duruyor
        # Onay-bekleme listesinde artik gorunmez
        assert oid.encode() not in client.get("/kisit-onay").data

    def test_olmayan_siparis_bulunamadi(self, client):
        r = client.post("/kisit-onay/YOK-SIL/sil")
        assert r.status_code == 302
        assert "hata=bulunamadi" in r.headers["Location"]

    def test_onaylanmis_kisitlar_korunur(self, app, client):
        """Sil yalniz beklemeyi kaldirir — onceden onaylanan kisitlar kalir."""
        oid = _notlu_siparis_ekle(
            app, order_id="T-SIL-2",
            motor_kisitlari={"locked_orientations": {"parca_a": 0}})
        client.post(f"/kisit-onay/{oid}/sil")
        meta = app.config["PENDING_STORE"].get(oid)
        assert meta and meta.get("motor_kisitlari")

    def test_listede_sil_butonu_gorunur(self, app, client):
        oid = _notlu_siparis_ekle(app, order_id="T-SIL-3")
        r = client.get("/kisit-onay")
        assert r.status_code == 200
        assert f"/kisit-onay/{oid}/sil".encode() in r.data


# ---------------------------------------------------------------------------
# /sonuc/rehberli-sokum (2026-08-16 SOKUM plani linki)
# ---------------------------------------------------------------------------


class TestSonucRehberliSokum:

    def test_kosu_yokken_404(self, client):
        r = client.get("/sonuc/rehberli-sokum")
        assert r.status_code == 404
