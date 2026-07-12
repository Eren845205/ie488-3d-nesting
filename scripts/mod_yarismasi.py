# -*- coding: utf-8 -*-
"""mod_yarismasi.py — mod-secici aday modellerin LOO-regret yarismasi (C3).

Tum adaylar (mevcut 4 + yeni 4) + KURALIN KENDISI (RuleAdapter, kiyas cizgisi)
ayni aile-farkindali LOO dongusunde yarisir; metrik Y-6 geregi REGRET (mm),
accuracy yalniz yardimci. HICBIR ARTEFAKT YAZILMAZ (Y-1/Y-4) — kazanan +
aile-kirilimli kanit insan kararina sunulur; promote ayri is (retrain_mod CLI,
Sprint 3).

Kotumser ceza konvansiyonu (gengap.loo_regret ile tutarli): tahmin edilen arm
o instance'ta OLCULMEMISSE regret = max-min (o instance'in legal armlari).
Kosum: python -m scripts.mod_yarismasi [--json YOL]   SAF ASCII stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.selection.bagging import MiniBaggingSelector
from src.nesting3d.selection.conformal import ConformalSelector
from src.nesting3d.selection.dataset import TrainingRow, heldout_instance_ids
from src.nesting3d.selection.dataset_v2 import build_training_table_v2
from src.nesting3d.selection.gengap import compute_generalization_gap
from src.nesting3d.selection.height_reg import (
    ArgminModeSelector,
    KNNHeightRegressor,
    RidgeGDRegressor,
)
from src.nesting3d.selection.model import (
    AlgorithmSelector,
    DecisionTreeSelector,
    KNNSelector,
    LogisticSelector,
)
from src.nesting3d.selection.regret_logistic import RegretWeightedLogistic

VARSAYILAN_JSON = _ROOT / "results" / "mod_yarismasi.json"


class RuleAdapter:
    """Kuralin kendisi 'aday' olarak: fit no-op, predict = onceden hesaplanmis
    kural karari (instance_id -> arm haritasi; fv uzerinden esletirilir).
    Kural veri gormez -> LOO'da sizinti kavrami yok; sabit kiyas cizgisi."""

    def __init__(self, kural_map: Dict[str, str]):
        self._kural_map = dict(kural_map)
        self._fv_map: Dict[tuple, str] = {}

    def fit(self, rows: List[TrainingRow]) -> None:
        for r in rows:
            arm = self._kural_map.get(r.instance_id)
            if arm:
                self._fv_map[tuple(r.feature_vector)] = arm

    def predict(self, features):
        arm = self._fv_map.get(tuple(features))
        return (arm, 1.0) if arm else ("heightmap", 0.0)

    def explain(self) -> str:
        return f"RuleAdapter | {len(self._kural_map)} kural karari (sabit)"


def _loo_regret_detay(table: List[TrainingRow], factory: Callable) -> dict:
    """Aile-kirimli LOO regret. Kotumser ceza: olcusmemis tahmin -> max-min."""
    if len(table) < 2:
        return {"mean": None, "max": None, "n": len(table), "aile": {},
                "accuracy": None, "not": "LOO icin tablo cok kucuk"}
    toplam: List[float] = []
    aile: Dict[str, List[float]] = {}
    dogru = 0
    for i, satir in enumerate(table):
        m = factory()
        m.fit(table[:i] + table[i + 1:])
        # RuleAdapter tum tabloyu gormeli (sabit harita; sizinti yok)
        if isinstance(m, RuleAdapter):
            m.fit(table)
        pred, _ = m.predict(satir.feature_vector)
        hs = satir.per_solver_heights or {}
        best = min(hs.values())
        r = (hs[pred] - best) if pred in hs else (max(hs.values()) - best)
        toplam.append(r)
        aile.setdefault(satir.aile, []).append(r)
        if pred == satir.winner:
            dogru += 1
    return {
        "mean": round(sum(toplam) / len(toplam), 2),
        "max": round(max(toplam), 2),
        "n": len(table),
        "accuracy": round(dogru / len(table), 3),
        "aile": {a: {"mean": round(sum(v) / len(v), 2), "n": len(v)}
                 for a, v in sorted(aile.items())},
    }


def adaylar(kural_map: Optional[Dict[str, str]] = None) -> Dict[str, Callable]:
    d: Dict[str, Callable] = {
        "1nn": AlgorithmSelector,
        "karar_agaci": lambda: DecisionTreeSelector(max_depth=2,
                                                    min_samples_leaf=2),
        "knn": KNNSelector,
        "logistic": LogisticSelector,
        "argmin_knn_reg": lambda: ArgminModeSelector(KNNHeightRegressor),
        "argmin_ridge_reg": lambda: ArgminModeSelector(RidgeGDRegressor),
        "regret_logistic": RegretWeightedLogistic,
        "conformal_logistic": lambda: ConformalSelector(LogisticSelector),
        "mini_bagging(deney)": MiniBaggingSelector,
    }
    if kural_map:
        d["KURAL(baseline)"] = lambda: RuleAdapter(kural_map)
    return d


def yarisma(table: List[TrainingRow],
            kural_map: Optional[Dict[str, str]] = None) -> dict:
    sonuc: Dict[str, dict] = {}
    for ad, factory in adaylar(kural_map).items():
        satir = _loo_regret_detay(table, factory)
        try:
            gg = compute_generalization_gap(table, model_factory=factory)
            satir["overfit_flag"] = bool(gg.overfit_flag)
        except Exception as e:
            satir["overfit_flag"] = None
            satir["gengap_hata"] = f"{type(e).__name__}: {e}"
        sonuc[ad] = satir
    return {"adaylar": sonuc, "n_tablo": len(table)}


def _ascii(sonuc: dict) -> str:
    c = [f"MOD YARISMASI — tablo n={sonuc['n_tablo']} "
         f"(metrik: LOO-regret mm; dusuk iyi)"]
    c.append(f"{'aday':<22} {'regret_ort':>10} {'regret_max':>10} "
             f"{'acc':>6} {'overfit':>8}")
    def _s(x):
        return "-" if x is None else x
    for ad, s in sorted(sonuc["adaylar"].items(),
                        key=lambda t: (t[1]["mean"] is None,
                                       t[1]["mean"] or 0)):
        c.append(f"{ad:<22} {_s(s['mean']):>10} {_s(s['max']):>10} "
                 f"{_s(s['accuracy']):>6} {_s(s['overfit_flag']):>8}")
        for aile, av in s.get("aile", {}).items():
            c.append(f"    {aile:<18} ort={av['mean']} (n={av['n']})")
    return "\n".join(c)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(VARSAYILAN_JSON))
    args = ap.parse_args()
    from src.nesting3d.telemetry import V2_DEFAULT_PATH, load_telemetry
    rows = load_telemetry(_ROOT / V2_DEFAULT_PATH)
    ist: dict = {}
    table = build_training_table_v2(
        rows, exclude_instance_ids=heldout_instance_ids(
            _ROOT / "data" / "registry.json"), istatistik=ist)
    kural_map = {}
    rr = _ROOT / "results" / "regret_raporu.json"
    if rr.exists():
        rj = json.loads(rr.read_text(encoding="utf-8"))
        kural_map = {iid: s["kural_arm"] for iid, s in rj["setler"].items()
                     if s.get("kural_arm")}
    sonuc = yarisma(table, kural_map)
    sonuc["tablo_istatistik"] = ist
    print(_ascii(sonuc))
    print(f"istatistik: {ist}")
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sonuc, indent=1, ensure_ascii=True),
                   encoding="utf-8")
    print(f"JSON: {out}")
    print("NOT: hicbir model artefakti yazilmadi (Y-1/Y-4) — promote ayri is.")


if __name__ == "__main__":
    main()
