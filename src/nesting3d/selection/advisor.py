"""selection/advisor.py -- Retrain ONERI motoru (read-only; ASLA egitmez).

Politika karari (2026-06-17, kullanici): Algoritma-secim modelinin "kendi kendini
gelistirme" dongusu OTOMATIK calismaz. Sistem kendini sessizce yanlis egitip
(overfit) bozarsa sorumluluk uygulamada kalir -- bu kabul edilemez. Bu yuzden:

  - Gercek egitim (run_retrain / artefakt yazma) YALNIZ kullanicinin acik
    komutuyla olur (`python -m scripts.retrain_selection`).
  - Bu modul SADECE ONERI uretir: "su kadar veri toplandi, retrain edersen kapi
    soyle karar verir, overfit riski su, su cozucular eksik -> su yonde instance
    uret". Hicbir dosya YAZMAZ, hicbir model EGITMEZ (read-only).
  - Karar her zaman kullanicinin.

DEGiSMEZ-A: motor modullerini (bin3d/sa3d/dblf/voxelize) import etmez.
Determinizm: ayni girdi -> ayni oneri.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from src.nesting3d.selection.dataset import build_training_table
from src.nesting3d.selection.gate import evaluate_candidate, MIN_GAIN_MM
from src.nesting3d.selection.gengap import compute_generalization_gap
from src.nesting3d.selection.persistence import load_selection_model
from src.nesting3d.telemetry import load_telemetry


# Portfoydeki tum cozucu adlari (string sabit -- motor import etmeden).
# Telemetride hic kazanmamis olanlar "eksik" sayilir (model onlari secemez).
POOL_SOLVERS: List[str] = ["dblf", "sa3d", "ga", "tabu", "multistart", "alns"]

# Bu kadar yeni instance birikince "retrain dusunulebilir" onerisi gosterilir.
# OTOMATIK TETIK DEGIL -- yalniz kullaniciya gosterilen bir esik.
SUGGEST_NEW_DATA_THRESHOLD: int = 20


@dataclass
class RetrainSuggestion:
    """Read-only retrain onerisi. Hicbir yan etki tasimaz."""

    n_total: int                       # telemetrideki toplam instance
    n_trained: int                     # yururlukteki artefaktin egitildigi instance sayisi
    n_new: int                         # son egitimden beri biriken yeni instance
    enough_new_data: bool              # n_new >= SUGGEST_NEW_DATA_THRESHOLD
    gate_would_promote: bool           # retrain edilseydi kapi promote eder miydi
    overfit_flag: bool                 # gengap overfit tespiti (retrain ENGELLENIRDI)
    cv_gap: float                      # LOO-CV vs hold-out acigi (overfit metrigi)
    delta_mm: float                    # aday - yururluk hold-out kazanci (pozitif=iyi)
    missing_solvers: List[str]         # telemetride hic kazanmamis cozucular
    headline: str                      # tek satir ozet
    recommendations: List[str] = field(default_factory=list)  # madde madde tavsiye

    def to_dict(self) -> dict:
        return {
            "n_total": self.n_total,
            "n_trained": self.n_trained,
            "n_new": self.n_new,
            "enough_new_data": self.enough_new_data,
            "gate_would_promote": self.gate_would_promote,
            "overfit_flag": self.overfit_flag,
            "cv_gap": self.cv_gap,
            "delta_mm": self.delta_mm,
            "missing_solvers": list(self.missing_solvers),
            "headline": self.headline,
            "recommendations": list(self.recommendations),
        }


def build_retrain_suggestion(
    telemetry_path: Union[str, Path],
    artifact_path: Union[str, Path],
    *,
    gain_mm: float = MIN_GAIN_MM,
) -> RetrainSuggestion:
    """Telemetri + yururlukteki artefakti analiz edip read-only ONERI uret.

    HICBIR yan etki: model egitmez, artefakt/log YAZMAZ. Kapi simulasyonu icin
    evaluate_candidate gecici (atilan) bir log dosyasiyla cagrilir -- gercek
    karar gunlugu (gate_log.jsonl) KIRLETILMEZ.

    Args:
        telemetry_path: JSONL telemetri dosyasi.
        artifact_path:  Yururlukteki artefakt (varsa). Yoksa "ilk model" senaryosu.
        gain_mm:        Kapi kazanc esigi (sadece simulasyon icin).

    Returns:
        RetrainSuggestion -- kullaniciya gosterilecek tavsiye.
    """
    telemetry_path = Path(telemetry_path)
    artifact_path = Path(artifact_path)

    rows = load_telemetry(telemetry_path)
    table = build_training_table(rows)
    n_total = len(table)

    # Yururlukteki artefaktin egitildigi instance sayisi (varsa)
    n_trained = 0
    if artifact_path.exists():
        try:
            _pf, cur_model = load_selection_model(artifact_path)
            n_trained = getattr(cur_model, "n_train", 0)
        except Exception:
            n_trained = 0
    n_new = max(0, n_total - n_trained)
    enough_new_data = n_new >= SUGGEST_NEW_DATA_THRESHOLD

    # Kazanan dagilimi -> eksik cozucular
    winners = {r.winner for r in table}
    missing_solvers = [s for s in POOL_SOLVERS if s not in winners]

    # Kapi simulasyonu (read-only: gecici log -> sil)
    tmp_log = Path(tempfile.mkdtemp()) / "advisor_gate_probe.jsonl"
    try:
        decision = evaluate_candidate(
            telemetry_path, artifact_path, gain_mm=gain_mm, log_path=tmp_log
        )
    finally:
        try:
            tmp_log.unlink()
            tmp_log.parent.rmdir()
        except OSError:
            pass

    gengap = compute_generalization_gap(table)

    # --- Tavsiye metni ---
    recs: List[str] = []

    if n_total < 10:
        headline = (
            f"Veri AZ ({n_total} instance). Once daha fazla benchmark/instance "
            f"toplanmali; retrain anlamli degil."
        )
        recs.append(
            "Cesitli ailelerden instance uret: "
            "`python scripts/generate_hard_instances.py`"
        )
    elif gengap.overfit_flag:
        headline = (
            f"DIKKAT: overfit sinyali (cv_gap={gengap.cv_gap:.2f}). Retrain edilse "
            f"kapi PROMOTE'u BLOKLAR. Once veri cesitliligi artirilmali."
        )
        recs.append(
            "Tek aileye/dar veriye asiri uyum var; farkli ailelerden "
            "(thin_plates, long_rods, few_large_many_small, ...) daha cok instance ekle."
        )
    elif decision.promote:
        headline = (
            f"ONERILIR: retrain edersen model GELISIR "
            f"(hold-out kazanci delta={decision.delta:.2f} mm, overfit yok)."
        )
        recs.append(
            "Onayliyorsan egit: `python -m scripts.retrain_selection` "
            "(once `--dry-run` ile karari gor)."
        )
    elif enough_new_data:
        headline = (
            f"{n_new} yeni instance birikti ama retrain hold-out'u iyilestirmiyor "
            f"(delta={decision.delta:.2f} mm < {gain_mm:.2f}). Su an gerek yok."
        )
    else:
        headline = (
            f"Su an retrain gereksiz: {n_new} yeni instance "
            f"(esik {SUGGEST_NEW_DATA_THRESHOLD}), kazanc delta={decision.delta:.2f} mm."
        )

    if missing_solvers:
        recs.append(
            f"Su cozucular telemetride HIC kazanmamis: {', '.join(missing_solvers)} "
            f"-> model onlari secemez. Bu cozuculerin parladigi zorlu instance'lar "
            f"uretmek model cesitligini artirir "
            f"(`scripts/generate_hard_instances.py`)."
        )

    recs.append(
        "Karar SENIN: sistem otomatik egitmez. Hazir oldugunda manuel komutla egit."
    )

    return RetrainSuggestion(
        n_total=n_total,
        n_trained=n_trained,
        n_new=n_new,
        enough_new_data=enough_new_data,
        gate_would_promote=decision.promote,
        overfit_flag=gengap.overfit_flag,
        cv_gap=gengap.cv_gap,
        delta_mm=decision.delta,
        missing_solvers=missing_solvers,
        headline=headline,
        recommendations=recs,
    )
