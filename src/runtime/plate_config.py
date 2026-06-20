"""src/runtime/plate_config.py — Gercek plaka (yazici tabani) konfig cozumu.

Kullanici karari (2026-06-20): plaka boyutu sonucu ciddi etkiler (yukseklik/
doluluk/sure), bu yuzden kullanicinin GERCEK yazici plakasini MANUEL girebilmesi
gerekir. Bu modul o plakayi tek yerden cozer.

Oncelik:
  1. configs/plate.local.json  (UI '/plaka-ayar' ekranindan kaydedilen)
  2. env PLATE_W_MM / PLATE_D_MM / PLATE_H_MM
  3. Hicbiri yok -> (None, None, None); run_pipeline parcalardan otomatik turetir.

Boylece "manuel sabit plaka" ve "otomatik plaka" birlikte calisir (cekirdek
politika ile uyumlu — bkz. src/nesting3d/instances/plate.py).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _pos(v: object) -> Optional[float]:
    """Pozitif float'a cevir; gecersiz/<=0 ise None."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _pos_env(key: str) -> Optional[float]:
    raw = os.environ.get(key, "").strip()
    return _pos(raw) if raw else None


def plate_cfg_path(root: Optional[object] = None) -> Path:
    base = Path(root) if root else Path.cwd()
    return base / "configs" / "plate.local.json"


def resolve_plate(
    root: Optional[object] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Gercek plaka (width, depth, height) mm dondur; tanimsiz boyut None.

    En az bir taban boyutu (w veya d) cozulurse config/env gecerli sayilir.
    Hicbiri yoksa (None, None, None) -> otomatik plaka (pipeline turetir).
    """
    p = plate_cfg_path(root)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            w = _pos(data.get("width_mm"))
            d = _pos(data.get("depth_mm"))
            h = _pos(data.get("height_mm"))
            if w is not None or d is not None:
                return w, d, h
        except Exception as exc:
            logger.warning("plate.local.json okunamadi (%s) — env'e dusuluyor", exc)

    return _pos_env("PLATE_W_MM"), _pos_env("PLATE_D_MM"), _pos_env("PLATE_H_MM")
