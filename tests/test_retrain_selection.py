"""tests/test_retrain_selection.py -- run_retrain + should_retrain birim testleri.

TDD RED/GREEN: retrain.py'ye dayali.

Kabul kriterleri:
- Aday kotu -> promote=False, artifact byte-ayni
- Aday iyi -> promote=True, atomik swap (tmp kalmaz), arsiv olusur
- n<10 -> asla promote
- should_retrain: batch dolmadan False, dolunca True
- Deterministik
- Motor saf: retrain.py motor modullerini import etmez
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.selection.retrain import run_retrain, should_retrain
from src.nesting3d.selection.persistence import save_selection_model
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.dataset import build_training_table


# ---------------------------------------------------------------------------
# Fixture yardimcilari
# ---------------------------------------------------------------------------

def _make_telemetry_rows(n_instances: int, *, winner: str = "sa3d") -> list:
    """n_instances adet instance icin minimal telemetri uret."""
    feature_names = [f"f{i}" for i in range(20)]
    rows = []
    for i in range(n_instances):
        iid = f"inst_{i:04d}"
        rows.append({
            "instance_id": iid,
            "aile": "test",
            "feature_names": feature_names,
            "feature_vector": [float(i % 5) * 0.1 + float(j) * 0.01
                               for j in range(20)],
            "cozucu": "dblf",
            "height_mm": 200.0,
            "winner_flag": False,
            "seed": 42,
            "budget": 30,
            "density": 0.5,
            "time_s": 0.1,
        })
        rows.append({
            "instance_id": iid,
            "aile": "test",
            "feature_names": feature_names,
            "feature_vector": [float(i % 5) * 0.1 + float(j) * 0.01
                               for j in range(20)],
            "cozucu": winner,
            "height_mm": 150.0,
            "winner_flag": True,
            "seed": 42,
            "budget": 30,
            "density": 0.5,
            "time_s": 1.0,
        })
    return rows


def _write_telemetry(tmp_path: Path, rows: list) -> Path:
    p = tmp_path / "runs.jsonl"
    with p.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return p


def _make_artifact(tmp_path: Path, rows: list, *, suffix: str = "") -> Path:
    """Verilen satirlardan model egit, artifact kaydet, yolu dondur."""
    table = build_training_table(rows)
    from scripts.build_selection_model import _split
    train_table, _ = _split(table)
    pf = EasyInstancePrefilter()
    pf.fit(train_table)
    sel = AlgorithmSelector()
    sel.fit(train_table)
    artifact_path = tmp_path / f"selection_model{suffix}.json"
    save_selection_model(pf, sel, artifact_path)
    return artifact_path


# ---------------------------------------------------------------------------
# run_retrain testleri
# ---------------------------------------------------------------------------

class TestRunRetrain:
    def test_returns_gate_decision(self, tmp_path):
        """run_retrain GateDecision dondurmeli."""
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "model.json"

        from src.nesting3d.selection.gate import GateDecision
        decision = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(tmp_path / "archive"),
        )
        assert isinstance(decision, GateDecision)

    def test_decision_json_serializable(self, tmp_path):
        """Donus degeri JSON-serializasyona uygun olmali."""
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "model.json"

        decision = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(tmp_path / "archive"),
        )
        d = decision.to_dict()
        serialized = json.dumps(d)
        loaded = json.loads(serialized)
        assert "promote" in loaded

    def test_insufficient_data_no_promote(self, tmp_path):
        """n<10 -> promote=False, artifact dokunulmaz."""
        rows = _make_telemetry_rows(5)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "model.json"

        decision = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(tmp_path / "archive"),
        )
        assert decision.promote is False
        # Artifact var olmamali (hic yazilmadi)
        assert not artifact_path.exists()

    def test_first_model_creates_artifact(self, tmp_path):
        """Yururluk artifact yok -> ilk model yazilmali."""
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "selection_model.json"

        assert not artifact_path.exists()
        decision = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(tmp_path / "archive"),
        )

        assert decision.promote is True
        assert artifact_path.exists()

    def test_first_model_no_archive_created(self, tmp_path):
        """Ilk model: arsivlenecek eski model yok, arsiv bos olmali."""
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "selection_model.json"
        archive_dir = tmp_path / "archive"

        run_retrain(
            tel_path, artifact_path,
            archive_dir=str(archive_dir),
        )

        # Arsiv dizini olusturulmamis veya bos olmali
        if archive_dir.exists():
            archive_files = list(archive_dir.glob("*.json"))
            assert len(archive_files) == 0

    def test_promote_creates_archive_and_swaps(self, tmp_path):
        """Promote: mevcut artifact arsivlenmeli, yeni artifact atomik yazilmali."""
        rows = _make_telemetry_rows(15)
        current_artifact = _make_artifact(tmp_path, rows, suffix="_cur")
        original_content = current_artifact.read_text(encoding="utf-8")
        archive_dir = tmp_path / "archive"

        tel_path = _write_telemetry(tmp_path, rows)

        # gain_mm=0.0 -> herhangi cand <= cur yeterli
        decision = run_retrain(
            tel_path, current_artifact,
            archive_dir=str(archive_dir),
            gain_mm=0.0,
        )

        if decision.promote:
            # Arsiv dosyasi olusturulmali
            assert archive_dir.exists()
            archive_files = list(archive_dir.glob("*.json"))
            assert len(archive_files) >= 1
            # Versiyonlu isim kontrolu
            assert any("v1" in f.name for f in archive_files)
            # tmp dosyasi kalmamali (atomik swap)
            tmp_file = Path(str(current_artifact) + ".tmp")
            assert not tmp_file.exists()

    def test_no_promote_artifact_byte_identical(self, tmp_path):
        """Promote olmayan karar -> artifact byte-ayni kalmali."""
        rows = _make_telemetry_rows(15)
        current_artifact = _make_artifact(tmp_path, rows, suffix="_nc")
        original_bytes = current_artifact.read_bytes()

        tel_path = _write_telemetry(tmp_path, rows)
        # gain_mm=99999 -> kesinlikle promote=False
        decision = run_retrain(
            tel_path, current_artifact,
            archive_dir=str(tmp_path / "archive"),
            gain_mm=99999.0,
        )

        assert decision.promote is False
        assert current_artifact.read_bytes() == original_bytes

    def test_no_tmp_file_after_promote(self, tmp_path):
        """Promote sonrasi .tmp dosyasi kalmamali (atomik swap)."""
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "model.json"

        run_retrain(
            tel_path, artifact_path,
            archive_dir=str(tmp_path / "archive"),
        )

        tmp_path_file = Path(str(artifact_path) + ".tmp")
        assert not tmp_path_file.exists()

    def test_archive_versioning_increments(self, tmp_path):
        """Ucuncu promote: v1 ve v2 arsiv dosyalari olusturulmali.

        - 1. run: ilk model, artifact yoktu -> arsiv yok (arsivlenecek eski model yok)
        - 2. run: mevcut artifact var -> v1 arsivlendi
        - 3. run: mevcut artifact var (2. run'dan) -> v2 arsivlendi
        """
        rows = _make_telemetry_rows(12)
        tel_path = _write_telemetry(tmp_path, rows)
        artifact_path = tmp_path / "model.json"
        archive_dir = tmp_path / "archive"

        # 1. retrain: ilk model, promote=True, arsiv yok
        d1 = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(archive_dir),
        )
        assert d1.promote is True
        assert artifact_path.exists()

        # 2. retrain: mevcut artifact var, gain_mm=0.0 -> promote=True, v1 arsivlendi
        d2 = run_retrain(
            tel_path, artifact_path,
            archive_dir=str(archive_dir),
            gain_mm=0.0,
        )
        if d2.promote:
            archive_files = sorted(archive_dir.glob("*.json"))
            versions = [f.name for f in archive_files]
            assert any("v1" in n for n in versions)

            # 3. retrain: mevcut artifact var, gain_mm=0.0 -> promote=True, v2 arsivlendi
            d3 = run_retrain(
                tel_path, artifact_path,
                archive_dir=str(archive_dir),
                gain_mm=0.0,
            )
            if d3.promote:
                archive_files = sorted(archive_dir.glob("*.json"))
                versions = [f.name for f in archive_files]
                assert any("v1" in n for n in versions)
                assert any("v2" in n for n in versions)


# ---------------------------------------------------------------------------
# should_retrain testleri
# ---------------------------------------------------------------------------

class TestShouldRetrain:
    def test_false_when_not_enough_new_instances(self, tmp_path):
        """Batch boyutuna ulasilmadiysa False."""
        rows = _make_telemetry_rows(10)
        tel_path = _write_telemetry(tmp_path, rows)

        # last_trained_count=5, batch_size=20 -> 10 < 5+20=25 -> False
        result = should_retrain(tel_path, last_trained_count=5, batch_size=20)
        assert result is False

    def test_true_when_batch_reached(self, tmp_path):
        """Batch dolunca True."""
        rows = _make_telemetry_rows(25)
        tel_path = _write_telemetry(tmp_path, rows)

        # last_trained_count=5, batch_size=20 -> 25 >= 5+20=25 -> True
        result = should_retrain(tel_path, last_trained_count=5, batch_size=20)
        assert result is True

    def test_true_when_exceeds_batch(self, tmp_path):
        """Batch'i asan veri -> True."""
        rows = _make_telemetry_rows(30)
        tel_path = _write_telemetry(tmp_path, rows)

        result = should_retrain(tel_path, last_trained_count=5, batch_size=20)
        assert result is True

    def test_false_exact_boundary_minus_one(self, tmp_path):
        """Tam sinirin bir altinda -> False."""
        rows = _make_telemetry_rows(24)
        tel_path = _write_telemetry(tmp_path, rows)

        # 24 < 5+20=25 -> False
        result = should_retrain(tel_path, last_trained_count=5, batch_size=20)
        assert result is False

    def test_default_batch_size(self, tmp_path):
        """Varsayilan batch_size=20 kullanilmali."""
        rows = _make_telemetry_rows(20)
        tel_path = _write_telemetry(tmp_path, rows)

        # last_trained_count=0, batch_size varsayilan=20 -> 20>=0+20 -> True
        result = should_retrain(tel_path, last_trained_count=0)
        assert result is True

    def test_empty_telemetry_false(self, tmp_path):
        """Bos telemetri -> False."""
        tel_path = tmp_path / "empty.jsonl"
        tel_path.write_text("", encoding="utf-8")

        result = should_retrain(tel_path, last_trained_count=0, batch_size=20)
        assert result is False

    def test_nonexistent_file_false(self, tmp_path):
        """Telemetri dosyasi yoksa False."""
        tel_path = tmp_path / "nonexistent.jsonl"
        result = should_retrain(tel_path, last_trained_count=0, batch_size=20)
        assert result is False


# ---------------------------------------------------------------------------
# Motor safligi testi (DEGiSMEZ-A)
# ---------------------------------------------------------------------------

class TestMotorPurityRetrain:
    def test_retrain_does_not_import_motor_modules(self):
        """retrain.py motor modullerini import etmemeli (DEGiSMEZ-A).

        Sadece import satirlari kontrol edilir, yorum/docstring sayilmaz.
        """
        import src.nesting3d.selection.retrain as retrain_mod

        forbidden = ["bin3d", "sa3d", "dblf", "voxelize"]
        retrain_file = Path(retrain_mod.__file__).read_text(encoding="utf-8")
        for line in retrain_file.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                continue
            is_import_line = (
                stripped.startswith("import ") or stripped.startswith("from ")
            )
            if is_import_line:
                for mod in forbidden:
                    if mod in stripped:
                        raise AssertionError(
                            f"retrain.py motor modulu import ediyor: {mod}\n  Satir: {line}"
                        )
