# -*- coding: utf-8 -*-
"""m4_portfoy_kosu.py — M4 portfoy kosusu: karsi-olgusal mod ETIKETI uretimi.

ML_YENIDEN_YAPILANMA_PLANI_2026-08-18 §2.1 + §6 M4: her egitim-sinifi
sentetik instance x {heightmap, nfv-fast, nfv-max} kosulur; her kol icin
A2 legal-yukseklik turetilir (tam yerlesim + clearance >= esik + 5-YON
kilit = 0; telemetrideki +Z-tek n_locked AYRICA kaydedilir ama legallik
5-yonden gelir). Instance etiketi = winner_mode + kol-basi regret_mm.

Kapsam notu: shell_bells / hollow_tubes AILELERI BILEREK DISLANDI —
box-source kopruleri ici-bos geometriyi kaybeder (synthetic.py docstring
uyarisi: "doluluk-yukseklik benchmark'inda kullanilirsa sonuc yaniltici").
holey_frames source="stl" oldugu icin gercek geometriyle girer.

Cikti:
  results/m4_portfoy_etiket.jsonl  (satir = instance; append-only)
  results/m4_portfoy_ozet.json     (aile-kirilimli ozet + kosum kunyesi)
Telemetri v2 satirlari run_pipeline icinden OTOMATIK yazilir
(source = scenario["kaynak"] = "m4:<aile>:s<seed>").

Kosum (kosu disiplini — D:\\ie488'den, munhasir K-57a):
  python -m scripts.detach_run m4_portfoy_kosu
Ayar env ile (detach_run arguman gecirmez):
  M4_SEEDS     her aileden seed sayisi (default 3)
  M4_FAMILIES  virgullu aile listesi (default: hepsi)
  M4_SCALE     kucuk|orta|buyuk — mass_plate_rod_mix adet olcegi (default kucuk)

A11 statusu: bu script ETIKET URETIMIdir (veri isi) — mekanizma/kazanc
ilani DEGILDIR; sonuclar egitim tablosuna girer, kapi/promote ayri (A6).
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.format import ContainerSpec, NestingInstance  # noqa: E402

LOG = Path(__file__).parent / "m4_portfoy_kosu.log"
OUT_ETIKET = _ROOT / "results" / "m4_portfoy_etiket.jsonl"
OUT_OZET = _ROOT / "results" / "m4_portfoy_ozet.json"
PLATE = 335.0  # hoca teyitli gercek plaka (2026-07-06)
CNT = ContainerSpec(width_mm=PLATE, depth_mm=PLATE, height_mm=None)

# Kollar: (etiket_adi, nesting_mode, nfv_quality)
ARMS = (
    ("heightmap", "heightmap", None),
    ("nfv_fast", "nfv", "fast"),
    ("nfv_max", "nfv", "max"),
)

# mass_plate_rod_mix adet olcegi (fsm-SINIFI yogunluk; kucuk = smoke-ucuz)
_MPRM_QTY = {"kucuk": 40, "orta": 120, "buyuk": 300}


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Aile kayitlari — her uretici (seed, scale, stl_dir) -> NestingInstance
# ---------------------------------------------------------------------------

def _f_thin_plates(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import thin_plates
    return thin_plates(n_parts=20, container=CNT, seed=seed)


def _f_long_rods(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import long_rods
    return long_rods(n_parts=16, container=CNT, seed=seed)


def _f_random_boxes(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import random_boxes
    return random_boxes(n_parts=16, container=CNT, seed=seed)


def _f_few_large_many_small(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import few_large_many_small
    return few_large_many_small(n_large=5, n_small=20, container=CNT, seed=seed)


def _f_high_qty_repeat(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import high_qty_repeat
    return high_qty_repeat(n_models=4, qty_per_model=10, container=CNT,
                           seed=seed)


def _f_repeat_rod_mix(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import repeat_rod_mix
    return repeat_rod_mix(container=CNT, seed=seed)


def _f_mass_plate_rod_mix(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import mass_plate_rod_mix
    return mass_plate_rod_mix(qty_per_plate=_MPRM_QTY[scale],
                              container=CNT, seed=seed)


def _f_holey_frames(seed, scale, stl_dir):
    from src.nesting3d.instances.synthetic import holey_frames
    return holey_frames(stl_dir=stl_dir, container=CNT, seed=seed)


FAMILY_BUILDERS = {
    "thin_plates": _f_thin_plates,
    "long_rods": _f_long_rods,
    "random_boxes": _f_random_boxes,
    "few_large_many_small": _f_few_large_many_small,
    "high_qty_repeat": _f_high_qty_repeat,
    "repeat_rod_mix": _f_repeat_rod_mix,
    "mass_plate_rod_mix": _f_mass_plate_rod_mix,
    "holey_frames": _f_holey_frames,
}


# ---------------------------------------------------------------------------
# Saf mantik (test edilir) — etiket turetimi
# ---------------------------------------------------------------------------

def kol_legal_mi(kol: Dict[str, Any], clearance_req: float) -> Optional[str]:
    """A2 uc-sart denetimi; legal ise None, degilse sebep string'i dondur.

    Kilit karari 5-YON metriginden (n_locked_5dir) — telemetrideki +Z-tek
    n_locked yalniz kayit. Olculemeyen bilesen (None) = INVALID (ANAYASA:
    kanitsizlik gecer not degildir). Rot-sokum denetimi BURADA KOSULMAZ;
    5-yon kilit>0 etikette invalid sayilir (konservatif taraf).
    """
    if kol.get("hata"):
        return f"kosu hatasi: {kol['hata']}"
    if int(kol.get("n_placed") or 0) != int(kol.get("n_total") or -1):
        return f"eksik yerlesim {kol.get('n_placed')}/{kol.get('n_total')}"
    cl = kol.get("min_clearance_mm")
    if cl is None:
        return "clearance olculemedi"
    if float(cl) < clearance_req:
        return f"clearance {float(cl):.3f}<{clearance_req}"
    n5 = kol.get("n_locked_5dir")
    if n5 is None:
        return "5-yon sokum olculemedi"
    if int(n5) > 0:
        return f"{int(n5)} kilit (5-yon)"
    return None


def etiket_hesapla(arms: Dict[str, Dict[str, Any]],
                   clearance_req: float) -> Dict[str, Any]:
    """Kol sonuclarindan winner_mode + regret_mm etiketi turet.

    regret_mm yalniz LEGAL kollar icin hesaplanir (h_kol - h_winner);
    invalid kol -> None. Hicbir kol legal degilse winner_mode None
    (etiket egitime girmez, kayit denetim izinde kalir).
    """
    legal_h: Dict[str, float] = {}
    sebepler: Dict[str, Optional[str]] = {}
    for ad, kol in arms.items():
        sebep = kol_legal_mi(kol, clearance_req)
        sebepler[ad] = sebep
        if sebep is None:
            legal_h[ad] = float(kol["height_mm"])
    if not legal_h:
        return {"winner_mode": None,
                "regret_mm": {ad: None for ad in arms},
                "invalid_reasons": sebepler, "n_legal": 0}
    winner = min(legal_h, key=lambda a: legal_h[a])
    h_win = legal_h[winner]
    regret = {ad: (round(legal_h[ad] - h_win, 2) if ad in legal_h else None)
              for ad in arms}
    return {"winner_mode": winner, "regret_mm": regret,
            "invalid_reasons": sebepler, "n_legal": len(legal_h)}


def scenario_kur(inst: NestingInstance, mode: str,
                 nfv_quality: Optional[str], seed: int,
                 kaynak: str, rich_scenario: Dict[str, Any],
                 order_id: str = "M4-PORTFOY") -> Dict[str, Any]:
    """Zorlanmis-mod run_pipeline senaryosu (k65 deseni; stl_path korunur)."""
    parts = []
    for p in inst.parts:
        d = {"id": p.id, "name": p.name, "qty": int(p.qty),
             "source": str(p.source),
             "width_mm": float(p.width_mm), "depth_mm": float(p.depth_mm),
             "height_mm": float(p.height_mm)}
        if getattr(p, "stl_path", None):
            d["stl_path"] = str(p.stl_path)
        parts.append(d)
    sc = {**rich_scenario, "seed": seed,
          "orders": [{"order_id": order_id, "customer": "SYN",
                      "deadline": "2026-12-31", "priority_class": 2,
                      "parts": parts}],
          "container": {"width_mm": float(inst.container.width_mm),
                        "depth_mm": float(inst.container.depth_mm)},
          "nesting_mode": mode,
          "auto_family_routing": False,
          "kaynak": kaynak}
    if nfv_quality is not None:
        sc["nfv_quality"] = nfv_quality
    return sc


# ---------------------------------------------------------------------------
# Kosu
# ---------------------------------------------------------------------------

def _kol_kos(inst: NestingInstance, mode: str, nfv_quality: Optional[str],
             seed: int, kaynak: str) -> Dict[str, Any]:
    """Tek kolu kos; kol sonucu sozlugu dondur (hata durumunda 'hata' alani)."""
    from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
    from src.nesting3d.accessibility import check_separability_5dir
    n_total = sum(int(p.qty) for p in inst.parts)
    kol: Dict[str, Any] = {"n_total": n_total}
    t0 = time.time()
    try:
        sc = scenario_kur(inst, mode, nfv_quality, seed, kaynak,
                          RICH_SCENARIO)
        r = run_pipeline(sc)
        nr = (r.get("nesting_results") or {}).get("B001") or {}
        kol["height_mm"] = float(nr.get("height_mm") or 0.0)
        kol["n_placed"] = int(nr.get("n_parts") or 0)
        kol["min_clearance_mm"] = nr.get("min_clearance_mm")
        kol["n_locked_z"] = nr.get("n_locked")  # +Z-tek (telemetri metrigi)
        kol["pitch_mm"] = nr.get("pitch_mm")
        kol["duration_s"] = round(float(nr.get("elapsed_sec") or 0.0), 2)
        # A2 uretim metrigi: 5-yon sirali sokum (rot-sokum katmani YOK —
        # konservatif; kilit>0 etikette invalid)
        pls = nr.get("placements")
        vps = nr.get("voxel_parts")
        if pls is not None and vps is not None and kol["n_placed"] > 0:
            try:
                kol["n_locked_5dir"] = int(
                    check_separability_5dir(list(pls), vps).n_locked)
            except Exception as exc:
                kol["n_locked_5dir"] = None
                kol["sokum_hata"] = str(exc)
        elif kol["n_placed"] == 0:
            kol["n_locked_5dir"] = None
    except Exception as exc:
        kol["hata"] = str(exc)
    kol["wall_s"] = round(time.time() - t0, 2)
    return kol


def main() -> int:
    seeds = int(os.environ.get("M4_SEEDS", "3"))
    scale = os.environ.get("M4_SCALE", "kucuk")
    if scale not in _MPRM_QTY:
        log(f"HATA: M4_SCALE '{scale}' gecersiz ({sorted(_MPRM_QTY)})")
        return 2
    fam_env = os.environ.get("M4_FAMILIES", "")
    families = ([f.strip() for f in fam_env.split(",") if f.strip()]
                if fam_env else list(FAMILY_BUILDERS))
    bilinmeyen = [f for f in families if f not in FAMILY_BUILDERS]
    if bilinmeyen:
        log(f"HATA: bilinmeyen aile(ler): {bilinmeyen}")
        return 2

    from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
    clearance_req = float(WEB_MIN_CLEARANCE_MM)
    stl_dir = _ROOT / "tmp" / "m4_stl"

    log("=" * 70)
    log("M4 PORTFOY KOSUSU — karsi-olgusal mod etiketi (ML plan §2.1)")
    log(f"aileler={families}")
    log(f"seeds={seeds}  scale={scale}  clearance_req={clearance_req}mm")
    log("kollar=" + ", ".join(a[0] for a in ARMS))
    log("NOT: etiket uretimi — kazanc ilani DEGILDIR (A11); kilit karari")
    log("     5-yon metriginden, rot-sokum katmani kosulmaz (konservatif).")
    log("=" * 70)
    t0 = time.time()
    OUT_ETIKET.parent.mkdir(exist_ok=True)

    ozet: Dict[str, Any] = {a: {"winner": {}, "invalid": 0, "n": 0}
                            for a in families}
    n_hata = 0
    for aile in families:
        builder = FAMILY_BUILDERS[aile]
        for s in range(seeds):
            iid = f"m4_{aile}_s{s}"
            kaynak = f"m4:{aile}:s{s}"
            try:
                inst = builder(s, scale, stl_dir)
            except Exception as exc:
                log(f"{iid}: INSTANCE URETILEMEDI: {exc}")
                n_hata += 1
                continue
            n_total = sum(int(p.qty) for p in inst.parts)
            log(f"\n{iid}  (n_parca={n_total})")
            arms: Dict[str, Dict[str, Any]] = {}
            for ad, mode, q in ARMS:
                kol = _kol_kos(inst, mode, q, seed=42, kaynak=kaynak)
                arms[ad] = kol
                if kol.get("hata"):
                    n_hata += 1
                    log(f"  {ad:10s}: KOSU HATASI {kol['hata']}")
                else:
                    log(f"  {ad:10s}: h={kol['height_mm']:7.1f}  "
                        f"cl={kol.get('min_clearance_mm')}  "
                        f"kilitZ={kol.get('n_locked_z')}  "
                        f"kilit5={kol.get('n_locked_5dir')}  "
                        f"sure={kol['wall_s']:.0f}s")
            et = etiket_hesapla(arms, clearance_req)
            satir = {"ts": time.time(), "instance_id": iid, "aile": aile,
                     "seed": s, "scale": scale, "n_total": n_total,
                     "clearance_req_mm": clearance_req,
                     "arms": arms, **et}
            # placements/voxel_parts JSONL'e YAZILMAZ (agir; kol sozlugunde yok)
            with OUT_ETIKET.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(satir, ensure_ascii=True,
                                    default=str) + "\n")
            oz = ozet[aile]
            oz["n"] += 1
            if et["winner_mode"] is None:
                oz["invalid"] += 1
            else:
                oz["winner"][et["winner_mode"]] = (
                    oz["winner"].get(et["winner_mode"], 0) + 1)
            log(f"  ETIKET: winner={et['winner_mode']}  "
                f"regret={et['regret_mm']}  n_legal={et['n_legal']}")

    log("")
    log("=" * 70)
    log("AILE KIRILIMI (winner sayimlari; invalid = hic legal kol yok):")
    for aile, oz in ozet.items():
        log(f"  {aile:22s}: n={oz['n']}  winner={oz['winner']}  "
            f"invalid={oz['invalid']}")
    kunye = {"tarih": str(date.today()), "seeds": seeds, "scale": scale,
             "families": families, "clearance_req_mm": clearance_req,
             "arms": [a[0] for a in ARMS], "n_hata": n_hata,
             "sure_s": round(time.time() - t0, 1),
             "etiket_dosyasi": str(OUT_ETIKET),
             "a11_not": ("etiket uretimi (veri isi); kazanc ilani degildir; "
                         "kilit=5-yon konservatif, rot-sokum kosulmadi")}
    OUT_OZET.write_text(json.dumps({"kunye": kunye, "aile_kirilimi": ozet},
                                   indent=2, ensure_ascii=True),
                        encoding="utf-8")
    log(f"KAYIT: {OUT_ETIKET}")
    log(f"KAYIT: {OUT_OZET}")
    log(f"BITTI  hata={n_hata}  sure={time.time() - t0:.0f}s")
    return 0 if n_hata == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
