"""test_demo_pipeline.py — Smoke testi: uçtan uca demo pipeline.

Kapsam:
    - Minik senaryo (2 sipariş, birkaç kutu parça, çok kaba pitch=20 mm)
    - Pipeline tamamlanabilmeli (istisna yok)
    - results/demo_pipeline_report.md oluşmalı
    - Rapor bölümleri mevcut olmalı
    - Deterministik: iki koşu aynı raporu üretmeli

Koşu: pytest tests/test_demo_pipeline.py -q
"""

from __future__ import annotations

import importlib
import sys
from datetime import date
from pathlib import Path

import pytest

# Proje kökünü sys.path'e ekle
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.demo_pipeline import run_pipeline, SCENARIO, RESULTS_DIR  # noqa: E402


# ---------------------------------------------------------------------------
# Küçük test senaryosu (2 sipariş, çok kaba pitch=20mm — hızlı)
# ---------------------------------------------------------------------------

SMOKE_SCENARIO = {
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 200_000.0,
    },
    "container": {
        "width_mm": 220.0,
        "depth_mm": 220.0,
    },
    "pitch": 20.0,
    "n_orientations": 2,
    "orders": [
        {
            "order_id": "SMOKE-A",
            "customer": "TestCo",
            "deadline": "2026-07-01",
            "priority_class": 1,
            "parts": [
                {"id": "p1", "name": "box_small", "qty": 2,
                 "source": "box", "width_mm": 40.0, "depth_mm": 40.0, "height_mm": 30.0},
            ],
        },
        {
            "order_id": "SMOKE-B",
            "customer": "TestCo2",
            "deadline": "2026-07-15",
            "priority_class": 2,
            "parts": [
                {"id": "p2", "name": "box_medium", "qty": 1,
                 "source": "box", "width_mm": 60.0, "depth_mm": 50.0, "height_mm": 40.0},
            ],
        },
    ],
    "pricing_rules": {
        "version": "1.0",
        "name": "smoke_rules",
        "rules": [
            {
                "id": "r_volume",
                "type": "unit_price",
                "input_field": "hacim_m3",
                "unit_price": 500.0,
                "description": "Hacim birim fiyat",
            },
            {
                "id": "r_min",
                "type": "min_clamp",
                "min_price": 100.0,
                "description": "Minimum fiyat",
            },
        ],
    },
}

REPORT_PATH = RESULTS_DIR / "demo_pipeline_report.md"


# ---------------------------------------------------------------------------
# Testler
# ---------------------------------------------------------------------------


class TestSmokePipeline:
    """Pipeline smoke testi — minik senaryo."""

    def test_pipeline_runs_without_exception(self):
        """Pipeline herhangi bir exception fırlatmamalı."""
        result = run_pipeline(SMOKE_SCENARIO)
        assert result is not None

    def test_report_file_created(self):
        """Rapor dosyası oluşmalı."""
        run_pipeline(SMOKE_SCENARIO)
        assert REPORT_PATH.exists(), f"Rapor dosyası bulunamadı: {REPORT_PATH}"

    def test_report_has_required_sections(self):
        """Rapor bölümleri mevcut olmalı."""
        run_pipeline(SMOKE_SCENARIO)
        content = REPORT_PATH.read_text(encoding="utf-8")

        required_sections = [
            "Siparis Oncelik Tablosu",
            "Parti Plani",
            "Nesting Sonuclari",
            "Fiyat Dokumu",
            "Ozet",
        ]
        for section in required_sections:
            assert section in content, (
                f"Beklenen bolum bulunamadi: '{section}'"
            )

    def test_pipeline_result_has_batches(self):
        """Sonuç en az bir parti içermeli."""
        result = run_pipeline(SMOKE_SCENARIO)
        assert len(result["batches"]) >= 1

    def test_pipeline_result_has_nesting_results(self):
        """Her parti için nesting sonucu olmalı."""
        result = run_pipeline(SMOKE_SCENARIO)
        assert "nesting_results" in result
        assert len(result["nesting_results"]) >= 1
        for batch_id, nr in result["nesting_results"].items():
            assert "height_mm" in nr, f"{batch_id} için height_mm eksik"
            assert "density" in nr, f"{batch_id} için density eksik"
            assert nr["height_mm"] >= 0.0

    def test_pipeline_result_has_pricing(self):
        """Her parti için fiyat sonucu olmalı."""
        result = run_pipeline(SMOKE_SCENARIO)
        assert "pricing_results" in result
        for batch_id, pr in result["pricing_results"].items():
            assert pr["total_price"] >= 0.0

    def test_pipeline_is_deterministic(self):
        """İki koşu aynı total fiyatları üretmeli."""
        r1 = run_pipeline(SMOKE_SCENARIO)
        r2 = run_pipeline(SMOKE_SCENARIO)

        for batch_id in r1["pricing_results"]:
            assert (
                r1["pricing_results"][batch_id]["total_price"]
                == r2["pricing_results"][batch_id]["total_price"]
            ), f"{batch_id} fiyatı deterministic degil"

        for batch_id in r1["nesting_results"]:
            assert (
                abs(r1["nesting_results"][batch_id]["height_mm"]
                    - r2["nesting_results"][batch_id]["height_mm"]) < 1e-6
            ), f"{batch_id} height_mm deterministic degil"

    def test_ranked_orders_in_result(self):
        """Sıralanmış sipariş listesi sonuçta mevcut olmalı."""
        result = run_pipeline(SMOKE_SCENARIO)
        assert "ranked_orders" in result
        assert len(result["ranked_orders"]) == 2

    def test_summary_section_in_report(self):
        """Raporda toplam ciro ve toplam uyarı sayısı satırı olmalı."""
        run_pipeline(SMOKE_SCENARIO)
        content = REPORT_PATH.read_text(encoding="utf-8")
        assert "Toplam Ciro" in content
        assert "Uyari Sayisi" in content
