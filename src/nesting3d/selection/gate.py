"""selection/gate.py -- Aday-vs-yururluk monoton guvenlik kapisi (Faz O1.1 + O1.2).

Overfit korumasi: yeni egitilmis artefakt SADECE hold-out'ta yururluktekini
MIN_GAIN_MM kadar gecerse varsayilan olur. Gecmezse eski artefakt KALIR +
karar append-only JSONL'e loglanir.

DEGiSMEZ-A: motor modullerini (bin3d/sa3d/dblf/voxelize) import etmez.
DEGiSMEZ-D: sistem ogrenirken asla kotulesemez.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

from src.nesting3d.selection.dataset import build_training_table
from src.nesting3d.selection.gengap import compute_generalization_gap
from src.nesting3d.selection.persistence import load_selection_model, save_selection_model
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.telemetry import load_telemetry

# build_selection_model.py'den import et (veya aynen al -- modul PATH icin aynen al)
# Plan: import et. Bu scriptin proje kok altindaki 'scripts/' icinde oldugu
# varsayilarak sys.path ekliyoruz.
import sys as _sys
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.build_selection_model import (
    _evaluate,
    _split,
    MIN_INSTANCES_FOR_HOLDOUT,
)

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

MIN_GAIN_MM: float = 0.1
"""Aday yururluktekini en az bu kadar mm gecmeli (gurultu payi)."""

_DEFAULT_LOG_PATH = _ROOT / "data" / "telemetry" / "gate_log.jsonl"


# ---------------------------------------------------------------------------
# GateDecision dataclass
# ---------------------------------------------------------------------------

@dataclass
class GateDecision:
    """Kapinin verdigi karar."""

    promote: bool
    """True -> aday yururluge gecmeli."""

    reason: str
    """Karar gerekce metni."""

    cand_holdout: float
    """Adayin hold-out selector_mean skoru (mm; dusuk = iyi)."""

    cur_holdout: float
    """Yururlukteki modelin hold-out selector_mean skoru (mm; inf = yok)."""

    delta: float
    """cur_holdout - cand_holdout; pozitif = aday daha iyi."""

    n_instances: int
    """Toplam instance sayisi."""

    n_holdout: int
    """Hold-out set buyuklugu."""

    overfit_flag: bool = False
    """gengap genelleme-acigi tespiti True ise aday overfit -> promote BLOKLU.
    DEGiSMEZ-D enforcement: sistem ogrenirken kotulesemez."""

    def to_dict(self) -> dict:
        """JSON-serializasyona uygun sozluk. inf/nan degerler null'a donusur."""
        def _safe(val: float):
            # inf-inf=nan senaryosu: delta = cur_holdout(inf) - cand_holdout(inf)
            # NaN'i json.dumps allow_nan=False altinda patlatmamak icin None'a cevir.
            if isinstance(val, float) and (math.isinf(val) or math.isnan(val)):
                return None
            return val

        return {
            "promote": self.promote,
            "reason": self.reason,
            "cand_holdout": _safe(self.cand_holdout),
            "cur_holdout": _safe(self.cur_holdout),
            "delta": _safe(self.delta),
            "n_instances": self.n_instances,
            "n_holdout": self.n_holdout,
            "overfit_flag": self.overfit_flag,
        }


# ---------------------------------------------------------------------------
# _log_decision
# ---------------------------------------------------------------------------

def _log_decision(
    decision: GateDecision,
    log_path: Union[str, Path, None] = None,
) -> None:
    """Kapinin kararini append-only JSONL'e yaz.

    Reddedilen adaylar silinmez, loglanir -- kotu lesememe kaniti.
    inf degerler JSON icin null'a cevirilir.
    """
    if log_path is None:
        log_path = _DEFAULT_LOG_PATH
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "ts": datetime.now().isoformat(),
        **decision.to_dict(),
    }

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# evaluate_candidate
# ---------------------------------------------------------------------------

def evaluate_candidate(
    telemetry_path: Union[str, Path],
    current_artifact_path: Union[str, Path],
    *,
    gain_mm: float = MIN_GAIN_MM,
    log_path: Union[str, Path, None] = None,
) -> GateDecision:
    """Telemetriden aday model egit, yururlukteki ile karsilastir.

    Adimlar
    -------
    1. Telemetri yukle -> build_training_table -> tablo.
    2. Veri yetersizligi freni: n_instances < MIN_INSTANCES_FOR_HOLDOUT
       -> promote=False, "veri yetersiz" reason.
    3. _split ile train/holdout ayir. Aday modeli egit. Aday hold-out skoru hesapla.
    4. Yururluk artefakti varsa yukle ve AYNI hold-out'ta degerlendir.
       Yoksa cur_holdout=+inf, promote=True (ilk model).
    5. promote = (cand_holdout <= cur_holdout - gain_mm).
    6. Karari logla, GateDecision dondur.

    Parameters
    ----------
    telemetry_path:        JSONL telemetri dosyasi.
    current_artifact_path: Mevcut yururlukteki artefakt JSON yolu.
                           Yoksa ilk model senaryosu.
    gain_mm:               Minimum kazanim esigi (mm). Varsayilan MIN_GAIN_MM.
    log_path:              Log JSONL dosya yolu. None -> varsayilan.

    Returns
    -------
    GateDecision
    """
    telemetry_path = Path(telemetry_path)
    current_artifact_path = Path(current_artifact_path)

    # --- 1. Telemetri yukle ---
    rows = load_telemetry(telemetry_path)
    table = build_training_table(rows)
    n_instances = len(table)

    # --- 2. Veri yetersizligi freni (DEGiSMEZ-D + O1.4) ---
    if n_instances < MIN_INSTANCES_FOR_HOLDOUT:
        decision = GateDecision(
            promote=False,
            reason=(
                f"veri yetersiz (n={n_instances} < {MIN_INSTANCES_FOR_HOLDOUT}), "
                f"kapi anlamsiz, yururluk korundu"
            ),
            cand_holdout=math.inf,
            cur_holdout=math.inf,
            delta=0.0,
            n_instances=n_instances,
            n_holdout=0,
        )
        _log_decision(decision, log_path)
        return decision

    # --- 3. Train/holdout bol, aday model egit ---
    train_table, holdout_table = _split(table)
    holdout_ids = {r.instance_id for r in holdout_table}

    cand_prefilter = EasyInstancePrefilter()
    cand_prefilter.fit(train_table)
    cand_model = AlgorithmSelector()
    cand_model.fit(train_table)

    cand_eval = _evaluate(table, cand_prefilter, cand_model, holdout_ids=holdout_ids)
    cand_holdout = cand_eval.get("selector_mean", math.inf)
    n_holdout = cand_eval.get("n_holdout", 0)

    # --- 4. Yururluk artefakti degerlendirme ---
    is_first_model = not current_artifact_path.exists()
    cur_holdout: float
    first_model_note = ""

    if is_first_model:
        cur_holdout = math.inf
        first_model_note = "ilk model, yururluk yok"
    else:
        cur_prefilter, cur_model = load_selection_model(current_artifact_path)
        cur_eval = _evaluate(table, cur_prefilter, cur_model, holdout_ids=holdout_ids)
        cur_holdout = cur_eval.get("selector_mean", math.inf)

    # --- 5. Promote karari (hold-out monoton kapisi) ---
    delta = cur_holdout - cand_holdout  # pozitif = aday daha iyi

    if is_first_model:
        promote = True
        reason = f"ilk model, yururluk yok; cand_holdout={cand_holdout:.4f} mm"
    elif delta >= gain_mm:
        promote = True
        reason = (
            f"aday daha iyi: delta={delta:.4f} mm >= gain_mm={gain_mm:.4f} mm; "
            f"cand={cand_holdout:.4f} mm, cur={cur_holdout:.4f} mm"
        )
    else:
        promote = False
        reason = (
            f"aday yeterince iyi degil: delta={delta:.4f} mm < gain_mm={gain_mm:.4f} mm; "
            f"cand={cand_holdout:.4f} mm, cur={cur_holdout:.4f} mm; yururluk korundu"
        )

    # --- 5b. Genelleme-acigi (overfit) kapisi (DEGiSMEZ-D enforcement) ---
    # gengap, adayin egitildigi AYNI tablo uzerinde train_acc vs holdout_acc
    # (+ prequential) acigini olcer. overfit_flag=True ise aday ezber yapmis
    # demektir; hold-out skoru iyi gorunse bile promote'u BLOKLA. Boylece
    # "sistem ogrenirken kotulesemez" sadece hold-out delta'siyla degil,
    # overfit tespitiyle de ENFORCE edilir.
    # NOT: gengap motor modullerini (bin3d/sa3d/dblf/voxelize) IMPORT ETMEZ
    # -> DEGiSMEZ-A korunur (gate -> gengap -> sadece selection meta-layer).
    gengap_report = compute_generalization_gap(table)
    overfit_flag = gengap_report.overfit_flag

    if promote and overfit_flag:
        promote = False
        reason = (
            f"OVERFIT BLOKU: hold-out kapisi gecti AMA genelleme-acigi tespit "
            f"edildi -> {gengap_report.reason}. Yururluk korundu (DEGiSMEZ-D). "
            f"[onceki karar: {reason}]"
        )

    decision = GateDecision(
        promote=promote,
        reason=reason,
        cand_holdout=cand_holdout,
        cur_holdout=cur_holdout,
        delta=delta,
        n_instances=n_instances,
        n_holdout=n_holdout,
        overfit_flag=overfit_flag,
    )

    # --- 6. Logla ---
    _log_decision(decision, log_path)
    return decision
