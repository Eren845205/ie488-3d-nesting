"""Plan2 HIZLI yaklaşık kıyas — ince pitch elle 2.5mm'ye sabit (suggest_pitch
baypas). Kesin koşu ~1mm'de dakikalarca sürüyor; bu, kaba pitch'le dakikalar
içinde YAKLAŞIK yükseklik verir (biraz yüksek tahmin, ama hızlı fikir)."""
from __future__ import annotations
import sys, time, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
HOCA_HEIGHT_MM = 492.39
PLATE_W, PLATE_D = 328.74, 328.19
FINE_PITCH = 1.5   # elle sabit: 1mm ince parçayı korur (1/1.5=0.67>=0.5) ama
                   # auto 0.4mm'den ~50x az voxel → dakikalar yerine saniyeler

QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}

if __name__ == "__main__":
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    print(f"HIZLI: {len(stl_map)} STL, {sum(QTY.values())} adet, fine_pitch={FINE_PITCH}mm", flush=True)
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_hizli",
    )
    print(f"Parça tipi: {len(res.instance.parts)} — coarse-to-fine başlıyor...", flush=True)
    t0 = time.perf_counter()
    r = solve_coarse_to_fine(
        res.instance, plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
        coarse_pitch=None, fine_pitch=FINE_PITCH, budget=25, seed=42,
    )
    dt = time.perf_counter() - t0
    bizim = round(r.height_mm, 1)
    print("\n===PLAN2_HIZLI_JSON===", flush=True)
    print(json.dumps({
        "fine_pitch_mm": FINE_PITCH,
        "bizim_yukseklik_mm": bizim,
        "hoca_yukseklik_mm": HOCA_HEIGHT_MM,
        "oran_bizim_bolu_hoca": round(bizim / HOCA_HEIGHT_MM, 3),
        "bizim_doluluk_pct": round(r.density * 100, 1),
        "sure_dk": round(dt / 60, 1),
        "not": "YAKLAŞIK (2.5mm ince pitch; kesin koşu ~1mm ayrı sürüyor)",
    }, ensure_ascii=False, indent=2), flush=True)
