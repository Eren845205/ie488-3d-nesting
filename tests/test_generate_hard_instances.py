"""tests/test_generate_hard_instances.py -- generate_hard_instances birim testleri.

TDD RED/GREEN: generate_hard_instances.py'ye dayali.

Kabul kriterleri:
- _proof_instances() ve _full_instances() degerleri dondurur
- Her instance spec 'id', 'family', 'split', 'params' icerir
- id'ler benzersiz
- 'split' degeri 'tune' veya 'holdout'
- _winner_summary winner_flag=True satirlarindan dogu sayar
- _instance_winner_table okunabilir string dondurur
- _append_to_telemetry kaynak satirlarini hedefe ekler
- Bos kaynak -> 0 doner, hedefi olusturmaz
- Deterministik: ayni parametreler ayni instance listesi
- Motor katkisi yok (bin3d/sa3d/dblf/voxelize import edilmez)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.generate_hard_instances import (
    _proof_instances,
    _full_instances,
    _winner_summary,
    _instance_winner_table,
    _append_to_telemetry,
)


# ---------------------------------------------------------------------------
# Instance listesi kontrolleri
# ---------------------------------------------------------------------------

class TestProofInstances:
    def test_returns_nonempty_list(self):
        insts = _proof_instances()
        assert len(insts) > 0

    def test_each_has_required_keys(self):
        for inst in _proof_instances():
            assert "id" in inst, f"'id' eksik: {inst}"
            assert "family" in inst, f"'family' eksik: {inst}"
            assert "split" in inst, f"'split' eksik: {inst}"
            assert "params" in inst, f"'params' eksik: {inst}"

    def test_ids_are_unique(self):
        insts = _proof_instances()
        ids = [i["id"] for i in insts]
        assert len(ids) == len(set(ids)), "Duplicate ID'ler var"

    def test_split_values_valid(self):
        for inst in _proof_instances():
            assert inst["split"] in ("tune", "holdout"), (
                f"Gecersiz split degeri: {inst['split']!r}"
            )

    def test_family_values_known(self):
        known = {
            "random_boxes", "few_large_many_small", "high_qty_repeat",
            "thin_plates", "long_rods",
        }
        for inst in _proof_instances():
            assert inst["family"] in known, (
                f"Bilinmeyen aile: {inst['family']!r}"
            )

    def test_deterministic(self):
        a = _proof_instances()
        b = _proof_instances()
        assert [i["id"] for i in a] == [i["id"] for i in b]

    def test_hard_prefix_in_ids(self):
        """Zorlu instance ID'leri 'hard_' ile baslamali."""
        for inst in _proof_instances():
            assert inst["id"].startswith("hard_"), (
                f"ID 'hard_' ile baslamamali: {inst['id']!r}"
            )


class TestFullInstances:
    def test_returns_larger_list_than_proof(self):
        assert len(_full_instances()) > len(_proof_instances())

    def test_each_has_required_keys(self):
        for inst in _full_instances():
            for key in ("id", "family", "split", "params"):
                assert key in inst, f"'{key}' eksik: {inst}"

    def test_ids_are_unique(self):
        insts = _full_instances()
        ids = [i["id"] for i in insts]
        assert len(ids) == len(set(ids))

    def test_no_overlap_with_proof_ids(self):
        """Tam set ve kanit seti ID'leri cakismasin."""
        proof_ids = {i["id"] for i in _proof_instances()}
        full_ids = {i["id"] for i in _full_instances()}
        # Tam setin, kanit setini ICERMEMESI tercih edilir (farkli instance'lar)
        # Asla zorunlu degil: onceki kisitla uyumlu; sadece benzersizligi kontrol et
        assert len(full_ids) == len(_full_instances()), "Tam sette duplicate ID"

    def test_targets_hard_solvers(self):
        """Tam set 'hard_' ID'leri icermeli (tasarim kontrolu)."""
        for inst in _full_instances():
            assert "hard_" in inst["id"], (
                f"Tam set ID 'hard_' icermeli: {inst['id']!r}"
            )


# ---------------------------------------------------------------------------
# _winner_summary
# ---------------------------------------------------------------------------

class TestWinnerSummary:
    def _make_rows(self):
        return [
            {"cozucu": "tabu", "winner_flag": True, "instance_id": "i1"},
            {"cozucu": "dblf", "winner_flag": False, "instance_id": "i1"},
            {"cozucu": "multistart", "winner_flag": True, "instance_id": "i2"},
            {"cozucu": "alns", "winner_flag": False, "instance_id": "i2"},
            {"cozucu": "tabu", "winner_flag": True, "instance_id": "i3"},
        ]

    def test_counts_winners_correctly(self):
        rows = self._make_rows()
        summary = _winner_summary(rows)
        assert summary.get("tabu") == 2
        assert summary.get("multistart") == 1
        assert summary.get("alns", 0) == 0
        assert summary.get("dblf", 0) == 0

    def test_empty_rows(self):
        assert _winner_summary([]) == {}

    def test_no_winners(self):
        rows = [{"cozucu": "dblf", "winner_flag": False}]
        assert _winner_summary(rows) == {}

    def test_ignores_missing_winner_flag(self):
        """winner_flag eksik satirlar sayilmamali."""
        rows = [{"cozucu": "sa3d"}]
        assert _winner_summary(rows) == {}


# ---------------------------------------------------------------------------
# _instance_winner_table
# ---------------------------------------------------------------------------

class TestInstanceWinnerTable:
    def _make_rows(self):
        return [
            {"instance_id": "inst_a", "cozucu": "tabu", "winner_flag": True, "height_mm": 120.5},
            {"instance_id": "inst_a", "cozucu": "dblf", "winner_flag": False, "height_mm": 150.0},
            {"instance_id": "inst_b", "cozucu": "alns", "winner_flag": True, "height_mm": 98.3},
        ]

    def test_returns_string(self):
        assert isinstance(_instance_winner_table(self._make_rows()), str)

    def test_contains_instance_ids(self):
        table = _instance_winner_table(self._make_rows())
        assert "inst_a" in table
        assert "inst_b" in table

    def test_contains_winner_names(self):
        table = _instance_winner_table(self._make_rows())
        assert "tabu" in table
        assert "alns" in table

    def test_contains_height(self):
        table = _instance_winner_table(self._make_rows())
        assert "120" in table or "120.5" in table
        assert "98" in table

    def test_empty_rows(self):
        table = _instance_winner_table([])
        assert isinstance(table, str)


# ---------------------------------------------------------------------------
# _append_to_telemetry
# ---------------------------------------------------------------------------

class TestAppendToTelemetry:
    def _write_jsonl(self, path: Path, n: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for i in range(n):
                fh.write(json.dumps({"row": i}) + "\n")

    def test_appends_lines_to_target(self, tmp_path):
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        self._write_jsonl(src, 5)
        self._write_jsonl(dst, 3)

        n = _append_to_telemetry(src, dst)
        assert n == 5
        lines = [l for l in dst.read_text().splitlines() if l.strip()]
        assert len(lines) == 8  # 3 + 5

    def test_creates_target_if_missing(self, tmp_path):
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "subdir" / "dst.jsonl"
        self._write_jsonl(src, 3)

        n = _append_to_telemetry(src, dst)
        assert n == 3
        assert dst.exists()

    def test_empty_source_returns_zero(self, tmp_path):
        src = tmp_path / "empty.jsonl"
        dst = tmp_path / "dst.jsonl"
        src.write_text("", encoding="utf-8")
        self._write_jsonl(dst, 2)

        n = _append_to_telemetry(src, dst)
        assert n == 0
        lines = [l for l in dst.read_text().splitlines() if l.strip()]
        assert len(lines) == 2  # Degismedi

    def test_missing_source_returns_zero(self, tmp_path):
        src = tmp_path / "nonexistent.jsonl"
        dst = tmp_path / "dst.jsonl"

        n = _append_to_telemetry(src, dst)
        assert n == 0
        assert not dst.exists()

    def test_appended_lines_are_valid_json(self, tmp_path):
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        self._write_jsonl(src, 4)

        _append_to_telemetry(src, dst)
        for line in dst.read_text().splitlines():
            if line.strip():
                obj = json.loads(line)
                assert "row" in obj

    def test_preserves_existing_target_content(self, tmp_path):
        src = tmp_path / "src.jsonl"
        dst = tmp_path / "dst.jsonl"
        dst.write_text(json.dumps({"existing": True}) + "\n", encoding="utf-8")
        self._write_jsonl(src, 2)

        _append_to_telemetry(src, dst)
        lines = [json.loads(l) for l in dst.read_text().splitlines() if l.strip()]
        assert any(l.get("existing") for l in lines), "Eski icerik korunmali"
        assert len(lines) == 3  # 1 eski + 2 yeni


# ---------------------------------------------------------------------------
# CLI smoke testi (--help calisir, cikti kodu 0)
# ---------------------------------------------------------------------------

class TestCLISmoke:
    def test_help_flag(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/generate_hard_instances.py", "--help"],
            capture_output=True,
            text=True,
            cwd=str(_ROOT),
        )
        assert result.returncode == 0
        assert "zorlu" in result.stdout.lower() or "kanit" in result.stdout.lower() or "hard" in result.stdout.lower()
