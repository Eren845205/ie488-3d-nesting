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
from src.nesting3d.selection.bagging import MiniBaggingSelector
from src.nesting3d.selection.model import DecisionTreeSelector

MODELLER = {"logistic": LogisticSelector,
            "regret_logistic": RegretWeightedLogistic,
            "mini_bagging": MiniBaggingSelector,
            "karar_agaci": DecisionTreeSelector}


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
                    help="virgullu guvenli URETIM-aile listesi (classify_prelim "
                         "adlari: thin_shell,tube,thin_plate,long_rod,solid_bulk,"
                         "mixed_scale) VEYA 'auto' = kapili LOO'da model<=kural "
                         "olan aileler (AC-10, 2026-09-02)")
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--min-n", type=int, default=3,
                    help="auto allowlist: ailenin guvenli sayilmasi icin min satir")
    ap.add_argument("--force", action="store_true",
                    help="karar-probu OLU (konustu=0) olsa da yaz (varsayilan: RET)")
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

    # --- AC-10 (2026-09-02): URETIM-AILE semantigi -------------------------
    # Uretim `karar(features, classify_prelim(instance))` ile sorar; allowlist
    # ve kapili-karar olcumu de AYNI aile adlariyla yapilir. Her satir icin
    # instance yeniden kurulur -> uretim ailesi + GERCEK uretim kural kolu
    # (predict_nfv_benefit; uretim bayraklari family_routing=True,
    # rot_sokum=True — demo_pipeline giris yollariyla ayni).
    from scripts.m4_portfoy_kosu import FAMILY_BUILDERS, _devset_builder
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.instances.family import classify_prelim
    from src.nesting3d.selection.uretim_aile import (
        URETIM_AILELERI, guvenli_aileler_sec, kapili_loo, karar_probu,
        satir_uretim_bilgisi)
    kural_map = {}
    rr = _ROOT / "results" / "regret_raporu.json"
    if rr.exists():
        rj = json.loads(rr.read_text(encoding="utf-8"))
        kural_map = {iid: s["kural_arm"] for iid, s in rj["setler"].items()
                     if s.get("kural_arm")}
    bilgi = satir_uretim_bilgisi(
        table, builders=FAMILY_BUILDERS, devset_builder=_devset_builder,
        classify=classify_prelim,
        kural_fn=lambda inst: predict_nfv_benefit(
            inst, family_routing=True, rot_sokum=True),
        kural_map=kural_map, stl_dir=_ROOT / "tmp" / "m4_stl")
    kaynak_sayim = {}
    for b in bilgi.values():
        kaynak_sayim[b["kaynak"]] = kaynak_sayim.get(b["kaynak"], 0) + 1
    print(f"uretim-bilgi kaynaklari: {kaynak_sayim}")
    if len(allowlist) == 1 and allowlist[0].lower() == "auto":
        guvenli, rapor0 = guvenli_aileler_sec(
            table, bilgi, ModelCls, args.alpha, min_n=args.min_n)
        allowlist = sorted(guvenli)
        print(f"auto allowlist (kapili LOO, model<kural kesin, n>={args.min_n}): "
              f"{allowlist}")
    yabanci = [a for a in allowlist if a not in URETIM_AILELERI]
    if yabanci:
        print(f"HATA: allowlist uretim-aile adi degil: {yabanci} "
              f"(gecerli: {sorted(URETIM_AILELERI)})")
        sys.exit(2)
    rapor = kapili_loo(table, bilgi, ModelCls, args.alpha, allowlist)
    print(f"kapili-karar LOO (alpha={args.alpha}, esik={rapor['esik']:.3f}): "
          f"regret model={rapor['regret_model']:.2f} kural="
          f"{rapor['regret_kural']:.2f} | konustu {rapor['konustu']}/{rapor['n']} "
          f"(isabet {rapor['isabet']}) | kural-bilinmeyen {rapor['kural_bilinmeyen']}")
    for f, d in rapor["aile"].items():
        print(f"   {f:12s} n={d['n']:3d} kural={d['kural_ort']:6.1f} "
              f"model={d['model_ort']:6.1f} konustu={d['konustu']} isabet={d['isabet']}")

    model = ModelCls()
    model.fit(table)
    conf = ConformalSelector(ModelCls, alpha=args.alpha)
    conf.fit(table)  # LOO skorlari (ayni matematik; base'i kendi egitir)
    print(f"model: {model.explain()}")
    print(f"conformal: n_skor={len(conf._skorlar)}  armlar={sorted(conf._armlar)}")
    print(f"allowlist: {allowlist}")

    # KARAR-PROBU (RUNBOOK P-7, 2026-09-02): artefakt gecici yola yazilir,
    # uretim yukleyicisiyle okunur, egitim satirlarinda uretim ailesiyle
    # karar() sorulur. konustu=0 -> OLU promote -> RET (--force ile gecilir).
    from src.nesting3d.selection.mode_model_io import load_mode_model
    gecici = _ROOT / "tmp" / "mode_model.karar_probu.json"
    gecici.parent.mkdir(parents=True, exist_ok=True)
    meta_probu = {"surum": "karar-probu", "alpha": args.alpha}
    save_mode_model(gecici, model, conf._skorlar, sorted(conf._armlar),
                    allowlist, meta=meta_probu)
    lm = load_mode_model(gecici)
    probu = karar_probu(lm, table, bilgi) if lm else {"olu": True, "n": 0,
                                                     "konustu": 0, "isabet": 0,
                                                     "aileler": {}}
    print(f"karar-probu: konustu {probu['konustu']}/{probu['n']} "
          f"(isabet {probu['isabet']}) aileler={probu['aileler']}"
          + ("  -> OLU" if probu["olu"] else ""))
    if probu["olu"] and not args.force:
        print("HATA: karar-probu OLU (model uretimde hic konusmaz) — promote "
              "reddedildi (P-7). alpha/allowlist'i gozden gecir; --force ile ez.")
        sys.exit(3)

    if args.dry_run:
        print("[dry-run] artefakt YAZILMADI")
        return
    hedef = Path(args.out)
    eski = _arsivle(hedef)
    if eski:
        print(f"eski artefakt arsivlendi: {eski}")
    save_mode_model(
        hedef, model, conf._skorlar, sorted(conf._armlar), allowlist,
        meta={"surum": f"ac10-uretim-aile-2026-09-02-{args.model}",
              "alpha": args.alpha,
              "n_train": len(table),
              "allowlist_semantigi": "classify_prelim uretim ailesi (AC-10)",
              "kapili_loo": {"regret_model": rapor["regret_model"],
                             "regret_kural": rapor["regret_kural"],
                             "konustu": rapor["konustu"], "n": rapor["n"],
                             "isabet": rapor["isabet"], "esik": rapor["esik"],
                             "aile": rapor["aile"]},
              "karar_probu": probu,
              "kanit": ("YONTEM 3.1 2026-09-02 16:10 (AC-10 kapili LOO) + "
                        "results/mod_yarismasi_20260902.json (ham) + "
                        "ASAMA2_KAPI_RAPORU EK"),
              "onay": "Eren 2026-09-02 ('2 yi yap' -> secenek A)"})
    print(f"YAZILDI: {hedef}")


if __name__ == "__main__":
    main()
