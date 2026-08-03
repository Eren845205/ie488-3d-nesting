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


def _no_go_coz(
    cfg_key: str, env_key: str, root: Optional[object] = None,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Ortak no-go dikdortgen cozucusu (config alani > env > None)."""
    p = plate_cfg_path(root)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ng = data.get(cfg_key)
            if ng and len(ng) == 2:
                (x1, y1), (x2, y2) = ng
                vals = [_pos(x2), _pos(y2)]  # ust sinirlar pozitif olmali
                if None not in vals and float(x1) < float(x2) and float(y1) < float(y2):
                    return ((float(x1), float(y1)), (float(x2), float(y2)))
        except Exception as exc:
            logger.warning("plate.local.json %s okunamadi (%s) — env'e dusuluyor",
                           cfg_key, exc)

    raw = os.environ.get(env_key, "").strip()
    if raw:
        try:
            x1, y1, x2, y2 = (float(v) for v in raw.split(","))
            if x1 < x2 and y1 < y2:
                return ((x1, y1), (x2, y2))
        except (TypeError, ValueError):
            logger.warning("%s parse edilemedi: %r", env_key, raw)
    return None


DEFAULT_CLEARANCE_MM = 2.0

# Sozlesme capraz-referans (2026-07-25): bu deger scripts/eval_gate.py'deki
# CLEARANCE_REQ_MM sozlesme sabitiyle (hoca sarti, A2) AYNI olmali. eval_gate
# sabiti sozlesme degisikligi sinifindadir (hoca teyidi + baseline yenileme
# gerektirir) — resolve_clearance() SADECE demo_pipeline'in kod-sabitini
# config/env'e tasir, sozlesme degerini DEGISTIRMEZ (config alani yokken
# davranis birebir 2.0 kalir).


def resolve_clearance(root: Optional[object] = None) -> float:
    """Web nesting min-clearance (mm) coz.

    Oncelik:
      1. configs/plate.local.json "min_clearance_mm" (opsiyonel alan — bu
         alan HENUZ eklenmedi, sozlesme degisikligi sinifinda ayri onay
         gerektirir; alan yoksa bu adim atlanir).
      2. env NESTING_CLEARANCE_MM
      3. DEFAULT_CLEARANCE_MM (2.0) — mevcut kod-sabiti davranisiyla birebir.
    """
    p = plate_cfg_path(root)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            v = _pos(data.get("min_clearance_mm"))
            if v is not None:
                return v
        except Exception as exc:
            logger.warning(
                "plate.local.json min_clearance_mm okunamadi (%s) — env/default'a "
                "dusuluyor", exc)

    env_v = _pos_env("NESTING_CLEARANCE_MM")
    if env_v is not None:
        return env_v

    return DEFAULT_CLEARANCE_MM


def resolve_no_go(
    root: Optional[object] = None,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Plakanin yasak bolgesi (no-go) dikdortgenini coz; yoksa None.

    Kaynak onceligi plate ile ayni:
      1. configs/plate.local.json  "no_go": [[x1,y1],[x2,y2]]  (mm)
      2. env PLATE_NOGO="x1,y1,x2,y2"
    Yasak bolge plaka/yazici OZELLIGIDIR (orn. hoca 2026-07-09: recoater kolonu
    x[152.5,185.5] y[0.2,45]) — bu yuzden plaka konfiguruyla birlikte yasar.
    Donen deger solve_nfv/solve_coarse_to_fine no_go_bounds ve
    Bin3D.no_go_mask_from_bounds sozlesmesiyle ayni: ((x1,y1),(x2,y2)).
    """
    return _no_go_coz("no_go", "PLATE_NOGO", root)


def resolve_no_go_soft(
    root: Optional[object] = None,
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """SOFT no-go dikdortgenini coz; ilan edilmemisse None (K-56g kablosu).

    SOZLESME-KAPILI aktivasyon: hoca 2026-07-09 cevap 3/9 ("yasak bolgeye cok
    hafif girisler sorun yaratmiyor") geregi yasak bolgenin operasyonel/soft
    siniri hard dikdortgenden kucuk olabilir (kanit K-56c: y-ust 45->33,
    plan1 202.2->171.7). Bu deger configs/plate.local.json "no_go_soft"
    alanindan (veya env PLATE_NOGO_SOFT) okunur; ALAN YOKSA None doner ve
    K-56g zinciri (soft maske + duz-pinleme) HIC devreye girmez — davranis
    bit-ozdes. Alanin config'e eklenmesi SOZLESME KARARIDIR (A11 madde 4:
    4-set kapi + baseline yenileme ile birlikte, Eren onayi).
    """
    return _no_go_coz("no_go_soft", "PLATE_NOGO_SOFT", root)
