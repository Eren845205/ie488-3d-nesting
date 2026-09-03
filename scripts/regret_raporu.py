# -*- coding: utf-8 -*-
"""regret_raporu.py — kural-vs-en-iyi-mod regret tablosu (ML plani Faz B).

A4 ucuz teshis: F5+K-45 kurallarinin her dev-set'te en iyi olculmus moddan
kac mm saptigini olcer. Bu tablo Faz C'nin KABUL ESIGIDIR: mod-secici model
ancak bu regret'i anlamli dusururse degerlidir (belki bazi ailelerde kural
yeterlidir — onu da bu tablo soyler).

Onemli dogruluk notu — nfv_kalite esdegeri: uretim recetesi (solve_nfv_kalite,
K-45) once HAM kosar, 5-YON (b) kilidi >0 ise GUARD'a gecer. Yani d4'te
uretim ciktisi 276.5'tir (231.5 sampiyonu rot-sokum sertifikasi ister; o
mekanizma uretim recetesinde OTOMATIK degil). Esdeger turetimi ham@2
satirinin b_kilit alanina bakar.

Sure kolonu: kalite/sure takasi gorunur olsun (d5 @1.0 = -5.5mm ama ~17x sure).
Kosum: python -m scripts.regret_raporu [--json YOL]   SAF ASCII stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.selection.dataset_v2 import HEIGHTMAP_ARM, arm_of

VARSAYILAN_JSON = _ROOT / "results" / "regret_raporu.json"


def kalite_esdegeri(armlar: Dict[str, Tuple[float, dict]]
                    ) -> Optional[Tuple[str, float]]:
    """nfv_kalite uretim-recetesinin esdeger ciktisi.

    armlar: arm -> (legal, meta) — meta'da b_kilit (5-yon) olabilir.
    Kural (K-45): ham@2 legal VE b_kilit==0 -> ham; aksi halde guard@2.
    Dogrudan olculmus nfv_kalite arm'i varsa o kazanir."""
    if "nfv_kalite" in armlar:
        return ("nfv_kalite", armlar["nfv_kalite"][0])
    ham = armlar.get("nfv_ham@2")
    if ham is not None and (ham[1].get("b_kilit") or 0) == 0:
        return ("nfv_ham@2", ham[0])
    guard = armlar.get("nfv_guard@2")
    if guard is not None:
        return ("nfv_guard@2", guard[0])
    return None


def rapor_uret(rows: list, karar_fn: Callable[[str], Tuple[str, bool]]) -> dict:
    """v2 satirlari + kural karar fonksiyonu -> rapor dict'i.

    karar_fn(set_adi) -> (mode, wall_aware) — CLI'da predict_nfv_benefit;
    testte enjekte edilir. Doner: {setler: {set: {armlar, kural_arm,
    kural_deger, regret, en_iyi, kotumser_ceza}}, n_otonom_dislanan}."""
    setler: Dict[str, dict] = {}
    n_otonom = 0
    for r in rows:
        if int(r.get("schema", 0)) != 2:
            continue
        if r.get("kaynak") == "otonom_gecmis":
            n_otonom += 1
            continue
        iid = r.get("instance_id")
        arm = arm_of(r.get("mode", ""), r.get("recete"), r.get("pitch_fine"))
        s = setler.setdefault(iid, {"armlar": {}})
        legal = r.get("legal_height_mm")
        kayit = s["armlar"].setdefault(
            arm, {"legal": None, "invalid": None, "sure_dk": None, "_meta": {}})
        if legal is None:
            if kayit["legal"] is None and kayit["invalid"] is None:
                kayit["invalid"] = r.get("invalid_reason") or "bilinmiyor"
            continue
        if kayit["legal"] is None or float(legal) < kayit["legal"]:
            kayit["legal"] = float(legal)
            kayit["invalid"] = None
            kayit["sure_dk"] = (round(r["duration_s"] / 60.0, 1)
                                if r.get("duration_s") else None)
            kayit["_meta"] = {"b_kilit": r.get("b_kilit")}

    for iid, s in setler.items():
        legal_armlar = {a: (k["legal"], k["_meta"])
                        for a, k in s["armlar"].items() if k["legal"] is not None}
        if not legal_armlar:
            s.update(kural_arm=None, kural_deger=None, regret=None,
                     en_iyi=None, kotumser_ceza=False)
            continue
        en_iyi = min(v[0] for v in legal_armlar.values())
        try:
            mode, wall = karar_fn(iid)
        except Exception as e:
            s.update(kural_arm=f"HATA:{type(e).__name__}", kural_deger=None,
                     regret=None, en_iyi=en_iyi, kotumser_ceza=False)
            continue
        if mode == "nfv":
            esdeger = kalite_esdegeri(legal_armlar)
            kural_arm, kural_deger = esdeger if esdeger else ("nfv_kalite", None)
        elif wall:
            kural_arm = "heightmap+wall_aware"
            kural_deger = (legal_armlar.get(kural_arm) or (None,))[0]
        else:
            kural_arm = HEIGHTMAP_ARM
            kural_deger = (legal_armlar.get(kural_arm) or (None,))[0]
        if kural_deger is None:
            degerler = [v[0] for v in legal_armlar.values()]
            regret = max(degerler) - min(degerler)  # kotumser (loo_regret ile tutarli)
            kotumser = True
        else:
            regret = kural_deger - en_iyi
            kotumser = False
        s.update(kural_arm=kural_arm, kural_deger=kural_deger,
                 regret=round(regret, 3), en_iyi=en_iyi, kotumser_ceza=kotumser)
        for k in s["armlar"].values():
            k.pop("_meta", None)
    return {"setler": setler, "n_otonom_dislanan": n_otonom}


def _ascii_tablo(rapor: dict) -> str:
    cizgiler = []
    for iid in sorted(rapor["setler"]):
        s = rapor["setler"][iid]
        cizgiler.append(f"== {iid} ==")
        for arm in sorted(s["armlar"]):
            k = s["armlar"][arm]
            if k["legal"] is not None:
                sure = f"  {k['sure_dk']} dk" if k["sure_dk"] else ""
                cizgiler.append(f"  {arm:<24} {k['legal']:>8.1f}{sure}")
            else:
                cizgiler.append(f"  {arm:<24} INV({k['invalid']})")
        cizgiler.append(
            f"  KURAL: {s['kural_arm']} = {s['kural_deger']}"
            f"  |  en iyi {s['en_iyi']}  |  REGRET = {s['regret']} mm"
            + ("  [KOTUMSER: kural-arm olculmemis]" if s["kotumser_ceza"] else ""))
    r_toplam = [s["regret"] for s in rapor["setler"].values()
                if s["regret"] is not None]
    if r_toplam:
        cizgiler.append(f"-- ortalama regret: {sum(r_toplam)/len(r_toplam):.1f} mm"
                        f"  maks: {max(r_toplam):.1f} mm"
                        f"  (n={len(r_toplam)} set;"
                        f" otonom dislanan {rapor['n_otonom_dislanan']})")
    return "\n".join(cizgiler)


def _kural_karari_uretim(set_adi: str) -> Tuple[str, bool]:
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    if set_adi == "deneme5":
        from scripts.ax24_kuyruk_335 import _load
        inst = _load("deneme5", (335.0, 335.0))
    else:
        from scripts.eval_gate import _load_instance
        inst = _load_instance(set_adi)
    dec = predict_nfv_benefit(inst, family_routing=True)
    return dec.mode, bool(getattr(dec, "wall_aware", False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=str(VARSAYILAN_JSON))
    args = ap.parse_args()
    from src.nesting3d.telemetry import V2_DEFAULT_PATH, load_telemetry
    rows = load_telemetry(_ROOT / V2_DEFAULT_PATH)
    rapor = rapor_uret(rows, _kural_karari_uretim)
    print(_ascii_tablo(rapor))
    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rapor, indent=1, ensure_ascii=True),
                   encoding="utf-8")
    print(f"JSON: {out}")


if __name__ == "__main__":
    main()
