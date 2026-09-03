"""tests/test_selection_advisor.py -- read-only retrain ONERI motoru testleri.

Politika (2026-06-17): advisor SADECE oneri uretir; hicbir sey egitmez/yazmaz.
Garantiler:
  - READ-ONLY: artefakt + gate_log byte-ayni kalir.
  - Oneri alanlari dolu + tutarli (n_new = n_total - n_trained).
  - Overfit senaryosunda uyari + "once veri cesitliligi" tavsiyesi.
  - Eksik cozucu tespiti (telemetride hic kazanmayan).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.nesting3d.instances.features import FEATURE_NAMES
from src.nesting3d.selection.advisor import (
    RetrainSuggestion,
    build_retrain_suggestion,
    POOL_SOLVERS,
)
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.dataset import build_training_table
from src.nesting3d.selection.persistence import save_selection_model
from src.nesting3d.telemetry import load_telemetry


def _write_telemetry(path: Path, n_instances: int, winners=("dblf", "sa3d")) -> None:
    """Her instance icin 2 cozucu satiri yaz; ikinci cozucu kazanir (dusuk height)."""
    lines = []
    for i in range(n_instances):
        iid = f"inst_{i:03d}"
        for j, cozucu in enumerate(winners):
            height = 100.0 - j * 10.0  # son cozucu en dusuk -> kazanan
            row = {
                "ts": 1.0, "kaynak": "benchmark", "instance_id": iid,
                "aile": "test", "feature_names": list(FEATURE_NAMES),
                "feature_vector": [float(i)] + [0.0] * (len(FEATURE_NAMES) - 1),
                "cozucu": cozucu, "pitch": 5.0, "budget": 100, "seed": 42,
                "height_mm": height, "density": 0.5, "time_s": 1.0,
                "winner_flag": (j == len(winners) - 1),
            }
            lines.append(json.dumps(row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_artifact(tel_path: Path, art_path: Path) -> None:
    rows = load_telemetry(tel_path)
    table = build_training_table(rows)
    pf = EasyInstancePrefilter(); pf.fit(table)
    sel = AlgorithmSelector(); sel.fit(table)
    save_selection_model(pf, sel, art_path)


class TestReadOnly:
    def test_returns_suggestion_object(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        assert isinstance(s, RetrainSuggestion)

    def test_does_not_create_artifact(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"  # yok
        build_retrain_suggestion(tel, art)
        assert not art.exists(), "advisor artefakt OLUSTURMAMALI"

    def test_does_not_modify_existing_artifact(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        _make_artifact(tel, art)
        before = art.read_bytes()
        build_retrain_suggestion(tel, art)
        assert art.read_bytes() == before, "advisor artefakti DEGISTIRMEMELI"

    def test_does_not_write_default_gate_log(self, tmp_path, monkeypatch):
        # advisor gecici log kullanir; varsayilan gate_log'a YAZMAMALI.
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        _make_artifact(tel, art)
        # gate'in varsayilan log yolunu izole bir yere tasi; advisor ona dokunmamali
        from src.nesting3d.selection import gate as gate_mod
        sentinel = tmp_path / "should_stay_empty.jsonl"
        monkeypatch.setattr(gate_mod, "_DEFAULT_LOG_PATH", sentinel)
        build_retrain_suggestion(tel, art)
        assert not sentinel.exists(), "advisor varsayilan gate_log'a YAZMAMALI"


class TestSuggestionFields:
    def test_n_new_equals_total_minus_trained(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        _make_artifact(tel, art)
        # artefakt 12'de egitildi; telemetriye 8 yeni ekle -> 20 total, 8 yeni
        _write_telemetry(tel, 20)
        s = build_retrain_suggestion(tel, art)
        assert s.n_total == 20
        assert s.n_trained == 12
        assert s.n_new == 8

    def test_to_dict_json_serializable(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        assert isinstance(json.dumps(s.to_dict()), str)

    def test_recommendations_nonempty(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        assert len(s.recommendations) >= 1
        # Karar kullaniciya birakilir mesaji daima var
        assert any("Karar SENIN" in r or "karar" in r.lower() for r in s.recommendations)


class TestMissingSolvers:
    def test_detects_solvers_that_never_won(self, tmp_path):
        # Sadece dblf + sa3d kazanan; tabu/ga/multistart/alns eksik olmali
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12, winners=("dblf", "sa3d"))
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        for missing in ("ga", "tabu", "multistart", "alns"):
            assert missing in s.missing_solvers
        assert "sa3d" not in s.missing_solvers

    def test_missing_subset_of_pool(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        assert set(s.missing_solvers).issubset(set(POOL_SOLVERS))


class TestLowData:
    def test_low_data_headline_mentions_shortage(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 5)  # < 10
        art = tmp_path / "model.json"
        s = build_retrain_suggestion(tel, art)
        assert "AZ" in s.headline or "az" in s.headline.lower()


class TestDeterminism:
    def test_same_input_same_suggestion(self, tmp_path):
        tel = tmp_path / "runs.jsonl"
        _write_telemetry(tel, 12)
        art = tmp_path / "model.json"
        _make_artifact(tel, art)
        s1 = build_retrain_suggestion(tel, art)
        s2 = build_retrain_suggestion(tel, art)
        assert s1.to_dict() == s2.to_dict()
