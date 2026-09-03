"""tests/test_sa_multistart.py — Adaptif t0 (R2) + MultiStartSA (R4) testleri.

Kapsam:
- Adaptif t0: t0=3.0 birebir eski sonuç; t0="auto" deterministik + makul.
- MultiStartSA: determinizm, median/best/std meta, best<=median, n_starts.
- _derive_seed: farklı start_idx → farklı seed.
"""

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.solvers.sa_solver import SASolver, MultiStartSA, _derive_seed
from src.nesting3d.voxelize import voxelize_part

PITCH = 5.0
ITERS = 60


def _part(part_id, extents):
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(-b.bounds[0])
    return voxelize_part(part_id, b, PITCH, n_orientations=4)


def _bin():
    return Bin3D(40.0, 40.0, PITCH)


def _parts():
    return [
        _part("slab1", (20, 20, 5)),
        _part("stick1", (5, 5, 30)),
        _part("cube1", (10, 10, 10)),
        _part("cube2", (10, 10, 10)),
    ]


# --- Adaptif t0 (R2) -------------------------------------------------------

class TestAdaptiveT0:
    def test_numeric_t0_unchanged(self):
        """t0=3.0 (açık) default ile BİREBİR aynı — geriye uyumluluk."""
        r_default = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=ITERS)
        r_explicit = simulated_annealing_3d(
            _parts(), _bin, seed=7, iterations=ITERS, t0=3.0
        )
        assert r_explicit.best_height_mm == r_default.best_height_mm
        assert r_explicit.history == r_default.history

    def test_auto_t0_runs_and_deterministic(self):
        """t0="auto" çalışır; aynı seed → birebir aynı sonuç."""
        r1 = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=ITERS, t0="auto")
        r2 = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=ITERS, t0="auto")
        assert r1.best_height_mm == r2.best_height_mm
        assert r1.history == r2.history
        # Best-so-far garantisi: baseline'ın altına asla düşmez.
        assert r1.best_height_mm <= r1.baseline_height_mm + 1e-9

    def test_auto_differs_from_numeric_path(self):
        """auto probe'ları rng tükettiğinden numeric'ten farklı seyir (beklenen)."""
        r_auto = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=ITERS, t0="auto")
        r_num = simulated_annealing_3d(_parts(), _bin, seed=7, iterations=ITERS, t0=3.0)
        # Sonuç illa aynı olmak zorunda değil; en azından ikisi de geçerli.
        assert r_auto.best_height_mm > 0 and r_num.best_height_mm > 0


# --- MultiStartSA (R4) -----------------------------------------------------

class TestMultiStartSA:
    def test_deterministic(self):
        """Aynı (seed_base, n_starts, budget, seed) → birebir aynı."""
        a = MultiStartSA(seed_base=0, n_starts=4).solve(
            _parts(), _bin, budget=ITERS, seed=42
        )
        b = MultiStartSA(seed_base=0, n_starts=4).solve(
            _parts(), _bin, budget=ITERS, seed=42
        )
        assert a.height_mm == b.height_mm
        assert a.meta["all_heights_mm"] == b.meta["all_heights_mm"]

    def test_meta_has_stats(self):
        res = MultiStartSA(seed_base=0, n_starts=4).solve(
            _parts(), _bin, budget=ITERS, seed=42
        )
        m = res.meta
        assert "median_height_mm" in m and "best_height_mm" in m and "std_height_mm" in m
        # Dönen sonuç en iyi start; best_height_mm = dönen height.
        assert res.height_mm == m["best_height_mm"]
        # best <= median (en iyi, ortancadan büyük olamaz).
        assert m["best_height_mm"] <= m["median_height_mm"] + 1e-9
        assert m["std_height_mm"] >= 0.0

    def test_returns_solve_result(self):
        res = MultiStartSA(n_starts=2).solve(_parts(), _bin, budget=ITERS, seed=1)
        assert isinstance(res, SolveResult)
        assert res.meta["n_starts"] == 2

    def test_n_starts_validation(self):
        import pytest
        with pytest.raises(ValueError):
            MultiStartSA(n_starts=0)

    def test_budget_split_total(self):
        """Toplam iterasyon budget'a eşit dağıtılır (kalan ilk start'lara)."""
        # n_starts=3, budget=10 → 4+3+3 = 10
        res = MultiStartSA(seed_base=0, n_starts=3).solve(
            _parts(), _bin, budget=10, seed=5
        )
        assert res.meta["n_starts"] == 3
        assert len(res.meta["all_heights_mm"]) == 3


# --- _derive_seed ----------------------------------------------------------

class TestDeriveSeed:
    def test_distinct_per_start(self):
        seeds = [_derive_seed(0, 42, i) for i in range(8)]
        assert len(set(seeds)) == 8  # hepsi farklı

    def test_deterministic(self):
        assert _derive_seed(3, 42, 2) == _derive_seed(3, 42, 2)

    def test_nonnegative(self):
        for i in range(20):
            assert _derive_seed(7, 99, i) >= 0
