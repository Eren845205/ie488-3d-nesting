"""solvers/sa_solver.py — Simulated Annealing çözücüleri (PLAN_DEMO1 §1.3, Faz 4).

SASolver: sa3d.simulated_annealing_3d sarmalayıcısı (sa3d.py'yi DEĞİŞTİRMEZ).
MultiStartSA (R4): N bağımsız SA start'ı deterministik seed'lerle koşar, en
iyiyi seçer, median/best/std raporlar.

Determinizm garantisi:
- SASolver: aynı (parts, bin_factory, budget, seed, order_key, t0) → birebir
  aynı SolveResult. t0="auto" da deterministik (problar ana döngü öncesi aynı
  seed'li rng'den çekilir; bkz sa3d._calibrate_t0).
- MultiStartSA: aynı (seed_base, n_starts, budget, seed) → birebir aynı sonuç.
  Start seed'leri _derive_seed ile (seed_base, run_seed, start_idx)'ten türetilir.

Geriye uyumluluk: SASolver() (argümansız) ve solve(...) eski davranışı verir —
t0 default 3.0, numune 181.5 mm rekoru etkilenmez.
"""

from __future__ import annotations

import statistics
import time
from typing import Callable, List, Optional, Union

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.voxelize import VoxelPart

# Seed türetme karıştırıcıları (golden-ratio sabitleri) — start'lar arası seed
# çakışmasını önler; deterministik.
_SEED_MIX: int = 0x9E3779B1
_SEED_STRIDE: int = 0x85EBCA77
_SEED_MASK: int = 0x7FFFFFFF  # pozitif 31-bit


def _derive_seed(seed_base: int, run_seed: int, start_idx: int) -> int:
    """(seed_base, run_seed, start_idx)'ten deterministik per-start seed türet.

    - Farklı seed_base (çözücü konfigi) farklı seed akışı verir.
    - Farklı run_seed (solve seed'i) farklı akış verir.
    - start_idx start'ları birbirinden ayırır (çakışma yok).
    """
    return (seed_base ^ (run_seed * _SEED_MIX) ^ (start_idx * _SEED_STRIDE)) & _SEED_MASK


class SASolver:
    """DBLF decoder üzerinde Simulated Annealing.

    `budget` → simulated_annealing_3d'ye `iterations` olarak geçer.

    t0 / t_min: SA-özel hiper-parametreler, Solver protokolünün parçası DEĞİL;
    __init__ argümanı olarak açılır (default 3.0 / 0.05 → eski davranış). t0
    sayısal VEYA "auto" (sa3d adaptif kalibrasyon) olabilir. Protokol imzası
    (solve) değişmez → diğer çözücüler etkilenmez.
    """

    def __init__(self, t0: Union[float, str] = 3.0, t_min: float = 0.05) -> None:
        self.t0 = t0
        self.t_min = t_min

    def solve(
        self,
        parts: List[VoxelPart],
        bin_factory: Callable[[], Bin3D],
        *,
        budget: int = 200,
        seed: int = 42,
        order_key: Optional[Callable[[VoxelPart], tuple]] = None,
    ) -> SolveResult:
        t_start = time.perf_counter()
        res = simulated_annealing_3d(
            parts,
            bin_factory,
            seed=seed,
            iterations=budget,
            t0=self.t0,
            t_min=self.t_min,
            order_key=order_key,
        )
        elapsed = time.perf_counter() - t_start

        return SolveResult(
            placements=res.placements,
            bin3d=res.bin3d,
            height_mm=res.best_height_mm,
            density=res.best_density,
            time_s=elapsed,
            history=res.history,
            meta={
                "solver": "sa",
                "params": {
                    "seed": seed,
                    "iterations": budget,
                    "t0": self.t0,
                    "baseline_height_mm": res.baseline_height_mm,
                    "accepted": res.accepted,
                },
            },
        )


class MultiStartSA:
    """R4: N bağımsız SA start'ı deterministik seed'lerle, en iyiyi seç.

    Toplam `budget` start'lara eşit bölünür (kalan ilk start'lara birer birer
    dağıtılır → toplam tam budget). Her start'ın seed'i _derive_seed ile
    türetilir → "şanslı seed" değil "tipik" kalite: meta median/best/std taşır.

    Determinizm: aynı (seed_base, n_starts, budget, seed, order_key) → birebir
    aynı sonuç. Start'lar SIRALI koşar — Windows'ta ProcessPoolExecutor lambda
    bin_factory'yi pickle edemez; sıralı koşu determinizmi garantiler. Paralellik
    HPC fazında bin_factory picklable yapılınca eklenir (backlog).
    """

    def __init__(
        self,
        seed_base: int = 0,
        n_starts: int = 4,
        t0: Union[float, str] = 3.0,
        t_min: float = 0.05,
    ) -> None:
        if n_starts < 1:
            raise ValueError(f"n_starts >= 1 olmalı, {n_starts} geldi")
        self.seed_base = seed_base
        self.n_starts = n_starts
        self.t0 = t0
        self.t_min = t_min

    def solve(
        self,
        parts: List[VoxelPart],
        bin_factory: Callable[[], Bin3D],
        *,
        budget: int = 200,
        seed: int = 42,
        order_key: Optional[Callable[[VoxelPart], tuple]] = None,
    ) -> SolveResult:
        t_start = time.perf_counter()
        base, rem = divmod(budget, self.n_starts)
        sa = SASolver(t0=self.t0, t_min=self.t_min)

        results: List[SolveResult] = []
        for i in range(self.n_starts):
            iters = base + (1 if i < rem else 0)
            if iters <= 0:
                continue
            start_seed = _derive_seed(self.seed_base, seed, i)
            results.append(
                sa.solve(parts, bin_factory, budget=iters,
                         seed=start_seed, order_key=order_key)
            )

        heights = [r.height_mm for r in results]
        best = min(results, key=lambda r: r.height_mm)
        elapsed = time.perf_counter() - t_start

        return SolveResult(
            placements=best.placements,
            bin3d=best.bin3d,
            height_mm=best.height_mm,
            density=best.density,
            time_s=elapsed,
            history=best.history,
            meta={
                "solver": "multistart_sa",
                "params": {
                    "seed_base": self.seed_base,
                    "seed": seed,
                    "n_starts": self.n_starts,
                    "budget_total": budget,
                    "t0": self.t0,
                },
                "median_height_mm": statistics.median(heights),
                "best_height_mm": min(heights),
                "std_height_mm": statistics.pstdev(heights) if len(heights) > 1 else 0.0,
                "all_heights_mm": heights,
                "n_starts": len(results),
            },
        )
