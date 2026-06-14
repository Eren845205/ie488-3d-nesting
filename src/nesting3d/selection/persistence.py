"""selection/persistence.py — EasyInstancePrefilter + AlgorithmSelector artefakt kaydedici/yukleyici.

JSON tabanlı basit serialize/deserialize — sklearn yok, binary blob yok.
Sadece öğrenilen alanlar (uygun özellik bilgisi + prototip listesi) dışa aktarılır;
yükleme sırasında fit() ÇAĞRILMAZ; nesne doğrudan yeniden inşa edilir.

Arayüz
------
    save_selection_model(prefilter, model, path)
    prefilter, model = load_selection_model(path)

Format (JSON)
-------------
{
  "schema_version": 1,
  "prefilter": {
    "fitted": bool,
    "n_train": int,
    "n_easy": int,
    "n_total": int,
    "rule_feature_idx": int | null,
    "rule_feature_name": str | null,
    "rule_threshold": float | null,
    "rule_side": str | null,
    "rule_confidence": float
  },
  "model": {
    "fitted": bool,
    "n_train": int,
    "solver_counts": {str: int},
    "training": [
      {
        "instance_id": str,
        "winner": str,
        "feature_vector": [float, ...],
        "feature_names": [str, ...]
      },
      ...
    ]
  }
}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple, Union

from src.nesting3d.selection.prefilter import EasyInstancePrefilter
from src.nesting3d.selection.model import AlgorithmSelector
from src.nesting3d.selection.dataset import TrainingRow


_SCHEMA_VERSION = 1


def save_selection_model(
    prefilter: EasyInstancePrefilter,
    model: AlgorithmSelector,
    path: Union[str, Path],
) -> None:
    """Prefilter + model durumunu JSON artefaktına kaydet.

    Parametreler
    ------------
    prefilter : Egitilmis EasyInstancePrefilter ornegi.
    model     : Egitilmis AlgorithmSelector ornegi.
    path      : Hedef JSON dosya yolu (yoksa olusturulur).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Prefilter durumu — ozel alanlar
    pf_data = {
        "fitted": prefilter._fitted,
        "n_train": prefilter.n_train,
        "n_easy": prefilter._n_easy,
        "n_total": prefilter._n_total,
        "rule_feature_idx": prefilter._rule_feature_idx,
        "rule_feature_name": prefilter._rule_feature_name,
        "rule_threshold": prefilter._rule_threshold,
        "rule_side": prefilter._rule_side,
        "rule_confidence": prefilter._rule_confidence,
    }

    # Model durumu — egitim satirlari (1-NN icin hafiza)
    training_rows = []
    for row in model._training:
        training_rows.append({
            "instance_id": row.instance_id,
            "winner": row.winner,
            "feature_vector": list(row.feature_vector),
            "feature_names": list(row.feature_names),
            "is_easy": row.is_easy,
            "dblf_height": row.dblf_height,
            "best_height": row.best_height,
            "aile": row.aile,
        })

    model_data = {
        "fitted": model._fitted,
        "n_train": model.n_train,
        "solver_counts": dict(model._solver_counts),
        "training": training_rows,
    }

    artifact = {
        "schema_version": _SCHEMA_VERSION,
        "prefilter": pf_data,
        "model": model_data,
    }

    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")


def load_selection_model(
    path: Union[str, Path],
) -> Tuple[EasyInstancePrefilter, AlgorithmSelector]:
    """JSON artefaktından prefilter + model yukle.

    fit() CAGRILMAZ — nesne dogrudan egitilmis durumda insa edilir.

    Parametreler
    ------------
    path : JSON artefakt dosya yolu.

    Dondurus
    --------
    (EasyInstancePrefilter, AlgorithmSelector) — egitilmis nesneler.

    Raises
    ------
    FileNotFoundError : Dosya bulunamazsa.
    ValueError        : Sema versiyonu eslesmezse veya gerekli alan eksikse.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Selection model artefakti bulunamadi: {path}")

    artifact = json.loads(path.read_text(encoding="utf-8"))

    version = artifact.get("schema_version", 0)
    if version != _SCHEMA_VERSION:
        raise ValueError(
            f"Artefakt sema versiyonu uyusmuyor: {version} != {_SCHEMA_VERSION}"
        )

    # --- Prefilter insa ---
    pf = EasyInstancePrefilter()
    pf_data = artifact["prefilter"]
    pf._fitted = bool(pf_data["fitted"])
    pf.n_train = int(pf_data["n_train"])
    pf._n_easy = int(pf_data["n_easy"])
    pf._n_total = int(pf_data["n_total"])
    pf._rule_feature_idx = pf_data["rule_feature_idx"]  # int or None
    pf._rule_feature_name = pf_data["rule_feature_name"]  # str or None
    pf._rule_threshold = pf_data["rule_threshold"]  # float or None
    pf._rule_side = pf_data["rule_side"]  # "below" | "above" | None
    pf._rule_confidence = float(pf_data["rule_confidence"])

    # --- Model insa ---
    sel = AlgorithmSelector()
    model_data = artifact["model"]
    sel._fitted = bool(model_data["fitted"])
    sel.n_train = int(model_data["n_train"])
    sel._solver_counts = {str(k): int(v) for k, v in model_data["solver_counts"].items()}

    rows = []
    for rd in model_data["training"]:
        rows.append(
            TrainingRow(
                instance_id=str(rd["instance_id"]),
                is_easy=bool(rd.get("is_easy", False)),
                winner=str(rd["winner"]),
                dblf_height=rd.get("dblf_height"),
                best_height=float(rd.get("best_height", 0.0)),
                feature_vector=[float(x) for x in rd["feature_vector"]],
                feature_names=[str(n) for n in rd["feature_names"]],
                aile=str(rd.get("aile", "")),
            )
        )
    sel._training = rows

    return pf, sel
