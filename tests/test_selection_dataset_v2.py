"""Faz C1 — selection/dataset_v2: v2 telemetriden mod-duzeyi egitim tablosu.

Kabul kriterleri (ML plani C1):
  1. arm_of: (mode, recete, pitch) -> kanonik arm (heightmap ailesi tek arm;
     nfv ham/guard pitch'li ayri armlar; kalite/uretim -> nfv_kalite).
  2. INVALID satir (legal None) o arm icin ADAY OLAMAZ (Y-7).
  3. winner = argmin legal (esitlikte alfabetik); per_solver_heights = arm->legal.
  4. dblf_height slotu = heightmap arm'inin legal'i (yoksa None + is_easy False).
  5. feature'siz satir tabloya girmez (sayilir); hic legal arm'i olmayan
     instance tabloya girmez (sayilir).
  6. Held-out dislama exclude_instance_ids ile.
  7. Mevcut TrainingRow tipi AYNEN (gengap/loo_regret/gate uyumu).
"""
from __future__ import annotations

import pytest

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.dataset_v2 import arm_of, build_training_table_v2

FV = [0.5] * 23
FN = [f"f{i}" for i in range(23)]


def _row(iid, mode, recete, pitch, legal, **o):
    r = dict(schema=2, instance_id=iid, mode=mode, recete=recete,
             pitch_fine=pitch, legal_height_mm=legal,
             height_mm=legal if legal is not None else 999.0,
             feature_vector=list(FV), feature_names=list(FN),
             family_f1="mixed_scale", duration_s=60.0, kaynak="backfill")
    r.update(o)
    return r


def test_arm_kanonu():
    assert arm_of("heightmap", "n24", 0.5) == "heightmap"
    assert arm_of("heightmap", "tilt_n24", None) == "heightmap"
    assert arm_of("heightmap+wall_aware", "n24", 0.5) == "heightmap+wall_aware"
    assert arm_of("nfv", "ham@2.0", 2.0) == "nfv_ham@2"
    assert arm_of("nfv", "derin@2.0", 2.0) == "nfv_ham@2"      # derin = ham mekanizmasi
    assert arm_of("nfv", "guard@2.0", 2.0) == "nfv_guard@2"
    assert arm_of("nfv", "ham@1.0", 1.0) == "nfv_ham@1"
    assert arm_of("nfv", "ham@auto2.5", 2.5) == "nfv_ham@2.5"
    assert arm_of("nfv", "kalite", 2.0) == "nfv_kalite"
    assert arm_of("nfv", "uretim", 2.0) == "nfv_kalite"


def test_tablo_kurulumu_winner_ve_invalid():
    rows = [
        _row("p2", "heightmap", "n24", 0.5, 618.0),
        _row("p2", "nfv", "ham@2.0", 2.0, None, n_locked=29),   # INVALID -> aday degil
        _row("p2", "nfv", "guard@2.0", 2.0, 544.5),
        _row("d5", "heightmap", "n24", 1.8, 338.4),
        _row("d5", "nfv", "ham@2.0", 2.0, 223.5),
        _row("d5", "nfv", "ham@1.0", 1.0, 218.0),
    ]
    tablo = build_training_table_v2(rows)
    assert all(isinstance(t, TrainingRow) for t in tablo)
    by_id = {t.instance_id: t for t in tablo}
    p2, d5 = by_id["p2"], by_id["d5"]
    assert p2.winner == "nfv_guard@2"
    assert "nfv_ham@2" not in p2.per_solver_heights          # INVALID dislandi
    assert p2.dblf_height == 618.0                            # heightmap slotu
    assert d5.winner == "nfv_ham@1"
    assert d5.per_solver_heights["nfv_ham@2"] == 223.5
    assert d5.best_height == 218.0


def test_ayni_arm_coklu_satir_min_alinir():
    rows = [_row("p1", "heightmap", "dik_n24", None, 260.0),
            _row("p1", "heightmap", "tilt_n24", None, 141.0)]
    t = build_training_table_v2(rows)[0]
    assert t.per_solver_heights == {"heightmap": 141.0}
    assert t.winner == "heightmap"


def test_dislama_ve_sayaclar():
    ist = {}
    rows = [
        _row("held1", "nfv", "ham@2.0", 2.0, 100.0),
        _row("no_feat", "nfv", "ham@2.0", 2.0, 100.0,
             feature_vector=None, feature_names=None),
        _row("all_inv", "nfv", "ham@2.0", 2.0, None, n_locked=5),
        _row("ok", "nfv", "ham@2.0", 2.0, 100.0),
    ]
    tablo = build_training_table_v2(rows, exclude_instance_ids={"held1"},
                                    istatistik=ist)
    assert [t.instance_id for t in tablo] == ["ok"]
    assert ist["n_heldout_dislanan"] == 1
    assert ist["n_featuresiz_satir"] == 1
    assert ist["n_legal_armsiz_instance"] == 1


def test_heightmap_yoksa_dblf_none():
    t = build_training_table_v2([_row("x", "nfv", "ham@2.0", 2.0, 50.0)])[0]
    assert t.dblf_height is None
    assert t.is_easy is False
    assert t.winner == "nfv_ham@2"
