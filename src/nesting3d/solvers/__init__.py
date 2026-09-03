"""src.nesting3d.solvers — pluggable solver portfolio (PLAN_DEMO1 Faz 1).

Public surface:
  base        — Solver protocol, SolveResult dataclass, decode(), GENOTYPE_CONTRACT
  dblf_solver — DBLFSolver (wraps dblf.dblf)
  sa_solver   — SASolver   (wraps sa3d.simulated_annealing_3d)
  portfolio   — run_portfolio(), PortfolioResult

Import note: sa3d.py imports decode from solvers.base; to avoid a circular
import at package initialisation time this __init__ does NOT eagerly import
SASolver or portfolio.  Consumers should import from the submodules directly:

    from src.nesting3d.solvers.base import Solver, SolveResult, decode
    from src.nesting3d.solvers.dblf_solver import DBLFSolver
    from src.nesting3d.solvers.sa_solver import SASolver
    from src.nesting3d.solvers.portfolio import run_portfolio, PortfolioResult
"""

# Only base is safe to import eagerly (no sa3d dependency).
from src.nesting3d.solvers.base import GENOTYPE_CONTRACT, Solver, SolveResult, decode

__all__ = [
    "GENOTYPE_CONTRACT",
    "Solver",
    "SolveResult",
    "decode",
]
