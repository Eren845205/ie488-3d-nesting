"""scripts/run_plan1.py — Hocanin Plan1 verisiyle bizim algoritmayi kostur.

Plan1: 12 cesit STL, toplam 112 parca. Hocanin Magics plakasi 328.74 x 328.19
(Plan2 gorselinden). Adil kiyas icin AYNI tabani kullaniriz; yukseklik acik.
Cikti: bizim yukseklik (mm) + doluluk + sure -> hoca Magics yuksekligiyle kiyas.
"""
from __future__ import annotations

import glob
import os
import tempfile
import time
from pathlib import Path

from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
from src.nesting3d.instances.stl_order_loader import build_instance_from_order

PLAN1_DIR = r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan1\Plan1"

# Hocanin ekran goruntusunden adet listesi (toplam 112)
QTY = {
    "ENG-500053_L-Bracket": 22,
    "811793-1": 20,
    "TAPER-GAUGE-1": 10,
    "bobbin_1_v2": 12,
    "bobbin_2_v2": 12,
    "bobbin_3_v2": 6,
    "811791-1": 19,
    "pyramid_with_doors": 5,
    "MTShoe": 1,
    "M18_toShopVac_Adapter": 2,
    "part262835": 2,
    "baseplate_v2": 1,
}

# Plan1'in GERCEK plakasi bilinmiyor (hocanin Plan1 gorseli plaka boyutu icermiyor;
# baseplate_v2 = 330.2 mm, Plan2'nin 328 plakasina sigmiyor -> Plan1 farkli plaka).
# Bu yuzden plakayi OTOMATIK turettiriyoruz (None -> parcalardan; sabit default yok).
PLATE_W = None
PLATE_D = None


def main() -> None:
    stl_map = {}
    for f in glob.glob(os.path.join(PLAN1_DIR, "*.stl")):
        name = os.path.splitext(os.path.basename(f))[0]
        with open(f, "rb") as fh:
            stl_map[name] = fh.read()

    print(f"[Plan1] {len(stl_map)} STL okundu, {sum(QTY.values())} parca (adet).")

    persist = Path(tempfile.gettempdir()) / "plan1_run"
    res = build_instance_from_order(
        stl_map, QTY,
        container_w_mm=PLATE_W, container_d_mm=PLATE_D, container_h_mm=None,
        persist_dir=persist,
    )
    if res.skipped_no_stl or res.skipped_no_qty:
        print("  ! skipped_no_stl:", res.skipped_no_stl)
        print("  ! skipped_no_qty:", res.skipped_no_qty)
    print("  eslesen cesit:", len(res.instance.parts),
          "toplam parca:", sum(p.qty for p in res.instance.parts))

    parts = [
        {
            "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
            "stl_path": p.stl_path, "width_mm": p.width_mm,
            "depth_mm": p.depth_mm, "height_mm": p.height_mm,
        }
        for p in res.instance.parts
    ]

    # Plaka: build_instance_from_order tarafindan cozuldu (otomatik veya verilen).
    c = res.instance.container
    plate_auto = res.instance.meta.get("plate_auto")
    print(f"  plaka = {c.width_mm:.1f} x {c.depth_mm:.1f} mm "
          f"({'OTOMATIK (parcalardan)' if plate_auto else 'verilen gercek plaka'})")

    order = {
        "order_id": "PLAN1", "customer": "HOCA",
        "deadline": "2026-12-31", "priority_class": 2, "parts": parts,
    }
    scenario = {
        **RICH_SCENARIO,
        "orders": [order],
        "container": {"width_mm": c.width_mm, "depth_mm": c.depth_mm, "height_mm": None},
    }

    print("[Plan1] run_pipeline basliyor (112 parca > esik -> coarse-to-fine)...")
    t0 = time.perf_counter()
    result = run_pipeline(scenario)
    dt = time.perf_counter() - t0

    print("\n==================== SONUC ====================")
    for bid, nr in result["nesting_results"].items():
        port = nr.get("portfolio") or {}
        winner = port.get("winner") if isinstance(port, dict) else None
        print(f"  batch={bid}")
        print(f"    yukseklik_mm = {nr.get('height_mm')}")
        print(f"    doluluk      = {nr.get('density')}")
        print(f"    n_parts      = {nr.get('n_parts')}")
        print(f"    kazanan_algo = {winner}")
        print(f"    nest_sure_s  = {nr.get('elapsed_sec')}")
        if nr.get("note"):
            print(f"    not          = {nr.get('note')}")
    print(f"  TOPLAM SURE  = {dt:.1f} s ({dt/60:.1f} dk)")
    print(f"  HOCA Magics  = (Plan1 yuksekligi henuz elimde yok)")
    print("===============================================")


if __name__ == "__main__":
    main()
