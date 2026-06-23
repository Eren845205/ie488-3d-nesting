"""Tests for src.nesting3d.parallel_decode — paralel NFV decode birebir + backend eşitliği.

Kabul kriterleri:
  1. decode(parallel=True) == decode(parallel=False) BİREBİR (height + raw placements) — kalite-koruma.
  2. Determinizm: iki koşu aynı sonuç.
  3. best_decode geçerli (height>0, n_placed==parça sayısı, strateji string).
  4. Backend eşitliği: scipy referansı; cupy varsa array_equal, yoksa skip (donanım-bağımsız).
"""
from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.fft_backend import get_backend, _scipy_feasible_mask
from src.nesting3d.parallel_decode import decode, best_decode

PLATE_W = PLATE_D = 100.0
PITCH = 5.0


def _make_instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id="box_a", name="box_a", qty=3, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="box_b", name="box_b", qty=3, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


def _parts():
    parts = to_voxel_parts(_make_instance(), PITCH, n_orientations=2, margin=1)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    return parts, nx, ny


def test_parallel_equals_serial_bit_exact():
    """Kol A orient-thread == seri: yükseklik + placement listesi BİREBİR."""
    parts, nx, ny = _parts()
    fm, _ = get_backend("scipy")
    hs, ps = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH, return_placements=True)
    hp, pp = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=PITCH, return_placements=True)
    assert abs(hs - hp) < 1e-9, f"yükseklik farkı: seri {hs} paralel {hp}"
    assert ps == pp, "placement listesi birebir değil (Kol A sıra/tie-break bozuyor)"


def test_determinism_run_twice():
    parts, nx, ny = _parts()
    fm, _ = get_backend("scipy")
    h1, p1 = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=PITCH, return_placements=True)
    h2, p2 = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=PITCH, return_placements=True)
    assert h1 == h2 and p1 == p2


def test_best_decode_valid():
    parts, nx, ny = _parts()
    h, raw, strat = best_decode(parts, nx, ny, pitch=PITCH, force="cpu-kolA")
    assert h > 0
    assert len(raw) == sum(1 for _ in parts)
    assert strat in ("gpu-resident", "cpu-kolA", "serial")
    # her raw kaydı (part_id, oi, x, y, z) ve plaka içinde
    by_id = {p.id: p for p in parts}
    for (pid, oi, x, y, z) in raw:
        fw, fd, fh = by_id[pid].orientations[oi].grid.shape
        assert 0 <= x and x + fw <= nx and 0 <= y and y + fd <= ny and z >= 0


def test_backend_equivalence_array_equal():
    """Her kullanılabilir backend mask == scipy mask (array_equal). cupy yoksa o kısım skip."""
    rng = np.random.default_rng(7)
    fixtures = [((30, 28, 24), (5, 4, 3), 0.3), ((48, 44, 40), (9, 7, 6), 0.6)]
    from src.nesting3d.capabilities import probe_cupy, probe_fast_backend
    from src.nesting3d.fft_backend import _make_cupy_feasible_mask, _make_fast_feasible_mask
    backends = []
    fast, fname = probe_fast_backend()
    if fast is not None:
        backends.append((fname, _make_fast_feasible_mask(fast)))
    cp = probe_cupy()
    if cp is not None:
        backends.append(("cupy", _make_cupy_feasible_mask(cp)))
    if not backends:
        pytest.skip("scipy dışı backend yok (cupy/mkl_fft kurulu değil)")
    for oshape, gshape, dens in fixtures:
        occ = rng.random(oshape) < dens
        grid = rng.random(gshape) < 0.6
        ref = _scipy_feasible_mask(occ, grid)
        for name, fn in backends:
            assert np.array_equal(ref, fn(occ, grid)), f"{name} backend scipy ile birebir değil"
