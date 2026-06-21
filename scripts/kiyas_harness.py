"""kiyas_harness.py — Faz 0: tekrarlanabilir Magics kıyas ölçüm altyapısı.

PLAN_IYILESTIRME_YOLHARITASI.md Faz 0. Tek script ile Plan1/Plan2 (ileride Plan3)
hoca verisini sabit tohum + sabit plakada koşar; (yükseklik, doluluk, süre,
yerleşen/toplam, oran) tablosunu basar ve results/kiyas_sonuclari.csv'ye append
eder. Böylece her iyileştirme fazı ÖNCE/SONRA aynı ölçütle karşılaştırılır.

İki mod:
  --mode kesin  : tam pipeline (run_pipeline), auto/suggest_pitch (~0.5mm),
                  Plan2'de ~78 dk. Resmî kıyas rakamı.
  --mode hizli  : solve_coarse_to_fine'a fine_pitch elle override (default 1.5mm),
                  dakikalar yerine saniye/dakika; YAKLAŞIK (biraz yüksek tahmin),
                  faz geliştirme döngüsü için hızlı sinyal.
                  (run_pipeline pitch'i fallback olduğundan — demo_pipeline:576
                   suggest_pitch her zaman kazanır — hızlı mod doğrudan C2F çağırır.)

Kullanım:
  PYTHONIOENCODING=utf-8 python -u scripts/kiyas_harness.py --plan plan1 --mode hizli
  PYTHONIOENCODING=utf-8 python -u scripts/kiyas_harness.py --plan all --mode kesin --tag faz1-sonrasi

Determinizm: sabit seed (default 42) → aynı girdi aynı sonuç. --tag ile CSV'de
hangi faz/değişiklik olduğunu işaretle (regresyon takibi).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
CSV_PATH = ROOT / "results" / "kiyas_sonuclari.csv"

# --- Plan tanımları (adetler mail görsellerinden; PLAN_KIYAS_IYILESTIRME.md §1) ---
# plate: (w_mm, d_mm) sabit hoca plakası, veya None → parçalardan otomatik.
# hoca_height_mm: Magics referansı (varsa); None → oran hesaplanmaz.
PLANS = {
    "plan1": {
        "stl_dir": VERILER / "Plan1" / "Plan1",
        "plate": None,           # auto plaka (hoca Plan1 plakası elimizde yok)
        "hoca_height_mm": None,  # hoca Plan1 yüksekliği gelmedi
        "qty": {
            "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
            "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6,
            "811791-1": 19, "pyramid_with_doors": 5, "MTShoe": 1,
            "M18_toShopVac_Adapter": 2, "part262835": 2, "baseplate_v2": 1,
        },
    },
    "plan2": {
        "stl_dir": VERILER / "Plan2" / "Plan2",
        "plate": (328.74, 328.19),  # HOCA plakası (adil kıyas — Plan2.jpg)
        "hoca_height_mm": 492.39,
        "qty": {
            "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
            "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
            "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
            "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
            "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
            "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
            "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
            "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
        },
    },
}

CSV_COLUMNS = [
    "timestamp", "tag", "plan", "mode", "n_orientations", "pitch_mm",
    "height_mm", "hoca_height_mm", "oran", "density_pct",
    "n_placed", "n_total", "sec", "winner_algo",
]


def _load_instance(plan, plan_cfg):
    """STL'leri oku + adetlerle NestingInstance kur (eksik/fazla uyarısı basar).

    persist_dir ŞART: build_instance_from_order STL'leri diske yazar ve
    stl_path'i oraya gösterir; verilmezse temp'e yazıp siler → to_voxel_parts
    'string is not a file' ile çöker.
    """
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order

    stl_dir = plan_cfg["stl_dir"]
    qty = plan_cfg["qty"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(stl_dir.glob("*.stl"))}
    eksik = set(k.lower() for k in qty) - set(k.lower() for k in stl_map)
    if eksik:
        print(f"  UYARI adet var STL yok: {sorted(eksik)}", flush=True)

    plate = plan_cfg["plate"]
    kwargs = {"persist_dir": ROOT / "data" / "mail_stl" / f"{plan}_harness"}
    if plate is not None:
        kwargs["container_w_mm"] = plate[0]
        kwargs["container_d_mm"] = plate[1]
    res = build_instance_from_order(stl_map, qty, **kwargs)
    return res.instance


def _run_kesin(plan, plan_cfg, seed, n_orient):
    """Tam pipeline (run_pipeline) — resmî kıyas. auto/suggest_pitch."""
    from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order

    stl_dir = plan_cfg["stl_dir"]
    qty = plan_cfg["qty"]
    plate = plan_cfg["plate"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(stl_dir.glob("*.stl"))}
    kwargs = {"persist_dir": ROOT / "data" / "mail_stl" / f"{plan}_harness"}
    if plate is not None:
        kwargs["container_w_mm"] = plate[0]
        kwargs["container_d_mm"] = plate[1]
    res = build_instance_from_order(stl_map, qty, **kwargs)

    parts = [{
        "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
        "stl_path": p.stl_path, "width_mm": p.width_mm,
        "depth_mm": p.depth_mm, "height_mm": p.height_mm,
    } for p in res.instance.parts]
    order = {"order_id": plan.upper(), "customer": f"HOCA-{plan.upper()}",
             "deadline": "2026-12-31", "priority_class": 2, "parts": parts}
    container = (None if plate is None else
                 {"width_mm": plate[0], "depth_mm": plate[1], "height_mm": None})
    scenario = {**RICH_SCENARIO, "orders": [order], "container": container,
                "seed": seed, "n_orientations": n_orient}

    t0 = time.perf_counter()
    result = run_pipeline(scenario)
    dt = time.perf_counter() - t0

    bid = next(iter(result["nesting_results"]))
    nr = result["nesting_results"][bid]
    return {
        "pitch_mm": nr.get("pitch_mm"),
        "height_mm": round(nr["height_mm"], 1),
        "density_pct": round(nr["density"] * 100, 1),
        "n_placed": nr["n_parts"],
        "n_total": sum(qty.values()),
        "sec": round(dt, 1),
        "winner_algo": (nr.get("tuner") or {}).get("winning_config"),
    }


def _run_hizli(plan, plan_cfg, seed, n_orient, fine_pitch, budget,
               fine_angle_window=0.0, fine_angle_step=1.0, fine_angle_axes="z",
               fine_angle_safe=True, adaptive=False):
    """solve_coarse_to_fine doğrudan, fine_pitch override — hızlı YAKLAŞIK."""
    from src.nesting3d.coarse_to_fine import solve_coarse_to_fine

    instance = _load_instance(plan, plan_cfg)
    plate = plan_cfg["plate"]
    if plate is not None:
        pw, pd = plate
    else:
        # auto plaka — parçalardan türet
        from src.nesting3d.instances.plate import resolve_container
        pdims = [(p.width_mm, p.depth_mm, p.height_mm) for p in instance.parts]
        pw, pd, _ch, _ = resolve_container(
            {"width_mm": None, "depth_mm": None, "height_mm": None}, pdims)

    t0 = time.perf_counter()
    r = solve_coarse_to_fine(
        instance, plate_w_mm=float(pw), plate_d_mm=float(pd),
        coarse_pitch=None, fine_pitch=fine_pitch, budget=budget, seed=seed,
        n_orientations=n_orient,
        fine_angle_window=fine_angle_window, fine_angle_step=fine_angle_step,
        fine_angle_axes=fine_angle_axes, fine_angle_safe=fine_angle_safe,
        adaptive=adaptive,
    )
    dt = time.perf_counter() - t0
    return {
        "pitch_mm": fine_pitch,
        "height_mm": round(r.height_mm, 1),
        "density_pct": round(r.density * 100, 1),
        "n_placed": r.n_placed,
        "n_total": sum(plan_cfg["qty"].values()),
        "sec": round(dt, 1),
        "winner_algo": f"c2f-hizli:{r.winning_config}",
        "adaptive_reason": getattr(r, "adaptive_reason", None),
    }


def _append_csv(row):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        if is_new:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="Faz 0 kıyas ölçüm harness'ı")
    ap.add_argument("--plan", choices=["plan1", "plan2", "all"], default="all")
    ap.add_argument("--mode", choices=["kesin", "hizli"], default="hizli")
    ap.add_argument("--fine-pitch", type=float, default=1.5,
                    help="hızlı modda ince pitch (mm); 1mm parça için >0.5 olmalı")
    ap.add_argument("--budget", type=int, default=25, help="hızlı mod arama bütçesi")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-orientations", type=int, default=4,
                    help="rotasyon poz sayısı (Faz 2'de artırılacak)")
    ap.add_argument("--fine-angle-window", type=float, default=0.0,
                    help="ince-açı refinement penceresi (derece); 0=kapalı (Faz 2b)")
    ap.add_argument("--fine-angle-step", type=float, default=1.0,
                    help="ince-açı adımı (derece, varsayılan 1.0)")
    ap.add_argument("--fine-angle-axes", default="z",
                    help="perturbasyon eksenleri: 'z' (in-plane) veya 'xyz'")
    ap.add_argument("--fine-angle-unsafe", action="store_true",
                    help="güvenli karşılaştırmayı KAPAT (refined koşulsuz; ham etki ölçümü)")
    ap.add_argument("--adaptive", action="store_true",
                    help="ince-açıyı kutuluk özelliğinden OTOMATIK seç (veri-odaklı)")
    ap.add_argument("--tag", default="", help="CSV etiketi (örn 'faz1-sonrasi')")
    args = ap.parse_args()

    plans = ["plan1", "plan2"] if args.plan == "all" else [args.plan]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for plan in plans:
        cfg = PLANS[plan]
        print(f"\n=== {plan.upper()} | mode={args.mode} | seed={args.seed} | "
              f"n_orient={args.n_orientations} ===", flush=True)
        if args.mode == "kesin":
            m = _run_kesin(plan, cfg, args.seed, args.n_orientations)
        else:
            m = _run_hizli(plan, cfg, args.seed, args.n_orientations,
                           args.fine_pitch, args.budget,
                           fine_angle_window=args.fine_angle_window,
                           fine_angle_step=args.fine_angle_step,
                           fine_angle_axes=args.fine_angle_axes,
                           fine_angle_safe=not args.fine_angle_unsafe,
                           adaptive=args.adaptive)

        hoca = cfg["hoca_height_mm"]
        oran = round(m["height_mm"] / hoca, 3) if hoca else None
        row = {
            "timestamp": ts, "tag": args.tag, "plan": plan, "mode": args.mode,
            "n_orientations": args.n_orientations, "pitch_mm": m["pitch_mm"],
            "height_mm": m["height_mm"], "hoca_height_mm": hoca, "oran": oran,
            "density_pct": m["density_pct"], "n_placed": m["n_placed"],
            "n_total": m["n_total"], "sec": m["sec"],
            "winner_algo": m["winner_algo"],
        }
        rows.append(row)
        _append_csv(row)
        print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)
        if m.get("adaptive_reason"):
            print(f"  ADAPTİF KARAR: {m['adaptive_reason']}", flush=True)

    print("\n=== ÖZET TABLO ===", flush=True)
    hdr = f"{'plan':<6} {'mode':<6} {'pitch':>6} {'yuk_mm':>8} {'hoca':>7} " \
          f"{'oran':>6} {'dol%':>6} {'yer/top':>9} {'sn':>7}"
    print(hdr, flush=True)
    for r in rows:
        yt = f"{r['n_placed']}/{r['n_total']}"
        print(f"{r['plan']:<6} {r['mode']:<6} {str(r['pitch_mm']):>6} "
              f"{r['height_mm']:>8} {str(r['hoca_height_mm']):>7} "
              f"{str(r['oran']):>6} {r['density_pct']:>6} {yt:>9} "
              f"{r['sec']:>7}", flush=True)
    print(f"\nCSV: {CSV_PATH}", flush=True)


if __name__ == "__main__":
    main()
