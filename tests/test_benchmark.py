"""tests/test_benchmark.py — Benchmark altyapisi birim testleri (PLAN_DEMO1 §2.5-2.7).

TDD RED -> GREEN: once testler, sonra implementasyon.

Kapsam:
- benchmark_config.py yuklenebilirlik + sabitlerin varligini dogrula.
- benchmark.py'nin run_benchmark() fonksiyonu mini sentetik setle uc-tan-uca.
- Cikti tablosu kolon seti (instance, aile, cozucu, height_mm, density, time_s,
  height_lb_mm, density_ratio — R5 kolon).
- Determinizm: ayni konfig -> ayni tablo.
- Tune/holdout bolunmesi belgeli ve sabit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixture: gecici cikti dizini
# ---------------------------------------------------------------------------

@pytest.fixture()
def out_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# benchmark_config.py — Yuklenebilirlik + sabit dogrulama
# ---------------------------------------------------------------------------

class TestBenchmarkConfig:
    def test_importable(self):
        from scripts import benchmark_config  # noqa: F401

    def test_has_pitch(self):
        from scripts.benchmark_config import PITCH
        assert isinstance(PITCH, (int, float))
        assert PITCH > 0

    def test_has_budget(self):
        from scripts.benchmark_config import BUDGET
        assert isinstance(BUDGET, int)
        assert BUDGET >= 0

    def test_has_seed(self):
        from scripts.benchmark_config import SEED
        assert isinstance(SEED, int)

    def test_has_solver_names(self):
        from scripts.benchmark_config import SOLVER_NAMES
        assert isinstance(SOLVER_NAMES, list)
        assert len(SOLVER_NAMES) >= 1
        for name in SOLVER_NAMES:
            assert isinstance(name, str)

    def test_has_tune_instances(self):
        from scripts.benchmark_config import TUNE_INSTANCES
        assert isinstance(TUNE_INSTANCES, list)
        assert len(TUNE_INSTANCES) >= 1

    def test_has_holdout_instances(self):
        from scripts.benchmark_config import HOLDOUT_INSTANCES
        assert isinstance(HOLDOUT_INSTANCES, list)
        assert len(HOLDOUT_INSTANCES) >= 1

    def test_tune_holdout_disjoint(self):
        from scripts.benchmark_config import TUNE_INSTANCES, HOLDOUT_INSTANCES

        tune_ids = {inst["id"] for inst in TUNE_INSTANCES}
        holdout_ids = {inst["id"] for inst in HOLDOUT_INSTANCES}
        assert tune_ids.isdisjoint(holdout_ids), (
            f"Tune/holdout kesisen ID'ler: {tune_ids & holdout_ids}"
        )

    def test_instances_have_required_fields(self):
        from scripts.benchmark_config import TUNE_INSTANCES, HOLDOUT_INSTANCES

        all_instances = TUNE_INSTANCES + HOLDOUT_INSTANCES
        for inst in all_instances:
            assert "id" in inst, f"'id' eksik: {inst}"
            assert "family" in inst, f"'family' eksik: {inst}"
            assert "split" in inst, f"'split' eksik: {inst}"
            assert inst["split"] in ("tune", "holdout"), (
                f"Gecersiz split degeri: {inst['split']}"
            )


# ---------------------------------------------------------------------------
# benchmark.py — run_benchmark() uc-tan-uca (mini set, kaba pitch)
# ---------------------------------------------------------------------------

class TestRunBenchmark:
    """Mini set: 2-3 instance, pitch=20, budget=10, DBLF only."""

    # Pitch: box voxelizasyonunda part boyutu >= pitch olmali.
    # random_boxes default min_dim=10 -> pitch=5 ile guvenli (ceil(10/5)=2 voxel).
    _TEST_PITCH = 5.0

    def _mini_instances(self):
        """Test icin minimal instance listesi — kaba/hizli.

        Pitch=5 ile guvenli voxelizasyon icin min_dim=10 kullanilir.
        Kucuk n_parts (3) ile hizli kosar.
        """
        from src.nesting3d.instances.synthetic import random_boxes
        from src.nesting3d.instances.format import ContainerSpec

        cont = ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None)
        return [
            {
                "id": "test_rb_s1",
                "family": "random_boxes",
                "split": "tune",
                "instance": random_boxes(
                    n_parts=3, min_dim=10.0, max_dim=40.0, seed=1, container=cont
                ),
            },
            {
                "id": "test_rb_s2",
                "family": "random_boxes",
                "split": "tune",
                "instance": random_boxes(
                    n_parts=3, min_dim=10.0, max_dim=40.0, seed=2, container=cont
                ),
            },
        ]

    def test_returns_rows(self, out_dir):
        from scripts.benchmark import run_benchmark

        rows = run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_mini",
        )
        # Her instance x her solver -> 1 satir
        assert len(rows) == 2  # 2 instance x 1 solver

    def test_row_has_required_columns(self, out_dir):
        from scripts.benchmark import run_benchmark

        rows = run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_cols",
        )
        required = [
            "instance_id", "aile", "split", "cozucu",
            "height_mm", "density", "time_s",
            "height_lb_mm", "density_ratio",
        ]
        for col in required:
            assert col in rows[0], f"Kolon eksik: {col}"

    def test_density_ratio_column(self, out_dir):
        """Q1: density_ratio = lb_mm / height_mm, aralik (0,1]."""
        from scripts.benchmark import run_benchmark

        rows = run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_r5",
        )
        for row in rows:
            dr = row["density_ratio"]
            assert dr is not None
            assert isinstance(dr, float)
            # (0,1]: lb <= height -> lb/height in (0,1]
            assert 0.0 < dr <= 1.0 + 1e-9, f"density_ratio aralik disi: {dr}"

    def test_density_ratio_reflects_lb_height_ratio(self, out_dir):
        """Q1: density_ratio = lb_mm / height_mm oldugunu dogrudan hesapla."""
        from scripts.benchmark import run_benchmark

        rows = run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_r5_ratio",
        )
        for row in rows:
            expected = row["height_lb_mm"] / max(row["height_mm"], 1e-12)
            assert abs(row["density_ratio"] - expected) < 1e-4, (
                f"density_ratio {row['density_ratio']} beklenen {expected}"
            )
            # Ozdeslik olmamali: height > lb => ratio < 1.0 cogunlukla
            # (en kotu durumda esit: ratio = 1.0; ama 1'den buyuk olmamali)
            assert row["density_ratio"] <= 1.0 + 1e-6

    def test_height_lb_leq_height_mm(self, out_dir):
        """Teorik alt sinir gercek yukseklikten kucuk ya da esit olmali."""
        from scripts.benchmark import run_benchmark

        rows = run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_lb",
        )
        for row in rows:
            assert row["height_lb_mm"] <= row["height_mm"] + 1e-6, (
                f"Alt sinir > gercek: {row['height_lb_mm']} > {row['height_mm']}"
            )

    def test_determinism(self, out_dir):
        """Ayni konfig -> ayni tablo."""
        from scripts.benchmark import run_benchmark

        kwargs = dict(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_det",
        )
        rows_a = run_benchmark(**kwargs)
        rows_b = run_benchmark(**kwargs)

        assert len(rows_a) == len(rows_b)
        for ra, rb in zip(rows_a, rows_b):
            assert ra["height_mm"] == rb["height_mm"]
            assert ra["density"] == rb["density"]

    def test_output_files_created(self, out_dir):
        """MD ve CSV cikti dosyalari olusturulmali."""
        from scripts.benchmark import run_benchmark

        run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_files",
        )
        md_files = list(out_dir.glob("benchmark_test_files*.md"))
        csv_files = list(out_dir.glob("benchmark_test_files*.csv"))
        assert len(md_files) >= 1, "MD dosyasi olusturulmamis"
        assert len(csv_files) >= 1, "CSV dosyasi olusturulmamis"

    def test_tune_holdout_separate_averages(self, out_dir):
        """Tablo tune/holdout ortalamalari ayri satirlar icermeli."""
        from scripts.benchmark import run_benchmark
        from src.nesting3d.instances.synthetic import random_boxes
        from src.nesting3d.instances.format import ContainerSpec

        cont = ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None)
        mixed = [
            {
                "id": "tune_inst",
                "family": "random_boxes",
                "split": "tune",
                "instance": random_boxes(
                    n_parts=3, min_dim=10.0, max_dim=40.0, seed=10, container=cont
                ),
            },
            {
                "id": "holdout_inst",
                "family": "random_boxes",
                "split": "holdout",
                "instance": random_boxes(
                    n_parts=3, min_dim=10.0, max_dim=40.0, seed=11, container=cont
                ),
            },
        ]

        rows = run_benchmark(
            instances=mixed,
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_split",
        )
        splits = {r["split"] for r in rows}
        assert "tune" in splits
        assert "holdout" in splits

        # Q8: MD cikti dosyasinda tune/holdout baslik + ortalama satirlari AYRI olmali
        md_path = out_dir / "benchmark_test_split.md"
        assert md_path.exists(), "MD dosyasi olusturulmamis"
        md_text = md_path.read_text(encoding="utf-8")
        # Her split icin ayri baslik "## Tune Seti" / "## Holdout Seti" olmali
        assert "## Tune Seti" in md_text, "Tune baslik MD'de eksik"
        assert "## Holdout Seti" in md_text, "Holdout baslik MD'de eksik"
        # Ortalama alt basliklarinin ayri varligini dogrula
        assert "### Tune Ortalamalar" in md_text, "Tune ortalama alt-baslik eksik"
        assert "### Holdout Ortalamalar" in md_text, "Holdout ortalama alt-baslik eksik"

    def test_telemetry_written(self, out_dir):
        """run_benchmark her satiri telemetriye yazmali."""
        from scripts.benchmark import run_benchmark

        run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_telemetry",
        )
        # Telemetri dosyasi out_dir/telemetry_runs.jsonl'a yazilmali
        telemetry_file = out_dir / "telemetry_runs.jsonl"
        assert telemetry_file.exists(), "Telemetri dosyasi olusturulmamis"
        from src.nesting3d.telemetry import load_telemetry
        tel_rows = load_telemetry(telemetry_file)
        # 2 instance x 1 solver = 2 satir
        assert len(tel_rows) == 2

    def test_is_quick_flag_in_telemetry(self, out_dir):
        """Q3: is_quick=True ile calistirilan kosularin telemetride is_quick=True olmali."""
        from scripts.benchmark import run_benchmark
        from src.nesting3d.telemetry import load_telemetry

        run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_isquick_true",
            is_quick=True,
        )
        tel_rows = load_telemetry(out_dir / "telemetry_runs.jsonl")
        assert len(tel_rows) >= 1
        for r in tel_rows:
            assert "is_quick" in r, "is_quick alani telemetride eksik"
            assert r["is_quick"] is True, f"is_quick=True beklendi, {r['is_quick']} geldi"

    def test_is_quick_false_in_telemetry(self, out_dir):
        """Q3: is_quick=False (varsayilan) ile kosularin telemetride is_quick=False olmali."""
        from scripts.benchmark import run_benchmark
        from src.nesting3d.telemetry import load_telemetry

        run_benchmark(
            instances=self._mini_instances(),
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_isquick_false",
        )
        tel_rows = load_telemetry(out_dir / "telemetry_runs.jsonl")
        for r in tel_rows:
            assert r.get("is_quick") is False, f"is_quick=False beklendi, {r.get('is_quick')} geldi"


# ---------------------------------------------------------------------------
# Feature vector kolonlari CSV'de
# ---------------------------------------------------------------------------

class TestFeatureColumnsInCSV:
    """Benchmark CSV ciktisi ozellik kolonlarini icermeli."""

    _TEST_PITCH = 5.0

    def test_feature_columns_in_rows(self, out_dir):
        from scripts.benchmark import run_benchmark
        from src.nesting3d.instances.synthetic import random_boxes
        from src.nesting3d.instances.format import ContainerSpec
        from src.nesting3d.instances.features import FEATURE_NAMES

        cont = ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None)
        instances = [
            {
                "id": "feat_test",
                "family": "random_boxes",
                "split": "tune",
                "instance": random_boxes(
                    n_parts=3, min_dim=10.0, max_dim=40.0, seed=5, container=cont
                ),
            }
        ]

        rows = run_benchmark(
            instances=instances,
            solver_names=["dblf"],
            pitch=self._TEST_PITCH,
            budget=5,
            seed=7,
            out_dir=out_dir,
            label="test_feat",
        )
        row = rows[0]
        for fname in FEATURE_NAMES:
            assert fname in row, f"Ozellik kolonu eksik: {fname}"
