"""src.nesting3d.selection — Algoritma-secim katmani (APP_YOL_HARITASI §6.3.1).

Public surface:
  dataset     — build_training_table(), TrainingRow
  prefilter   — EasyInstancePrefilter (Renau & Hart 2024 kolay-instance on-filtresi)
  model       — AlgorithmSelector (1-NN prototip, yorumlanabilir)
  selector    — select_and_solve(), SelectionResult, SolvePath (orkestrator)
  persistence — save_selection_model(), load_selection_model()
"""

from src.nesting3d.selection.dataset import TrainingRow, build_training_table
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.selector import (
    SelectionResult,
    SolvePath,
    select_and_solve,
)
from src.nesting3d.selection.persistence import (
    save_selection_model,
    load_selection_model,
)
from src.nesting3d.selection.advisor import (
    RetrainSuggestion,
    build_retrain_suggestion,
)

__all__ = [
    "TrainingRow",
    "build_training_table",
    "EasyInstancePrefilter",
    "AlgorithmSelector",
    "SelectionResult",
    "SolvePath",
    "select_and_solve",
    "save_selection_model",
    "load_selection_model",
    "RetrainSuggestion",
    "build_retrain_suggestion",
]
