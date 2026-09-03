"""Plan1 taze kıyas koşusu — gerçek STL + gerçek adetlerle bizim sonuç.

Kullanıcının verdiği Plan1 adetleriyle (toplam 112 parça) pipeline'ı koşar;
yükseklik / doluluk / süre / plaka raporlar. Hocanın Magics yüksekliği gelince
oran (bizim/hoca) elle hesaplanır.
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.plate import resolve_container

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan1\Plan1")

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

if __name__ == "__main__":
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    print(f"STL dosyaları: {len(stl_map)} | adet kalemleri: {len(QTY)} | toplam adet: {sum(QTY.values())}")
    eksik = set(k.lower() for k in QTY) - set(k.lower() for k in stl_map)
    if eksik:
        print("UYARI eşleşmeyen adet anahtarı:", eksik)

    persist = ROOT / "data" / "mail_stl" / "plan1_kiyas"
    res = build_instance_from_order(stl_map, QTY, persist_dir=persist)
    print(f"Eşleşen parça tipi: {len(res.instance.parts)} | adetsiz atlanan: {res.skipped_no_qty} | STL'siz: {res.skipped_no_stl}")

    parts = [{
        "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
        "stl_path": p.stl_path, "width_mm": p.width_mm,
        "depth_mm": p.depth_mm, "height_mm": p.height_mm,
    } for p in res.instance.parts]

    # Otomatik (veri-odaklı) plaka — parçalardan türetilir; raporda gösterilir
    pdims = [(p["width_mm"], p["depth_mm"], p["height_mm"]) for p in parts]
    cw, cd, ch, auto = resolve_container({"width_mm": None, "depth_mm": None, "height_mm": None}, pdims)
    print(f"Otomatik plaka: {cw:.1f} x {cd:.1f} mm (auto={auto})")

    order = {
        "order_id": "PLAN1", "customer": "HOCA-PLAN1",
        "deadline": "2026-12-31", "priority_class": 2, "parts": parts,
    }
    scenario = {**RICH_SCENARIO, "orders": [order], "container": None}  # auto plaka

    t0 = time.perf_counter()
    result = run_pipeline(scenario)
    dt = time.perf_counter() - t0

    out = {}
    for bid, nr in result["nesting_results"].items():
        out[bid] = {
            "height_mm": round(nr["height_mm"], 1),
            "density_pct": round(nr["density"] * 100, 1),
            "n_parts_placed": nr["n_parts"],
            "pitch_mm": nr.get("pitch_mm"),
            "nest_sec": nr["elapsed_sec"],
        }
    print("\n===PLAN1_SONUC_JSON===")
    print(json.dumps({
        "toplam_adet": sum(QTY.values()),
        "parca_tipi": len(parts),
        "plaka_mm": [round(cw, 1), round(cd, 1)],
        "pipeline_sec": round(dt, 1),
        "batches": out,
        "skipped_orders": result.get("skipped_orders", []),
    }, ensure_ascii=False, indent=2))
