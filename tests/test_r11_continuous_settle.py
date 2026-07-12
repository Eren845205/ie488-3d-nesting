"""R11: surekli (alt-voxel) z-kompaksiyon — mekanizma testleri.

Kabul kriterleri:
  1. Ustteki parca alttakine hedef bosluga (clearance+pay) kadar iner, ICINDEN
     GECEMEZ (tunel yok).
  2. Tam-2.0mm yan komsu dusmeyi BLOKLAMAZ (mesafe azalmiyorsa serbest) —
     voxel kafesinin tipik yan boslugu; mutlak esik olsaydi hicbir sey inemezdi.
  3. Bos zeminde parca plakaya oturur (taban temasi serbest).
  4. Kademeli kule tek sweep zincirinde asagi akar (sira: alt-z artan).
  5. apply_settle sonrasi min_clearance >= clearance korunur, yukseklik duser.
  6. Determinizm: ayni girdi -> ayni dz.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import (
    ContinuousSettleResult,
    apply_settle,
    continuous_z_settle,
)


def _box(w, d, h, at=(0.0, 0.0, 0.0)):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2 + at[0], d / 2 + at[1], h / 2 + at[2]])
    return m


def test_stacked_gap_closes_to_target_no_tunnel():
    a = _box(20, 20, 10, at=(0, 0, 0))
    b = _box(20, 20, 10, at=(0, 0, 13))     # dikey bosluk 3.0mm
    r = continuous_z_settle([a, b], clearance_mm=2.0, pay_mm=0.1)
    assert r.dz[0] == 0.0                    # a plakada
    assert 0.7 <= r.dz[1] <= 1.0             # b ~0.9 iner (3.0 -> ~2.1)
    assert r.height_mm == pytest.approx(23.0 - r.dz[1], abs=1e-9)
    assert r.gain_mm > 0.5


def test_exact_2mm_side_neighbor_does_not_block():
    a = _box(20, 20, 10, at=(0, 0, 0))       # plakada
    c = _box(20, 20, 10, at=(22.0, 0, 5))    # yan bosluk TAM 2.0, havada
    r = continuous_z_settle([a, c], clearance_mm=2.0, pay_mm=0.1)
    assert r.dz[1] == pytest.approx(5.0, abs=0.05)   # plakaya oturur


def test_free_fall_to_plate():
    m = _box(15, 15, 10, at=(0, 0, 4.0))
    r = continuous_z_settle([m], clearance_mm=2.0)
    assert r.dz[0] == pytest.approx(4.0, abs=0.03)
    assert r.height_mm == pytest.approx(10.0, abs=0.03)


def test_tower_cascades_down():
    a = _box(20, 20, 10, at=(0, 0, 0))
    b = _box(20, 20, 10, at=(0, 0, 13))      # +3 bosluk
    c = _box(20, 20, 10, at=(0, 0, 26))      # +3 bosluk
    r = continuous_z_settle([a, b, c], clearance_mm=2.0, pay_mm=0.1)
    assert 0.7 <= r.dz[1] <= 1.0
    assert 1.5 <= r.dz[2] <= 2.0             # iki bosluk birden (~1.8)
    assert r.n_moved == 2


def test_clearance_preserved_after_apply():
    rng_boxes = [
        _box(20, 20, 8, at=(0, 0, 0)),
        _box(20, 20, 8, at=(0, 0, 11.5)),    # 3.5 bosluk
        _box(14, 14, 20, at=(24.0, 2, 3.0)), # yanda, 4mm yan bosluk, havada
    ]
    r = continuous_z_settle(rng_boxes, clearance_mm=2.0, pay_mm=0.1)
    shifted = apply_settle(rng_boxes, r)
    rep = min_clearance(shifted, samples_per_mesh=4000)
    assert rep.min_mm >= 2.0
    assert r.height_mm < r.height_before_mm


def test_deterministic():
    def scene():
        return [_box(20, 20, 10, at=(0, 0, 0)),
                _box(18, 16, 9, at=(1, 2, 13.7)),
                _box(10, 10, 30, at=(25, 0, 6.2))]
    r1 = continuous_z_settle(scene(), clearance_mm=2.0)
    r2 = continuous_z_settle(scene(), clearance_mm=2.0)
    assert np.array_equal(r1.dz, r2.dz)
    assert r1.height_mm == r2.height_mm


def test_result_fields():
    m = _box(10, 10, 10, at=(0, 0, 0))
    r = continuous_z_settle([m])
    assert isinstance(r, ContinuousSettleResult)
    assert r.dz.shape == (1,)
    assert r.sweeps_used >= 1
    assert r.telemetri["req_mm"] == pytest.approx(2.1)
