# -*- coding: utf-8 -*-
"""k62_v28_app_dogrulama.py — v28 URETIM-KABLO uctan-uca dogrulama (plan1).

APP'IN BIREBIR CAGIRDIGI YOL (run_pipeline, nesting_mode="nfv") uzerinden
plan1 kosulur; beklenti kanopi zincirinin tetiklenip A2-legal ~129.00
sinifi sonucu OTOMATIK bulmasi (eski uretim pin yolu 140.21).

Rapor: yukseklik + kanopi_zincir telemetrisi (tetik/etiket/A2/geri-dusus)
+ nfv_kalite izi. Ayrica ayni senaryo kanopi_zincir=False ile KOSULMAZ
(süre); ref yuksekligi telemetriden okunur (ref_height_mm).

Kosum: python -m scripts.detach_run k62_v28_app_dogrulama
       (D:\\ie488, MUNHASIR — K-57a; RAM >= 4GB bos sart. ~30-60dk.)
SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k62_v28_app_dogrulama.log"
OUT = _ROOT / "results" / "k62_v28_app_dogrulama.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v28 URETIM-KABLO app-yolu dogrulamasi (plan1, nfv modu)")

    from datetime import date

    import scripts.eval_gate as eg
    from scripts.demo_pipeline import run_pipeline
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order

    cfg = eg.DATASETS["plan1"]
    stl_map = {f.stem: f.read_bytes()
               for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"],
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_plan1",
        container_w_mm=eg.PLATE_STD[0], container_d_mm=eg.PLATE_STD[1])
    parts = [{
        "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
        "stl_path": p.stl_path, "width_mm": p.width_mm,
        "depth_mm": p.depth_mm, "height_mm": p.height_mm,
    } for p in res.instance.parts]
    n_total = sum(p["qty"] for p in parts)
    log(f"parca tipi: {len(parts)} | toplam adet: {n_total}")

    scenario = {
        "ref_date": date(2026, 8, 15),
        "seed": 42,
        "capacity": {"num_machines": 1, "batch_duration_hours": 24.0,
                     "shifts_per_day": 1,
                     "max_volume_per_batch_cm3": None},
        "container": {"width_mm": eg.PLATE_STD[0],
                      "depth_mm": eg.PLATE_STD[1], "height_mm": 600.0},
        "nesting_mode": "nfv",  # kalite modu — v28 kablosu default-ACIK
        "orders": [{"order_id": "PLAN1-V28", "customer": "DOGRULAMA",
                    "deadline": "2026-12-31", "priority_class": 2,
                    "parts": parts}],
        "pricing_rules": {"version": "1.0", "name": "dogrulama",
                          "rules": [{"id": "r_min", "type": "min_clamp",
                                     "min_price": 0.0,
                                     "description": "n/a"}]},
    }
    # no_go: scenario'ya YAZILMAZ — run_pipeline configs/plate.local.json'dan
    # cozer (no_go_soft dahil) = app'in birebir yolu.

    log("run_pipeline basladi (nfv modu; kanopi zinciri default-acik)...")
    sonuc = run_pipeline(scenario)
    wall = time.perf_counter() - t0

    doc = {"olcum": "k62_v28_app_dogrulama",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("v28 uretim-kablosu app-yolu dogrulamasi; tek-set "
                    "(plan1). p2/d4 sure-etkisi ayri kosu ister."),
           "n_total": n_total, "sure_s": round(wall, 1), "partiler": {}}
    for bid, nr in sonuc["nesting_results"].items():
        kz = nr.get("kanopi_zincir") or {}
        nk = nr.get("nfv_kalite") or {}
        satir = {
            "height_mm": nr.get("height_mm"),
            "n_parts": nr.get("n_parts"),
            "nesting_mode_used": nr.get("nesting_mode_used"),
            "kanopi": {
                "tetik": kz.get("tetik"), "secilen": kz.get("secilen"),
                "etiket": kz.get("etiket"),
                "ref_height_mm": kz.get("ref_height_mm"),
                "ref_eff_height_mm": kz.get("ref_eff_height_mm"),
                "kazanc_mm": kz.get("kazanc_mm"),
                "a2": kz.get("a2"), "geri_dusus": kz.get("geri_dusus"),
                "sure_s": kz.get("sure_s"),
                "zincir_adimlar": (kz.get("zincir") or {}).get("adimlar"),
            },
            "nfv_kalite_secilen": nk.get("secilen"),
        }
        doc["partiler"][bid] = satir
        log(f"[{bid}] h={satir['height_mm']} n={satir['n_parts']}"
            f" mod={satir['nesting_mode_used']}")
        log(f"  kanopi: tetik={satir['kanopi']['tetik']}"
            f" secilen={satir['kanopi']['secilen']}"
            f" etiket={satir['kanopi']['etiket']}"
            f" ref={satir['kanopi']['ref_height_mm']}"
            f" kazanc={satir['kanopi']['kazanc_mm']}")
        log(f"  A2: {satir['kanopi']['a2']}")
        for a in (satir["kanopi"]["zincir_adimlar"] or []):
            log(f"    adim: {a}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
            log(f"kopya: {ek}")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")
    log(f"WALL_S={wall:.1f} ({wall / 60:.1f} dk)")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
