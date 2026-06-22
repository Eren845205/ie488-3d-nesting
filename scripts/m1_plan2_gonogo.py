"""m1_plan2_gonogo.py — M1 DECISIVE GO/NO-GO: cavity-EP Plan2 (cavity-dominant) verisinde.

Plan2 = asil cavity vakasi (kutuluk 0.07, %93 bos parcalar). Numune cavity-dominant
DEGILDI (orada cavity kotu cikti). Burada KABA pitch'te (hiz icin) ayni parcalar uzerinde
3 yontem; mutlak mm fine'dan farkli ama AYNI pitch'te goreli kiyas gecerli sinyaldir.

KARAR: cavity-EP < bbox-EP (ve heightmap) ise gercek-veri oyugu aliniyor → M1 GO,
fine'a/M2 metaheuristic'e olcekle. ~esit/kotu ise greedy constructive yetmiyor → M2 sart.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
MAGICS_H, BBOX_FLOOR = 492.39, 586.0

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

PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
N_OR = 4
MARGIN = 1
CAVITY_CAP = 15000


def main():
    print("=" * 66)
    print(f"M1 Plan2 GO/NO-GO  (KABA pitch={PITCH}, n_or={N_OR})")
    print(f"  referans: Magics {MAGICS_H} | bbox-tabani {BBOX_FLOOR} | biz(fine) 621")
    print("=" * 66, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")
    print(f"parca tipi: {len(res.instance.parts)} | toplam adet: {sum(QTY.values())}", flush=True)

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)

    nx = int(PLATE_W // PITCH)
    ny = int(PLATE_D // PITCH)

    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm_h = hb.max_height_mm()
    print(f"[1] HEIGHTMAP : {hm_h:.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    t = time.perf_counter()
    _, ob = place_extreme_point(parts, lambda: OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH))
    bbox_h = ob.height_mm()
    print(f"[2] BBOX-EP   : {bbox_h:.1f} mm  ({time.perf_counter()-t:.0f}s, dol {ob.fill_ratio()*100:.1f}%)", flush=True)

    t = time.perf_counter()
    _, oc = place_extreme_point(parts, lambda: OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH, cavity=True, cavity_cap=CAVITY_CAP))
    cav_h = oc.height_mm()
    print(f"[3] CAVITY-EP : {cav_h:.1f} mm  ({time.perf_counter()-t:.0f}s, dol {oc.fill_ratio()*100:.1f}%)", flush=True)

    print("-" * 66)
    print(f"  heightmap {hm_h:.1f} | bbox-EP {bbox_h:.1f} | cavity-EP {cav_h:.1f}  (KABA pitch={PITCH})")
    base = min(hm_h, bbox_h)
    if cav_h < base - 0.5:
        print(f"  -> [GO] cavity-EP en iyiyi %{(base-cav_h)/base*100:.1f} GECTI -- gercek-veri oyugu aliniyor")
    else:
        print(f"  -> [NO-GO] cavity en iyiyi gecemedi (greedy yetmiyor -- M2 metaheuristic)")
    print("=" * 66)


if __name__ == "__main__":
    main()
