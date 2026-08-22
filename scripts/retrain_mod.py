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
from src.nesting3d.selection.model import LogisticSelector
from src.nesting3d.selection.regret_logistic import RegretWeightedLogistic
from src.nesting3d.telemetry import V2_DEFAULT_PATH, load_telemetry

# Asama-1 guncellemesi (2026-08-22): tur-5 kapi kaniti kazanani LOGISTIC
# (karar_agaci overfit-bayrakli — plan §5.4). Model secimi CLI'da;
# mode_model_io serilestirmesi iki sinifla da ayni alanlari kullanir.
MODELLER = {"logistic": LogisticSelector,
            "regret_logistic": RegretWeightedLogistic}


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
    ap.add_argument("--model", choices=sorted(MODELLER), default="logistic",
                    help="promote edilecek aday (tur-5 kaniti: logistic)")
    ap.add_argument("--m4-etiket",
                    default=str(_ROOT / "results" / "m4_portfoy_etiket.jsonl"))
    ap.add_argument("--m4-kapali", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(_ROOT / MODE_MODEL_PATH))
    args = ap.parse_args()
    allowlist = [a.strip() for a in args.allowlist.split(",") if a.strip()]

    ist = {}
    heldout = heldout_instance_ids(_ROOT / "data" / "registry.json")
    rows = load_telemetry(_ROOT / V2_DEFAULT_PATH)
    table = build_training_table_v2(
        rows, exclude_instance_ids=heldout, istatistik=ist)
    m4_yol = Path(args.m4_etiket)
    if not args.m4_kapali and m4_yol.exists():
        # mod_yarismasi tur-5 tablosuyla AYNI kurulum (kafes dahil —
        # Eren onayi 2026-08-21; kablo MK-03 uretimde oldugu icin model
        # kafes onerebilir)
        from scripts.mod_yarismasi import _m4_feature_resolver
        from src.nesting3d.selection.m4_koprusu import m4_training_rows
        satirlar = [json.loads(s) for s in
                    m4_yol.read_text(encoding="utf-8").splitlines()
                    if s.strip()]
        m4_rows = m4_training_rows(
            satirlar, _m4_feature_resolver(), kafes_dahil=True,
            exclude_instance_ids=heldout,
            mevcut_ids={r.instance_id for r in table}, istatistik=ist)
        table = sorted(table + m4_rows, key=lambda r: r.instance_id)
    print(f"tablo: {len(table)} instance  istatistik: {ist}")
    if len(table) < 10:
        print("HATA: tablo cok kucuk (<10) — promote reddedildi")
        sys.exit(2)

    ModelCls = MODELLER[args.model]
    model = ModelCls()
    model.fit(table)
    conf = ConformalSelector(ModelCls, alpha=args.alpha)
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
        meta={"surum": f"asama1-tur5-2026-08-22-{args.model}",
              "alpha": args.alpha,
              "n_train": len(table),
              "kanit": ("results/mod_yarismasi.json tur-5 n=80 "
                        "(logistic 8,72 bayraksiz vs KURAL 16,44; "
                        "fsm610_gercek 0,0 vs 144,0) + "
                        "STRATEJI/ASAMA1_KAPI_RAPORU_2026-08-21.md"),
              "onay": "Eren 2026-08-22 (karar paketi 'Devam et')"})
    print(f"YAZILDI: {hedef}")


if __name__ == "__main__":
    main()
