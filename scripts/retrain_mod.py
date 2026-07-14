# -*- coding: utf-8 -*-
"""retrain_mod.py — mod-secici modeli egit + artefakti yaz (C4 promote CLI).

Y-1 geregi YALNIZ insan komutuyla kosulur (Eren onayi 2026-07-14: YARISMA-2
kaniti uzerine regret_logistic + allowlist promote'u). Akis:
  1. runs_v2 -> build_training_table_v2 (held-out yapisal disarida)
  2. RegretWeightedLogistic fit (tum tablo)
  3. LOO-conformal kalibrasyon skorlari (ConformalSelector ile ayni matematik)
  4. data/mode_model.json ATOMIK yaz (+ data/selection_archive/ mode_model.vN)
--dry-run: yazmadan ozet basar. --allowlist: virgullu aile listesi.
Kosum: python -m scripts.retrain_mod --allowlist long_rod,solid_bulk
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.selection.conformal import ConformalSelector
from src.nesting3d.selection.dataset import heldout_instance_ids
from src.nesting3d.selection.dataset_v2 import build_training_table_v2
from src.nesting3d.selection.mode_model_io import MODE_MODEL_PATH, save_mode_model
from src.nesting3d.selection.regret_logistic import RegretWeightedLogistic
from src.nesting3d.telemetry import V2_DEFAULT_PATH, load_telemetry


def _arsivle(hedef: Path):
    if not hedef.exists():
        return None
    arsiv = _ROOT / "data" / "selection_archive"
    arsiv.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(p.stem.split(".v")[-1])
                 for p in arsiv.glob("mode_model.v*.json")), default=0)
    yol = arsiv / f"mode_model.v{n}.json"
    shutil.copy2(hedef, yol)
    return yol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allowlist", required=True,
                    help="virgullu guvenli-aile listesi (yarisma kaniti sart)")
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(_ROOT / MODE_MODEL_PATH))
    args = ap.parse_args()
    allowlist = [a.strip() for a in args.allowlist.split(",") if a.strip()]

    ist = {}
    rows = load_telemetry(_ROOT / V2_DEFAULT_PATH)
    table = build_training_table_v2(
        rows, exclude_instance_ids=heldout_instance_ids(
            _ROOT / "data" / "registry.json"), istatistik=ist)
    print(f"tablo: {len(table)} instance  istatistik: {ist}")
    if len(table) < 10:
        print("HATA: tablo cok kucuk (<10) — promote reddedildi")
        sys.exit(2)

    model = RegretWeightedLogistic()
    model.fit(table)
    conf = ConformalSelector(RegretWeightedLogistic, alpha=args.alpha)
    conf.fit(table)  # LOO skorlari (ayni matematik; base'i kendi egitir)
    print(f"model: {model.explain()}")
    print(f"conformal: n_skor={len(conf._skorlar)}  armlar={sorted(conf._armlar)}")
    print(f"allowlist: {allowlist}")

    if args.dry_run:
        print("[dry-run] artefakt YAZILMADI")
        return
    hedef = Path(args.out)
    eski = _arsivle(hedef)
    if eski:
        print(f"eski artefakt arsivlendi: {eski}")
    save_mode_model(
        hedef, model, conf._skorlar, sorted(conf._armlar), allowlist,
        meta={"surum": "yarisma2-2026-07-14", "alpha": args.alpha,
              "n_train": len(table),
              "kanit": "results/mod_yarismasi_v2.json (9.66 vs kural 17.0mm)",
              "onay": "Eren 2026-07-14"})
    print(f"YAZILDI: {hedef}")


if __name__ == "__main__":
    main()
