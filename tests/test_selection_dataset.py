"""tests/test_selection_dataset.py — dataset.py birim testleri.

TDD RED: selection/dataset.py henuz yok; testler onceden yazildi.
"""
from __future__ import annotations

import pytest

from src.nesting3d.selection.dataset import (
    TrainingRow,
    build_training_table,
)


# ---------------------------------------------------------------------------
# Yardimci: minimal telemetri satirlari
# ---------------------------------------------------------------------------

def _make_rows(
    instance_id: str,
    solver_heights: dict,
    feature_vector: list | None = None,
) -> list:
    """Verilen {cozucu: height_mm} sozlugunden telemetri satirlari uret."""
    if feature_vector is None:
        feature_vector = [1.0] * 20
    feature_names = [f"f{i}" for i in range(20)]
    rows = []
    min_h = min(solver_heights.values())
    for cozucu, h in solver_heights.items():
        rows.append(
            {
                "instance_id": instance_id,
                "aile": "test",
                "feature_names": feature_names,
                "feature_vector": feature_vector,
                "cozucu": cozucu,
                "height_mm": h,
                "winner_flag": abs(h - min_h) < 1e-9,
                "seed": 42,
                "budget": 30,
                "density": 0.5,
                "time_s": 1.0,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Testler
# ---------------------------------------------------------------------------


class TestBuildTrainingTable:
    def test_empty_rows_returns_empty(self):
        result = build_training_table([])
        assert result == []

    def test_single_easy_instance(self):
        """Tum cozucular ayni height -> is_easy=True."""
        rows = _make_rows("inst_easy", {"dblf": 100.0, "sa3d": 100.0, "ga": 100.0})
        table = build_training_table(rows)
        assert len(table) == 1
        row = table[0]
        assert row.instance_id == "inst_easy"
        assert row.is_easy is True
        assert abs(row.dblf_height - 100.0) < 1e-9
        assert abs(row.best_height - 100.0) < 1e-9

    def test_single_hard_instance(self):
        """SA dblf'yi geciyor -> is_easy=False."""
        rows = _make_rows("inst_hard", {"dblf": 200.0, "sa3d": 150.0, "ga": 160.0})
        table = build_training_table(rows)
        assert len(table) == 1
        row = table[0]
        assert row.is_easy is False
        assert abs(row.dblf_height - 200.0) < 1e-9
        assert abs(row.best_height - 150.0) < 1e-9
        assert row.winner == "sa3d"

    def test_winner_field_is_best_solver(self):
        """Kazanan en dusuk height'li cozucu."""
        rows = _make_rows(
            "inst_w",
            {"dblf": 100.0, "sa3d": 90.0, "tabu": 95.0},
        )
        table = build_training_table(rows)
        assert table[0].winner == "sa3d"

    def test_feature_vector_preserved(self):
        fv = [float(i) for i in range(20)]
        rows = _make_rows("inst_fv", {"dblf": 50.0, "sa3d": 50.0}, feature_vector=fv)
        table = build_training_table(rows)
        assert table[0].feature_vector == fv

    def test_multiple_instances(self):
        rows = _make_rows("A", {"dblf": 10.0, "sa3d": 10.0})
        rows += _make_rows("B", {"dblf": 20.0, "sa3d": 15.0})
        table = build_training_table(rows)
        assert len(table) == 2
        ids = {r.instance_id for r in table}
        assert ids == {"A", "B"}

    def test_is_easy_epsilon_boundary(self):
        """Epsilon icindeyse kolay (varsayilan epsilon=0.5 mm)."""
        # 0.3 mm fark -> kolay
        rows = _make_rows("inst_ep", {"dblf": 100.0, "sa3d": 99.7})
        table = build_training_table(rows, epsilon_mm=0.5)
        assert table[0].is_easy is True

    def test_is_easy_epsilon_above(self):
        """Epsilon uzerindeyse zor."""
        rows = _make_rows("inst_ep2", {"dblf": 100.0, "sa3d": 99.0})
        table = build_training_table(rows, epsilon_mm=0.5)
        assert table[0].is_easy is False

    def test_no_dblf_in_group(self):
        """DBLF olmayan grup; dblf_height=None, is_easy=False."""
        rows = [
            {
                "instance_id": "no_dblf",
                "aile": "test",
                "feature_names": [f"f{i}" for i in range(20)],
                "feature_vector": [1.0] * 20,
                "cozucu": "sa3d",
                "height_mm": 80.0,
                "winner_flag": True,
                "seed": 42,
                "budget": 30,
                "density": 0.5,
                "time_s": 1.0,
            }
        ]
        table = build_training_table(rows)
        assert len(table) == 1
        assert table[0].dblf_height is None
        assert table[0].is_easy is False

    def test_training_row_is_named_tuple_or_dataclass(self):
        rows = _make_rows("x", {"dblf": 5.0})
        table = build_training_table(rows)
        row = table[0]
        # Must have these attrs
        assert hasattr(row, "instance_id")
        assert hasattr(row, "is_easy")
        assert hasattr(row, "winner")
        assert hasattr(row, "dblf_height")
        assert hasattr(row, "best_height")
        assert hasattr(row, "feature_vector")
        assert hasattr(row, "feature_names")

    def test_duplicate_solver_rows_takes_best(self):
        """Ayni instance+cozucu'da birden fazla satir varsa en dusuk yukseklik alinir."""
        rows = [
            {
                "instance_id": "dup",
                "aile": "t",
                "feature_names": [f"f{i}" for i in range(20)],
                "feature_vector": [1.0] * 20,
                "cozucu": "dblf",
                "height_mm": 100.0,
                "winner_flag": False,
                "seed": 42,
                "budget": 30,
                "density": 0.5,
                "time_s": 0.1,
            },
            {
                "instance_id": "dup",
                "aile": "t",
                "feature_names": [f"f{i}" for i in range(20)],
                "feature_vector": [1.0] * 20,
                "cozucu": "dblf",
                "height_mm": 90.0,
                "winner_flag": True,
                "seed": 42,
                "budget": 30,
                "density": 0.5,
                "time_s": 0.1,
            },
        ]
        table = build_training_table(rows)
        assert len(table) == 1
        assert abs(table[0].dblf_height - 90.0) < 1e-9
