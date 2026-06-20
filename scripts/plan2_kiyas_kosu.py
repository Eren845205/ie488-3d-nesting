"""Plan2 taze kıyas koşusu — bizim sonuç vs hoca Magics (492.39 mm).

Hoca Magics referansı (Plan2.jpg görselinden): yükseklik 492.39 mm,
plaka 328.74 x 328.19 mm, 226 parça. ADİL kıyas için bizim koşu da AYNI
plakada yapılır; yalnız yükseklik (stack) karşılaştırılır.
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.demo_pipeline import RICH_SCENARIO, run_pipeline
from src.nesting3d.instances.stl_order_loader import build_instance_from_order

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")

# Hoca Magics referansı (görselden)
HOCA_HEIGHT_MM = 492.39
PLATE_W, PLATE_D = 328.74, 328.19

QTY = {
    "P00000002586": 20,
    "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9,
    "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5,
    "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5,
    "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20,
    "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17,
    "part282115_07D4113": 9,
    "PO-TR155318-17709": 5,
    "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1,
    "PO-TR155308-17705": 1,
}

if __name__ == "__main__":
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    print(f"STL: {len(stl_map)} | adet kalemi: {len(QTY)} | toplam adet: {sum(QTY.values())}", flush=True)
    eksik = set(k.lower() for k in QTY) - set(k.lower() for k in stl_map)
    fazla = set(k.lower() for k in stl_map) - set(k.lower() for k in QTY)
    if eksik:
        print("UYARI adet var STL yok:", eksik, flush=True)
    if fazla:
        print("UYARI STL var adet yok:", fazla, flush=True)

    persist = ROOT / "data" / "mail_stl" / "plan2_kiyas"
    res = build_instance_from_order(
        stl_map, QTY,
        container_w_mm=PLATE_W, container_d_mm=PLATE_D,  # HOCA plakası (adil kıyas)
        persist_dir=persist,
    )
    print(f"Eşleşen parça tipi: {len(res.instance.parts)} | adetsiz: {res.skipped_no_qty} | STLsiz: {res.skipped_no_stl}", flush=True)

    parts = [{
        "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
        "stl_path": p.stl_path, "width_mm": p.width_mm,
        "depth_mm": p.depth_mm, "height_mm": p.height_mm,
    } for p in res.instance.parts]

    order = {
        "order_id": "PLAN2", "customer": "HOCA-PLAN2",
        "deadline": "2026-12-31", "priority_class": 2, "parts": parts,
    }
    # Hoca plakasını pipeline'a dayat (adil kıyas — aynı taban)
    scenario = {**RICH_SCENARIO, "orders": [order],
                "container": {"width_mm": PLATE_W, "depth_mm": PLATE_D, "height_mm": None}}

    print("Koşu başlıyor (coarse-to-fine, ~birkaç dk)...", flush=True)
    t0 = time.perf_counter()
    result = run_pipeline(scenario)
    dt = time.perf_counter() - t0

    bid = next(iter(result["nesting_results"]))
    nr = result["nesting_results"][bid]
    bizim_h = round(nr["height_mm"], 1)
    oran = round(bizim_h / HOCA_HEIGHT_MM, 3)
    print("\n===PLAN2_SONUC_JSON===", flush=True)
    print(json.dumps({
        "toplam_adet": sum(QTY.values()),
        "parca_tipi": len(parts),
        "plaka_mm": [PLATE_W, PLATE_D],
        "bizim_yukseklik_mm": bizim_h,
        "hoca_yukseklik_mm": HOCA_HEIGHT_MM,
        "oran_bizim_bolu_hoca": oran,
        "bizim_doluluk_pct": round(nr["density"] * 100, 1),
        "yerlesen_parca": nr["n_parts"],
        "pitch_mm": nr.get("pitch_mm"),
        "nest_sec": nr["elapsed_sec"],
        "pipeline_sec": round(dt, 1),
        "kazanan_algoritma": (nr.get("tuner") or {}).get("winning_config"),
    }, ensure_ascii=False, indent=2), flush=True)
