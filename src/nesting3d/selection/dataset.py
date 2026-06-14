"""selection/dataset.py — Telemetri JSONL -> instance-basi egitim tablosu.

Her instance icin:
  - ozellik vektoru
  - her cozucunun en iyi yuksekligi
  - ETIKETLER:
      is_easy  : hic bir metaheuristik DBLF'yi epsilon'dan fazla gecmemis mi
                 (kolay = evet -> DBLF yeterli)
      winner   : en iyi cozucu adi
      dblf_height: DBLF'nin en iyi yuksekligi (None = DBLF bu grupta yok)
      best_height: tum cozucular icinde en dusuk yukseklik

Duplike satir politikasi: ayni (instance_id, cozucu) cifte karsilasinca
en dusuk height alinir (optimistik best-of-run).

is_easy tanimlamasi (Renau & Hart 2024):
  hic bir cozucu DBLF'den epsilon_mm'den fazla iyi degilse -> kolay.
  DBLF yoksa -> konservatif: is_easy=False.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# TrainingRow
# ---------------------------------------------------------------------------

@dataclass
class TrainingRow:
    """Tek bir instance icin egitim satiri."""

    instance_id: str
    is_easy: bool
    winner: str
    dblf_height: Optional[float]
    best_height: float
    feature_vector: List[float]
    feature_names: List[str]
    aile: str


# ---------------------------------------------------------------------------
# build_training_table
# ---------------------------------------------------------------------------

def build_training_table(
    rows: List[dict],
    *,
    epsilon_mm: float = 0.5,
) -> List[TrainingRow]:
    """Telemetri satirlarindan instance-basi egitim tablosu olustur.

    Args:
        rows:       load_telemetry() ciktisi (liste[dict]).
        epsilon_mm: "kolay" tanimi icin esik (mm). Hic bir cozucu
                    DBLF'yi bu kadardan fazla gecmemisse -> kolay.

    Returns:
        List[TrainingRow] — her eleman bir instance.
    """
    if not rows:
        return []

    # --- 1. instance_id bazinda grupla ------------------------------------
    # Her grup: {cozucu: [height_mm, ...]} sozlugu

    groups: Dict[str, dict] = {}  # instance_id -> grup_meta

    for row in rows:
        iid = row.get("instance_id", "")
        if not iid:
            continue

        if iid not in groups:
            groups[iid] = {
                "solver_heights": defaultdict(list),
                "feature_vector": row.get("feature_vector", []),
                "feature_names": row.get("feature_names", []),
                "aile": row.get("aile", ""),
            }

        cozucu = row.get("cozucu", "")
        height = row.get("height_mm")
        if cozucu and height is not None:
            groups[iid]["solver_heights"][cozucu].append(float(height))

    # --- 2. Her grup icin TrainingRow uret ---------------------------------
    result: List[TrainingRow] = []

    for iid, meta in groups.items():
        solver_heights = meta["solver_heights"]
        # Duplike: her cozucu icin en dusuk height al
        best_per_solver: Dict[str, float] = {
            s: min(hs) for s, hs in solver_heights.items()
        }

        if not best_per_solver:
            continue

        # DBLF baseline
        dblf_height: Optional[float] = best_per_solver.get("dblf")

        # Genel en iyi
        best_height = min(best_per_solver.values())

        # Kazanan cozucu (en dusuk height; esi varsa ilk alfabetik)
        winner = min(
            best_per_solver.keys(),
            key=lambda s: (best_per_solver[s], s),
        )

        # is_easy: DBLF yoksa konservatif False;
        # DBLF varsa: hicbir cozucu DBLF'den epsilon_mm'den fazla iyi degilse True
        if dblf_height is None:
            is_easy = False
        else:
            max_improvement = dblf_height - best_height  # pozitif = metaheuristik kazandi
            is_easy = max_improvement < epsilon_mm

        result.append(
            TrainingRow(
                instance_id=iid,
                is_easy=is_easy,
                winner=winner,
                dblf_height=dblf_height,
                best_height=best_height,
                feature_vector=list(meta["feature_vector"]),
                feature_names=list(meta["feature_names"]),
                aile=meta["aile"],
            )
        )

    return result
