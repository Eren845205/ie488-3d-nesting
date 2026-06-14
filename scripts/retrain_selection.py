"""scripts/retrain_selection.py -- Otomatik retrain CLI (Faz O1.3).

Kullanim:
    python -m scripts.retrain_selection
    python -m scripts.retrain_selection --jsonl data/telemetry/runs.jsonl
    python -m scripts.retrain_selection --artifact data/selection_model.json
    python -m scripts.retrain_selection --gain-mm 0.5

Cikti:
  - Karar: promote evet/hayir
  - Aday hold-out vs yururluk hold-out (mm)
  - Reason (gerekce)
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

# Proje kokunu sys.path'e ekle (dogrudan betik olarak calistirilinca)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.selection.retrain import run_retrain
from src.nesting3d.selection.gate import MIN_GAIN_MM

# Varsayilan yollar
_DEFAULT_JSONL = _ROOT / "data" / "telemetry" / "runs.jsonl"
_DEFAULT_ARTIFACT = _ROOT / "data" / "selection_model.json"
_DEFAULT_ARCHIVE = _ROOT / "data" / "selection_archive"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telemetriden aday model egit, guvenlik kapisindan gecir, "
                    "promote ise yururluk artefaktini atomik degistir.",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        default=_DEFAULT_JSONL,
        help=f"Telemetri JSONL dosyasi (varsayilan: {_DEFAULT_JSONL})",
    )
    parser.add_argument(
        "--artifact",
        type=Path,
        default=_DEFAULT_ARTIFACT,
        help=f"Yururluk artefakt yolu (varsayilan: {_DEFAULT_ARTIFACT})",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=_DEFAULT_ARCHIVE,
        help=f"Arsiv dizini (varsayilan: {_DEFAULT_ARCHIVE})",
    )
    parser.add_argument(
        "--gain-mm",
        type=float,
        default=MIN_GAIN_MM,
        help=f"Minimum kazanim esigi mm (varsayilan: {MIN_GAIN_MM})",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("retrain_selection.py -- Algoritma Secim Modeli Otomatik Retrain")
    print("=" * 70)
    print(f"  Telemetri : {args.jsonl}")
    print(f"  Artefakt  : {args.artifact}")
    print(f"  Arsiv     : {args.archive_dir}")
    print(f"  Gain esigi: {args.gain_mm} mm")
    print()

    decision = run_retrain(
        args.jsonl,
        args.artifact,
        archive_dir=str(args.archive_dir),
        gain_mm=args.gain_mm,
    )

    promote_str = "EVET -- yururluk guncellendi" if decision.promote else "HAYIR -- yururluk korundu"
    print(f"Karar        : {promote_str}")
    print(f"Gerekce      : {decision.reason}")
    print(f"n_instances  : {decision.n_instances}")
    print(f"n_holdout    : {decision.n_holdout}")

    def _fmt(val: float) -> str:
        if math.isinf(val):
            return "inf (yururluk yok)"
        return f"{val:.4f} mm"

    print(f"Aday holdout : {_fmt(decision.cand_holdout)}")
    print(f"Cur holdout  : {_fmt(decision.cur_holdout)}")
    delta = decision.delta
    if math.isinf(delta):
        delta_str = "inf"
    else:
        delta_str = f"{delta:+.4f} mm"
    print(f"Delta (cur-cand): {delta_str}  (pozitif = aday daha iyi)")
    print("=" * 70)


if __name__ == "__main__":
    main()
