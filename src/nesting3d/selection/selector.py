"""selection/selector.py — Algoritma-secim orkestratoru.

select_and_solve(instance, parts, bin_factory, *, budget, seed,
                 prefilter=None, model=None) -> SelectionResult

Akis:
  1. extract_features(instance) -> ozellik vektoru
  2. DBLF her zaman kosulur (monoton garanti temeli).
  3. prefilter varsa:
     - KOLAY (is_easy=True, guven yeterli) -> sadece DBLF, metaheuristik ATLA.
  4. Kolay degilse:
     - model varsa ve yeterli guven -> secili cozucuyu kosu, DBLF ile karsilastir.
     - model yoksa veya dusuk guven -> tam portfoy fallback.
  5. Sonuc asla DBLF'den kotu olamaz (monoton garanti).

Guvenlik degismezleri:
  MONOTON  : selector sonucu height_mm <= dblf_baseline (asla daha kotu).
             Yanlis-kolay tahmini sadece bir iyilestirmeyi kacirabilir;
             kalite riski sinirli — yanlis/kotu SONUÇ URETMEZ.
  GUVENSIZ : model dusuk guven veya None -> tam portfoy (guvenli).
  YORUML.  : reason alani okunabilir aciklama tasir.
  DETERMIN.: ayni giris+seed -> ayni SelectionResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from src.nesting3d.instances.features import extract_features
from src.nesting3d.instances.format import NestingInstance
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.solvers.base import SolveResult
from src.nesting3d.solvers.dblf_solver import DBLFSolver
from src.nesting3d.voxelize import VoxelPart


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

CONFIDENCE_THRESHOLD: float = 0.6   # bu altinda model guvenilmez -> portfoy
EASY_CONFIDENCE_THRESHOLD: float = 0.7  # kolay diyebilmek icin min guven


# ---------------------------------------------------------------------------
# SolvePath — hangi yol kullanildi
# ---------------------------------------------------------------------------

class SolvePath(Enum):
    """Hangi karar yolu izlendi."""
    EASY_DBLF = "easy_dblf"                         # kolay: sadece DBLF
    SELECTED = "selected"                            # model secti, kostu
    FULL_PORTFOLIO_FALLBACK = "full_portfolio_fallback"  # tam portfoy


# ---------------------------------------------------------------------------
# SelectionResult
# ---------------------------------------------------------------------------

@dataclass
class SelectionResult:
    """Orkestrasyon sonucu."""

    solve_result: SolveResult    # en iyi bulunan sonuc
    path: SolvePath              # hangi karar yolu
    reason: str                  # okunabilir aciklama
    dblf_baseline: float         # DBLF yuksekligi (mm) — monoton referansi


# ---------------------------------------------------------------------------
# Yardimci: portfoy listesi
# ---------------------------------------------------------------------------

def _build_full_portfolio() -> list:
    """Varsayilan tam portfoy cozuculer (lazy import, circular borclanma onler)."""
    from src.nesting3d.solvers.sa_solver import SASolver
    from src.nesting3d.solvers.ga_solver import GASolver
    from src.nesting3d.solvers.tabu_solver import TabuSolver
    return [DBLFSolver(), SASolver(), GASolver(), TabuSolver()]


def _solver_by_name(name: str) -> object:
    """Cozucu adina gore ornek dondur (portfoy secim yolu icin)."""
    from src.nesting3d.solvers.sa_solver import SASolver
    from src.nesting3d.solvers.ga_solver import GASolver
    from src.nesting3d.solvers.tabu_solver import TabuSolver

    mapping = {
        "dblf": DBLFSolver,
        "sa3d": SASolver,
        "sa": SASolver,
        "ga": GASolver,
        "tabu": TabuSolver,
    }
    cls = mapping.get(name.lower())
    if cls is None:
        return DBLFSolver()
    return cls()


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def select_and_solve(
    instance: NestingInstance,
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    *,
    budget: int,
    seed: int,
    prefilter: Optional[object] = None,
    model: Optional[object] = None,
) -> SelectionResult:
    """Algoritma sec ve coz.

    Args:
        instance:    NestingInstance (ozellik vektoru icin).
        parts:       VoxelPart listesi (cozuculere verilir).
        bin_factory: () -> Bin3D (taze bin uretir).
        budget:      Iterasyon butcesi.
        seed:        Raslantisallik tohumu (determinizm).
        prefilter:   EasyInstancePrefilter ornegi ya da None.
        model:       AlgorithmSelector ornegi ya da None.

    Returns:
        SelectionResult — solve_result, path, reason, dblf_baseline.

    Guvenlik: sonuc height_mm <= dblf_baseline her zaman saglanir.
    """
    # --- 1. Ozellik vektoru -----------------------------------------------
    fv = extract_features(instance)
    features = fv.values

    # --- 2. DBLF her zaman kosulur (monoton garanti temeli) ---------------
    dblf_solver = DBLFSolver()
    dblf_result = dblf_solver.solve(
        parts, bin_factory, budget=0, seed=seed
    )
    dblf_baseline = dblf_result.height_mm

    # --- 3. Prefilter: KOLAY mi? ------------------------------------------
    if prefilter is not None:
        is_easy, easy_conf = prefilter.predict(features)
        if is_easy and easy_conf >= EASY_CONFIDENCE_THRESHOLD:
            return SelectionResult(
                solve_result=dblf_result,
                path=SolvePath.EASY_DBLF,
                reason=(
                    f"Kolay instance (prefilter guven={easy_conf:.2%}); "
                    f"sadece DBLF kosuldu. "
                    f"{prefilter.explain()}"
                ),
                dblf_baseline=dblf_baseline,
            )

    # --- 4a. Model yoksa veya dusuk guven -> tam portfoy ------------------
    if model is None:
        return _run_full_portfolio(
            parts, bin_factory, budget=budget, seed=seed,
            dblf_baseline=dblf_baseline, dblf_result=dblf_result,
            reason="Model saglanmadi; tam portfoy fallback.",
        )

    selected_name, model_conf = model.predict(features)

    if model_conf < CONFIDENCE_THRESHOLD:
        return _run_full_portfolio(
            parts, bin_factory, budget=budget, seed=seed,
            dblf_baseline=dblf_baseline, dblf_result=dblf_result,
            reason=(
                f"Model guven dusuk ({model_conf:.2%} < "
                f"{CONFIDENCE_THRESHOLD:.0%}); tam portfoy fallback."
            ),
        )

    # --- 4b. Secimlicozucu kosu ------------------------------------------
    if selected_name.lower() == "dblf":
        # DBLF zaten kostu
        best_result = dblf_result
        reason = (
            f"Model secti: dblf (guven={model_conf:.2%}). "
            f"DBLF zaten baseline olarak kostu."
        )
        return SelectionResult(
            solve_result=best_result,
            path=SolvePath.SELECTED,
            reason=reason,
            dblf_baseline=dblf_baseline,
        )

    selected_solver = _solver_by_name(selected_name)
    sel_result = selected_solver.solve(
        parts, bin_factory, budget=budget, seed=seed
    )

    # --- 5. MONOTON garanti: asla DBLF'den kotu olma ---------------------
    if sel_result.height_mm <= dblf_baseline:
        best_result = sel_result
        reason = (
            f"Model secti: {selected_name} (guven={model_conf:.2%}). "
            f"Sonuc: {sel_result.height_mm:.2f} mm "
            f"(DBLF baseline: {dblf_baseline:.2f} mm)."
        )
    else:
        # Secili cozucu DBLF'den kotu -> DBLF kullan (monoton garanti)
        best_result = dblf_result
        reason = (
            f"Model secti: {selected_name} (guven={model_conf:.2%}), "
            f"ancak sonuc ({sel_result.height_mm:.2f} mm) DBLF "
            f"({dblf_baseline:.2f} mm) kadar iyi degil. "
            f"DBLF korundu (monoton garanti)."
        )

    return SelectionResult(
        solve_result=best_result,
        path=SolvePath.SELECTED,
        reason=reason,
        dblf_baseline=dblf_baseline,
    )


# ---------------------------------------------------------------------------
# Yardimci: tam portfoy
# ---------------------------------------------------------------------------

def _run_full_portfolio(
    parts: List[VoxelPart],
    bin_factory: Callable[[], Bin3D],
    *,
    budget: int,
    seed: int,
    dblf_baseline: float,
    dblf_result: SolveResult,
    reason: str,
) -> SelectionResult:
    """Tam portfoyu kosu; en iyi sonucu dondur (asla DBLF'den kotu degil)."""
    solvers = _build_full_portfolio()
    results: List[SolveResult] = []

    for solver in solvers:
        try:
            r = solver.solve(parts, bin_factory, budget=budget, seed=seed)
            results.append(r)
        except Exception:
            pass  # hata olan cozucu atlanir; portfoy devam eder

    if not results:
        # Hic sonuc yoksa DBLF'ye geri don (monoton garanti)
        return SelectionResult(
            solve_result=dblf_result,
            path=SolvePath.FULL_PORTFOLIO_FALLBACK,
            reason=reason + " (portfoy bos; DBLF fallback).",
            dblf_baseline=dblf_baseline,
        )

    best = min(results, key=lambda r: (r.height_mm, r.meta.get("solver", "")))

    # Monoton garanti: asla DBLF'den kotu olma
    if best.height_mm > dblf_baseline:
        best = dblf_result

    return SelectionResult(
        solve_result=best,
        path=SolvePath.FULL_PORTFOLIO_FALLBACK,
        reason=reason,
        dblf_baseline=dblf_baseline,
    )
