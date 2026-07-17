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


# ---------------------------------------------------------------------------
# K-55 (2026-07-16): cok-cekirdek + distance_upper_bound budamasi BIT-OZDES
# ---------------------------------------------------------------------------

def _k55_sahne(n=10, seed=3):
    import numpy as np
    import trimesh
    rng = np.random.default_rng(seed)
    meshes = []
    z_top = [0.0, 0.0]
    for i in range(n):
        k = i % 2
        w, d, h = rng.uniform(15, 25, 3)
        gap = float(rng.uniform(3.0, 8.0))
        m = trimesh.creation.box(extents=[w, d, h])
        m.apply_translation([k * 35 + w / 2, w / 2, z_top[k] + gap + h / 2])
        z_top[k] += gap + h
        meshes.append(m)
    return meshes


def test_k55_workers_dz_bit_ozdes():
    """worker sayisi SONUCU degistirmez: w=1 ve w=4 dz vektoru birebir."""
    import numpy as np
    from src.nesting3d.continuous_settle import continuous_z_settle
    meshes = _k55_sahne()
    r1 = continuous_z_settle(meshes, clearance_mm=2.0,
                             samples_per_mesh=800, workers=1)
    r4 = continuous_z_settle(meshes, clearance_mm=2.0,
                             samples_per_mesh=800, workers=4)
    assert np.array_equal(r1.dz, r4.dz)
    assert r1.height_mm == r4.height_mm


def test_k55_esik_budamasi_kesin_esdeger():
    """Dayandigimiz scipy sozlesmesi: query(distance_upper_bound=esik) ile
    'herhangi d < esik' testi, tam min(d) < esik ile AYNI karari verir
    (sonlu donen d'ler kesin mesafe; sinirdaki d==esik iki yolda da False)."""
    import numpy as np
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(11)
    a = rng.uniform(0, 50, (400, 3))
    b = rng.uniform(20, 70, (400, 3))
    tree = cKDTree(b)
    d_tam, _ = tree.query(a, k=1)
    tam_min = float(np.min(d_tam))
    for esik in (0.5, 1.0, float(tam_min), tam_min + 1e-9, 5.0, 30.0):
        d_bud, _ = tree.query(a, k=1, distance_upper_bound=esik)
        assert bool((d_bud < esik).any()) == (tam_min < esik), esik


def test_k55_min_clearance_workers_bit_ozdes():
    """min_clearance workers=1 / workers=-1 ayni raporu verir."""
    from src.nesting3d.clearance import min_clearance
    meshes = _k55_sahne(n=6)
    r1 = min_clearance(meshes, samples_per_mesh=500, workers=1)
    r2 = min_clearance(meshes, samples_per_mesh=500, workers=-1)
    assert r1.min_mm == r2.min_mm
    assert r1.worst_pair == r2.worst_pair
    assert r1.n_pairs_checked == r2.n_pairs_checked


def test_k55_default_workers_sinirlari(monkeypatch):
    """R11_WORKERS env override + tavan-6/taban-1 kurali."""
    from src.nesting3d.continuous_settle import _default_workers
    monkeypatch.setenv("R11_WORKERS", "3")
    assert _default_workers() == 3
    monkeypatch.setenv("R11_WORKERS", "bozuk")
    assert 1 <= _default_workers() <= 6
    monkeypatch.delenv("R11_WORKERS")
    assert 1 <= _default_workers() <= 6
