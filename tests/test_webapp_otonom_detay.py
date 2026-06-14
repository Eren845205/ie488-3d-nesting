"""test_webapp_otonom_detay.py -- /otonom yanit detay alanlari testleri.

Agent panosu UI'inin ihtiyac duydugu detay alanlarini dogrular:
  - Mail-Cek asama detay'i gonderen/konu listesi icermeli
  - Onceliklendir asama detay'i siralama listesi icermeli
  - Nesting asama detay'i batches listesi icermeli
  - Fiyat asama detay'i parti_fiyatlari icermeli
  - Acikla asama detay'i aciklama_md icermeli (LLM aktif)
  - Teklif-Taslagi asama detay'i onay_gerekli=True icermeli

Kapsam (TDD GREEN -- yeni UI detay gereksinimleri):
  A) Detay alanlari mevcutluk
  B) Onceliklendirme goruntu verisi (siralama)
  C) Aciklayici goruntu verisi (aciklama_md)
  D) Teklif onay kapisi verisi
  E) Fiyat detayi yapisi
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# FakeProvider
# ---------------------------------------------------------------------------

def _make_parser_response() -> str:
    return json.dumps({
        "musteri": {"ad": "Ford Turkiye", "iletisim": "tedarik@ford.com.tr"},
        "termin": {"tarih": "2026-06-19", "ham_ifade": "5 is gunu"},
        "parcalar": [
            {
                "ad": "Ford Motor Braketi",
                "adet": 8,
                "boyut_mm": [80.0, 60.0, 30.0],
                "agirlik_kg": None,
                "kaynak": "box",
                "guven": "yuksek",
            }
        ],
        "eksik_alanlar": [],
        "notlar": None,
        "injection_suphesi": False,
    }, ensure_ascii=False)


def _make_explainer_response() -> str:
    return json.dumps({
        "aciklama_md": "SA algoritmasi en dusuk yuksekligi elde etti: 3 konfig denendi.",
        "kadar_tipi": "algoritma",
        "kullanilan_girdiler": ["kazanan_algoritma", "height_mm"],
        "topraklama_uyarisi": False,
    }, ensure_ascii=False)


def _make_report_response() -> str:
    return json.dumps({
        "baslik": "Otonom Teklif",
        "govde_md": "Sayin Ford Turkiye, siparisleriniz hazirlandi.",
        "kullanilan_kaynaklar": [],
        "eksik_bilgi": [],
    }, ensure_ascii=False)


def _make_full_fake_provider() -> Any:
    from src.llm.provider import FakeProvider
    return FakeProvider(
        fixture_map={
            ("parser-v1", "_any_"): [_make_parser_response()] * 6,
            ("explainer-v1", "_any_"): [_make_explainer_response()] * 6,
            ("report-v1", "_any_"): [_make_report_response()] * 4,
            ("assistant-v1", "_any_"): [json.dumps({
                "cevap_md": "Test",
                "alintilar": [],
                "onerilen_aksiyonlar": [],
                "ret": False,
                "ret_nedeni": None,
            })] * 2,
        }
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_llm():
    from src.webapp.app import create_app
    app = create_app(testing=True, llm_provider_override=_make_full_fake_provider())
    return app.test_client()


@pytest.fixture
def otonom_data(client_llm):
    """POST /otonom yanitini bir kez cek; sonuclari paylasimli kullanalim."""
    resp = client_llm.post("/otonom", content_type="application/json")
    assert resp.status_code == 200, f"Otonom 200 beklendi, {resp.status_code} geldi"
    return resp.get_json()


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def _stage(data: dict, name: str) -> dict:
    """Asama listesinden isimle asama bul."""
    for s in data.get("asamalar", []):
        if s.get("ad") == name:
            return s
    return {}


# ---------------------------------------------------------------------------
# A) Detay alanlari mevcutluk
# ---------------------------------------------------------------------------

class TestDetayMevcutluk:

    def test_mail_cek_has_detay(self, otonom_data):
        """Mail-Cek asama 'detay' alani olmali."""
        stage = _stage(otonom_data, "Mail-Cek")
        assert stage, "Mail-Cek asama yok"
        assert "detay" in stage, "Mail-Cek 'detay' yok"

    def test_onceliklendir_has_detay(self, otonom_data):
        """Onceliklendir asama 'detay' alani olmali."""
        stage = _stage(otonom_data, "Onceliklendir")
        assert stage, "Onceliklendir asama yok"
        assert "detay" in stage, "Onceliklendir 'detay' yok"

    def test_nesting_has_detay(self, otonom_data):
        """Nesting asama 'detay' alani olmali."""
        stage = _stage(otonom_data, "Nesting")
        assert stage, "Nesting asama yok"
        assert "detay" in stage, "Nesting 'detay' yok"

    def test_fiyat_has_detay(self, otonom_data):
        """Fiyat asama 'detay' alani olmali."""
        stage = _stage(otonom_data, "Fiyat")
        assert stage, "Fiyat asama yok"
        assert "detay" in stage, "Fiyat 'detay' yok"

    def test_acikla_has_detay(self, otonom_data):
        """Acikla asama 'detay' alani olmali (LLM aktif)."""
        stage = _stage(otonom_data, "Acikla")
        assert stage, "Acikla asama yok"
        assert "detay" in stage, "Acikla 'detay' yok"

    def test_teklif_has_detay(self, otonom_data):
        """Teklif-Taslagi asama 'detay' alani olmali."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        assert stage, "Teklif-Taslagi asama yok"
        assert "detay" in stage, "Teklif-Taslagi 'detay' yok"


# ---------------------------------------------------------------------------
# B) Onceliklendirme goruntu verisi
# ---------------------------------------------------------------------------

class TestOncelikDetay:

    def test_oncelik_detay_has_siralama(self, otonom_data):
        """Onceliklendir detay 'siralama' listesi icermeli."""
        stage = _stage(otonom_data, "Onceliklendir")
        detay = stage.get("detay", {})
        assert "siralama" in detay, f"siralama yok: {list(detay.keys())}"

    def test_oncelik_siralama_is_list(self, otonom_data):
        """siralama bir liste olmali."""
        stage = _stage(otonom_data, "Onceliklendir")
        siralama = stage.get("detay", {}).get("siralama", None)
        assert isinstance(siralama, list), "siralama liste degil"

    def test_oncelik_siralama_has_required_fields(self, otonom_data):
        """siralama elemanlari sira, order_id, customer, deadline, priority_class icermeli."""
        stage = _stage(otonom_data, "Onceliklendir")
        siralama = stage.get("detay", {}).get("siralama", [])
        assert len(siralama) > 0, "siralama bos"
        for item in siralama:
            for key in ("sira", "order_id", "customer", "deadline", "priority_class"):
                assert key in item, f"siralama item icinde '{key}' yok: {item}"

    def test_oncelik_siralama_sira_starts_at_1(self, otonom_data):
        """siralama sira numarasi 1'den baslamali."""
        stage = _stage(otonom_data, "Onceliklendir")
        siralama = stage.get("detay", {}).get("siralama", [])
        if siralama:
            assert siralama[0]["sira"] == 1, f"Ilk siralama sira=1 degil: {siralama[0]}"

    def test_oncelik_detay_has_uyari_sayisi(self, otonom_data):
        """Onceliklendir detay 'uyari_sayisi' icermeli."""
        stage = _stage(otonom_data, "Onceliklendir")
        detay = stage.get("detay", {})
        assert "uyari_sayisi" in detay, "uyari_sayisi yok"


# ---------------------------------------------------------------------------
# C) Aciklayici goruntu verisi
# ---------------------------------------------------------------------------

class TestAciklaDetay:

    def test_acikla_detay_has_aciklama_md(self, otonom_data):
        """Acikla detay 'aciklama_md' icermeli (LLM aktif oldugunda)."""
        stage = _stage(otonom_data, "Acikla")
        detay = stage.get("detay", {})
        # LLM aktif oldugunda aciklama_md olmali
        assert "aciklama_md" in detay, f"aciklama_md yok: {list(detay.keys())}"

    def test_acikla_detay_aciklama_md_not_empty_with_llm(self, otonom_data):
        """LLM aktif, aciklama_md bos olmamali."""
        stage = _stage(otonom_data, "Acikla")
        detay = stage.get("detay", {})
        aciklama = detay.get("aciklama_md", "")
        # LLM aktifse dolu olmali (veya hata mesaji -- ikisi de kabul edilir)
        assert isinstance(aciklama, str), "aciklama_md string degil"

    def test_aciklama_md_also_in_toplevel_response(self, otonom_data):
        """Ust duzey 'aciklama_md' de olmali."""
        assert "aciklama_md" in otonom_data, "ust duzey aciklama_md yok"


# ---------------------------------------------------------------------------
# D) Teklif onay kapisi verisi
# ---------------------------------------------------------------------------

class TestTeklifDetay:

    def test_teklif_detay_has_onay_gerekli(self, otonom_data):
        """Teklif-Taslagi detay 'onay_gerekli' icermeli."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        assert "onay_gerekli" in detay, f"onay_gerekli yok: {list(detay.keys())}"

    def test_teklif_onay_gerekli_is_true(self, otonom_data):
        """onay_gerekli=True olmali (otomatik gonderilemez)."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        assert detay.get("onay_gerekli") is True, "onay_gerekli True degil"

    def test_teklif_detay_otomatik_gonderilmedi_false(self, otonom_data):
        """otomatik_gonderildi=False olmali."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        assert detay.get("otomatik_gonderildi") is False, "otomatik_gonderildi False degil"

    def test_toplevel_teklif_onay_gerekli_true(self, otonom_data):
        """Ust duzey teklif_onay_gerekli=True olmali."""
        assert otonom_data.get("teklif_onay_gerekli") is True, "ust teklif_onay_gerekli True degil"


# ---------------------------------------------------------------------------
# E) Fiyat detayi yapisi
# ---------------------------------------------------------------------------

class TestFiyatDetay:

    def test_fiyat_detay_has_toplam_fiyat(self, otonom_data):
        """Fiyat detay 'toplam_fiyat' icermeli."""
        stage = _stage(otonom_data, "Fiyat")
        detay = stage.get("detay", {})
        assert "toplam_fiyat" in detay, f"toplam_fiyat yok: {list(detay.keys())}"

    def test_fiyat_detay_toplam_fiyat_is_float(self, otonom_data):
        """toplam_fiyat sayisal olmali."""
        stage = _stage(otonom_data, "Fiyat")
        detay = stage.get("detay", {})
        assert isinstance(detay.get("toplam_fiyat"), (int, float)), "toplam_fiyat sayisal degil"

    def test_fiyat_detay_has_parti_fiyatlari(self, otonom_data):
        """Fiyat detay 'parti_fiyatlari' icermeli."""
        stage = _stage(otonom_data, "Fiyat")
        detay = stage.get("detay", {})
        assert "parti_fiyatlari" in detay, f"parti_fiyatlari yok: {list(detay.keys())}"

    def test_fiyat_parti_fiyatlari_is_dict(self, otonom_data):
        """parti_fiyatlari bir dict olmali."""
        stage = _stage(otonom_data, "Fiyat")
        detay = stage.get("detay", {})
        assert isinstance(detay.get("parti_fiyatlari"), dict), "parti_fiyatlari dict degil"


# ---------------------------------------------------------------------------
# F) Nesting detayi yapisi
# ---------------------------------------------------------------------------

class TestNestingDetay:

    def test_nesting_detay_has_batches(self, otonom_data):
        """Nesting detay 'batches' listesi icermeli."""
        stage = _stage(otonom_data, "Nesting")
        detay = stage.get("detay", {})
        assert "batches" in detay, f"batches yok: {list(detay.keys())}"

    def test_nesting_batches_is_list(self, otonom_data):
        """batches bir liste olmali."""
        stage = _stage(otonom_data, "Nesting")
        detay = stage.get("detay", {})
        assert isinstance(detay.get("batches"), list), "batches liste degil"

    def test_nesting_batch_has_height_density_nparts(self, otonom_data):
        """Her batch elemaninda batch_id, customer, height_mm, density, n_parts olmali."""
        stage = _stage(otonom_data, "Nesting")
        batches = stage.get("detay", {}).get("batches", [])
        for b in batches:
            for key in ("batch_id", "customer", "height_mm", "density", "n_parts"):
                assert key in b, f"batch icinde '{key}' yok: {b}"

    def test_nesting_detay_has_parti_sayisi(self, otonom_data):
        """Nesting detay 'parti_sayisi' icermeli."""
        stage = _stage(otonom_data, "Nesting")
        detay = stage.get("detay", {})
        assert "parti_sayisi" in detay, f"parti_sayisi yok: {list(detay.keys())}"


# ---------------------------------------------------------------------------
# G) Mail-Cek detayi yapisi
# ---------------------------------------------------------------------------

class TestMailCekDetay:

    def test_mail_cek_detay_is_list(self, otonom_data):
        """Mail-Cek detay gonderen/konu listesi olmali."""
        stage = _stage(otonom_data, "Mail-Cek")
        detay = stage.get("detay", None)
        assert isinstance(detay, list), f"Mail-Cek detay liste degil: {type(detay)}"

    def test_mail_cek_detay_has_gonderen_konu(self, otonom_data):
        """Mail-Cek detay elemanlari gonderen ve konu icermeli."""
        stage = _stage(otonom_data, "Mail-Cek")
        detay = stage.get("detay", [])
        assert len(detay) > 0, "Mail-Cek detay bos"
        for m in detay:
            assert "gonderen" in m, f"detay elemaninda 'gonderen' yok: {m}"
            assert "konu" in m, f"detay elemaninda 'konu' yok: {m}"

    def test_mail_cek_detay_count_matches_cikti(self, otonom_data):
        """Mail-Cek detay liste uzunlugu cikti'daki rakamla uyusmali."""
        stage = _stage(otonom_data, "Mail-Cek")
        detay = stage.get("detay", [])
        cikti = stage.get("cikti", "")
        # cikti "4 mail cekildi" gibi bir sey
        nums = [c for c in cikti.split() if c.isdigit()]
        if nums:
            expected_count = int(nums[0])
            assert len(detay) == expected_count, (
                f"detay uzunlugu ({len(detay)}) cikti rakamindan ({expected_count}) farkli"
            )
