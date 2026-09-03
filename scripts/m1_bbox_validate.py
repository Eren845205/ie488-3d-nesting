"""m1_bbox_validate.py — bbox-EP gerçekten kalite kazandırıyor mu? (cavity'siz, hızlı)

M1 yan bulgusu: bbox-EP Plan2 kaba'da (pitch2) naive heightmap'i %9 geçti (672 vs 740).
SORU: bu fine'da da tutuyor mu, ve ÜRETİMDEKİ 621'i (0.5mm coarse-to-fine+SA) geçiyor mu?

Birkaç pitch'te yan yana: naive heightmap DBLF vs bbox-EP (OccupancyBin3D, cavity=False).
Cavity YOK -> hızlı. Pitch ne kadar ince, mutlak o kadar düşer; bbox-EP@ince < 621 ise GO.
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
MAGICS_H, BBOX_FLOOR, PROD_FINE = 492.39, 586.0, 621.0
N_OR, MARGIN = 4, 1

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

PITCHES = [float(a) for a in sys.argv[1:]] or [1.5, 1.0]


def main():
    print("=" * 70)
    print(f"bbox-EP DOGRULAMA  (n_or={N_OR})")
    print(f"  referans: Magics {MAGICS_H} | bbox-tabani {BBOX_FLOOR} | URETIM(0.5mm) {PROD_FINE}")
    print("=" * 70, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")

    print(f"{'pitch':>6} | {'heightmap':>10} | {'bbox-EP':>9} | {'fark%':>6} | {'bbox/621':>8} | {'sure':>12}")
    print("-" * 70, flush=True)
    for pitch in PITCHES:
        t = time.perf_counter()
        parts = to_voxel_parts(res.instance, pitch, n_orientations=N_OR, margin=MARGIN)
        tv = time.perf_counter() - t
        nx, ny = int(PLATE_W // pitch), int(PLATE_D // pitch)

        t = time.perf_counter()
        _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, pitch, z_clearance=MARGIN))
        hm = hb.max_height_mm(); th = time.perf_counter() - t

        t = time.perf_counter()
        _, ob = place_extreme_point(parts, lambda: OccupancyBin3D(nx, ny, nz_limit=600, pitch=pitch))
        bb = ob.height_mm(); tb = time.perf_counter() - t

        d = (hm - bb) / hm * 100
        ratio = bb / PROD_FINE
        print(f"{pitch:>6.2f} | {hm:>10.1f} | {bb:>9.1f} | {d:>5.1f}% | {ratio:>7.2f}x | "
              f"vox{tv:>4.0f} hm{th:>3.0f} ep{tb:>3.0f}s", flush=True)

    print("=" * 70)
    print("YORUM: bbox-EP < 621 (oran<1.0) ise URETIMi geciyor -> cavity'siz kazanc.")
    print("       bbox-EP > heightmap sabit ise constructive EP gercek bir lever.")
    print("=" * 70)


if __name__ == "__main__":
    main()
