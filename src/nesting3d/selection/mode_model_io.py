"""mode_model_io.py — mod-secici model artefakti (yaz/yukle) + calisma-zamani karari.

C4 kablosunun veri katmani (ML plani Sprint-3, Eren onayi 2026-07-14):
YARISMA-2 kazanani RegretWeightedLogistic + LOO-conformal skorlari +
guvenli-aile allowlist'i tek JSON'da (data/mode_model.json, schema=2).
Cikarim SAF stdlib (Y-3): musteri kurulumu ek bagimlilik gormez.

Karar sozlesmesi (CIFT KILIT): model yalniz (a) instance ailesi allowlist'te
VE (b) conformal prediction-set TEKIL ise konusur; aksi halde None doner ve
cagiran (predict_nfv_benefit) mevcut KURALLA devam eder. Boylece model
yalniz kanitli+emin oldugu yerde kurali ezebilir.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

MODE_MODEL_PATH = "data/mode_model.json"
_SCHEMA = 2


def _node_to_dict(n) -> dict:
    """_DTNode -> saf-JSON (E-genisletme 2026-09-02)."""
    if n.winner is not None:
        return {"w": n.winner, "c": float(n.confidence), "n": int(n.n_samples)}
    return {"f": int(n.feature_idx), "t": float(n.threshold),
            "L": _node_to_dict(n.left), "R": _node_to_dict(n.right)}


def _tree_walk(d: dict, features):
    """Serilestirilmis agacta saf-stdlib gezinme -> (winner, confidence)."""
    while "w" not in d:
        xi = float(features[d["f"]]) if d["f"] < len(features) else 0.0
        d = d["L"] if xi <= d["t"] else d["R"]
    return d["w"], float(d["c"])


def save_mode_model(path, logistic, skorlar: List[float], armlar: List[str],
                    allowlist: List[str], meta: dict) -> None:
    """Fit edilmis secici + conformal kalibrasyon ATOMIK yaz.

    Tip-dalli (E-genisletme 2026-09-02): Logistic ailesi eski alanlarla
    BIREBIR; MiniBagging/DecisionTree agac-listesiyle. Schema ayni; eski
    artefaktlar aynen okunur."""
    tip = type(logistic).__name__
    if tip in ("MiniBaggingSelector", "DecisionTreeSelector"):
        koklar = ([a._root for a in logistic._agaclar]
                  if tip == "MiniBaggingSelector" else [logistic._root])
        row = {
            "schema": _SCHEMA,
            "model_tipi": tip,
            "agaclar": [_node_to_dict(k) for k in koklar],
            "n_train": int(getattr(logistic, "n_train", 0) or 0),
            "conformal": {"alpha": meta.get("alpha", 0.1),
                          "skorlar": [float(s) for s in sorted(skorlar)],
                          "armlar": sorted(armlar)},
            "guvenli_aileler": sorted(allowlist),
            "meta": meta,
        }
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(row, indent=1, ensure_ascii=True),
                       encoding="utf-8")
        os.replace(tmp, path)
        return
    row = {
        "schema": _SCHEMA,
        "model_tipi": type(logistic).__name__,
        "classes": list(logistic._classes),
        "W": [list(w) for w in logistic._W],
        "b": list(logistic._b),
        "mu": list(logistic._mu),
        "sigma": list(logistic._sigma),
        "temperature": float(logistic.temperature),
        "n_train": int(logistic.n_train),
        "conformal": {"alpha": meta.get("alpha", 0.1),
                      "skorlar": [float(s) for s in sorted(skorlar)],
                      "armlar": sorted(armlar)},
        "guvenli_aileler": sorted(allowlist),
        "meta": meta,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, indent=1, ensure_ascii=True),
                   encoding="utf-8")
    os.replace(tmp, path)


class LoadedModeModel:
    """Artefakttan yuklenen cikarim modeli — stdlib softmax + conformal kapi."""

    def __init__(self, d: dict):
        self.model_tipi: str = d.get("model_tipi", "LogisticSelector")
        self.agaclar: List[dict] = d.get("agaclar") or []
        if not self.agaclar:
            self.classes: List[str] = d["classes"]
            self.W: List[List[float]] = d["W"]
            self.b: List[float] = d["b"]
            self.mu: List[float] = d["mu"]
            self.sigma: List[float] = d["sigma"]
            self.temperature: float = d["temperature"]
        self.alpha: float = d["conformal"]["alpha"]
        self.skorlar: List[float] = d["conformal"]["skorlar"]
        self.armlar: Set[str] = set(d["conformal"]["armlar"])
        self.guvenli_aileler: Set[str] = set(d["guvenli_aileler"])
        self.meta: dict = d.get("meta", {})

    def proba(self, features: Sequence[float]) -> Dict[str, float]:
        if self.agaclar:
            # Bagging/agac dali (E-genisletme): oy dagilimi — saf stdlib (Y-3).
            oylar: Dict[str, float] = {}
            for kok in self.agaclar:
                ad, _c = _tree_walk(kok, features)
                oylar[ad] = oylar.get(ad, 0.0) + 1.0
            n = float(len(self.agaclar))
            return {a: c / n for a, c in sorted(oylar.items())}
        # LogisticSelector._norm ile birebir ayni normalizasyon
        xn = []
        for i in range(len(self.mu)):
            xi = float(features[i]) if i < len(features) else 0.0
            xn.append((xi - self.mu[i]) / self.sigma[i])
        z = [sum(w * v for w, v in zip(self.W[c], xn)) + self.b[c]
             for c in range(len(self.classes))]
        z = [v / max(self.temperature, 1e-6) for v in z]
        m = max(z)
        e = [math.exp(v - m) for v in z]
        s = sum(e)
        return {c: ei / s for c, ei in zip(self.classes, e)}

    def _esik(self) -> float:
        n = len(self.skorlar)
        if n == 0:
            return 1.0
        k = min(n, math.ceil((n + 1) * (1.0 - self.alpha)))
        return self.skorlar[k - 1]

    def prediction_set(self, features: Sequence[float]) -> Set[str]:
        q = self._esik()
        p = self.proba(features)
        kume = {a for a in self.armlar if 1.0 - p.get(a, 0.0) <= q}
        if not kume and p:
            kume = {max(p, key=p.get)}
        return kume

    def karar(self, features: Sequence[float], aile: str
              ) -> Optional[Tuple[str, str]]:
        """CIFT KILIT karari: (arm, gerekce) veya None (kural devam eder)."""
        if aile not in self.guvenli_aileler:
            return None
        kume = self.prediction_set(features)
        if len(kume) != 1:
            return None
        arm = next(iter(kume))
        return arm, (f"mode_model({self.meta.get('surum', '?')}): aile={aile} "
                     f"allowlist'te + conformal-tekil -> {arm}")


def load_mode_model(path) -> Optional[LoadedModeModel]:
    """Yukle; dosya yok/bozuk/sema-uyumsuz -> None (kural devam eder, ASLA hata)."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(d.get("schema", 0)) != _SCHEMA:
            return None
        return LoadedModeModel(d)
    except Exception:
        return None
