"""kafes_zincir.py — KAFES mekanizmasinin uretim kablosu (MK-03, Eren onayi
2026-08-22 "Devam et" karar paketi madde-2).

Kanopi zinciri (kanopi_zincir.kanopi_zinciri_uretim) desenine birebir uyar:

- TETIK yoksa SIFIR maliyet + sonuc AYNEN (tek-tarafli): kafes_coz_instance
  kendi geometrik tetigini tasir (tekrar-kitle payi + plaka-asan cubuk;
  veri-adi YOK — A11).
- Tetikliyse aday cozulur; KABUL ancak (a) TAM yerlesim, (b) clearance >=
  esik, (c) 5-yon kilit == 0 (rot-sokum katmani BILINCLI kosulmaz —
  konservatif; kafes cozumleri kapi kanitinda kilit=0), (d) ref'ten
  DUSUK yukseklik. Aksi halde ref AYNEN doner.
- Kare olmayan plakada tetik DENENMEZ (kafes dekodu tek-kenar sozlesmeli;
  dar baslar, genisletme ayri olcum ister).
- Her hata yutulur -> ref doner (uretim yolu dusurulmez); telemetri
  "kafes_zinciri" alaninda seffaftir.

Kanit zinciri: K-66-d kapi 12/12 LEGAL + tetik 24/24 + 2W/10T/0L (yfp 0)
+ plan-skoru v2 (YONTEM §3) + M4 orta 6/6 winner=kafes + fsm610 etiketi
winner=kafes 400,0. Pitch == clearance (K-38).
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


def _a2_kafes(res, n_total: int, clearance_mm: float) -> Dict[str, Any]:
    """Kafes adayinin A2 olcumu (uretim kollariyla ayni katman;
    m4_portfoy _kol_kafes ile tutarli)."""
    from src.nesting3d.accessibility import check_separability_5dir
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.export_stl import placed_meshes

    meshes = placed_meshes(list(res.placements), res.fine_voxel_parts,
                           float(res.fine_pitch))
    cl = round(float(min_clearance(meshes).min_mm), 3)
    kilit = int(check_separability_5dir(
        list(res.placements), res.fine_voxel_parts).n_locked)
    legal = (int(res.n_placed) == int(n_total)
             and cl >= float(clearance_mm) and kilit == 0)
    return {"min_clearance_mm": cl, "kilit_5yon": kilit,
            "n_placed": int(res.n_placed), "legal": legal}


def kafes_zinciri_uretim(
    inst,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    clearance_mm: float = 2.0,
    pitch_mm: Optional[float] = None,
    quality: str = "fast",
    seed: int = 42,
    durus_koru: bool = False,
    ref_res=None,
    ref_height_mm: Optional[float] = None,
    _coz=None,
    _a2=None,
) -> Tuple[Any, Dict[str, Any]]:
    """(final_result, telemetri) doner. ref_res ZORUNLU (kalite yolunun
    secili sonucu). _coz/_a2 test enjeksiyonu (imzalar gercekle ayni)."""
    t0 = time.perf_counter()
    n_total = sum(int(p.qty) for p in inst.parts)
    ref_h = (float(ref_height_mm) if ref_height_mm is not None
             else float(ref_res.height_mm))
    tel: Dict[str, Any] = {"tetik": False, "secilen": "ref",
                           "ref_height_mm": float(ref_res.height_mm),
                           "ref_eff_height_mm": ref_h}
    if abs(float(plate_w_mm) - float(plate_d_mm)) > 1e-6:
        tel["atlandi"] = "kare-olmayan plaka (kafes tek-kenar sozlesmesi)"
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return ref_res, tel

    try:
        if _coz is None:
            from scripts.k66_d_kafes_dekod import kafes_coz_instance as _coz
        r = _coz(inst, plate=float(plate_w_mm), clear=float(clearance_mm),
                 pitch=(float(pitch_mm) if pitch_mm is not None
                        else float(clearance_mm)),  # K-38: pitch==clearance
                 quality=quality, seed=seed, durus_koru=durus_koru)
    except Exception as exc:
        tel["hata"] = f"{type(exc).__name__}: {exc}"
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return ref_res, tel

    if not r.get("tetik"):
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return ref_res, tel
    tel["tetik"] = True
    tel["durus_koru"] = bool(durus_koru)
    if r.get("hata"):
        tel["hata"] = str(r["hata"])
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return ref_res, tel

    aday = r["res"]
    tel["aday_height_mm"] = float(aday.height_mm)
    try:
        a2 = (_a2 or _a2_kafes)(aday, n_total, clearance_mm)
    except Exception as exc:  # olculemedi = kanitsizlik = RED
        tel["hata"] = f"a2 olcum: {type(exc).__name__}: {exc}"
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return ref_res, tel
    tel["a2"] = a2
    if a2["legal"] and float(aday.height_mm) < ref_h:
        tel["secilen"] = "kafes"
        tel["kazanc_mm"] = round(ref_h - float(aday.height_mm), 2)
        tel["sure_s"] = round(time.perf_counter() - t0, 1)
        return aday, tel
    tel["red_sebep"] = ("a2-illegal" if not a2["legal"]
                       else f"ref'ten iyi degil ({aday.height_mm:.1f} >= "
                            f"{ref_h:.1f})")
    tel["sure_s"] = round(time.perf_counter() - t0, 1)
    return ref_res, tel
