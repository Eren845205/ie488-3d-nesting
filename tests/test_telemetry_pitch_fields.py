"""tests/test_telemetry_pitch_fields.py — suggested/applied pitch telemetri alanlari.

Neden: musait ~2GB RAM sessiz geri-kabalastirma (bellek pre-flight) yapabiliyor;
onerilen (suggested) ve fiilen uygulanan (applied) pitch AYRI kayit edilmeli ki
cidar-duyarli faz yanlislikla "etkisiz" gorunmesin. Geriye-uyumlu: eski kayitlar
bu alanlar olmadan da okunur (None); alanlar yalniz verildiginde yazilir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.nesting3d.instances.features import FEATURE_NAMES


@pytest.fixture()
def telemetry_path(tmp_path: Path) -> Path:
    return tmp_path / "runs.jsonl"


def _base_row():
    return dict(
        kaynak="pipeline",
        instance_id="pitch_inst",
        aile="thin_shell",
        feature_vector=[0.0] * len(FEATURE_NAMES),
        cozucu="nfv",
        pitch=0.5,
        budget=0,
        seed=1,
        height_mm=282.0,
        density=0.4,
        time_s=1.0,
        winner_flag=True,
    )


class TestPitchTelemetryFields:
    def test_suggested_and_applied_written(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, suggested_pitch_mm=0.5, applied_pitch_mm=2.0,
                   **_base_row())
        row = load_telemetry(telemetry_path)[0]
        assert row["suggested_pitch_mm"] == pytest.approx(0.5)
        assert row["applied_pitch_mm"] == pytest.approx(2.0)

    def test_backward_compatible_when_omitted(self, telemetry_path):
        # Alanlar verilmezse satira YAZILMAZ (eski davranis birebir).
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, **_base_row())
        row = load_telemetry(telemetry_path)[0]
        assert "suggested_pitch_mm" not in row
        assert "applied_pitch_mm" not in row

    def test_partial_field_ok(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, suggested_pitch_mm=0.5, **_base_row())
        row = load_telemetry(telemetry_path)[0]
        assert row["suggested_pitch_mm"] == pytest.approx(0.5)
        assert "applied_pitch_mm" not in row

    def test_coerced_to_float(self, telemetry_path):
        from src.nesting3d.telemetry import append_run, load_telemetry

        append_run(telemetry_path, suggested_pitch_mm="0.5", applied_pitch_mm=2,
                   **_base_row())
        row = load_telemetry(telemetry_path)[0]
        assert isinstance(row["suggested_pitch_mm"], float)
        assert isinstance(row["applied_pitch_mm"], float)
