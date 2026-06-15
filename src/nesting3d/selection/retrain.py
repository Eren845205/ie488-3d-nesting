"""selection/retrain.py -- Otomatik retrain orkestratoru (Faz O1.3 + O1.5).

Saf fonksiyon -- Flask/cron/kuyruk bilmez. PLAN_SERVIS scheduler'i
run_retrain'i periyodik veya batch-tetikli olarak cagirabilir.

DEGiSMEZ-A: motor modullerini (bin3d/sa3d/dblf/voxelize) import etmez.
DEGiSMEZ-D: promote yoksa artifact BYTE-AYNI kalir.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Union

from src.nesting3d.selection.gate import (
    GateDecision,
    MIN_GAIN_MM,
    evaluate_candidate,
)
from src.nesting3d.selection.dataset import build_training_table
from src.nesting3d.selection.persistence import save_selection_model
from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.telemetry import load_telemetry

import sys as _sys
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from scripts.build_selection_model import _split


# ---------------------------------------------------------------------------
# _next_archive_version
# ---------------------------------------------------------------------------

def _next_archive_version(archive_dir: Path) -> int:
    """Arsiv dizinindeki en yuksek versiyon numarasinin bir fazlasini dondur.

    Isimlendirme: selection_model.v<N>.json
    Yoksa 1 dondur.
    """
    max_n = 0
    if archive_dir.exists():
        pattern = re.compile(r"selection_model\.v(\d+)\.json$")
        for f in archive_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
    return max_n + 1


# ---------------------------------------------------------------------------
# run_retrain
# ---------------------------------------------------------------------------

def run_retrain(
    telemetry_path: Union[str, Path],
    artifact_path: Union[str, Path],
    *,
    archive_dir: Union[str, Path] = "data/selection_archive",
    gain_mm: float = MIN_GAIN_MM,
) -> GateDecision:
    """Telemetriden aday model egit, kapidan gecir, promote ise atomik swap yap.

    Adimlar
    -------
    1. evaluate_candidate ile karar al.
    2. promote=True ise:
       a. Mevcut artifact_path varsa arsivle (selection_model.vN.json).
       b. Aday modeli TMP'ye yaz, os.replace ile atomik swap.
    3. promote=False ise artifact_path BYTE-AYNI kalir.
    4. GateDecision dondur.

    Parameters
    ----------
    telemetry_path: JSONL telemetri dosyasi.
    artifact_path:  Yururlukteki artefakt (varsa) ve hedef yol.
    archive_dir:    Eski artefaktlarin arsivlendigi dizin.
    gain_mm:        Minimum kazanim esigi (mm).

    Returns
    -------
    GateDecision -- JSON-serializasyona uygun.
    """
    telemetry_path = Path(telemetry_path)
    artifact_path = Path(artifact_path)
    archive_dir = Path(archive_dir)

    # --- 0. Telemetri SNAPSHOT (TOCTOU kapatma) ---
    # C4 fix: kapinin gordugu veri ile diske yazilan modelin egitildigi veri
    # AYNI olmali. Telemetriyi BIR KEZ oku ve degismez bir snapshot dosyasina
    # yaz; hem evaluate_candidate hem de yazilan model bu snapshot'tan beslenir.
    # Iki ayri load_telemetry arasinda telemetri dosyasi degisirse (TOCTOU)
    # artefakt kapinin gormedigi veriyle egitilebilirdi -- snapshot bunu onler.
    rows = load_telemetry(telemetry_path)
    snapshot_path = Path(str(artifact_path) + ".telemetry.snapshot.jsonl")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with snapshot_path.open("w", encoding="utf-8") as _fh:
        for _r in rows:
            _fh.write(json.dumps(_r, ensure_ascii=False) + "\n")

    try:
        # --- 1. Karar al (snapshot uzerinden) ---
        decision = evaluate_candidate(snapshot_path, artifact_path, gain_mm=gain_mm)

        if not decision.promote:
            return decision

        # --- 2. Aday modeli egit (snapshot ile AYNI rows; kapi ile ozdes girdi) ---
        # evaluate_candidate ile bire bir ayni egitim girdisi: ayni rows ->
        # ayni build_training_table -> ayni _split -> ayni (deterministik)
        # prefilter/selector. Boylece diske yazilan NESNE = kapinin onayladigi.
        table = build_training_table(rows)
        train_table, _ = _split(table)

        pf = EasyInstancePrefilter()
        pf.fit(train_table)
        sel = AlgorithmSelector()
        sel.fit(train_table)

        # --- 3. Mevcut artifact arsivle (promote kesinlestikten sonra) ---
        if artifact_path.exists():
            archive_dir.mkdir(parents=True, exist_ok=True)
            version = _next_archive_version(archive_dir)
            archive_path = archive_dir / f"selection_model.v{version}.json"
            # Shutil kullanmadan okuma-yazma ile kopyala (pure stdlib)
            archive_path.write_bytes(artifact_path.read_bytes())

        # --- 4. Atomik yazma: once TMP, sonra os.replace ---
        tmp_path = Path(str(artifact_path) + ".tmp")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        save_selection_model(pf, sel, tmp_path)
        os.replace(str(tmp_path), str(artifact_path))

        return decision
    finally:
        # Snapshot gecicidir; promote olsun olmasin temizle.
        try:
            snapshot_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# should_retrain
# ---------------------------------------------------------------------------

def should_retrain(
    telemetry_path: Union[str, Path],
    last_trained_count: int,
    *,
    batch_size: int = 20,
) -> bool:
    """Mevcut telemetri sayisi >= last_trained_count + batch_size ise True.

    Batch-tetikli strateji: belli miktar yeni veri birikince retrain tetiklenir.
    Per-instance retrain DEGiL.

    Parameters
    ----------
    telemetry_path:     JSONL telemetri dosyasi.
    last_trained_count: Son retrain anindaki instance sayisi.
    batch_size:         Tetik icin gereken yeni instance adedi (varsayilan 20).

    Returns
    -------
    bool -- True = retrain tetiklenmeli.
    """
    telemetry_path = Path(telemetry_path)
    rows = load_telemetry(telemetry_path)
    if not rows:
        return False
    table = build_training_table(rows)
    current_count = len(table)
    return current_count >= last_trained_count + batch_size
