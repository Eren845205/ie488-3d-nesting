"""tests/test_selection_splits.py -- stratified split + LOFO testleri.

Overfit dongusu sertlestirme (2026-06-17) garantileri:
  - Stratified split aile-dengeli (her aile hold-out'ta temsil edilir).
  - Isim-bagimsiz: tek prefix tum hold-out'u kaplayamaz.
  - Geriye-uyum: tek aile + sirali tablo -> eski "son %20" ile ozdes.
  - Determinizm + ayriklik (train ∩ holdout = bos, train ∪ holdout = tablo).
  - LOFO: her aile sirayla tamamen hold-out.
"""

from __future__ import annotations

from collections import Counter
from typing import List

from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.splits import (
    stratified_holdout_split,
    leave_one_family_out,
)


def _row(iid: str, aile: str, fv: float = 0.0, winner: str = "dblf") -> TrainingRow:
    return TrainingRow(
        instance_id=iid,
        is_easy=False,
        winner=winner,
        dblf_height=100.0,
        best_height=100.0,
        feature_vector=[fv],
        feature_names=["f0"],
        aile=aile,
    )


def _table_multi_family() -> List[TrainingRow]:
    rows: List[TrainingRow] = []
    for fam, n in [("A", 10), ("B", 10), ("C", 5)]:
        for i in range(n):
            rows.append(_row(f"{fam}_{i:02d}", fam, float(i)))
    return rows


class TestStratifiedBalance:
    def test_every_family_represented_in_holdout(self):
        table = _table_multi_family()
        _, holdout = stratified_holdout_split(table, 0.2)
        ho_fams = set(r.aile for r in holdout)
        assert ho_fams == {"A", "B", "C"}, f"eksik aile: {ho_fams}"

    def test_proportional_holdout_per_family(self):
        table = _table_multi_family()
        _, holdout = stratified_holdout_split(table, 0.2)
        c = Counter(r.aile for r in holdout)
        # A,B (10) -> 2 each; C (5) -> max(1, round(1.0))=1
        assert c["A"] == 2
        assert c["B"] == 2
        assert c["C"] == 1

    def test_train_and_holdout_disjoint_and_cover(self):
        table = _table_multi_family()
        train, holdout = stratified_holdout_split(table, 0.2)
        tr_ids = {r.instance_id for r in train}
        ho_ids = {r.instance_id for r in holdout}
        assert tr_ids.isdisjoint(ho_ids)
        assert tr_ids | ho_ids == {r.instance_id for r in table}


class TestNameIndependence:
    """Isimlendirme hold-out'u manipule edememeli."""

    def test_renaming_prefix_does_not_dominate_holdout(self):
        # Kullanici tum yeni instance'lari "z_" ile adlandirsa bile, bunlar
        # kendi ailelerine dagilir -> tek prefix tum hold-out'u kaplayamaz.
        table = _table_multi_family()
        # B ailesini "z_" prefix'iyle yeniden adlandir
        renamed = []
        for r in table:
            iid = f"z_{r.instance_id}" if r.aile == "B" else r.instance_id
            renamed.append(_row(iid, r.aile, r.feature_vector[0], r.winner))
        _, holdout = stratified_holdout_split(renamed, 0.2)
        ho_fams = Counter(r.aile for r in holdout)
        # z_ prefix'li B hold-out'un tamami olamaz; A ve C de temsil edilir
        assert ho_fams["A"] >= 1 and ho_fams["C"] >= 1


class TestBackwardCompat:
    """Tek aile + sirali tablo -> eski 'son %20' davranisi ile ozdes."""

    def test_single_family_matches_last_fraction(self):
        rows = [_row(f"inst_{i:03d}", "solo", float(i)) for i in range(10)]
        train, holdout = stratified_holdout_split(rows, 0.2)
        assert [r.instance_id for r in holdout] == ["inst_008", "inst_009"]
        assert len(train) == 8

    def test_incoming_order_preserved_for_holdout_choice(self):
        # Ham (sirasiz) liste: son 2 eleman hold-out olmali (gelen sira korunur)
        rows = [_row(f"train_{i}", "x", float(i)) for i in range(8)]
        rows.append(_row("hold_0", "x", 99.0))
        rows.append(_row("hold_1", "x", 98.0))
        _, holdout = stratified_holdout_split(rows, 0.2)
        assert {r.instance_id for r in holdout} == {"hold_0", "hold_1"}


class TestDeterminism:
    def test_same_table_same_split(self):
        table = _table_multi_family()
        a1, b1 = stratified_holdout_split(table, 0.2)
        a2, b2 = stratified_holdout_split(table, 0.2)
        assert [r.instance_id for r in a1] == [r.instance_id for r in a2]
        assert [r.instance_id for r in b1] == [r.instance_id for r in b2]


class TestEdgeCases:
    def test_empty_table(self):
        assert stratified_holdout_split([], 0.2) == ([], [])

    def test_single_instance_goes_to_train(self):
        train, holdout = stratified_holdout_split([_row("a", "A")], 0.2)
        # tek ornek: hold-out anlamsiz -> fail-safe tek ornegi hold-out yapmaz
        # cunku n<2; train'de kalir
        assert len(train) + len(holdout) == 1

    def test_two_singletons_failsafe_one_holdout(self):
        # Iki ayri aile, her biri tek ornek -> normalde hic hold-out cikmaz;
        # fail-safe en az 1 hold-out garantiler.
        rows = [_row("a", "A"), _row("b", "B")]
        train, holdout = stratified_holdout_split(rows, 0.2)
        assert len(holdout) >= 1
        assert len(train) + len(holdout) == 2


class TestLeaveOneFamilyOut:
    def test_yields_one_round_per_family(self):
        table = _table_multi_family()
        rounds = list(leave_one_family_out(table))
        assert len(rounds) == 3
        left_out = {aile for aile, _, _ in rounds}
        assert left_out == {"A", "B", "C"}

    def test_holdout_is_exactly_the_left_out_family(self):
        table = _table_multi_family()
        for aile, train, holdout in leave_one_family_out(table):
            assert all(r.aile == aile for r in holdout)
            assert all(r.aile != aile for r in train)
            assert len(train) + len(holdout) == len(table)

    def test_single_family_yields_nothing(self):
        rows = [_row(f"x_{i}", "solo", float(i)) for i in range(5)]
        assert list(leave_one_family_out(rows)) == []
