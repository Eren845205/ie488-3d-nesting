"""scripts/retrain_selection.py -- MANUEL retrain + ONERI CLI.

POLITIKA (2026-06-17): Retrain ASLA otomatik calismaz. Model kendini sessizce
yanlis egitip (overfit) bozarsa risk uygulamada kalir -- kabul edilemez. Gercek
egitim YALNIZ kullanicinin acik komutuyla olur. Karar her zaman kullanicinin.

Kullanim:
    # 1) ONERI AL (read-only; ne yapmali?) -- onerilen baslangic:
    python -m scripts.retrain_selection --suggest
    # 2) Kapi kararini gor (yazmaz):
    python -m scripts.retrain_selection --dry-run
    # 3) Onayliyorsan EGIT (promote ise artefakti gunceller):
    python -m scripts.retrain_selection
    # Secenekler:
    python -m scripts.retrain_selection --jsonl data/telemetry/runs.jsonl
    python -m scripts.retrain_selection --gain-mm 0.5

Cikti:
  --suggest : toplanan veri ozeti + overfit riski + eksik cozucular + tavsiye
  --dry-run : kapi karari detayi (promote?, overfit_flag, holdout, delta)
  (argumansiz): gercek retrain -- promote ise artefakti atomik degistirir
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
from src.nesting3d.selection.gate import MIN_GAIN_MM, evaluate_candidate
from src.nesting3d.selection.advisor import build_retrain_suggestion

# Varsayilan yollar
_DEFAULT_JSONL = _ROOT / "data" / "telemetry" / "runs.jsonl"
_DEFAULT_ARTIFACT = _ROOT / "data" / "selection_model.json"
_DEFAULT_ARCHIVE = _ROOT / "data" / "selection_archive"


def _fmt_mm(val: float) -> str:
    """Sayisal mm degerini okunabilir yaz; inf'i acikla."""
    if math.isinf(val):
        return "inf  (yururluk yok)"
    return f"{val:.4f} mm"


def _fmt_delta(val: float) -> str:
    """Delta degerini is areti ile yaz."""
    if math.isnan(val) or math.isinf(val):
        return "inf"
    return f"{val:+.4f} mm"


def _print_decision(decision, *, dry_run: bool = False) -> None:
    """Kapi kararini okunabilir sekilde yazdir."""
    mode_tag = "  [DRY-RUN -- artefakt YAZILMADI]" if dry_run else ""

    promote_str = (
        f"EVET -- yururluk guncellendi{mode_tag}"
        if decision.promote
        else f"HAYIR -- yururluk korundu{mode_tag}"
    )

    # overfit_flag: kapinin bloklama nedeni
    overfit_tag = "EVET (promote BLOKLU)" if decision.overfit_flag else "hayir"

    # cv_gap: gengap raporundan (GateDecision'da dogrudan saklanmiyor;
    # reason metni icinde var -- ozet bilgi promote blogu + flag'ten alinir)
    overfit_detail = ""
    if decision.overfit_flag:
        overfit_detail = "  (gengap reason gecersiz kilinmis, yukaridaki Gerekce'ye bak)"

    delta = decision.delta

    print(f"  Karar          : {promote_str}")
    print(f"  Gerekce        : {decision.reason}")
    print(f"  Overfit flag   : {overfit_tag}{overfit_detail}")
    print(f"  n_instances    : {decision.n_instances}")
    print(f"  n_holdout      : {decision.n_holdout}")
    print(f"  Aday holdout   : {_fmt_mm(decision.cand_holdout)}")
    print(f"  Cur  holdout   : {_fmt_mm(decision.cur_holdout)}")
    print(f"  Delta(cur-cand): {_fmt_delta(delta)}  (pozitif = aday daha iyi)")


def _print_suggestion(s) -> None:
    """Read-only retrain onerisini okunabilir yazdir."""
    print("--- ONERI (read-only -- hicbir sey egitilmedi/yazilmadi) ---")
    print(f"  Toplam instance     : {s.n_total}")
    print(f"  Egitilmis (yururluk): {s.n_trained}")
    print(f"  Yeni (egitilmemis)  : {s.n_new}")
    print(f"  Overfit sinyali     : {'EVET' if s.overfit_flag else 'hayir'} "
          f"(cv_gap={s.cv_gap:.3f})")
    print(f"  Retrain promote eder mi: {'EVET' if s.gate_would_promote else 'hayir'} "
          f"(delta={s.delta_mm:+.3f} mm)")
    if s.missing_solvers:
        print(f"  Hic kazanmayan cozucu : {', '.join(s.missing_solvers)}")
    print()
    print(f"  >> {s.headline}")
    print()
    print("  Tavsiyeler:")
    for i, r in enumerate(s.recommendations, 1):
        print(f"    {i}. {r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "MANUEL retrain + ONERI. Retrain ASLA otomatik degildir; karar sizin.\n\n"
            "Oneri al (ne yapmali?):\n"
            "  python -m scripts.retrain_selection --suggest\n"
            "Kapi kararini gor (yazmaz):\n"
            "  python -m scripts.retrain_selection --dry-run\n"
            "Onayliyorsan egit:\n"
            "  python -m scripts.retrain_selection"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Artefakti YAZMADAN kapi kararini goster. "
            "Yururluk model degismez; kapidan gecen karar olup olmayacagini "
            "onceden kontrol etmek icin kullanin."
        ),
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        default=False,
        help=(
            "READ-ONLY oneri: toplanan veri + overfit riski + eksik cozucular + "
            "tavsiye. Hicbir sey egitmez/yazmaz. Karar size kalir."
        ),
    )
    args = parser.parse_args()

    print("=" * 70)
    print("retrain_selection.py -- MANUEL Retrain + Oneri (otomatik DEGIL)")
    if args.suggest:
        print("  MOD: ONERI (read-only)")
    elif args.dry_run:
        print("  MOD: DRY-RUN (artefakt yazilmayacak)")
    print("=" * 70)
    print(f"  Telemetri : {args.jsonl}")
    print(f"  Artefakt  : {args.artifact}")
    print(f"  Arsiv     : {args.archive_dir}")
    print(f"  Gain esigi: {args.gain_mm} mm")
    print()

    if args.suggest:
        suggestion = build_retrain_suggestion(
            args.jsonl, args.artifact, gain_mm=args.gain_mm
        )
        _print_suggestion(suggestion)
    elif args.dry_run:
        # Sadece karar hesapla; artefakti yazma
        decision = evaluate_candidate(
            args.jsonl,
            args.artifact,
            gain_mm=args.gain_mm,
        )
        print("--- Kapi Karari (DRY-RUN) ---")
        _print_decision(decision, dry_run=True)
    else:
        decision = run_retrain(
            args.jsonl,
            args.artifact,
            archive_dir=str(args.archive_dir),
            gain_mm=args.gain_mm,
        )
        print("--- Kapi Karari ---")
        _print_decision(decision, dry_run=False)

    print("=" * 70)


if __name__ == "__main__":
    main()
