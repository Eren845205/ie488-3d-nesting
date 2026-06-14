"""src.nesting3d.selection — Algoritma-secim katmani (APP_YOL_HARITASI §6.3.1).

Public surface:
  dataset   — build_training_table(), TrainingRow
  prefilter — EasyInstancePrefilter (Renau & Hart 2024 kolay-instance on-filtresi)
  model     — AlgorithmSelector (1-NN prototip, yorumlanabilir)
  selector  — select_and_solve(), SelectionResult, SolvePath (orkestrator)
"""

from src.nesting3d.selection.dataset import TrainingRow, build_training_table
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.selector import (
    SelectionResult,
    SolvePath,
    select_and_solve,
)

__all__ = [
    "TrainingRow",
    "build_training_table",
    "EasyInstancePrefilter",
    "AlgorithmSelector",
    "SelectionResult",
    "SolvePath",
    "select_and_solve",
]
