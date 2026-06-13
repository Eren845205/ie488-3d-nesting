"""tests/test_telemetry.py — Telemetri katmani birim testleri (PLAN_DEMO1 §2 kalici telemetri).

TDD RED -> GREEN: her test once yazildi, sonra implementasyon.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.nesting3d.instances.features import FEATURE_NAMES


# ---------------------------------------------------------------------------
# Fixture: gecici telemetri dizini
# ---------------------------------------------------------------------------

@pytest.fixture()
def telemetry_path(tmp_path: Path) -> Path:
    """Gecici JSONL dosyasi."""
    return tmp_path / "runs.jsonl"


# ---------------------------------------------------------------------------
# Import testi
# ---------------------------------------------------------------------------

class TestImport:
    def test_module_importable(self):
        from src.nesting3d import telemetry  # noqa: F401

    def test_append_run_exists(self):
        from src.nesting3d.telemetry import append_run
        assert callable(append_run)

    def test_load_telemetry_exists(self):
        from src.nesting3d.telemetry import load_telemetry
        assert callable(load_telemetry)


# ---------------------------------------------------------------------------
# Satir sema testi
# ---------------------------------------------------------------------------

class TestSchema:
    """append_run satirinin zorunlu alanlari icermesi."""

    REQUIRED_FIELDS = [
        "ts", "kaynak", "instance_id", "aile",
        "cozucu", "pitch", "budget", "seed",
        "height_mm", "density", "time_s", "winner_flag",
    ]

    def _make_row(self):
        """Minimal gecerli satir icin keyword argumanlari."""
        feature_values = [0.0] * len(FEATURE_NAMES)
        return dict(
            kaynak="benchmark",
            instance_id="test_inst_001",
            aile="random_boxes",
            feature_vector=feature_values,
            cozucu="dblf",
            pitch=15.0,
            budget=50,
            seed=7,
            height_mm=120.5,
            density=0.42,
            time_s=0.123,
            winner_flag=True,
        )

    def test_required_fields_present(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, **self._make_row())
        rows = load_telemetry(telemetry_path)
        assert len(rows) == 1
        row = rows[0]
        for field in self.REQUIRED_FIELDS:
            assert field in row, f"Zorunlu alan eksik: {field}"

    def test_feature_vector_length(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, **self._make_row())
        rows = load_telemetry(telemetry_path)
        row = rows[0]
        assert "feature_vector" in row
        assert len(row["feature_vector"]) == len(FEATURE_NAMES)

    def test_feature_names_in_row(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, **self._make_row())
        rows = load_telemetry(telemetry_path)
        row = rows[0]
        assert "feature_names" in row
        assert row["feature_names"] == list(FEATURE_NAMES)

    def test_ts_is_numeric(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        t_before = time.time()
        append_run(telemetry_path, **self._make_row())
        t_after = time.time()
        rows = load_telemetry(telemetry_path)
        ts = rows[0]["ts"]
        assert isinstance(ts, float)
        assert t_before <= ts <= t_after


# ---------------------------------------------------------------------------
# Round-trip testi
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_single_row_round_trip(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        feature_values = [float(i) for i in range(len(FEATURE_NAMES))]
        append_run(
            telemetry_path,
            kaynak="pipeline",
            instance_id="inst_rt_001",
            aile="thin_plates",
            feature_vector=feature_values,
            cozucu="sa3d",
            pitch=10.0,
            budget=100,
            seed=42,
            height_mm=200.0,
            density=0.55,
            time_s=1.5,
            winner_flag=False,
        )
        rows = load_telemetry(telemetry_path)
        assert len(rows) == 1
        r = rows[0]
        assert r["instance_id"] == "inst_rt_001"
        assert r["aile"] == "thin_plates"
        assert r["cozucu"] == "sa3d"
        assert abs(r["pitch"] - 10.0) < 1e-9
        assert r["budget"] == 100
        assert r["seed"] == 42
        assert abs(r["height_mm"] - 200.0) < 1e-9
        assert abs(r["density"] - 0.55) < 1e-9
        assert r["winner_flag"] is False
        assert r["feature_vector"] == feature_values

    def test_multiple_rows_append(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        fv = [0.0] * len(FEATURE_NAMES)
        for i in range(3):
            append_run(
                telemetry_path,
                kaynak="benchmark",
                instance_id=f"inst_{i:03d}",
                aile="random_boxes",
                feature_vector=fv,
                cozucu="dblf",
                pitch=15.0,
                budget=0,
                seed=i,
                height_mm=100.0 + i,
                density=0.4,
                time_s=0.1,
                winner_flag=(i == 0),
            )

        rows = load_telemetry(telemetry_path)
        assert len(rows) == 3
        assert rows[0]["instance_id"] == "inst_000"
        assert rows[2]["instance_id"] == "inst_002"

    def test_jsonl_format(self, telemetry_path):
        """Her satir gecerli JSON olmali."""
        from src.nesting3d.telemetry import append_run

        fv = [0.0] * len(FEATURE_NAMES)
        append_run(
            telemetry_path,
            kaynak="benchmark",
            instance_id="jsonl_test",
            aile="long_rods",
            feature_vector=fv,
            cozucu="dblf",
            pitch=15.0,
            budget=0,
            seed=0,
            height_mm=80.0,
            density=0.3,
            time_s=0.05,
            winner_flag=True,
        )
        lines = telemetry_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["instance_id"] == "jsonl_test"

    def test_missing_file_returns_empty(self, tmp_path):
        from src.nesting3d.telemetry import load_telemetry

        nonexistent = tmp_path / "no_such_file.jsonl"
        rows = load_telemetry(nonexistent)
        assert rows == []

    def test_extra_fields_preserved(self, telemetry_path):
        """Sema genislemesinde ek alanlar eski satirlari bozmamali."""
        from src.nesting3d.telemetry import append_run, load_telemetry

        fv = [0.0] * len(FEATURE_NAMES)
        append_run(
            telemetry_path,
            kaynak="benchmark",
            instance_id="extra_field_test",
            aile="random_boxes",
            feature_vector=fv,
            cozucu="dblf",
            pitch=15.0,
            budget=0,
            seed=0,
            height_mm=90.0,
            density=0.35,
            time_s=0.08,
            winner_flag=True,
            # ek alan — gelecek sema genislemesi simule ediliyor
            extra_metric=3.14,
        )
        rows = load_telemetry(telemetry_path)
        assert rows[0].get("extra_metric") == pytest.approx(3.14)
