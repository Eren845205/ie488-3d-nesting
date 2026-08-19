"""test_demo_pipeline.py — Smoke testi: uçtan uca demo pipeline.

Kapsam:
    - Minik senaryo (2 sipariş, birkaç kutu parça, çok kaba pitch=20 mm)
    - Pipeline tamamlanabilmeli (istisna yok)
    - results/demo_pipeline_report.md oluşmalı
    - Rapor bölümleri mevcut olmalı
    - Deterministik: iki koşu aynı raporu üretmeli
    - Portföy: nesting_results portföy kıyas verisi içermeli
    - RICH_SCENARIO: zengin senaryo smoke testi (yavaş olduğu için slow ile işaretli)
    - Timing guard: toplam süre < 60 sn (reviewer bulgu #4 — sessiz yavaşlama koruması)

Koşu: pytest tests/test_demo_pipeline.py -q
"""

from __future__ import annotations

import importlib
import sys
import time
from datetime import date
from pathlib import Path

import pytest

# Proje kökünü sys.path'e ekle
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.demo_pipeline import (  # noqa: E402
    run_pipeline, SCENARIO, RICH_SCENARIO, RESULTS_DIR,
)


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
    # Küçük budget: testler dakika sürmemeli (DBLF deterministic, SA/GA/Tabu 10 iter)
    "portfolio_budget": 10,
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

    def test_auto_mode_resolves_and_runs(self):
        """nesting_mode='auto' → predict_nfv_benefit mod seçer, pipeline çalışır, şeffaf gerekçe.

        Akıllı mod (2026-06-27): auto, instance'tan veri-odaklı NFV/heightmap seçer. Bu test
        auto'nun çözüldüğünü + fiilen kullanılan mod ve gerekçenin çıktıya yazıldığını doğrular.
        """
        result = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "auto"})
        assert result is not None
        for nr in result["nesting_results"].values():
            if nr.get("n_parts", 0) > 0 and nr.get("note", "") == "":
                assert nr.get("nesting_mode_used") in ("nfv", "heightmap"), \
                    f"auto çözülmedi: {nr.get('nesting_mode_used')}"
                assert nr.get("auto_mode_reason") and "auto->" in nr["auto_mode_reason"], \
                    f"auto gerekçesi şeffaf değil: {nr.get('auto_mode_reason')}"

    def test_report_file_created(self):
        """Rapor dosyası oluşmalı."""
        run_pipeline(SMOKE_SCENARIO)
        assert REPORT_PATH.exists(), f"Rapor dosyası bulunamadı: {REPORT_PATH}"

    def test_nfv_modu_kanopi_kablosu_tetiksiz_iz_ve_kapatma(self):
        """K-62 v18 kablosu: nfv modunda kanopi zinciri DEFAULT devrede.

        Kutu-parça (stl'siz) sette geometrik tetik yapısal ateşleyemez →
        (a) telemetri izi düşer (tetik=False), (b) yükseklik bayrak
        kapalı koşuyla BİREBİR (tek-taraflılık + sıfır-dokunuş),
        (c) kanopi_zincir=False anahtar kabloyu tamamen kapatır (iz yok).
        """
        r_acik = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv"})
        r_kapali = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv",
                                 "kanopi_zincir": False})
        for bid, nr in r_acik["nesting_results"].items():
            if nr.get("n_parts", 0) > 0 and nr.get("note", "") == "":
                kz = nr.get("kanopi_zincir")
                assert kz is not None, "kanopi_zincir telemetrisi düşmedi"
                assert kz["tetik"] is False and kz["secilen"] == "ref"
                nr2 = r_kapali["nesting_results"][bid]
                assert "kanopi_zincir" not in nr2
                assert nr["height_mm"] == nr2["height_mm"]

    def test_report_has_required_sections(self):
        """Rapor bölümleri mevcut olmalı."""
        run_pipeline(SMOKE_SCENARIO)
        content = REPORT_PATH.read_text(encoding="utf-8")

        required_sections = [
            "Siparis Oncelik Tablosu",
            "Parti Plani",
            "Nesting Sonuclari",
            "Instance-Tuner Konfig Kiyasi",
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

    def test_nesting_results_have_portfolio(self):
        """Nesting sonuçları tuner kıyas verisi içermeli (portfolio anahtarı korunur)."""
        result = run_pipeline(SMOKE_SCENARIO)
        for batch_id, nr in result["nesting_results"].items():
            # portfolio anahtarı geriye uyum için hâlâ var olmalı
            assert "portfolio" in nr, f"{batch_id} için 'portfolio' anahtarı eksik"
            port = nr["portfolio"]
            if port is not None:
                assert "winner" in port, f"{batch_id} portfolio'da 'winner' eksik"
                assert "rows" in port, f"{batch_id} portfolio'da 'rows' eksik"
                assert isinstance(port["rows"], list)
                # Tuner konfigleri: baseline + sa_auto + sa_3starts + sa_5starts +
                # dblf_only + ga_only + tabu_only = 7
                assert len(port["rows"]) >= 1, (
                    f"{batch_id} portfolio'da satır yok"
                )
                # Kazanan konfig adı string olmalı
                assert isinstance(port["winner"], str), f"{batch_id}: winner string değil"

    def test_nesting_results_have_tuner(self):
        """Nesting sonuçları tuner bilgisi içermeli."""
        result = run_pipeline(SMOKE_SCENARIO)
        for batch_id, nr in result["nesting_results"].items():
            assert "tuner" in nr, f"{batch_id} için 'tuner' anahtarı eksik"
            tuner_data = nr["tuner"]
            if tuner_data is not None:
                assert "winning_config" in tuner_data, f"{batch_id} tuner'da 'winning_config' eksik"
                assert "baseline_height_mm" in tuner_data
                assert "improvement_mm" in tuner_data
                assert tuner_data["improvement_mm"] >= 0.0, (
                    f"{batch_id}: tuner improvement negatif (monoton ihlal)"
                )

    def test_nesting_results_have_selection_key(self):
        """Nesting sonuçları selection anahtarı içermeli (None olabilir)."""
        result = run_pipeline(SMOKE_SCENARIO)
        for batch_id, nr in result["nesting_results"].items():
            assert "selection" in nr, f"{batch_id} için 'selection' anahtarı eksik"

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

    def test_adaptif_pitch_used(self):
        """Adaptif pitch kullanıldığında pitch_mm nesting sonucunda görünmeli."""
        result = run_pipeline(SMOKE_SCENARIO)
        found_pitch = False
        for batch_id, nr in result["nesting_results"].items():
            if nr.get("pitch_mm") is not None:
                found_pitch = True
                assert nr["pitch_mm"] > 0.0, f"{batch_id} pitch_mm sıfır veya negatif"
        # En az bir parti adaptif pitch almış olmalı
        assert found_pitch, "Hiçbir partide pitch_mm bulunamadı (adaptif pitch çalışmıyor olabilir)"

    def test_pipeline_total_elapsed_under_budget(self):
        """Toplam pipeline süresi 60 sn altında olmalı (timing regression guard).

        SMOKE_SCENARIO portfolio_budget=10 + pitch=20mm ile tasarlandı; bu
        bütçede 60 sn çok rahatlıkla yetmeli. Test gelecekte sessiz yavaşlamaları
        (örn. yanlışlıkla büyütülen iter sayısı, fazladan senkron I/O) erken yakalar.
        """
        _ELAPSED_LIMIT_SEC = 60.0
        t0 = time.perf_counter()
        run_pipeline(SMOKE_SCENARIO)
        elapsed = time.perf_counter() - t0
        assert elapsed < _ELAPSED_LIMIT_SEC, (
            f"Pipeline {elapsed:.1f}s sürdü, sınır {_ELAPSED_LIMIT_SEC}s "
            f"(SMOKE_SCENARIO budget=10 + pitch=20mm ile bu süre aşılmamalı)"
        )


def _shell_scenario(auto_family_routing=None):
    """F5 opt-in testleri için kabuk-profilli minik senaryo.

    Parça source='box' (dilim-voxelizer dims'ten hızlı üretir) ama wall_mm+düşük
    true_fill enjekte edilir → classify_prelim thin_shell (güven ~0.87) görür →
    predict_nfv_benefit aile katmanı wall_aware önerir. Dims küçük (hızlı voxelize).
    """
    parts = [{
        "id": "sh1", "name": "kabuk_parca", "qty": 2, "source": "box",
        "width_mm": 30.0, "depth_mm": 30.0, "height_mm": 24.0,
        "wall_mm": 2.0, "true_fill": 0.15,  # F5/F1 kabuk sinyali (loader'ın doldurduğu meta)
    }]
    sc = {
        "ref_date": date(2026, 6, 13),
        "seed": 7,
        "capacity": {"num_machines": 1, "batch_duration_hours": 8.0,
                     "shifts_per_day": 1, "max_volume_per_batch_cm3": 200_000.0},
        "container": {"width_mm": 220.0, "depth_mm": 220.0},
        "pitch": 20.0,
        "n_orientations": 2,
        "portfolio_budget": 10,
        "nesting_mode": "auto",
        # Bu fixture kabuk->heightmap+wall_aware (F5/H15p) YOLUNU test eder;
        # uretim default'u rot_sokum_routing=True thin_shell'i NFV'ye cevirir
        # (Eren karari 2026-07-15) — o yol ayri testte (rot_sokum testleri).
        "rot_sokum_routing": False,
        "orders": [{
            "order_id": "SHELL-A", "customer": "KabukCo",
            "deadline": "2026-07-01", "priority_class": 1, "parts": parts,
        }],
        "pricing_rules": SMOKE_SCENARIO["pricing_rules"],
    }
    if auto_family_routing is not None:
        sc["auto_family_routing"] = auto_family_routing
    return sc


class TestF5AutoFamilyRouting:
    """F5 opt-in aile-yönlendirme kablosu (demo_pipeline).

    Sözleşme: auto_family_routing default False → davranış BİT-ÖZDEŞ (wall_aware_pitch
    açılmaz). True + nesting_mode='auto' + kabuk-ailesi → wall_aware_pitch OTOMATİK açılır.
    """

    def _nesting_rows(self, result):
        return [nr for nr in result["nesting_results"].values()
                if nr.get("n_parts", 0) > 0]

    def test_flag_yok_wall_aware_kapali(self):
        """Bayrak yok (default) → v1: aile katmanı çalışmaz, wall_aware_pitch False.

        family_routing=False geçtiğinden kabuk fixture'ı bile 'kabuk' gerekçesi ALMAZ
        (v1 kuralları) — mod-flip de wall_aware da üretilmez (asimetri yok).
        """
        result = run_pipeline(_shell_scenario())
        rows = self._nesting_rows(result)
        assert rows, "kabuk partisi çözülmedi"
        for nr in rows:
            assert nr.get("wall_aware_pitch") is False
            assert "kabuk" not in (nr.get("auto_mode_reason") or "").lower()

    def test_flag_kapali_acikca_wall_aware_kapali(self):
        """Bayrak açıkça False → wall_aware_pitch False."""
        result = run_pipeline(_shell_scenario(auto_family_routing=False))
        for nr in self._nesting_rows(result):
            assert nr.get("wall_aware_pitch") is False

    def test_flag_acik_kabuk_wall_aware_aktif(self):
        """Bayrak True + auto + kabuk-ailesi → wall_aware_pitch OTOMATİK True.

        predict_nfv_benefit kabuk-ailesini yakalar (heightmap + wall_aware önerisi);
        opt-in kablo bu öneriyi cidar-duyarlı pitch'e (F3) bağlar.
        """
        result = run_pipeline(_shell_scenario(auto_family_routing=True))
        rows = self._nesting_rows(result)
        assert rows, "kabuk partisi çözülmedi"
        for nr in rows:
            assert nr.get("wall_aware_pitch") is True, \
                f"F5 opt-in wall_aware açılmadı: {nr.get('auto_mode_reason')}"
            # Aile katmanı gerekçesi şeffaf: 'kabuk' geçmeli (auto->heightmap: kabuk...)
            assert "kabuk" in (nr.get("auto_mode_reason") or "").lower()

    def test_rot_sokum_default_kabuk_nfv_yolu(self):
        """URETIM DEFAULT'U (Eren karari 2026-07-15): rot_sokum_routing
        verilmedi (default True) + aile katmani + thin_shell -> NFV+rot yolu.

        Kanit K-46/K-52: d4 kabuk hukmu rot-sokum dunyasinda TERSINE (NFV ham
        231.5 legal + rot-kabul 220.69 < heightmap 287.0)."""
        sc = _shell_scenario(auto_family_routing=True)
        sc.pop("rot_sokum_routing")  # default'a birak (True)
        result = run_pipeline(sc)
        rows = self._nesting_rows(result)
        assert rows, "kabuk partisi cozulmedi"
        for nr in rows:
            reason = (nr.get("auto_mode_reason") or "").lower()
            assert reason.startswith("auto->nfv"), reason
            assert "rot-sokum" in reason
            assert nr.get("wall_aware_pitch") is False

    def test_rot_sokum_kapali_eski_yol(self):
        """rot_sokum_routing=False -> kabuk eski heightmap+wall_aware yolunda
        (fixture default'u; kapatma anahtari calisiyor)."""
        result = run_pipeline(_shell_scenario(auto_family_routing=True))
        for nr in self._nesting_rows(result):
            assert nr.get("wall_aware_pitch") is True

    def test_kutu_flag_acik_bile_wall_aware_kapali(self):
        """Katı kutu (kabuk sinyali yok) + bayrak True → wall_aware_pitch yine False.

        Aile katmanı yalnız kabuk-ailesinde tetikler; kutuda öneri yok → opt-in
        kablo hiçbir şey açmaz (yanlış-pozitif koruması).
        """
        result = run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "auto",
                               "auto_family_routing": True})
        for nr in self._nesting_rows(result):
            assert nr.get("wall_aware_pitch") is False


class TestH15pFineAngleSkip:
    """H-15p (v1+v2): kabuk-ailesi (F3 wall_aware) C2F yolunda hem ince-aci
    rafinesi HEM coarse arama menusu KISITLANIR.

    Sozlesme: wall_aware_pitch True + C2F yolu (qty>C2F_THRESHOLD=40) iken
    solve_coarse_to_fine'e skip_fine_angle=True + menu={"dblf_only": ...} gecer
    + _instr'e iz yazilir (fine_angle_reason, coarse_menu_reason). wall_aware
    False iken skip=False + menu=None (davranis birebir).

    M1 fix (reviewer): eski test yalniz sonuc alanlarini (fine_angle_used)
    kontrol ediyordu — bu, gercek data'da rafinenin zaten kazanmamasindan
    dolayi da False cikabilecegi icin false-green riski tasiyordu. Bu surum
    solve_coarse_to_fine'e giden GERCEK kwargs'i spy ile yakalayip dogrudan
    dogrular (kablo calisiyor mu, sonuctan bagimsiz).
    """

    def _rows(self, result):
        return [nr for nr in result["nesting_results"].values()
                if nr.get("n_parts", 0) > 0]

    def _spy_c2f(self, monkeypatch):
        """solve_coarse_to_fine'e giden kwargs'i yakalayan spy kur, kaydi dondur."""
        import src.nesting3d.coarse_to_fine as c2f_mod
        captured: dict = {}
        orig = c2f_mod.solve_coarse_to_fine

        def _spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        monkeypatch.setattr(c2f_mod, "solve_coarse_to_fine", _spy)
        return captured

    def test_wall_aware_c2f_skips_fine_angle_and_traces(self, monkeypatch):
        """Kabuk-ailesi + qty>40 -> C2F + wall_aware True -> skip izi + used False."""
        captured = self._spy_c2f(monkeypatch)
        sc = _shell_scenario(auto_family_routing=True)
        sc["orders"][0]["parts"][0]["qty"] = 42  # >C2F_THRESHOLD -> C2F yolu
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        # Kablo dogrudan dogrulama (sonuctan bagimsiz, false-green riski yok):
        assert captured.get("skip_fine_angle") is True, \
            "wall_aware True iken solve_coarse_to_fine skip_fine_angle=True almali"
        _menu = captured.get("menu")
        assert _menu is not None, "wall_aware True iken kisitli menu gecmeli (None degil)"
        assert set(_menu.keys()) == {"dblf_only"}, \
            f"kisitli coarse menu yalniz dblf_only olmali: {list(_menu.keys())}"
        for nr in rows:
            assert nr.get("wall_aware_pitch") is True
            assert nr.get("fine_angle_reason") == "skipped: thin_shell/H-15p"
            assert nr.get("coarse_menu_reason") == (
                "dblf_only: thin_shell/H-15p (coarse tune %90 pay, "
                "SA/GA kazandirmiyor)"
            )
            assert nr.get("fine_angle_used") is False

    def test_no_wall_aware_no_skip_trace(self, monkeypatch):
        """wall_aware False (bayrak yok) + C2F yolu -> skip=False + menu=None + iz YOK."""
        captured = self._spy_c2f(monkeypatch)
        sc = _shell_scenario(auto_family_routing=False)
        sc["orders"][0]["parts"][0]["qty"] = 42
        sc["nesting_mode"] = "heightmap"  # auto degil -> family layer hic calismaz
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        assert captured.get("skip_fine_angle") is False, \
            "wall_aware False iken solve_coarse_to_fine skip_fine_angle=False almali"
        assert captured.get("menu") is None, \
            "wall_aware False iken menu=None gecmeli (mevcut davranis birebir)"
        for nr in rows:
            assert nr.get("wall_aware_pitch") is False
            assert nr.get("fine_angle_reason") is None
            assert nr.get("coarse_menu_reason") is None

    def test_c2f_telemetry_scalars_present(self):
        """H-15p v2 telemetri: coarse_time_s/fine_time_s/winning_config her C2F
        kosusunda _instr'e (rapor-only) eklenmis olmali (getattr guvenli)."""
        sc = _shell_scenario(auto_family_routing=True)
        sc["orders"][0]["parts"][0]["qty"] = 42
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        for nr in rows:
            assert isinstance(nr.get("coarse_time_s"), float)
            assert nr.get("coarse_time_s") >= 0.0
            assert isinstance(nr.get("fine_time_s"), float)
            assert nr.get("fine_time_s") >= 0.0
            assert isinstance(nr.get("winning_config"), str)
            assert len(nr["winning_config"]) > 0


class TestH16wDropCacheWiring:
    """H-16w: dirty-region drop_map onbellegi (H-16) URETIME BAGLAMA.

    Sozlesme: wall_aware_pitch True + C2F yolu (qty>C2F_THRESHOLD=40) iken
    solve_coarse_to_fine'e drop_cache=True gecer + fine Bin3D onbellegi acilir
    + _instr'e cache istatistikleri (hit_ratio/keys/peak_mb/...) yazilir.
    wall_aware False iken drop_cache=False + telemetri alanlari EKLENMEZ
    (davranis BIT-OZDES eski yol).
    """

    def _rows(self, result):
        return [nr for nr in result["nesting_results"].values()
                if nr.get("n_parts", 0) > 0]

    def _spy_c2f(self, monkeypatch):
        import src.nesting3d.coarse_to_fine as c2f_mod
        captured: dict = {}
        orig = c2f_mod.solve_coarse_to_fine

        def _spy(*args, **kwargs):
            captured.update(kwargs)
            return orig(*args, **kwargs)

        monkeypatch.setattr(c2f_mod, "solve_coarse_to_fine", _spy)
        return captured

    def test_wall_aware_passes_drop_cache_true(self, monkeypatch):
        """Kabuk-ailesi + qty>40 -> solve_coarse_to_fine'e drop_cache=True gecer
        (kablo dogrudan spy ile dogrulanir, sonuctan bagimsiz)."""
        captured = self._spy_c2f(monkeypatch)
        sc = _shell_scenario(auto_family_routing=True)
        sc["orders"][0]["parts"][0]["qty"] = 42
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        assert captured.get("drop_cache") is True, \
            "wall_aware True iken solve_coarse_to_fine drop_cache=True almali"

    def test_no_wall_aware_drop_cache_false(self, monkeypatch):
        """wall_aware False -> drop_cache=False + telemetri alanlari EKLENMEZ
        (bit-ozdes eski yol)."""
        captured = self._spy_c2f(monkeypatch)
        sc = _shell_scenario(auto_family_routing=False)
        sc["orders"][0]["parts"][0]["qty"] = 42
        sc["nesting_mode"] = "heightmap"  # auto degil -> family layer calismaz
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        assert captured.get("drop_cache") is False, \
            "wall_aware False iken drop_cache=False almali (default)"
        for nr in rows:
            # kapali yolda cache telemetrisi HIC eklenmez (birebir dokunulmazlik)
            assert "drop_cache_hit_ratio" not in nr
            assert "drop_cache_keys" not in nr
            assert "drop_cache_peak_mb" not in nr

    def test_cache_stats_in_telemetry(self):
        """wall_aware -> _instr'e cache istatistikleri (rapor-only) eklenmis
        olmali: hit_ratio [0,1], keys/fallbacks/evictions int, peak_mb float."""
        sc = _shell_scenario(auto_family_routing=True)
        sc["orders"][0]["parts"][0]["qty"] = 42
        result = run_pipeline(sc)
        rows = self._rows(result)
        assert rows, "kabuk partisi cozulmedi"
        for nr in rows:
            hr = nr.get("drop_cache_hit_ratio")
            assert isinstance(hr, float) and 0.0 <= hr <= 1.0
            assert isinstance(nr.get("drop_cache_keys"), int)
            assert isinstance(nr.get("drop_cache_peak_mb"), float)
            assert isinstance(nr.get("drop_cache_fallbacks"), int)
            assert isinstance(nr.get("drop_cache_evictions"), int)


@pytest.mark.slow
class TestRichScenario:
    """Zengin senaryo smoke testi — portföyün ayırt ettiği yoğun vaka.

    pytest -m slow ile çalıştırılır (CI'da atlanır).
    """

    def test_rich_pipeline_runs(self):
        """Zengin senaryo hatasız tamamlanmalı."""
        result = run_pipeline(RICH_SCENARIO)
        assert result is not None
        assert len(result["batches"]) >= 1

    def test_rich_has_portfolio(self):
        """Zengin senaryo her partide tuner/portföy kıyas tablosu üretmeli."""
        result = run_pipeline(RICH_SCENARIO)
        for batch_id, nr in result["nesting_results"].items():
            assert "portfolio" in nr, f"{batch_id} portfolio eksik"
            port = nr["portfolio"]
            if port is not None:
                assert len(port["rows"]) >= 1
                assert isinstance(port["winner"], str)

    def test_coarse_path_unchanged_after_double_voxelize_removal(self, monkeypatch):
        """coarse_to_fine yolu deterministik + clearance-zorunlu referansı korur.

        45 box parça (>C2F_THRESHOLD=40) → coarse_to_fine yolu (solve_coarse_to_fine
        kendi voxelize'ını yapar; çift-voxelize refactor'u 2026-06-26 kalıcı).

        REFERANS GÜNCELLEMESİ (clearance fix 2026-07-06): eski referans 36.0mm,
        margin=0 + z_clearance=1 ile üretilmişti = parçalar TEMAS ediyordu (hoca
        >= 1mm şartı 2026-06-11 İHLAL, üretilemez). Web NFV-DIŞI yollar artık
        clearance_mm=WEB_MIN_CLEARANCE_MM (1mm) ile koşuyor: coarse+fine voxelize
        yatay margin dilation + Bin3D z_clearance pitch'ten türetilir. Bu, HER
        parça-çifti arasına >= 1 voxel boşluk koyar (bu instance'ın kaba pitch'inde
        1 voxel > 1mm; dürüst clearance maliyeti) -> yeni dürüst referans 86.4mm.
        36.0 sayısı ARTIK GEÇERSİZ (0-boşluk, üretilemez).

        İZOLASYON (2026-07-16 bulgusu): senaryo no_go_bounds GEÇİRMEZ ->
        run_pipeline geliştirici-lokal configs/plate.local.json'un no_go'sunu
        çözer ve sentetik 250x250 plakaya hocanın no-go kolonu sızar (86.4
        referansı no-go'suz dünyadan; no-go'lu SA 79.2'ye sapıyordu = makine-yerel
        FAIL). resolve_no_go None'a sabitlenir — referansın tanımlı olduğu
        koşul (test_ingest_zip_stl izolasyon deseninin no-go karşılığı).
        """
        import src.runtime.plate_config as plate_cfg
        monkeypatch.setattr(plate_cfg, "resolve_no_go", lambda root: None)
        parts = [{"id": f"b{i}", "name": f"box{i}", "qty": 1, "source": "box",
                  "width_mm": 30.0 + (i % 12), "depth_mm": 25.0 + (i % 7),
                  "height_mm": 18.0 + (i % 5)} for i in range(45)]
        scenario = {**RICH_SCENARIO,
                    "orders": [{"order_id": "SYN-COARSE", "customer": "TEST",
                                "deadline": "2030-01-01", "priority_class": 1, "parts": parts}],
                    "container": {"width_mm": 250.0, "depth_mm": 250.0, "height_mm": None},
                    "nesting_mode": "heightmap"}
        result = run_pipeline(scenario)
        nr = result["nesting_results"]
        assert nr, "nesting_results bos"
        nest = next(iter(nr.values()))
        assert nest["n_parts"] == 45, f"45 parca beklendi: {nest['n_parts']}"
        # DÜRÜST (clearance >= 1mm zorunlu) referans: 86.4mm (eski 36.0 = 0-boşluk,
        # üretilemez). Determinizm + clearance-yolu kapısı.
        assert abs(nest["height_mm"] - 86.4) < 1e-6, \
            f"coarse yolu height degisti: {nest['height_mm']} (beklenen 86.4, clearance-zorunlu)"


# ---------------------------------------------------------------------------
# Robustluk: bos/sifir-adet siparis tum partiyi cokertmez
# ---------------------------------------------------------------------------

import copy  # noqa: E402


class TestEmptyOrderRobustness:
    """Parcasiz/sifir-adet siparis (gercek kutuda LLM uretebiliyor) gecerli
    siparisleri COKERTMEMELI — atlanmali, durum warnings'e yazilmali."""

    def _scenario_with_empty(self):
        sc = copy.deepcopy(SMOKE_SCENARIO)
        # Gecerli SMOKE-A + SMOKE-B'nin yanina parcasiz bir siparis ekle
        sc["orders"].append({
            "order_id": "BOS-LLM",
            "customer": "Hayalet",
            "deadline": "2026-07-20",
            "priority_class": 3,
            "parts": [],  # LLM sinyal gordu ama parca uretemedi
        })
        return sc

    def test_empty_order_does_not_crash(self):
        """Bir bos siparis varken pipeline gecerlileri isler, exception atmaz."""
        result = run_pipeline(self._scenario_with_empty())
        assert result is not None
        # Gecerli iki siparis islendi
        ids = {o.order_id for o in result["ranked_orders"]}
        assert "SMOKE-A" in ids and "SMOKE-B" in ids
        # Bos siparis atlandi
        assert "BOS-LLM" not in ids
        assert "BOS-LLM" in result["skipped_orders"]

    def test_empty_order_surfaced_in_skipped(self):
        """Atlanan siparis sessizce dusurulmez — skipped_orders'da gorunur."""
        result = run_pipeline(self._scenario_with_empty())
        assert "BOS-LLM" in result["skipped_orders"]
        # warnings yapisal feasibility nesneleri tutar; string karismaz
        assert all(not isinstance(w, str) for w in result["warnings"])

    def test_all_empty_raises_clear_error(self):
        """Tum siparisler bos -> net ValueError (caller yakalar)."""
        sc = copy.deepcopy(SMOKE_SCENARIO)
        for o in sc["orders"]:
            o["parts"] = []
        with pytest.raises(ValueError, match="Gecerli siparis yok"):
            run_pipeline(sc)


# ---------------------------------------------------------------------------
# Fix-1 (CRITICAL): siparis basina asiri buyuk toplam adet -> OOM koruma guard'i
# ---------------------------------------------------------------------------


class TestAbsurdQtyOrderRobustness:
    """Bir siparisin toplam parca adedi MAX_ORDER_TOTAL_QTY'i asarsa siparis
    tum partiyi cokertmez — atlanir, skipped_orders'da GORUNUR (mevcut bos-
    siparis atlama desenininin simetrigi).

    NOT: gercek MAX_ORDER_TOTAL_QTY (100_000) ile pipeline'i UCTAN UCA kosmak
    testi asiri yavaslatir/OOM riski tasir (bu da tam bu Fix'in onledigi sey).
    Bu yuzden testler modul sabitini kucuk bir degere monkeypatch'ler; boylece
    gercek nesting/tuner asamalari kucuk, hizli adetlerle kosar.
    """

    def _scenario_with_qty(self, qty):
        sc = copy.deepcopy(SMOKE_SCENARIO)
        sc["orders"].append({
            "order_id": "BOMBA-QTY",
            "customer": "KotuNiyetli",
            "deadline": "2026-07-20",
            "priority_class": 3,
            "parts": [
                {"id": "pb1", "name": "bomba", "qty": qty,
                 "source": "box", "width_mm": 10.0, "depth_mm": 10.0, "height_mm": 10.0},
            ],
        })
        return sc

    def test_absurd_qty_order_does_not_crash(self, monkeypatch):
        """Limiti asan siparis varken pipeline gecerlileri isler, exception atmaz."""
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "MAX_ORDER_TOTAL_QTY", 5)
        result = dp.run_pipeline(self._scenario_with_qty(6))
        assert result is not None
        ids = {o.order_id for o in result["ranked_orders"]}
        assert "SMOKE-A" in ids and "SMOKE-B" in ids
        assert "BOMBA-QTY" not in ids

    def test_absurd_qty_order_surfaced_in_skipped(self, monkeypatch):
        """Atlanan siparis sessizce dusurulmez — skipped_orders'da gorunur."""
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "MAX_ORDER_TOTAL_QTY", 5)
        result = dp.run_pipeline(self._scenario_with_qty(6))
        assert "BOMBA-QTY" in result["skipped_orders"]

    def test_qty_at_limit_is_not_skipped(self, monkeypatch):
        """Tam sinirda olan siparis atlanmaz (simetrik: '>' kullanilir, '>=' degil)."""
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "MAX_ORDER_TOTAL_QTY", 5)
        result = dp.run_pipeline(self._scenario_with_qty(5))
        assert "BOMBA-QTY" not in result["skipped_orders"]

    def test_default_max_order_total_qty_is_reasonable(self):
        """Modul sabiti tekli-yuzlu gercekci adetlerin (bkz. gercek mail: en fazla
        22) USTUNDE ama sinirsiz DEGIL — asiri buyuk deger yakalanir."""
        from scripts.demo_pipeline import MAX_ORDER_TOTAL_QTY
        assert 0 < MAX_ORDER_TOTAL_QTY < 999_999_999


# ---------------------------------------------------------------------------
# Parti-paralel nesting: paralel == sıralı (determinizm) + gerçekten paralel
# ---------------------------------------------------------------------------

class TestParallelBatches:
    """5 müşteriden 5 ayrı sipariş gibi BAĞIMSIZ partiler ayrı süreçlerde
    paralel koşar; sonuç sıralı ile BİREBİR aynı olmalı (her parti aynı seed)."""

    def _multi_batch_scenario(self, n=3):
        """n ayrı müşteri -> allow_mixing=False -> n ayrı parti."""
        sc = copy.deepcopy(SMOKE_SCENARIO)
        orders = []
        for i in range(n):
            orders.append({
                "order_id": f"P{i:02d}",
                "customer": f"Musteri{i}",      # farklı müşteri -> ayrı parti
                "deadline": "2026-07-10",
                "priority_class": 2,
                "parts": [
                    {"id": f"p{i}a", "name": f"box_{i}a", "qty": 2, "source": "box",
                     "width_mm": 40.0, "depth_mm": 30.0, "height_mm": 20.0},
                    {"id": f"p{i}b", "name": f"box_{i}b", "qty": 1, "source": "box",
                     "width_mm": 50.0, "depth_mm": 40.0, "height_mm": 25.0},
                ],
            })
        sc["orders"] = orders
        return sc

    def test_parallel_equals_sequential(self):
        """parallel_batches=True ve =False AYNI yükseklik+fiyat üretmeli."""
        seq = self._multi_batch_scenario(); seq["parallel_batches"] = False
        par = self._multi_batch_scenario(); par["parallel_batches"] = True
        rs = run_pipeline(seq)
        rp = run_pipeline(par)
        assert set(rs["nesting_results"]) == set(rp["nesting_results"])
        for bid in rs["nesting_results"]:
            assert abs(rs["nesting_results"][bid]["height_mm"]
                       - rp["nesting_results"][bid]["height_mm"]) < 1e-9, bid
            assert abs(rs["pricing_results"][bid]["total_price"]
                       - rp["pricing_results"][bid]["total_price"]) < 1e-9, bid

    def test_parallel_actually_runs_in_processes(self, monkeypatch):
        """_run_batches_parallel GERÇEKTEN süreçlerde koşmalı (boş dönerse
        sessizce sıralıya düşmüş demektir — Windows spawn kırık). Boş-değil +
        doğru batch_id'ler = paralel yol canlı."""
        from scripts import demo_pipeline as dp
        from scripts.demo_pipeline import _run_batches_parallel
        # RAM kapısını izole et: testi koşan makinenin anlık boş RAM'inden
        # bağımsız olsun (bol RAM + bol çekirdek varsay → >=2 işçi garanti).
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 64.0)
        monkeypatch.setattr(dp, "_detect_cores", lambda: 8)
        sc = self._multi_batch_scenario(n=2)
        # run_pipeline'ın kurduğu payload şeklini birebir taklit et
        payloads = []
        for o in sc["orders"]:
            payloads.append({
                "batch_id": o["order_id"], "all_parts": o["parts"],
                "batch_volume_cm3": 100.0, "container_cfg": sc.get("container"),
                "pitch_fallback": sc["pitch"], "n_orient": sc["n_orientations"],
                "seed": sc["seed"], "pricing_rules": sc["pricing_rules"],
            })
        out = _run_batches_parallel(payloads)
        assert out, "ProcessPool boş döndü — paralel yol sessizce sıralıya düşüyor"
        assert set(out) == {"P00", "P01"}
        # 3D nesneler (placements/voxel_parts) pickle ile geri geldi mi?
        for bid in out:
            assert "placements" in out[bid]["nesting"]
            assert "voxel_parts" in out[bid]["nesting"]

    def test_3d_objects_survive_pickle(self):
        """Paralel sonuçta placements/voxel_parts (3D önizleme nesneleri) korunur."""
        par = self._multi_batch_scenario(n=2); par["parallel_batches"] = True
        rp = run_pipeline(par)
        for bid, nr in rp["nesting_results"].items():
            assert len(nr.get("placements", [])) >= 1
            assert len(nr.get("voxel_parts", {})) >= 1


# ---------------------------------------------------------------------------
# Paralel işçi ÜST SINIRI: donanım-farkında, sınırsız değil
# ---------------------------------------------------------------------------

class TestParallelWorkerLimit:
    """İşçi (süreç) sayısı çekirdeğe göre belirlenir ama üst-sınırlıdır —
    işlemciyi/RAM'i boğmaz, OS/UI'ye pay bırakır."""

    def test_detect_cores_positive(self):
        from scripts.demo_pipeline import _detect_cores
        assert _detect_cores() >= 1

    def test_capped_by_batch_count(self):
        """İş 2 partiyse 2'den fazla süreç açılmaz (çekirdek çok olsa bile)."""
        from scripts.demo_pipeline import _resolve_max_workers
        assert _resolve_max_workers(2) <= 2

    def test_hard_cap_enforced(self, monkeypatch):
        """Çok yüksek override bile PARALLEL_HARD_CAP'i aşamaz."""
        from scripts import demo_pipeline as dp
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 999.0)  # RAM kapısını izole et
        monkeypatch.setenv("NESTING_MAX_WORKERS", "999")
        # 100 parti istense bile tavanla sınırlı
        assert dp._resolve_max_workers(100) == dp.PARALLEL_HARD_CAP

    def test_explicit_override(self, monkeypatch):
        """NESTING_MAX_WORKERS kesin sayıyı belirler (iş kadarına kıstırılır)."""
        from scripts import demo_pipeline as dp
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 999.0)  # RAM kapısını izole et
        monkeypatch.setenv("NESTING_MAX_WORKERS", "3")
        assert dp._resolve_max_workers(10) == 3   # tavan(8) altında, iş(10) altında
        assert dp._resolve_max_workers(2) == 2    # iş 2 ise 2

    def test_reserve_leaves_headroom(self, monkeypatch):
        """Otomatik modda OS/UI'ye çekirdek payı bırakılır (rezerv kadar az)."""
        from scripts.demo_pipeline import _resolve_max_workers, _detect_cores
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setenv("NESTING_RESERVE_CORES", "2")
        cores = _detect_cores()
        # bol partiyle: işçi <= çekirdek-2 (en az 1), yani tüm çekirdek alınmaz
        got = _resolve_max_workers(1000)
        assert got <= max(1, cores - 2)
        assert got >= 1

    def test_min_one_worker(self, monkeypatch):
        """Aşırı rezerv bile en az 1 işçi bırakır (paralel hiç çökmez)."""
        from scripts.demo_pipeline import _resolve_max_workers
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setenv("NESTING_RESERVE_CORES", "9999")
        assert _resolve_max_workers(5) >= 1


# ---------------------------------------------------------------------------
# RAM-farkında işçi sınırı: az-RAM'li makinede süreç şişmesini önler
# ---------------------------------------------------------------------------

class TestRamAwareLimit:
    """İşçi sayısı CPU çekirdeğine EK OLARAK boş RAM'e de tabidir."""

    def test_available_ram_reads_or_none(self):
        """RAM okuması bir sayı (>0) veya None döner; istisna atmaz."""
        from scripts.demo_pipeline import _available_ram_gb
        v = _available_ram_gb()
        assert v is None or v > 0

    def test_low_ram_caps_workers(self, monkeypatch):
        """Bol çekirdek ama AZ RAM → işçi RAM'e göre kısılır."""
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setattr(dp, "_detect_cores", lambda: 32)      # bol CPU
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 3.0) # az RAM (3GB boş)
        # ram_workers = floor(3.0 * 0.8 / 1.5) = floor(1.6) = 1 → sıralıya düşer
        assert dp._resolve_max_workers(10) == 1

    def test_ample_ram_allows_cpu_limit(self, monkeypatch):
        """Bol RAM → RAM kapısı bağlamaz, CPU limiti geçerli."""
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setattr(dp, "_detect_cores", lambda: 8)
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 64.0)  # bol RAM
        # CPU: 8-2=6; RAM: floor(64*0.8/1.5)=34 → min → 6 (10 iş, tavan 8)
        assert dp._resolve_max_workers(10) == 6

    def test_ram_unreadable_skips_gate(self, monkeypatch):
        """RAM okunamazsa (None) RAM kapısı atlanır → CPU-only davranış."""
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setattr(dp, "_detect_cores", lambda: 8)
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: None)
        assert dp._resolve_max_workers(10) == 6   # sadece CPU: 8-2=6

    def test_ram_overrides_even_explicit_workers(self, monkeypatch):
        """Açık NESTING_MAX_WORKERS verilse bile RAM yetmiyorsa düşürülür (güvenlik)."""
        from scripts import demo_pipeline as dp
        monkeypatch.setenv("NESTING_MAX_WORKERS", "8")
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 3.0)  # 1 işçilik RAM
        assert dp._resolve_max_workers(10) == 1


# ---------------------------------------------------------------------------
# Tavan env ile ezilebilir: süper bilgisayarda daha çok süreç
# ---------------------------------------------------------------------------

class TestConfigurableHardCap:
    """PARALLEL_HARD_CAP varsayılan 8 ama NESTING_HARD_CAP env ile ezilir —
    süper bilgisayarda (bol çekirdek+RAM) çok daha geniş paralellik."""

    def test_default_cap_is_8(self, monkeypatch):
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_HARD_CAP", raising=False)
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setattr(dp, "_detect_cores", lambda: 64)
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 999.0)  # bol RAM
        # 64 çekirdek + bol RAM ama varsayılan tavan 8
        assert dp._resolve_max_workers(50) == 8

    def test_env_raises_cap_for_supercomputer(self, monkeypatch):
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setenv("NESTING_HARD_CAP", "48")
        monkeypatch.setattr(dp, "_detect_cores", lambda: 64)     # 64-2=62
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 999.0)
        # tavan 48; CPU 62; iş 50 → min = 48
        assert dp._resolve_max_workers(50) == 48

    def test_env_cap_still_bounded_by_cpu_and_work(self, monkeypatch):
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setenv("NESTING_HARD_CAP", "1000")   # çok yüksek tavan
        monkeypatch.setattr(dp, "_detect_cores", lambda: 64)
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 999.0)
        # tavan 1000 ama iş 5 → 5; CPU 62 → yine iş kazanır
        assert dp._resolve_max_workers(5) == 5

    def test_env_cap_still_bounded_by_ram(self, monkeypatch):
        from scripts import demo_pipeline as dp
        monkeypatch.delenv("NESTING_MAX_WORKERS", raising=False)
        monkeypatch.setenv("NESTING_HARD_CAP", "1000")
        monkeypatch.setattr(dp, "_detect_cores", lambda: 64)
        monkeypatch.setattr(dp, "_available_ram_gb", lambda: 12.0)  # az RAM
        # RAM: floor(12*0.8/1.5)=6 → tavan 1000 ve CPU 62'ye rağmen 6
        assert dp._resolve_max_workers(50) == 6


class TestClearanceGate:
    """HIGH-2 runtime clearance kapisi (_clearance_gate, 2026-07-06).

    Gate KARARINI (uyari uret / gec / atla / fail-open) izole test eder;
    placed_meshes + min_clearance mock'lanir (agir geometri gerekmez). Hoca
    >= 2mm sarti (WEB_MIN_CLEARANCE_MM=2.0; A2 guncellemesi 2026-07-09 cevap 5,
    K-45 kablosu 2026-07-11 — eski 1mm kural degerleri birlikte guncellendi).
    """

    def test_flags_violation(self, monkeypatch):
        from types import SimpleNamespace
        from scripts import demo_pipeline as dp
        import src.nesting3d.export_stl as es
        import src.nesting3d.clearance as cl
        monkeypatch.setattr(es, "placed_meshes", lambda *a, **k: ["m1", "m2"])
        monkeypatch.setattr(cl, "min_clearance",
                            lambda *a, **k: SimpleNamespace(min_mm=0.5))
        instr = {}
        note = dp._clearance_gate(["p1", "p2"], {}, 0.5, instr)
        assert note and "URETILEMEZ" in note, f"ihlal uyarisi bekleniyordu: {note!r}"
        assert instr["min_clearance_mm"] == 0.5
        assert "clearance_check_s" in instr

    def test_ok_no_warning(self, monkeypatch):
        from types import SimpleNamespace
        from scripts import demo_pipeline as dp
        import src.nesting3d.export_stl as es
        import src.nesting3d.clearance as cl
        monkeypatch.setattr(es, "placed_meshes", lambda *a, **k: ["m1", "m2"])
        monkeypatch.setattr(cl, "min_clearance",
                            lambda *a, **k: SimpleNamespace(min_mm=2.5))
        instr = {}
        note = dp._clearance_gate(["p1", "p2"], {}, 0.5, instr)
        assert note == "", f"esik ustu -> uyari OLMAMALI: {note!r}"
        assert instr["min_clearance_mm"] == 2.5

    def test_skips_single_part(self):
        from scripts import demo_pipeline as dp
        instr = {}
        assert dp._clearance_gate(["p1"], {}, 0.5, instr) == ""
        assert "min_clearance_mm" not in instr  # <2 parca -> hic olcum yok

    def test_fail_open_on_error(self, monkeypatch):
        from scripts import demo_pipeline as dp
        import src.nesting3d.export_stl as es

        def _boom(*a, **k):
            raise RuntimeError("devox patladi")

        monkeypatch.setattr(es, "placed_meshes", _boom)
        instr = {}
        note = dp._clearance_gate(["p1", "p2"], {}, 0.5, instr)
        assert note == ""  # gate hatasi nest'i BOZMAZ (fail-open)
        assert "devox patladi" in instr.get("clearance_check_error", "")


class TestKapaliKaviteGate:
    """FAZ-1 kapali kavite TELEMETRISI (_kapali_kavite_gate, DENETIM_RAPORU_
    2026-07-03.md #21). Tek-tarafli: hata olursa instr'a alan hic konmaz,
    uretim (nest sonucu) ASLA etkilenmez. kapali_kavite_analizi mock'lanir
    (agir geometri gerekmez) — TestClearanceGate ile ayni izolasyon deseni.
    """

    def test_alan_eklenir(self, monkeypatch):
        from scripts import demo_pipeline as dp
        import src.nesting3d.cavity as cav

        monkeypatch.setattr(cav, "occ_grid_from_placements",
                            lambda *a, **k: object())
        monkeypatch.setattr(
            cav, "kapali_kavite_analizi",
            lambda *a, **k: {"hacim_mm3": 12.0, "n_bolge": 1,
                             "en_buyuk_mm3": 12.0, "sure_s": 0.001})
        instr = {}
        dp._kapali_kavite_gate(["p1", "p2"], {}, 100.0, 100.0, 2.0, instr)
        assert instr["kapali_kavite"]["hacim_mm3"] == 12.0
        assert instr["kapali_kavite"]["n_bolge"] == 1

    def test_hata_durumunda_alan_konmaz(self, monkeypatch):
        """kapali_kavite_analizi patlarsa instr'da alan HIC OLMAMALI —
        cozum/uretim akisi bundan bagimsiz devam eder (tek-tarafli sart)."""
        from scripts import demo_pipeline as dp
        import src.nesting3d.cavity as cav

        def _boom(*a, **k):
            raise RuntimeError("kavite analizi patladi")

        monkeypatch.setattr(cav, "occ_grid_from_placements",
                            lambda *a, **k: object())
        monkeypatch.setattr(cav, "kapali_kavite_analizi", _boom)
        instr = {}
        dp._kapali_kavite_gate(["p1", "p2"], {}, 100.0, 100.0, 2.0, instr)
        assert "kapali_kavite" not in instr

    def test_bos_yerlesimde_atlanir(self):
        from scripts import demo_pipeline as dp
        instr = {}
        dp._kapali_kavite_gate([], {}, 100.0, 100.0, 2.0, instr)
        assert "kapali_kavite" not in instr

    def test_gecersiz_pitch_atlanir(self):
        from scripts import demo_pipeline as dp
        instr = {}
        dp._kapali_kavite_gate(["p1"], {}, 100.0, 100.0, 0.0, instr)
        assert "kapali_kavite" not in instr


# ---------------------------------------------------------------------------
# K-53c (2026-07-16): aile poz-seti onerisi kablosu — rot-sokum thin_shell
# NFV yolunda nfv_quality verilmemisse "max" (AX24) dolar; acik deger ezer.
# ---------------------------------------------------------------------------

def _kalite_sarici(monkeypatch):
    """solve_nfv_kalite'yi sarip cagri kwargs'ini yakalar (gercek solve kosar)."""
    import src.nesting3d.nfv_solve as nfv_mod
    orijinal = nfv_mod.solve_nfv_kalite
    yakalanan = {}

    def sarici(inst, **kw):
        yakalanan.update(kw)
        return orijinal(inst, **kw)

    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sarici)
    return yakalanan


def test_rot_sokum_kabukta_nfv_quality_max_dolar(monkeypatch):
    """nfv_quality verilmedi + rot-sokum thin_shell -> quality='max' (K-53c)."""
    yakalanan = _kalite_sarici(monkeypatch)
    sc = _shell_scenario(auto_family_routing=True)
    sc.pop("rot_sokum_routing")  # uretim default'u (True)
    run_pipeline(sc)
    assert yakalanan.get("quality") == "max", yakalanan


def test_acik_nfv_quality_aile_onerisini_ezer(monkeypatch):
    """Senaryo acikca nfv_quality='fast' derse oneri EZILMEZ degil EZER."""
    yakalanan = _kalite_sarici(monkeypatch)
    sc = _shell_scenario(auto_family_routing=True)
    sc.pop("rot_sokum_routing")
    sc["nfv_quality"] = "fast"
    run_pipeline(sc)
    assert yakalanan.get("quality") == "fast", yakalanan


# ---------------------------------------------------------------------------
# M1 (2026-08-18): telemetri v2 mod-duzeyi alan kablosu — STRATEJI/01_VERI.md
# §5 semasindaki additive alanlarin (pitch_coarse, nfv_quality, peak_ram_mb,
# n_orientations) demo_pipeline uretim yolunda GERCEKTEN append_run_v2'ye
# ulastigini dogrular. append_run_v2 spy'lanir (gercek dosyaya yazilmaz) ve
# PYTEST_CURRENT_TEST kasitli silinir (uretimde bu env yok; test bunu
# taklit ederek normalde atlanan telemetri blogunu calistirir).
# ---------------------------------------------------------------------------

class TestTelemetryV2ModDuzeyiKablo:

    def _spy(self, monkeypatch):
        import src.nesting3d.telemetry as telemetry_mod
        captured: list = []

        def _fake(path, **kwargs):
            captured.append(kwargs)
            return {"schema": 2, **kwargs}

        monkeypatch.setattr(telemetry_mod, "append_run_v2", _fake)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        return captured

    def test_heightmap_yolu_yeni_alanlar_akiyor(self, monkeypatch):
        captured = self._spy(monkeypatch)
        run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "heightmap"})
        assert captured, "telemetri v2 hic cagrilmadi (heightmap yolu)"
        for kw in captured:
            assert kw["mode"] == "heightmap"
            # additive alanlar KEY olarak var (None olabilir ama eksik degil)
            assert "pitch_coarse" in kw
            assert "peak_ram_mb" in kw
            assert "nfv_quality" in kw
            assert kw["nfv_quality"] is None  # heightmap yolunda nfv kalitesi yok
            assert kw["n_orientations"] == SMOKE_SCENARIO["n_orientations"]

    def test_nfv_yolu_nfv_quality_akiyor(self, monkeypatch):
        captured = self._spy(monkeypatch)
        run_pipeline({**SMOKE_SCENARIO, "nesting_mode": "nfv", "nfv_quality": "fast"})
        assert captured, "telemetri v2 hic cagrilmadi (nfv yolu)"
        for kw in captured:
            assert kw["mode"] == "nfv"
            assert kw["nfv_quality"] == "fast"
            assert "peak_ram_mb" in kw

    def test_eski_cagri_imzasi_hala_calisir(self, tmp_path):
        """Geriye-uyum: yeni parametreler verilmeden append_run_v2 eski
        cagiranlar (kxx_telemetri/backfill_v2 tarzi) icin BIREBIR calismali."""
        from src.nesting3d.telemetry import append_run_v2

        row = append_run_v2(
            tmp_path / "v2.jsonl", kaynak="pipeline", instance_id="X",
            mode="heightmap", height_mm=100.0, n_placed=1, n_total=1,
            min_clearance_mm=2.0, n_locked=0,
        )
        assert row["legal_height_mm"] == 100.0
        assert row["pitch_coarse"] is None
        assert row["nfv_quality"] is None
        assert row["peak_ram_mb"] is None
