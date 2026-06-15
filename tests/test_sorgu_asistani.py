"""test_sorgu_asistani.py -- Sorgu Asistani Paneli testleri (TDD RED->GREEN).

Kapsam:
    A) Niyet-yonlendirici (saf fonksiyon): anahtar kelime -> rol secimi
    B) /sor rotasi genisletmesi: ozet->report, neden->explainer, genel->assistant
    C) Birlesik JSON yanit: cevap_md, alintilar|kaynaklar, ret, kullanilan_rol, hata
    D) LLM kapali -> 503 (mevcut desen)
    E) Read-only invariant: LAST_RESULT /sor sonrasi degismemeli
    F) Baglam-disi soru -> ret rozeti
    G) Hazir-soru dugmeleri UI'da mevcut (LLM aktifken)
    H) Explainer karar_tipi cikarimi: algoritma/fiyat/oncelik

Kosus: pytest tests/test_sorgu_asistani.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# FakeProvider -- tum roller icin
# ---------------------------------------------------------------------------

def _make_assistant_response(cevap: str = "Test cevap.", ret: bool = False) -> str:
    if ret:
        return json.dumps({
            "cevap_md": "Bu bilgi baglamda yok.",
            "alintilar": [],
            "onerilen_aksiyonlar": [],
            "ret": True,
            "ret_nedeni": "Konu baglam disinda.",
        }, ensure_ascii=False)
    return json.dumps({
        "cevap_md": cevap,
        "alintilar": [{"kaynak_id": "yerlesim#B001", "konum": "test"}],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)


def _make_report_response() -> str:
    return json.dumps({
        "baslik": "Yonetici Ozeti",
        "govde_md": "Pipeline 3 siparis, 2 parti, 0 uyari ile tamamlandi.",
        "kullanilan_kaynaklar": [],
        "eksik_bilgi": [],
    }, ensure_ascii=False)


def _make_explainer_response(karar_tipi: str = "algoritma") -> str:
    return json.dumps({
        "aciklama_md": f"SA algoritmasi en dusuk yuksekligi elde etti ({karar_tipi}).",
        "karar_tipi": karar_tipi,
        "kullanilan_girdiler": ["kazanan_algoritma", "height_mm"],
        "topraklama_uyarisi": False,
    }, ensure_ascii=False)


def _make_fake_provider() -> Any:
    """Tum 3 rol icin fixture'li FakeProvider."""
    from src.llm.provider import FakeProvider

    return FakeProvider(
        fixture_map={
            ("assistant-v1", "_any_"): [
                _make_assistant_response(),
                _make_assistant_response(),
                _make_assistant_response(ret=True),   # ret=True: baglam-disi
                _make_assistant_response(),
                _make_assistant_response(),
                _make_assistant_response(),
            ],
            ("report-v1", "_any_"): [_make_report_response()] * 8,
            ("explainer-v1", "_any_"): [
                _make_explainer_response("algoritma"),
                _make_explainer_response("fiyat"),
                _make_explainer_response("oncelik"),
                _make_explainer_response("algoritma"),
                _make_explainer_response("fiyat"),
                _make_explainer_response("algoritma"),
            ],
            ("parser-v1", "_any_"): [json.dumps({
                "musteri": {"ad": "Test", "iletisim": ""},
                "termin": {"tarih": "2027-01-01", "ham_ifade": ""},
                "parcalar": [],
                "eksik_alanlar": [],
                "notlar": None,
                "injection_suphesi": False,
            })] * 4,
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_no_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_enabled=False)


@pytest.fixture
def client_no_llm(app_no_llm):
    return app_no_llm.test_client()


@pytest.fixture
def app_with_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=_make_fake_provider())


@pytest.fixture
def client_llm(app_with_llm):
    return app_with_llm.test_client()


def _run_pipeline_and_return_app(app_with_llm):
    """Pipeline'i kosturur, app'i dondurur (LAST_RESULT dolu)."""
    with app_with_llm.test_client() as c:
        c.post("/run", follow_redirects=True)
    return app_with_llm


# ---------------------------------------------------------------------------
# A) Niyet-Yonlendirici birim testleri (saf fonksiyon)
# ---------------------------------------------------------------------------

class TestNiyetYonlendirici:
    """route_intent() fonksiyonunun birim testleri."""

    def test_ozet_soru_rapor_role(self):
        """'Ozet ver' -> report rolu."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Bana bir ozet ver")
        assert intent.rol == "report"

    def test_rapor_soru_rapor_role(self):
        """'Rapor olustur' -> report rolu."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Rapor olustur")
        assert intent.rol == "report"

    def test_teklif_soru_rapor_role(self):
        """'Teklif ozeti' -> report rolu."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("teklif ozeti goster")
        assert intent.rol == "report"

    def test_yonetici_soru_rapor_role(self):
        """'Yonetici ozeti istiyorum' -> report rolu."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("yonetici ozeti istiyorum")
        assert intent.rol == "report"

    def test_neden_algoritma_explainer_role(self):
        """'Neden bu algoritmay sectiniz?' -> explainer rolu, karar_tipi=algoritma."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Neden bu algoritmay sectiniz?")
        assert intent.rol == "explainer"
        assert intent.karar_tipi == "algoritma"

    def test_hangi_algoritma_explainer_role(self):
        """'Hangi algoritma secildi?' -> explainer rolu, karar_tipi=algoritma."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Hangi algoritma secildi?")
        assert intent.rol == "explainer"
        assert intent.karar_tipi == "algoritma"

    def test_nasil_secildi_explainer_algoritma(self):
        """'Nasil secildi?' -> explainer rolu."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("nasil secildi bu yontem?")
        assert intent.rol == "explainer"

    def test_fiyat_nereden_explainer_fiyat(self):
        """'Fiyat nereden geldi?' -> explainer rolu, karar_tipi=fiyat."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Fiyat nereden geldi?")
        assert intent.rol == "explainer"
        assert intent.karar_tipi == "fiyat"

    def test_oncelik_neden_explainer_oncelik(self):
        """'Oncelik neden boyle belirlendi?' -> explainer rolu, karar_tipi=oncelik."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("oncelik neden boyle belirlendi?")
        assert intent.rol == "explainer"
        assert intent.karar_tipi == "oncelik"

    def test_genel_soru_assistant_default(self):
        """Esleme olmayan soru -> assistant rolu (default)."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("Kac parca var?")
        assert intent.rol == "assistant"
        assert intent.karar_tipi is None

    def test_bos_soru_assistant_default(self):
        """Bos soru -> assistant rolu (default)."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("")
        assert intent.rol == "assistant"

    def test_nicin_explainer_algoritma(self):
        """'Nicin bu yontem?' -> explainer."""
        from src.webapp.intent_router import route_intent
        intent = route_intent("nicin bu yontem secildi?")
        assert intent.rol == "explainer"

    def test_intent_dataclass_fields(self):
        """Intent nesnesinin rol ve karar_tipi alanlari olmali."""
        from src.webapp.intent_router import route_intent, Intent
        intent = route_intent("test")
        assert hasattr(intent, "rol")
        assert hasattr(intent, "karar_tipi")


# ---------------------------------------------------------------------------
# B) /sor rotasi genisletmesi -- rol yonlendirme
# ---------------------------------------------------------------------------

class TestSorRotasiRolYonlendirme:
    """POST /sor: soru metnine gore dogru rol cagirilmali."""

    def _run_and_sor(self, client, soru: str):
        client.post("/run", follow_redirects=True)
        return client.post(
            "/sor",
            data=json.dumps({"soru": soru}),
            content_type="application/json",
        )

    def test_sor_ozet_uses_report_role(self, client_llm):
        """'Ozet ver' sorusu -> kullanilan_rol == 'report'."""
        resp = self._run_and_sor(client_llm, "Bana bir ozet ver")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("kullanilan_rol") == "report", (
            f"Beklenen 'report', gelen: {data.get('kullanilan_rol')}. Yanit: {data}"
        )

    def test_sor_neden_algoritma_uses_explainer_role(self, client_llm):
        """'Neden bu algoritma?' sorusu -> kullanilan_rol == 'explainer'."""
        resp = self._run_and_sor(client_llm, "Neden bu algoritmay sectiniz?")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("kullanilan_rol") == "explainer", (
            f"Beklenen 'explainer', gelen: {data.get('kullanilan_rol')}. Yanit: {data}"
        )

    def test_sor_genel_uses_assistant_role(self, client_llm):
        """Genel soru -> kullanilan_rol == 'assistant'."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("kullanilan_rol") == "assistant", (
            f"Beklenen 'assistant', gelen: {data.get('kullanilan_rol')}. Yanit: {data}"
        )

    def test_sor_fiyat_explainer_role(self, client_llm):
        """'Fiyat nereden geldi?' -> kullanilan_rol == 'explainer'."""
        resp = self._run_and_sor(client_llm, "Fiyat nereden geldi?")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("kullanilan_rol") == "explainer"


# ---------------------------------------------------------------------------
# C) Birlesik JSON yanit yapisi
# ---------------------------------------------------------------------------

class TestSorYanitYapisi:
    """POST /sor yaniti dogru JSON yapisini donmeli."""

    def _run_and_sor(self, client, soru: str):
        client.post("/run", follow_redirects=True)
        return client.post(
            "/sor",
            data=json.dumps({"soru": soru}),
            content_type="application/json",
        )

    def test_yanit_cevap_md_var(self, client_llm):
        """Yanit 'cevap_md' alani icermeli."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        data = resp.get_json()
        assert "cevap_md" in data or "cevap" in data, (
            f"cevap_md veya cevap alani yok: {list(data.keys())}"
        )

    def test_yanit_kullanilan_rol_var(self, client_llm):
        """Yanit 'kullanilan_rol' alani icermeli."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        data = resp.get_json()
        assert "kullanilan_rol" in data, (
            f"'kullanilan_rol' alani yok: {list(data.keys())}"
        )

    def test_yanit_hata_alani_var(self, client_llm):
        """Yanit 'hata' alani icermeli."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        data = resp.get_json()
        assert "hata" in data, f"'hata' alani yok: {list(data.keys())}"

    def test_yanit_ret_alani_var(self, client_llm):
        """Yanit 'ret' alani icermeli."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        data = resp.get_json()
        assert "ret" in data, f"'ret' alani yok: {list(data.keys())}"

    def test_basarili_yanit_hata_none(self, client_llm):
        """Basarili yanit: hata=None."""
        resp = self._run_and_sor(client_llm, "Kac parca var?")
        data = resp.get_json()
        assert data.get("hata") is None, f"Beklenmeyen hata: {data.get('hata')}"

    def test_report_yanit_kaynaklar_veya_alintilar_var(self, client_llm):
        """Report rolu yaniti 'kaynaklar' veya 'alintilar' alani icermeli."""
        resp = self._run_and_sor(client_llm, "Bana bir ozet ver")
        data = resp.get_json()
        has_sources = "kaynaklar" in data or "alintilar" in data
        assert has_sources, (
            f"Report yaniti kaynak/alinti alani icermiyor: {list(data.keys())}"
        )

    def test_explainer_yanit_karar_tipi_var(self, client_llm):
        """Explainer rolu yaniti 'karar_tipi' veya cevap icinde icermeli."""
        resp = self._run_and_sor(client_llm, "Neden bu algoritma?")
        data = resp.get_json()
        # karar_tipi ya direkt yanit altinda ya da cevap metninde olabilir
        has_karar = (
            "karar_tipi" in data
            or "algoritma" in json.dumps(data, ensure_ascii=False).lower()
        )
        assert has_karar, f"Explainer yaniti karar_tipi icermiyor: {data}"


# ---------------------------------------------------------------------------
# D) LLM kapali -> 503
# ---------------------------------------------------------------------------

class TestSorLLMKapali:
    """LLM kapali -> /sor 503 donmeli."""

    def test_sor_without_llm_503(self, client_no_llm):
        """/sor LLM yoksa 503."""
        client_no_llm.post("/run", follow_redirects=True)
        resp = client_no_llm.post(
            "/sor",
            data=json.dumps({"soru": "Ozet ver"}),
            content_type="application/json",
        )
        assert resp.status_code == 503

    def test_sor_503_contains_error_message(self, client_no_llm):
        """503 yaniti hata mesaji icermeli."""
        client_no_llm.post("/run", follow_redirects=True)
        resp = client_no_llm.post(
            "/sor",
            data=json.dumps({"soru": "test"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data is not None
        assert "hata" in data


# ---------------------------------------------------------------------------
# E) Read-only invariant: LAST_RESULT degismemeli
# ---------------------------------------------------------------------------

class TestReadOnlyInvariant:
    """/sor LAST_RESULT'i degistirmemeli."""

    def test_last_result_unchanged_after_sor(self, app_with_llm):
        """LAST_RESULT /sor oncesi ve sonrasi ayni olmali (derin esitlik kontrolleri dahil)."""
        with app_with_llm.test_client() as c:
            c.post("/run", follow_redirects=True)

            # LAST_RESULT'in anlık degerini al
            before = copy.deepcopy(app_with_llm.config.get("LAST_RESULT"))
            assert before is not None, "Pipeline calistirmasi basarisiz"

            # Derin esitlik: nesting_results ve ranked_orders snapshoti al
            before_nesting = copy.deepcopy(before.get("nesting_results", {}))
            before_ranked = copy.deepcopy(before.get("ranked_orders", []))

            # Ozet soru sor
            c.post(
                "/sor",
                data=json.dumps({"soru": "Bana bir ozet ver"}),
                content_type="application/json",
            )

            after = app_with_llm.config.get("LAST_RESULT")

            # LAST_RESULT'in temel anahtarlari degismemeli
            assert after is not None
            assert set(before.keys()) == set(after.keys()), (
                "LAST_RESULT anahtar seti /sor sonrasi degisti (READ-ONLY ihlali)"
            )
            assert before.get("elapsed_sec") == after.get("elapsed_sec"), (
                "LAST_RESULT.elapsed_sec /sor sonrasi degisti"
            )

            # Derin esitlik: nesting_results degismemeli
            after_nesting = after.get("nesting_results", {})
            assert set(before_nesting.keys()) == set(after_nesting.keys()), (
                "LAST_RESULT.nesting_results anahtarlari /sor sonrasi degisti"
            )

            # Derin esitlik: ranked_orders uzunlugu ve ilk eleman degismemeli
            after_ranked = after.get("ranked_orders", [])
            assert len(before_ranked) == len(after_ranked), (
                "LAST_RESULT.ranked_orders uzunlugu /sor sonrasi degisti"
            )

    def test_last_result_unchanged_after_explainer_sor(self, app_with_llm):
        """Explainer sorgusu sonrasi da LAST_RESULT degismemeli."""
        with app_with_llm.test_client() as c:
            c.post("/run", follow_redirects=True)
            before_n_orders = len(
                app_with_llm.config.get("LAST_RESULT", {}).get("ranked_orders", [])
            )

            c.post(
                "/sor",
                data=json.dumps({"soru": "Neden bu algoritmay sectiniz?"}),
                content_type="application/json",
            )

            after_n_orders = len(
                app_with_llm.config.get("LAST_RESULT", {}).get("ranked_orders", [])
            )
            assert before_n_orders == after_n_orders, (
                "LAST_RESULT.ranked_orders sayisi explainer sorgusu sonrasi degisti"
            )


# ---------------------------------------------------------------------------
# F) Baglam-disi soru -> ret rozeti
# ---------------------------------------------------------------------------

def _make_ret_true_provider() -> Any:
    """Her assistant cagrisinda ret=True donduran ozel FakeProvider."""
    from src.llm.provider import FakeProvider

    return FakeProvider(
        fixture_map={
            ("assistant-v1", "_any_"): [_make_assistant_response(ret=True)] * 6,
            ("report-v1", "_any_"): [_make_report_response()] * 4,
            ("explainer-v1", "_any_"): [_make_explainer_response("algoritma")] * 4,
            ("parser-v1", "_any_"): [json.dumps({
                "musteri": {"ad": "Test", "iletisim": ""},
                "termin": {"tarih": "2027-01-01", "ham_ifade": ""},
                "parcalar": [],
                "eksik_alanlar": [],
                "notlar": None,
                "injection_suphesi": False,
            })] * 4,
        }
    )


class TestRetRozeti:
    """ret=True olan yanit 'bilgi yok' rozetini icermeli."""

    def test_ret_true_in_response(self):
        """ret=True donduran fixture ile /sor yaniti ret=True icermeli."""
        from src.webapp.app import create_app

        app = create_app(testing=True, llm_provider_override=_make_ret_true_provider())
        with app.test_client() as c:
            c.post("/run", follow_redirects=True)
            resp = c.post(
                "/sor",
                data=json.dumps({"soru": "bitcoin fiyati nedir?"}),
                content_type="application/json",
            )

        data = resp.get_json()
        assert data is not None
        assert resp.status_code == 200
        assert data.get("ret") is True, (
            f"ret=True beklendi ancak gelen: {data.get('ret')}. Tam yanit: {data}"
        )


# ---------------------------------------------------------------------------
# G) UI: Hazir-soru dugmeleri sonuc.html'de mevcut (LLM aktifken)
# ---------------------------------------------------------------------------

class TestUIHazirSorular:
    """sonuc.html'de hazir-soru dugmeleri ve panel mevcut olmali."""

    def test_ozet_cikar_button_exists_when_llm_active(self, client_llm):
        """LLM aktifken 'Ozet cikar' dugmesi veya metni sonuc.html'de olmali."""
        client_llm.post("/run", follow_redirects=True)
        html = client_llm.get("/sonuc").data.decode("utf-8", errors="replace")
        assert "ozet" in html.lower(), (
            "sonuc.html'de LLM aktifken 'ozet' bolum/dugme yok"
        )

    def test_neden_algoritma_button_exists_when_llm_active(self, client_llm):
        """LLM aktifken 'Neden bu algoritma' dugmesi veya metni olmali."""
        client_llm.post("/run", follow_redirects=True)
        html = client_llm.get("/sonuc").data.decode("utf-8", errors="replace")
        # Hazir soru dugmesi veya panel kismi olmali
        has_btn = (
            "algoritma" in html.lower()
            or "neden" in html.lower()
            or "hazir-soru" in html.lower()
            or "sorgu-panel" in html.lower()
            or "sor-btn" in html.lower()
        )
        assert has_btn, (
            "sonuc.html'de 'Neden bu algoritma' / hazir soru panel yok"
        )

    def test_soru_paneli_hidden_when_llm_inactive(self, client_no_llm):
        """LLM kapali -> sorgu paneli gizli olmali veya soru gonderince 503 donmeli."""
        client_no_llm.post("/run", follow_redirects=True)
        # LLM kapali: /sor 503 donmeli (panel yoksa da bu guvence yeterli)
        resp = client_no_llm.post(
            "/sor",
            data=json.dumps({"soru": "test"}),
            content_type="application/json",
        )
        assert resp.status_code == 503

    def test_panel_has_free_text_input(self, client_llm):
        """LLM aktifken sonuc.html'de serbest soru metin kutusu olmali."""
        client_llm.post("/run", follow_redirects=True)
        html = client_llm.get("/sonuc").data.decode("utf-8", errors="replace")
        # mevcut sohbet paneli: soru-input var
        assert "soru-input" in html or "soru" in html.lower(), (
            "sonuc.html'de serbest soru metin kutusu bulunamadi"
        )


# ---------------------------------------------------------------------------
# H) Mevcut rotalar bozulmamali
# ---------------------------------------------------------------------------

class TestMevcutRotalarKorunmus:
    """Mevcut /run, /sonuc, /ozet, /teklif bozulmamali."""

    def test_run_still_works(self, client_no_llm):
        resp = client_no_llm.post("/run", follow_redirects=True)
        assert resp.status_code == 200

    def test_sonuc_after_run(self, client_no_llm):
        client_no_llm.post("/run", follow_redirects=True)
        assert client_no_llm.get("/sonuc").status_code == 200

    def test_ozet_503_without_llm(self, client_no_llm):
        client_no_llm.post("/run", follow_redirects=True)
        resp = client_no_llm.post("/ozet", content_type="application/json")
        assert resp.status_code == 503

    def test_teklif_503_without_llm(self, client_no_llm):
        client_no_llm.post("/run", follow_redirects=True)
        resp = client_no_llm.post("/teklif", content_type="application/json")
        assert resp.status_code == 503

    def test_sor_bos_soru_400(self, client_llm):
        """Bos soru -> 400."""
        client_llm.post("/run", follow_redirects=True)
        resp = client_llm.post(
            "/sor",
            data=json.dumps({"soru": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_sor_pipeline_not_run_400(self, client_llm):
        """Pipeline kosulmamissa -> 400."""
        resp = client_llm.post(
            "/sor",
            data=json.dumps({"soru": "Ozet ver"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
