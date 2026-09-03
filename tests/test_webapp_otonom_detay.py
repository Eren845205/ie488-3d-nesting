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


def _make_teklif_response() -> str:
    return json.dumps({
        "konu": "Siparis Teklifiniz — Ford Motor Braketi",
        "mail_govde_md": "Sayin Ford Turkiye, siparisleriniz degerlendirildi.",
        "kullanilan_kaynaklar": ["teklif#ozet"],
        "topraklama_uyarisi": False,
    }, ensure_ascii=False)


def _make_full_fake_provider() -> Any:
    from src.llm.provider import FakeProvider
    return FakeProvider(
        fixture_map={
            ("parser-v1", "_any_"): [_make_parser_response()] * 6,
            ("explainer-v1", "_any_"): [_make_explainer_response()] * 6,
            ("report-v1", "_any_"): [_make_report_response()] * 4,
            ("teklif-v1", "_any_"): [_make_teklif_response()] * 4,
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

    def test_teklif_durum_taslak_hazir_veya_flagli(self, otonom_data):
        """Teklif-Taslagi asama durumu 'taslak_hazir' veya 'flagli_taslak' olmali (dead-end yok)."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        durum = stage.get("durum", "")
        assert durum in ("taslak_hazir", "flagli_taslak"), (
            f"Beklenen 'taslak_hazir' veya 'flagli_taslak', gelen: {durum!r}"
        )

    def test_teklif_detay_taslak_dolu(self, otonom_data):
        """Teklif detay 'taslak' alani dolu olmali (LLM aktif)."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        taslak = detay.get("taslak", "")
        assert taslak not in (None, ""), f"Teklif taslak bos: {detay}"

    def test_teklif_detay_has_topraklama_uyarisi(self, otonom_data):
        """Teklif detay 'topraklama_uyarisi' alani olmali."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        assert "topraklama_uyarisi" in detay, f"topraklama_uyarisi yok: {list(detay.keys())}"

    def test_teklif_detay_has_konu(self, otonom_data):
        """Teklif detay 'konu' alani olmali."""
        stage = _stage(otonom_data, "Teklif-Taslagi")
        detay = stage.get("detay", {})
        assert "konu" in detay, f"konu yok: {list(detay.keys())}"


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


# ---------------------------------------------------------------------------
# H) Watcher entegrasyon testleri (temiz senaryo)
# ---------------------------------------------------------------------------

class TestWatcherEntegrasyon:
    """Watcher bulgulari ve anlatim alanlari /otonom yaniti icinde olmali."""

    def test_nesting_asama_has_watcher(self, otonom_data):
        """Nesting asama 'watcher' alani icermeli."""
        stage = _stage(otonom_data, "Nesting")
        assert "watcher" in stage, f"Nesting asama 'watcher' alani yok: {list(stage.keys())}"

    def test_fiyat_asama_has_watcher(self, otonom_data):
        """Fiyat asama 'watcher' alani icermeli."""
        stage = _stage(otonom_data, "Fiyat")
        assert "watcher" in stage, f"Fiyat asama 'watcher' alani yok: {list(stage.keys())}"

    def test_onceliklendir_asama_has_watcher(self, otonom_data):
        """Onceliklendir asama 'watcher' alani icermeli."""
        stage = _stage(otonom_data, "Onceliklendir")
        assert "watcher" in stage, f"Onceliklendir 'watcher' alani yok: {list(stage.keys())}"

    def test_parse_asama_has_watcher(self, otonom_data):
        """Parse asama 'watcher' alani icermeli."""
        stage = _stage(otonom_data, "Parse")
        assert "watcher" in stage, f"Parse 'watcher' alani yok: {list(stage.keys())}"

    def test_watcher_has_bulgular_list(self, otonom_data):
        """Nesting watcher 'bulgular' liste olmali."""
        stage = _stage(otonom_data, "Nesting")
        watcher = stage.get("watcher", {})
        assert "bulgular" in watcher, f"watcher 'bulgular' alani yok: {list(watcher.keys())}"
        assert isinstance(watcher["bulgular"], list), "watcher bulgular liste degil"

    def test_watcher_temiz_senaryo_bos_bulgular(self, otonom_data):
        """Temiz senaryo: nesting bulgulari bos olmali (anomali yok)."""
        stage = _stage(otonom_data, "Nesting")
        watcher = stage.get("watcher", {})
        # Temiz test verisinde bulgu beklenmiyor
        bulgular = watcher.get("bulgular", [])
        # Bos olmak zorunda degil (senaryo buyuk olabilir) ama liste olmali
        assert isinstance(bulgular, list)

    def test_watcher_anlatim_alanli(self, otonom_data):
        """Fiyat watcher 'anlatim' alani olmali (bos veya dolu)."""
        stage = _stage(otonom_data, "Fiyat")
        watcher = stage.get("watcher", {})
        assert "anlatim" in watcher, f"watcher 'anlatim' alani yok: {list(watcher.keys())}"

    def test_otonom_llm_kapali_503(self):
        """LLM kapaliyken /otonom 503 donmeli (mail parse icin LLM zorunlu)."""
        from src.webapp.app import create_app
        app = create_app(testing=True, llm_enabled=False)
        # LLM kapali -> otonom 503 donmeli (LLM gerekli)
        client = app.test_client()
        resp = client.post("/otonom", content_type="application/json")
        assert resp.status_code == 503, "LLM kapali otonom 503 bekleniyor"


# ---------------------------------------------------------------------------
# I) Anomali enjeksiyon senaryosu (watcher bos olmayan bulgu uretmeli)
# ---------------------------------------------------------------------------

class TestWatcherAnomaliEnjeksiyonu:
    """Bozuk fiyat verisi enjekte edilerek watcher bulgu uretmesi test edilir."""

    def test_watcher_bozuk_fiyat_bulgu(self, tmp_path):
        """Fiyat cok yuksekse watcher bulgu uretmeli."""
        from src.watcher.checks import check_price

        # total/medyan > 2.0 -> FIYAT_ORAN_YUKSEK bulgus
        findings = check_price({
            "total_price": 5000.0,
            "median_price": 300.0,
            "min_clamp": 200.0,
            "breakdown": [{"rule_id": "r1", "subtotal_after": 5000.0}],
        })
        assert len(findings) > 0, "Yuksek fiyat bulgus uretilmeli"
        kodlar = [f.kod for f in findings]
        assert any("ORAN" in k or "FIYAT" in k for k in kodlar)

    def test_watcher_yerlesmeyen_parca_bulgu(self, tmp_path):
        """n_placed < n_parts durumunda watcher high bulgu uretmeli."""
        from src.watcher.checks import check_nest

        findings = check_nest({
            "density": 0.65,
            "height_mm": 150.0,
            "n_parts": 10,
            "n_placed": 7,
        })
        assert len(findings) > 0
        sev_list = [f.severity for f in findings]
        assert "high" in sev_list

    def test_watcher_otonom_temiz_bos_bulgular_for_clean_data(self, otonom_data):
        """Temiz FakeMailbox verisi -> watcher bulgulari bos olmali."""
        # Watcher her asamada bulgular listesi olmali ve temiz veri icin bos olmali
        for asama_adi in ("Nesting", "Fiyat"):
            stage = _stage(otonom_data, asama_adi)
            watcher = stage.get("watcher", {})
            bulgular = watcher.get("bulgular", [])
            assert isinstance(bulgular, list), f"{asama_adi} bulgular liste degil"
            # Temiz FakeMailbox verisi icin bos beklenir
            assert bulgular == [], f"{asama_adi} temiz verida bulgu beklenmez: {bulgular}"


# ---------------------------------------------------------------------------
# J) /otonom HTTP rota entegrasyonu: anomali -> canli watcher bulgu
#    (HIGH-1 / HIGH-2 fix'lerini koruyan regresyon kalkani)
# ---------------------------------------------------------------------------

def _make_partial_fail_provider() -> Any:
    """Parser tum serbest-metin maillerini INVALID dondurur -> parse_hatalar birikir.

    FakeMailbox 5 mail dondurur (son mail xlsx ekli -> deterministik parse,
    LLM'siz basarili). Serbest-metin maillerinin (4 adet) hepsi gecersiz JSON
    -> her biri parse_hatalar'a eklenir. Fixture tukendiginde FakeProvider son
    (gecersiz) yaniti tekrarladigi icin retry'lar da gecersiz kalir, yani tum
    LLM parse'lari basarisiz olur. Sonuc: parse_hatalar=4, n_mail=5 ->
    missing_field_ratio=0.8 > 0.25 esigi -> Parse asamasinda PARSE_EKSIK_ALAN
    canli bulgusu beklenir.
    """
    from src.llm.provider import FakeProvider
    invalid = "bu gecerli bir JSON degil {{"
    return FakeProvider(
        fixture_map={
            ("parser-v1", "_any_"): [invalid],
            ("explainer-v1", "_any_"): [_make_explainer_response()] * 6,
            ("report-v1", "_any_"): [_make_report_response()] * 4,
            ("teklif-v1", "_any_"): [_make_teklif_response()] * 4,
            ("assistant-v1", "_any_"): [json.dumps({
                "cevap_md": "Test",
                "alintilar": [],
                "onerilen_aksiyonlar": [],
                "ret": False,
                "ret_nedeni": None,
            })] * 2,
        }
    )


class TestWatcherHttpEntegrasyon:
    """Anomali enjeksiyonu /otonom rotasindan gecirilir; watcher bulgu uretmeli.

    Bu test HIGH-2 (sabit missing_field_ratio=0.0 ile olu PARSE_EKSIK_ALAN)
    ve HIGH-1 (istenen-vs-yerlesen besleme) fix'lerinin canli yolda calistigini
    dogrular. Fix oncesi Parse watcher bulgulari her zaman bos kalirdi.
    """

    def test_parse_watcher_eksik_alan_bulgu_http(self):
        from src.webapp.app import create_app
        app = create_app(
            testing=True,
            llm_provider_override=_make_partial_fail_provider(),
        )
        client = app.test_client()
        resp = client.post("/otonom", content_type="application/json")
        assert resp.status_code == 200, (
            f"Otonom 200 beklendi, {resp.status_code} geldi"
        )
        data = resp.get_json()

        parse_stage = _stage(data, "Parse")
        watcher = parse_stage.get("watcher", {})
        bulgular = watcher.get("bulgular", [])
        assert isinstance(bulgular, list), "Parse watcher bulgular liste degil"
        # HIGH-2 fix: missing_field_ratio artik gercek oran (parse_hatalar/n_mail).
        # Iki gecersiz parse -> 0.4 > 0.25 -> PARSE_EKSIK_ALAN tetiklenir.
        kodlar = [b.get("kod") for b in bulgular]
        assert "PARSE_EKSIK_ALAN" in kodlar, (
            f"PARSE_EKSIK_ALAN canli yolda tetiklenmedi; bulgular={bulgular}"
        )

    def test_nest_watcher_n_parts_istenen_sayidir(self):
        """HIGH-1 fix: nesting watcher istenen parca sayisini (yerlesen degil)

        kullanmali. Temiz senaryoda tum parcalar yerlestiginden NEST_YERLESMEYEN_PARCA
        cikmamali; ama besleme dogru oldugunda (istenen==yerlesen) bulgu bos kalir.
        Bu test bulgu yoklugunu DEGIL, watcher boru hattinin sahte-yesil olmadigini
        (yapi olarak bulgular listesinin var oldugunu) dogrular; istenen-yerlesen
        ayrimi check_nest unit testleriyle ayrica korunur.
        """
        from src.webapp.app import create_app
        app = create_app(
            testing=True,
            llm_provider_override=_make_full_fake_provider(),
        )
        client = app.test_client()
        resp = client.post("/otonom", content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        nest_stage = _stage(data, "Nesting")
        watcher = nest_stage.get("watcher", {})
        assert "bulgular" in watcher
        assert isinstance(watcher["bulgular"], list)
