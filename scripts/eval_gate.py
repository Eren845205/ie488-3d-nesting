# -*- coding: utf-8 -*-
"""eval_gate.py — STRATEJI Faz-0: tek-komut degerlendirme kapisi.

Amac (STRATEJI/02_EVAL_KAPISI.md §2, §5 Faz-0): her "iyilestirme iddiasi"
sonrasi TUM dev-set'leri URETIM sampiyonu yollarindan kosar, DURUST metrigi
(legal_height: yerlesen==N ve min_clearance>=1mm ve 0 kilit) olcer, baseline
ile kiyaslar, ANAYASA B2 esikleriyle verdict basar. Yeni algoritma YOK —
mevcut parcalarin konsolidasyonu (c3_generality DATASETS + clearance.
min_clearance + accessibility.check_placements + uretim solve yollari).

Kullanim:
  python -m scripts.eval_gate --save-baseline          # ilk koşu: baseline yaz
  python -m scripts.eval_gate                          # kiyas + verdict
  python -m scripts.eval_gate --sets deneme4           # tek set (smoke)
  python -m scripts.eval_gate --heldout-final --sets boxy   # held-out FINAL kosusu
                                                       # (bakisi 01_VERI registry'ye YAZ!)
Esikler (00_ANAYASA B2): herhangi bir set >%2 kotu veya INVALID -> FAIL;
+-%0.5 gurultu bandi; hicbiri kotulesmeden >=1 set iyilesme -> PASS; arasi
-> INSAN KARARI. Held-out setler --heldout-final bayragi olmadan REDDEDILIR.

Sampiyon yollar (uretim paritesi = URETIM DEFAULT'U):
  plan1/plan2/plan3 : solve_coarse_to_fine default heightmap yolu
                      (clearance_mm=1.0, a274628 kablosu) — uretim default'u.
                      NOT: NFV kalite modu (opt-in) SAMPIYON DEGIL — ilk kapi
                      kosusu (2026-07-06) NFV'yi plan ailesinde A2 ile INVALID
                      olctu: clearance 0.083/0.055mm (HIGH-3 olculdu) +
                      plan1 81 / plan3 87 KILIT (K-21'in plan karsiligi).
                      NFV ancak legallik isi (F2-v2 + NFV-clearance) gecince
                      sampiyonluga aday olur; o degisiklik de bu kapidan gecer.
  deneme4           : solve_coarse_to_fine wall_aware 264-config (plate 325,
                      fine 0.5, dblf_only, skip_fine_angle, drop_cache,
                      clearance_mm=1.0) — beklenen anchor 264.0mm
  boxy (held-out)   : ayni heightmap yolu, auto-plaka, clearance 1.0

Cikti: ASCII tablo + results/eval_gate_last.json (+ --save-baseline ile
results/eval_gate_baseline.json). Stdout SAF ASCII (cp1254).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.tuner import build_menu  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from scripts.c3_generality import DATASETS, _boxy_stl_map_and_qty  # noqa: E402

BASELINE = _ROOT / "results" / "eval_gate_baseline.json"
LAST = _ROOT / "results" / "eval_gate_last.json"

CLEARANCE_REQ_MM = 1.0
FAIL_PCT = 2.0    # B2: bir sette bundan fazla kotulesme -> FAIL
NOISE_PCT = 0.5   # B2: voxel-kuantizasyon gurultu bandi

# Faz-1: roller data/registry.json'dan (tek dogruluk kaynagi; 01_VERI §2).
# Registry yoksa/bozuksa guvenli fallback sabitler.
REGISTRY = _ROOT / "data" / "registry.json"
_KOSULABILIR = {"plan1", "plan2", "plan3", "deneme4", "boxy"}  # config'i olanlar


def _load_roles():
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        sets = reg.get("sets", {})
        dev = [s for s, v in sets.items()
               if v.get("rol") == "dev" and s in _KOSULABILIR]
        held = [s for s, v in sets.items()
                if v.get("rol") == "held-out" and s in _KOSULABILIR]
        if dev:
            return dev, held
    except Exception:
        pass
    return (["plan1", "plan2", "plan3", "deneme4"], ["boxy"])


def _log_heldout_bakis(set_names, reason):
    """A3: held-out'a her bakis registry'ye tarihle islenir (yapisal, unutulmaz)."""
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        reg.setdefault("bakislar", []).append({
            "setler": list(set_names),
            "tarih": datetime.now().isoformat(timespec="seconds"),
            "sebep": reason or "belirtilmedi",
        })
        REGISTRY.write_text(json.dumps(reg, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    except Exception as exc:  # bakis loglanamiyorsa kosu da OLMAZ (A3 sert)
        raise RuntimeError(f"held-out bakisi registry'ye yazilamadi: {exc}")


DEV_SETS, HELDOUT_SETS = _load_roles()
# Hoca cevabi 2026-07-06: deneme4 gercek plaka 335-2x5 kenar = 325x325
DENEME4_PLATE = (325.0, 325.0)


# ---------------------------------------------------------------------------
# Sampiyon kosucular
# ---------------------------------------------------------------------------

def _load_instance(name):
    if name == "boxy":
        stl_map, qty = _boxy_stl_map_and_qty()
        plate = None
    else:
        cfg = DATASETS[name]
        stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
        qty = cfg["qty"]
        plate = cfg["plate"]
    if name == "deneme4":
        plate = DENEME4_PLATE
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"gen_{name}"}
    if plate is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = plate
    res = build_instance_from_order(stl_map, qty, **kwargs)
    return res.instance


def _run_champion(name, inst, seed, budget=None, n_orientations=None):
    """Set'in URETIM DEFAULT yolunu kosar -> result (placements/fine_voxel_parts/height).

    Uretim paritesi demo_pipeline zinciriyle BIREBIR (elle config YOK):
      wall_aware = predict_nfv_benefit(family_routing=True).wall_aware  (F5)
      pitch      = suggest_pitch(instance, wall_aware=...)              (K-19)
      solve_coarse_to_fine(budget=COARSE_BUDGET, menu=dblf_only|None,
                           skip_fine_angle=wall, drop_cache=wall,
                           clearance_mm=WEB_MIN_CLEARANCE_MM)
    deneme4'te bu zincir 264-config'i KENDISI uretir (zincir testi 3/3 +
    anchor 264.0 bu kapida iki kez birebir dogrulandi).
    NFV kalite modu bilerek DISARIDA (docstring'deki EVAL-1 INVALID bulgusu)."""
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.instances.pitch import suggest_pitch
    from scripts.demo_pipeline import COARSE_BUDGET, WEB_MIN_CLEARANCE_MM

    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    dec = predict_nfv_benefit(inst, family_routing=True)
    wall = bool(getattr(dec, "wall_aware", False))
    pitch = suggest_pitch(inst, wall_aware=wall)
    kw = dict(coarse_pitch=None, fine_pitch=pitch,
              budget=(budget if budget is not None else COARSE_BUDGET),
              seed=seed, drop_cache=wall, skip_fine_angle=wall,
              clearance_mm=WEB_MIN_CLEARANCE_MM)
    if n_orientations is not None:
        kw["n_orientations"] = n_orientations  # tune_bo override (04 §1)
    if wall:
        kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
    print(f"    [{name}] routing: wall_aware={wall}  pitch={pitch}", flush=True)
    return solve_coarse_to_fine(inst, plate_w_mm=pw, plate_d_mm=pd, **kw)


# ---------------------------------------------------------------------------
# Durust metrik (SAF fonksiyonlar — test edilir)
# ---------------------------------------------------------------------------

def legal_of(height_mm, n_placed, n_total, min_clear_mm, n_locked,
             clearance_req=CLEARANCE_REQ_MM):
    """(legal_height | None, invalid_reason | None) — ANAYASA A2 tanimi.

    min_clear_mm None = olculemedi -> INVALID (kanitsizlik gecer not verilmez);
    --skip-clearance ile bilerek atlanirsa cagiran bunu isaretler.
    """
    reasons = []
    if n_placed != n_total:
        reasons.append(f"eksik yerlesim {n_placed}/{n_total}")
    if min_clear_mm is None:
        reasons.append("clearance olculemedi")
    elif min_clear_mm < clearance_req:
        reasons.append(f"clearance {min_clear_mm:.3f}<{clearance_req}")
    if n_locked is None:
        reasons.append("erisilebilirlik olculemedi")
    elif n_locked > 0:
        reasons.append(f"{n_locked} kilit")
    if reasons:
        return None, "; ".join(reasons)
    return float(height_mm), None


def compare_verdict(cur, base, fail_pct=FAIL_PCT, noise_pct=NOISE_PCT):
    """{set: legal|None} x2 -> (overall, {set: (delta_pct|None, durum)}).

    overall: PASS | FAIL | INSAN-KARARI | NOOP | BASELINE-YOK
    Yukseklik kucuk=iyi. delta_pct = (cur-base)/base*100 (pozitif = KOTU).
    """
    if base is None:
        return "BASELINE-YOK", {s: (None, "baseline yok") for s in cur}
    per = {}
    any_fail = any_worse = any_better = False
    for s, c in cur.items():
        b = base.get(s)
        if c is None:
            per[s] = (None, "INVALID -> FAIL")
            any_fail = True
        elif b is None:
            per[s] = (None, "baseline INVALID/yok -> iyilesme")
            any_better = True
        else:
            d = (c - b) / b * 100.0
            if d > fail_pct:
                per[s] = (d, f"> +%{fail_pct} -> FAIL")
                any_fail = True
            elif d > noise_pct:
                per[s] = (d, "kotulesme (gurultu ustu)")
                any_worse = True
            elif d < -noise_pct:
                per[s] = (d, "iyilesme")
                any_better = True
            else:
                per[s] = (d, "degisim yok (gurultu bandi)")
    if any_fail:
        return "FAIL", per
    if any_worse:
        return "INSAN-KARARI", per
    if any_better:
        return "PASS", per
    return "NOOP", per


# ---------------------------------------------------------------------------
# Ana akis
# ---------------------------------------------------------------------------

def evaluate_set(name, seed, skip_clearance=False, budget=None,
                 n_orientations=None):
    t0 = time.perf_counter()
    inst = _load_instance(name)
    n_total = sum(int(p.qty) for p in inst.parts)
    r = _run_champion(name, inst, seed, budget=budget,
                      n_orientations=n_orientations)
    n_placed = int(getattr(r, "n_placed", len(r.placements)))
    height = float(r.height_mm)

    min_clear = None
    if not skip_clearance:
        pitch = float(getattr(r, "fine_pitch"))
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch)
        rep = min_clearance(meshes)
        min_clear = float(rep.min_mm)

    n_locked = int(check_placements(r.placements, r.fine_voxel_parts).n_locked)

    legal, reason = legal_of(height, n_placed, n_total, min_clear, n_locked)
    if skip_clearance and reason == "clearance olculemedi":
        reason += " (--skip-clearance)"
    return {
        "legal_height_mm": legal, "invalid_reason": reason,
        "height_mm": height, "n_placed": n_placed, "n_total": n_total,
        "min_clearance_mm": min_clear, "n_locked": n_locked,
        "duration_s": round(time.perf_counter() - t0, 1),
    }


def main():
    ap = argparse.ArgumentParser(description="STRATEJI Faz-0 eval kapisi")
    ap.add_argument("--sets", default=",".join(DEV_SETS),
                    help=f"virgullu set listesi (default: {','.join(DEV_SETS)})")
    ap.add_argument("--baseline", type=Path, default=BASELINE)
    ap.add_argument("--save-baseline", action="store_true",
                    help="bu kosuyu baseline olarak YAZ (bilincli karar!)")
    ap.add_argument("--heldout-final", action="store_true",
                    help="held-out setleri kosmaya izin (bakis registry'ye OTOMATIK yazilir)")
    ap.add_argument("--reason", default=None,
                    help="held-out bakis sebebi (registry bakislar kaydina gider)")
    ap.add_argument("--skip-clearance", action="store_true",
                    help="clearance olcumunu atla (SONUC INVALID kalir; hizli debug)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sets = [s.strip() for s in args.sets.split(",") if s.strip()]
    bilinmeyen = [s for s in sets if s not in DEV_SETS + HELDOUT_SETS]
    if bilinmeyen:
        print(f"HATA: bilinmeyen set(ler): {bilinmeyen}. "
              f"Gecerli: {DEV_SETS + HELDOUT_SETS}")
        sys.exit(2)
    heldout_istenen = [s for s in sets if s in HELDOUT_SETS]
    if heldout_istenen and not args.heldout_final:
        print(f"RED (ANAYASA A3): {heldout_istenen} HELD-OUT. Final dogrulama "
              f"icin --heldout-final (+--reason) ekle. Held-out ile TUNING YASAK.")
        sys.exit(3)
    if heldout_istenen:
        _log_heldout_bakis(heldout_istenen, args.reason)
        print(f"[registry] held-out bakisi loglandi: {heldout_istenen} "
              f"(sebep: {args.reason or 'belirtilmedi'})")

    print("=" * 78)
    print(f"EVAL KAPISI (Faz-0) — setler: {sets}  seed={args.seed}  "
          f"clearance_req={CLEARANCE_REQ_MM}mm")
    print("=" * 78, flush=True)

    results = {}
    for name in sets:
        print(f"[{name}] kosuyor...", flush=True)
        try:
            results[name] = evaluate_set(name, args.seed, args.skip_clearance)
        except Exception as e:  # bir setin cokusu digerlerini olcmeyi engellemesin
            results[name] = {
                "legal_height_mm": None, "invalid_reason": f"EXCEPTION: {e}",
                "height_mm": None, "n_placed": None, "n_total": None,
                "min_clearance_mm": None, "n_locked": None, "duration_s": None,
            }
        r = results[name]
        lh = r["legal_height_mm"]
        lh_s = f"{lh:.1f}mm" if lh is not None else f"INVALID({r['invalid_reason']})"
        print(f"[{name}] legal_height={lh_s}  ham={r['height_mm']}  "
              f"clear={r['min_clearance_mm']}  kilit={r['n_locked']}  "
              f"({r['duration_s']}s)", flush=True)

    # --- kiyas ---------------------------------------------------------------
    base = None
    if args.baseline.exists():
        base_doc = json.loads(args.baseline.read_text(encoding="utf-8"))
        base = {s: v.get("legal_height_mm") for s, v in base_doc["sets"].items()}
    cur = {s: r["legal_height_mm"] for s, r in results.items()}
    overall, per = compare_verdict(
        cur, {s: base.get(s) for s in cur} if base is not None else None)

    print("-" * 78)
    print(f"  {'set':<10} {'baseline':>10} {'simdi':>10} {'delta%':>8}  durum")
    for s in sets:
        b = (base or {}).get(s)
        c = cur[s]
        d, durum = per[s]
        print(f"  {s:<10} {(f'{b:.1f}' if b is not None else 'INV/yok'):>10} "
              f"{(f'{c:.1f}' if c is not None else 'INVALID'):>10} "
              f"{(f'{d:+.2f}' if d is not None else '-'):>8}  {durum}")
    print("-" * 78)
    print(f"  VERDICT: {overall}")
    if overall == "INSAN-KARARI":
        print("  -> trade-off tablosunu Eren'e sun; karar insana ait (B2).")
    print("=" * 78)

    # --- yazim ---------------------------------------------------------------
    doc = {
        "schema": 1, "created": datetime.now().isoformat(timespec="seconds"),
        "seed": args.seed, "clearance_req_mm": CLEARANCE_REQ_MM,
        "sets": results, "verdict": overall,
    }
    LAST.parent.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"yazildi: {LAST}")
    if args.save_baseline:
        invalids = [s for s, v in cur.items() if v is None]
        if invalids:
            print(f"BASELINE YAZILMADI: INVALID set(ler) var: {invalids} — "
                  f"bozuk baseline kilitlenemez.")
            sys.exit(4)
        args.baseline.write_text(
            json.dumps(doc, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"BASELINE yazildi: {args.baseline}")
    sys.exit(0 if overall in ("PASS", "NOOP", "BASELINE-YOK") else 1)


if __name__ == "__main__":
    main()
