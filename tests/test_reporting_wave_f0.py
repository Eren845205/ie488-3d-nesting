"""test_reporting_wave_f0.py — F0 rapor/enstrumantasyon dalgasi.

Bu dalga SALT rapor/enstrumantasyon: cozucu yukseklik/yerlesim hicbir default
kosuda DEGISMEZ. Testler yeni raporlama alanlarini + davranis-korumayi dogrular:

  1. PLAKA RAPORLAMA  (#18)  — nesting sonuc dict plate_w_mm/plate_d_mm/plate_auto
  2. HACIM-% DOLULUK  (#17/#19) — _parts_real_volume_mm3 (STL true_fill), mesh_fill_ratio
  3. RAM ON-GUARD     (#23/#24) — _ram_guard_reason (rapor-only; pitch DEGISMEZ)
  4. ZAMAN BUTCESI    (#22)     — time_budget_sec kablosu + budget_exceeded izi

Kosu: pytest tests/test_reporting_wave_f0.py -q
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.demo_pipeline import (  # noqa: E402
    _build_pricing_inputs,
    _parts_volume_cm3,
    _parts_real_volume_mm3,
    _ram_guard_reason,
    run_pipeline,
)
from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.scheduling.models import Order  # noqa: E402


# ---------------------------------------------------------------------------
# Kucuk, hizli senaryo (kutu parcalar, kaba pitch)
# ---------------------------------------------------------------------------

def _mini_scenario(**over):
    sc = {
        "ref_date": date(2026, 6, 13),
        "seed": 42,
        "capacity": {
            "num_machines": 1,
            "batch_duration_hours": 8.0,
            "shifts_per_day": 1,
            "max_volume_per_batch_cm3": 500_000.0,
        },
        "container": {"width_mm": 220.0, "depth_mm": 220.0},
        "pitch": 20.0,
        "n_orientations": 2,
        "portfolio_budget": 10,
        "nesting_mode": "heightmap",  # deterministik, hizli
        "orders": [
            {
                "order_id": "MINI-A",
                "customer": "TestCo",
                "deadline": "2026-07-01",
                "priority_class": 1,
                "parts": [
                    {"id": "p1", "name": "box_small", "qty": 2, "source": "box",
                     "width_mm": 40.0, "depth_mm": 40.0, "height_mm": 30.0},
                ],
            },
        ],
        "pricing_rules": {
            "version": "1.0", "name": "mini",
            "rules": [
                {"id": "r_volume", "type": "unit_price",
                 "input_field": "hacim_m3", "unit_price": 500.0, "description": "v"},
                {"id": "r_min", "type": "min_clamp",
                 "min_price": 100.0, "description": "m"},
            ],
        },
    }
    sc.update(over)
    return sc


# ---------------------------------------------------------------------------
# 2. HACIM-% DOLULUK — hacim yardimcilari
# ---------------------------------------------------------------------------

class TestGercekHacim:
    def test_box_hacmi_tam_kutu(self):
        parts = [{"source": "box", "width_mm": 10.0, "depth_mm": 20.0,
                  "height_mm": 5.0, "qty": 3}]
        vol, missing = _parts_real_volume_mm3(parts)
        assert vol == pytest.approx(10 * 20 * 5 * 3)
        assert missing == 0

    def test_stl_true_fill_ile_katki(self):
        # ESKIDEN STL 0 katki veriyordu; simdi true_fill*bbox katkisi olmali.
        parts = [{"source": "stl", "width_mm": 10.0, "depth_mm": 10.0,
                  "height_mm": 10.0, "qty": 2, "true_fill": 0.5}]
        vol, missing = _parts_real_volume_mm3(parts)
        assert vol == pytest.approx(0.5 * 1000 * 2)
        assert missing == 0

    def test_stl_true_fill_yoksa_hacim_bilinmiyor_izi(self):
        parts = [{"source": "stl", "width_mm": 10.0, "depth_mm": 10.0,
                  "height_mm": 10.0, "qty": 4, "true_fill": None}]
        vol, missing = _parts_real_volume_mm3(parts)
        assert vol == 0.0
        assert missing == 4  # adet kadar 'hacim eksik parca' izi

    def test_parts_volume_cm3_stl_dahil(self):
        # _parts_volume_cm3 artik STL parcayi da sayar (eskiden 0'di).
        parts = [{"source": "stl", "width_mm": 100.0, "depth_mm": 100.0,
                  "height_mm": 100.0, "qty": 1, "true_fill": 0.4}]
        cm3 = _parts_volume_cm3(parts)
        assert cm3 == pytest.approx(0.4 * 1_000_000 / 1000.0)  # 400 cm3

    def test_parts_volume_cm3_box_birebir_korunur(self):
        # DAVRANIS KORUMA: box-only hacim eski formulle birebir.
        parts = [{"source": "box", "width_mm": 40.0, "depth_mm": 40.0,
                  "height_mm": 30.0, "qty": 2}]
        assert _parts_volume_cm3(parts) == pytest.approx(40 * 40 * 30 / 1000.0 * 2)

    def test_stl_hacim_fiyata_yansir_bilincli_karar(self):
        # BILINCLI KARAR 2026-07-03 (DENETIM_RAPORU Dalga-3 #17 kapanisi):
        # STL gercek mesh hacmi (true_fill*bbox) fiyat girdisine (hacim_m3) VE
        # parti gruplamaya yansir. Bu zincir pinlenir:
        #   _parts_volume_cm3 -> Order.total_volume_cm3 -> _build_pricing_inputs
        #   -> hacim_m3.  Fiyatin STL hacminden ETKILENMESI kasitli/kabul edilmis.
        stl_parts = [{"source": "stl", "width_mm": 100.0, "depth_mm": 100.0,
                      "height_mm": 100.0, "qty": 1, "true_fill": 0.4}]
        vol_cm3 = _parts_volume_cm3(stl_parts)  # 0.4 * 1e6 mm3 -> 400 cm3
        assert vol_cm3 > 0.0  # eskiden STL hacmi 0 yutuluyordu

        o = Order(order_id="STL-1", customer="C", parts_ref="STL-1",
                  total_quantity=1, total_volume_cm3=vol_cm3,
                  deadline="2026-07-01", priority_class=1)
        assert o.total_volume_cm3 > 0.0  # parti hacmine akan girdi > 0

        inputs = _build_pricing_inputs(
            batch_volume_cm3=o.total_volume_cm3, height_mm=100.0, density=0.5)
        assert inputs["hacim_m3"] > 0.0  # STL hacmi fiyat girdisine yansidi
        assert inputs["hacim_m3"] == pytest.approx(vol_cm3 / 1_000_000.0)


class TestBin3DMeshFill:
    def test_mesh_fill_ratio_zarf_bazli(self):
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=10.0, z_clearance=1)
        # yukseklik olmadan 0
        assert b.mesh_fill_ratio(1000.0) == 0.0

    def test_mesh_fill_ratio_packing_density_ayri(self):
        # packing_density'ye DOKUNULMADI — imza + davranis korunur.
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=10.0, z_clearance=1)
        assert hasattr(b, "packing_density")
        assert hasattr(b, "mesh_fill_ratio")

    def test_mesh_fill_ratio_pozitif_dolgu_dali(self):
        # h > 0 + bilinen mesh hacmi -> beklenen oran (pozitif-dolgu dali).
        b = Bin3D(plate_w_mm=100.0, plate_d_mm=100.0, pitch=10.0, z_clearance=0)
        b.height[0, 0] = 5  # 5 voxel * 10mm -> max_height 50mm
        assert b.max_height_mm() == pytest.approx(50.0)
        envelope = 100.0 * 100.0 * 50.0  # 500_000 mm3
        # part_volume 250_000 mm3 -> oran 0.5
        assert b.mesh_fill_ratio(250_000.0) == pytest.approx(250_000.0 / envelope)
        assert b.mesh_fill_ratio(250_000.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 3. RAM ON-GUARD — rapor-only (pitch DEGISMEZ)
# ---------------------------------------------------------------------------

class TestRamGuard:
    def test_ram_none_ise_guard_yok(self):
        # RAM okunamadi (None) -> guard DEVRE DISI (CPU-only davranis korunur).
        assert _ram_guard_reason(2.0, 220.0, 220.0, None) is None

    def test_bol_ram_tetiklemez(self):
        # Default kosu: kaba pitch + kucuk plaka + bol RAM -> None (davranis degismez).
        big_ram = 64 * 1024 ** 3
        assert _ram_guard_reason(2.0, 220.0, 220.0, big_ram) is None

    def test_asiri_durumda_iz_birakir(self):
        # Cok kucuk RAM + ince pitch + buyuk plaka -> reason (gorunur iz).
        tiny_ram = 8 * 1024 ** 2  # 8 MB
        reason = _ram_guard_reason(0.5, 2000.0, 2000.0, tiny_ram)
        assert reason is not None
        assert isinstance(reason, str) and reason.strip()


# ---------------------------------------------------------------------------
# Entegrasyon — pipeline sonuc dict yeni alanlar
# ---------------------------------------------------------------------------

class TestPipelinePlakaAlanlari:
    def test_plate_alanlari_sonuc_dictte(self):
        result = run_pipeline(_mini_scenario())
        nr = next(iter(result["nesting_results"].values()))
        assert "plate_w_mm" in nr and nr["plate_w_mm"] == pytest.approx(220.0)
        assert "plate_d_mm" in nr and nr["plate_d_mm"] == pytest.approx(220.0)
        assert nr.get("plate_auto") is False  # container acikca verildi

    def test_plate_auto_turetildi_bayragi(self):
        result = run_pipeline(_mini_scenario(container=None))
        nr = next(iter(result["nesting_results"].values()))
        assert nr.get("plate_auto") is True
        assert nr.get("plate_w_mm", 0) > 0

    def test_hacim_alanlari_sonuc_dictte(self):
        result = run_pipeline(_mini_scenario())
        nr = next(iter(result["nesting_results"].values()))
        assert "volume_fill_pct" in nr
        assert "mesh_volume_cm3" in nr
        assert "volume_missing_parts" in nr
        assert nr["volume_fill_pct"] >= 0.0


class TestPipelineBudget:
    def test_budget_none_default_birebir(self):
        # time_budget_sec verilmezse budget_exceeded False + sonuc uretilir.
        result = run_pipeline(_mini_scenario())
        nr = next(iter(result["nesting_results"].values()))
        assert nr.get("budget_exceeded") in (False, None)


class TestBoxOnlyDavranisKoruma:
    def test_box_only_run_pipeline_yukseklik_kimlik(self):
        # KATMAN-USTU DAVRANIS KANITI: hacim degisikligi (STL fiyat-hacmi #17)
        # box-only kosuyu ETKILEMEZ. Iki bagimsiz kosu AYNI yukseklik uretmeli
        # (deterministik) + yukseklik pozitif (gercek yerlesim oldu). Hizli:
        # kucuk plaka + kaba pitch + tek kutu parca (buyuk grid YOK).
        r1 = run_pipeline(_mini_scenario())
        r2 = run_pipeline(_mini_scenario())
        h1 = next(iter(r1["nesting_results"].values()))["height_mm"]
        h2 = next(iter(r2["nesting_results"].values()))["height_mm"]
        assert h1 == pytest.approx(h2)  # davranis degismedi (birebir tekrar)
        assert h1 > 0.0                  # gercek yerlesim yapildi

    def test_box_only_hacim_fiyata_akar(self):
        # box-only kosuda da hacim > 0 fiyat girdisine (hacim_m3) akmali —
        # STL/#17 kablosunun box tarafinda regresyon olmadiginin kaniti.
        result = run_pipeline(_mini_scenario())
        pr = next(iter(result["pricing_results"].values()))
        assert pr["inputs"]["hacim_m3"] > 0.0


# ---------------------------------------------------------------------------
# M1 (F3): suggested vs applied pitch — solver-ICI geri-kabalastirma gorunurlugu
# ---------------------------------------------------------------------------

class TestSuggestedVsAppliedPitch:
    def test_heightmap_yolu_suggested_esittir_applied(self):
        # Heightmap/tuner yolu: solver'a giren pitch = uygulanan pitch -> ikisi ESIT.
        # (Silent re-coarsening YOK; iki alan da raporda gorunur.)
        result = run_pipeline(_mini_scenario())
        nr = next(iter(result["nesting_results"].values()))
        assert "suggested_pitch_mm" in nr and "applied_pitch_mm" in nr
        assert nr["applied_pitch_mm"] == pytest.approx(nr["suggested_pitch_mm"])

    def test_solver_kabalasmasi_applied_pitchte_gorunur(self, monkeypatch):
        # M1 kanit: solver ICI (nfv bellek pre-flight / c2f) pitch'i kabalastirirsa
        # applied_pitch_mm GERCEK sonuc pitch'ini yansitmali (suggested'tan sapar).
        # c2f cozucusunu sahte sonucla degistir: fine_pitch = suggested'tan FARKLI.
        from types import SimpleNamespace

        import src.nesting3d.coarse_to_fine as c2f_mod

        RESULT_PITCH = 99.0  # suggested (12mm) ile ASLA cakismaz -> ayrim netlesir

        def _fake_c2f(instance, *, plate_w_mm, plate_d_mm, coarse_pitch,
                      fine_pitch, budget, seed):
            bin3d = Bin3D(plate_w_mm, plate_d_mm, RESULT_PITCH)
            tune_result = SimpleNamespace(
                winning_config_name="fake", baseline_height_mm=100.0,
                improvement_mm=0.0, all_results=[], result=None,
            )
            return c2f_mod.CoarseToFineResult(
                placements=[], bin3d=bin3d, height_mm=100.0, density=0.5,
                winning_config="fake", coarse_height_mm=100.0,
                coarse_pitch=coarse_pitch, fine_pitch=RESULT_PITCH,
                coarse_time_s=0.0, fine_time_s=0.0, n_placed=0,
                tune_result=tune_result, fine_voxel_parts={},
                adaptive_reason=None,
            )

        monkeypatch.setattr(c2f_mod, "solve_coarse_to_fine", _fake_c2f)

        # c2f dalini tetikle: qty > C2F_THRESHOLD (40).
        sc = _mini_scenario()
        sc["orders"][0]["parts"][0]["qty"] = 60
        result = run_pipeline(sc)
        nr = next(iter(result["nesting_results"].values()))

        # applied = solver sonuc pitch'i; suggested = ideal ince pitch -> FARKLI.
        assert nr["applied_pitch_mm"] == pytest.approx(RESULT_PITCH)
        assert nr["suggested_pitch_mm"] != pytest.approx(RESULT_PITCH)
        assert nr["suggested_pitch_mm"] < nr["applied_pitch_mm"]
