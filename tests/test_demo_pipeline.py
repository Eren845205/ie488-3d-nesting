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
