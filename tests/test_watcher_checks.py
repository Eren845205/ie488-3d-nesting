"""test_watcher_checks.py — src/watcher/checks.py TDD testleri.

Kapsam:
  - Finding dataclass alanlar
  - parse sonrasi kontrollar: sigma-sapma, negatif/sifir boyut, eksik-alan orani
  - nest sonrasi kontrollar: doluluk, yukseklik-oran, yerlesmeyen parca
  - fiyat sonrasi kontrollar: total/medyan oran, min-clamp, negatif kalem
  - oncelik sonrasi kontrollar: termin-uyari sayisi, tek-sinif
  - Baseline var/yok iki yolu
  - LLM YOK — sadece deterministik logik

TDD: ag baglantisi YOK, LLM YOK.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.watcher.checks import (
    check_parse,
    check_nest,
    check_price,
    check_priority,
)
from src.watcher.thresholds import WatcherThresholds


# ---------------------------------------------------------------------------
# Yardimci veri fabrikasi
# ---------------------------------------------------------------------------

def _temiz_parse_data():
    """Anomali olmayan parse verisi."""
    return {
        "parts": [
            {"width_mm": 80.0, "depth_mm": 60.0, "height_mm": 30.0},
            {"width_mm": 100.0, "depth_mm": 80.0, "height_mm": 20.0},
            {"width_mm": 70.0, "depth_mm": 70.0, "height_mm": 25.0},
        ],
        "missing_field_ratio": 0.02,
    }


def _temiz_nest_data(baseline_median: float = None):
    """Anomali olmayan nest verisi."""
    d = {
        "density": 0.72,
        "height_mm": 150.0,
        "container_height_mm": 400.0,
        "n_parts": 8,
        "n_placed": 8,
    }
    if baseline_median is not None:
        d["baseline_median_density"] = baseline_median
    return d


def _temiz_price_data(median_price: float = 300.0):
    """Anomali olmayan fiyat verisi."""
    return {
        "total_price": 320.0,
        "median_price": median_price,
        "min_clamp": 200.0,
        "breakdown": [
            {"rule_id": "r_volume", "subtotal_after": 260.0},
            {"rule_id": "r_konteyner", "subtotal_after": 320.0},
        ],
    }


def _temiz_priority_data():
    """Anomali olmayan oncelik verisi."""
    return {
        "warnings": [],
        "priority_classes": [1, 2, 1, 2],
    }


# ---------------------------------------------------------------------------
# Finding dataclass testleri
# ---------------------------------------------------------------------------

class TestFindingDataclass:

    def test_finding_has_required_fields(self):
        from src.watcher.checks import Finding
        f = Finding(
            asama="parse",
            kod="PARSE_NEG_BOYUT",
            severity="high",
            baslik="Negatif boyut tespit edildi",
            ham_detay="width_mm=-5.0",
            metrik={"width_mm": -5.0},
        )
        assert f.asama == "parse"
        assert f.kod == "PARSE_NEG_BOYUT"
        assert f.severity == "high"
        assert f.baslik == "Negatif boyut tespit edildi"
        assert f.ham_detay == "width_mm=-5.0"
        assert f.metrik == {"width_mm": -5.0}

    def test_finding_severity_values(self):
        """Severity 'low', 'med', 'high' olabilir."""
        from src.watcher.checks import Finding
        for sev in ("low", "med", "high"):
            f = Finding(
                asama="test",
                kod="T",
                severity=sev,
                baslik="t",
                ham_detay="",
                metrik={},
            )
            assert f.severity == sev


# ---------------------------------------------------------------------------
# PARSE sonrasi kontroller
# ---------------------------------------------------------------------------

class TestCheckParse:

    # --- Pozitif (anomali yakalanir) ---

    def test_negatif_boyut_high(self):
        """Negatif boyut -> high severity bulgu."""
        data = {
            "parts": [
                {"width_mm": -5.0, "depth_mm": 60.0, "height_mm": 30.0},
                {"width_mm": 80.0, "depth_mm": 60.0, "height_mm": 30.0},
            ],
            "missing_field_ratio": 0.0,
        }
        findings = check_parse(data)
        kodlar = [f.kod for f in findings]
        assert any("NEG" in k or "BOYUT" in k for k in kodlar), f"Beklenen bulgu yok: {kodlar}"
        sev_list = [f.severity for f in findings if "NEG" in f.kod or "BOYUT" in f.kod]
        assert "high" in sev_list

    def test_sifir_boyut_high(self):
        """Sifir boyut -> high severity bulgu."""
        data = {
            "parts": [
                {"width_mm": 0.0, "depth_mm": 60.0, "height_mm": 30.0},
            ],
            "missing_field_ratio": 0.0,
        }
        findings = check_parse(data)
        kodlar = [f.kod for f in findings]
        assert any("NEG" in k or "SIFIR" in k or "BOYUT" in k for k in kodlar)

    def test_yuksek_eksik_alan_orani(self):
        """Eksik alan orani esik uzerinde -> med/high bulgu."""
        data = _temiz_parse_data()
        data["missing_field_ratio"] = 0.40  # varsayilan esik 0.25
        findings = check_parse(data)
        kodlar = [f.kod for f in findings]
        assert any("EKSIK" in k or "ALAN" in k for k in kodlar)

    def test_sigma_sapma_uc_parca(self):
        """3+ parca, buyuk boyut farki -> sigma-sapma bulgu."""
        # Cok buyuk bir sigma ile parca listesi (biri anormal buyuk)
        data = {
            "parts": [
                {"width_mm": 50.0, "depth_mm": 50.0, "height_mm": 20.0},
                {"width_mm": 55.0, "depth_mm": 55.0, "height_mm": 22.0},
                {"width_mm": 800.0, "depth_mm": 600.0, "height_mm": 500.0},  # aykiri
            ],
            "missing_field_ratio": 0.0,
        }
        findings = check_parse(data)
        kodlar = [f.kod for f in findings]
        assert any("SIGMA" in k or "SAPMA" in k or "BOYUT" in k for k in kodlar)

    def test_sigma_sapma_atla_iki_parca(self):
        """2 parca -> sigma sapma atlani (en az 3 gerekir)."""
        data = {
            "parts": [
                {"width_mm": 50.0, "depth_mm": 50.0, "height_mm": 20.0},
                {"width_mm": 800.0, "depth_mm": 600.0, "height_mm": 500.0},
            ],
            "missing_field_ratio": 0.0,
        }
        findings = check_parse(data)
        # 2 parca ile sigma atlanir; sadece boyut kontrolu kalmali
        sigma_bul = [f for f in findings if "SIGMA" in f.kod or "SAPMA" in f.kod]
        assert len(sigma_bul) == 0, "2 parca icin sigma atlanmali"

    # --- Negatif (temiz -> bos) ---

    def test_temiz_parse_bos(self):
        """Temiz parse verisi -> bos bulgu listesi."""
        findings = check_parse(_temiz_parse_data())
        assert findings == [], f"Beklenmez bulgular: {findings}"


# ---------------------------------------------------------------------------
# NEST sonrasi kontroller
# ---------------------------------------------------------------------------

class TestCheckNest:

    # --- Pozitif (anomali yakalanir) ---

    def test_dusuk_doluluk_statik_taban(self):
        """Doluluk statik tabandan dusuk -> bulgu."""
        data = _temiz_nest_data()
        data["density"] = 0.10  # statik taban ~0.25
        findings = check_nest(data)
        kodlar = [f.kod for f in findings]
        assert any("DOLULUK" in k or "DENSITY" in k for k in kodlar)

    def test_dusuk_doluluk_baseline_median(self):
        """Baseline medyan varken dusuk doluluk -> bulgu."""
        # median=0.72, tol=0.15 -> 0.72*(1-0.15)=0.612; density=0.40 < 0.612
        data = _temiz_nest_data(baseline_median=0.72)
        data["density"] = 0.40
        findings = check_nest(data)
        kodlar = [f.kod for f in findings]
        assert any("DOLULUK" in k or "DENSITY" in k for k in kodlar)

    def test_temiz_doluluk_baseline_median(self):
        """Baseline medyan varken yeterli doluluk -> doluluk bulgusuz."""
        # median=0.72; density=0.70 ~ median*(1-0.15)=0.612 -> temiz
        data = _temiz_nest_data(baseline_median=0.72)
        data["density"] = 0.70
        findings = check_nest(data)
        doluluk_bul = [f for f in findings if "DOLULUK" in f.kod or "DENSITY" in f.kod]
        assert len(doluluk_bul) == 0

    def test_yukseklik_oran_asimi(self):
        """Yukseklik/konteyner orani cok yuksek -> bulgu."""
        data = _temiz_nest_data()
        data["height_mm"] = 390.0
        data["container_height_mm"] = 400.0  # %97.5 -> asim
        findings = check_nest(data)
        kodlar = [f.kod for f in findings]
        assert any("YUKSEKLIK" in k or "HEIGHT" in k for k in kodlar)

    def test_yerlesmeyen_parca(self):
        """n_placed < n_parts -> yerlesmeyen parca bulgus."""
        data = _temiz_nest_data()
        data["n_parts"] = 10
        data["n_placed"] = 7
        findings = check_nest(data)
        kodlar = [f.kod for f in findings]
        assert any("PARCA" in k or "PLACED" in k or "UNPLACED" in k for k in kodlar)

    # --- Negatif (temiz -> bos) ---

    def test_temiz_nest_bos(self):
        """Temiz nest verisi -> bos bulgu listesi."""
        findings = check_nest(_temiz_nest_data())
        assert findings == [], f"Beklenmez bulgular: {findings}"

    def test_temiz_nest_baseline_yok(self):
        """baseline_median olmadanda temiz veri -> bos."""
        findings = check_nest(_temiz_nest_data(baseline_median=None))
        assert findings == [], f"Beklenmez bulgular: {findings}"


# ---------------------------------------------------------------------------
# FIYAT sonrasi kontroller
# ---------------------------------------------------------------------------

class TestCheckPrice:

    # --- Pozitif (anomali yakalanir) ---

    def test_oran_cok_yuksek(self):
        """total/medyan > 2.0 -> bulgu."""
        data = _temiz_price_data(median_price=100.0)
        data["total_price"] = 250.0  # 250/100 = 2.5 > 2.0
        findings = check_price(data)
        kodlar = [f.kod for f in findings]
        assert any("ORAN" in k or "FIYAT" in k or "RATIO" in k for k in kodlar)

    def test_oran_cok_dusuk(self):
        """total/medyan < 0.5 -> bulgu."""
        data = _temiz_price_data(median_price=1000.0)
        data["total_price"] = 400.0  # 400/1000 = 0.4 < 0.5
        findings = check_price(data)
        kodlar = [f.kod for f in findings]
        assert any("ORAN" in k or "FIYAT" in k or "RATIO" in k for k in kodlar)

    def test_min_clamp_takili(self):
        """total == min_clamp -> min-clamp bulgus."""
        data = _temiz_price_data()
        data["total_price"] = 200.0   # min_clamp=200.0, ayni deger
        data["min_clamp"] = 200.0
        findings = check_price(data)
        kodlar = [f.kod for f in findings]
        assert any("CLAMP" in k or "MIN" in k for k in kodlar)

    def test_negatif_kalem(self):
        """Breakdown'da negatif subtotal_after -> bulgu."""
        data = _temiz_price_data()
        data["breakdown"] = [
            {"rule_id": "r_volume", "subtotal_after": 260.0},
            {"rule_id": "r_negatif", "subtotal_after": -50.0},
        ]
        findings = check_price(data)
        kodlar = [f.kod for f in findings]
        assert any("NEGATIF" in k or "NEG" in k or "KALEM" in k for k in kodlar)

    # --- Negatif (temiz -> bos) ---

    def test_temiz_fiyat_bos(self):
        """Temiz fiyat verisi -> bos bulgu listesi."""
        findings = check_price(_temiz_price_data())
        assert findings == [], f"Beklenmez bulgular: {findings}"

    def test_temiz_fiyat_median_yok(self):
        """median_price olmayan veri -> oran kontrolu atlanir, bos donmeli."""
        data = {
            "total_price": 320.0,
            "min_clamp": 200.0,
            "breakdown": [{"rule_id": "r1", "subtotal_after": 320.0}],
        }
        findings = check_price(data)
        # median yoksa oran atlanir; min-clamp takili degil; negatif yok -> bos
        clamp_bulgular = [f for f in findings if "CLAMP" in f.kod or "MIN" in f.kod]
        assert len(clamp_bulgular) == 0


# ---------------------------------------------------------------------------
# ONCELIK sonrasi kontroller
# ---------------------------------------------------------------------------

class TestCheckPriority:

    # --- Pozitif (anomali yakalanir) ---

    def test_cok_fazla_uyari(self):
        """Termin uyari sayisi esik ustu -> bulgu."""
        data = {
            "warnings": ["w1", "w2", "w3", "w4", "w5"],  # esik genellikle 3
            "priority_classes": [1, 2, 1, 2, 1, 2],
        }
        findings = check_priority(data)
        kodlar = [f.kod for f in findings]
        assert any("UYARI" in k or "WARNING" in k or "TERMIN" in k for k in kodlar)

    def test_tek_sinif(self):
        """Tum siparisler ayni sinifta -> bulgu."""
        data = {
            "warnings": [],
            "priority_classes": [2, 2, 2, 2, 2],
        }
        findings = check_priority(data)
        kodlar = [f.kod for f in findings]
        assert any("SINIF" in k or "CLASS" in k or "TEK" in k for k in kodlar)

    # --- Negatif (temiz -> bos) ---

    def test_temiz_oncelik_bos(self):
        """Temiz oncelik verisi -> bos bulgu listesi."""
        findings = check_priority(_temiz_priority_data())
        assert findings == [], f"Beklenmez bulgular: {findings}"

    def test_bos_warnings_tamam(self):
        """Uyari bos + karisik siniflar -> bos."""
        data = {
            "warnings": [],
            "priority_classes": [1, 2],
        }
        findings = check_priority(data)
        assert findings == [], f"Beklenmez bulgular: {findings}"


# ---------------------------------------------------------------------------
# Esikler dosyasi testleri
# ---------------------------------------------------------------------------

class TestThresholds:

    def test_thresholds_varsayilan_attr(self):
        """WatcherThresholds varsayilan esik degerlerini icermeli."""
        t = WatcherThresholds()
        assert hasattr(t, "parse_missing_field_ratio_max")
        assert hasattr(t, "nest_density_static_min")
        assert hasattr(t, "nest_density_tolerance")
        assert hasattr(t, "nest_height_ratio_max")
        assert hasattr(t, "price_ratio_min")
        assert hasattr(t, "price_ratio_max")
        assert hasattr(t, "priority_warning_count_max")

    def test_thresholds_mantikli_araliklar(self):
        """Esik degerleri makul aralikta olmali."""
        t = WatcherThresholds()
        assert 0.0 < t.parse_missing_field_ratio_max < 1.0
        assert 0.0 < t.nest_density_static_min < 1.0
        assert 0.0 < t.nest_density_tolerance < 1.0
        assert 0.5 < t.nest_height_ratio_max < 1.0
        assert 0.0 < t.price_ratio_min < 1.0
        assert t.price_ratio_max > 1.0
        assert t.priority_warning_count_max >= 1

    def test_thresholds_baseline_json_yoksa_statik(self):
        """Baseline JSON yokken statik degerler kullanilmali (zarif dusus)."""
        t = WatcherThresholds(baseline_path="/gecersiz/yol/watcher_baseline.json")
        # Hata firlatmamali; statik degerler korunmali
        assert t.nest_density_static_min > 0.0

    def test_thresholds_baseline_json_varsa_medyan(self, tmp_path):
        """Baseline JSON varsa medyan referansi kullanilmali."""
        import json
        bl_path = tmp_path / "watcher_baseline.json"
        bl_path.write_text(
            json.dumps({"nest_density_median": 0.68}),
            encoding="utf-8",
        )
        t = WatcherThresholds(baseline_path=str(bl_path))
        assert t.nest_density_baseline_median == pytest.approx(0.68)
