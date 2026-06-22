"""m1_numune_gonogo.py — M1 ASIL GO/NO-GO: cavity-EP gercek numune verisinde kazaniyor mu?

Ayni pitch'te 3 yontem:
  1. heightmap DBLF (mevcut uretim)
  2. bbox-EP (mevcut OccupancyBin3D, cavity=False) — numune'de heightmap'le berabereydi
  3. cavity-EP (M1: NFV-lite oyuk-ici aday uretimi, cavity=True)

KARAR: cavity-EP < bbox-EP ve < heightmap ise M1 GERCEK parcada da calisiyor → Plan2'ye olcekle.
~esit ise cavity gercek-veri oyugunu pratikte alamiyor → tasarimi gozden gecir.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point

PITCH, PLATE, MARGIN, N_OR = 2.0, 335.0, 1, 8


def main():
    if not NUMUNE_DIR.exists():
        print("Numuneler/ yok"); sys.exit(2)
    print("=" * 64)
    print(f"M1 GO/NO-GO (numune, pitch={PITCH}, n_or={N_OR})")
    print("=" * 64, flush=True)

    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)

    nx = int(PLATE // PITCH)

    # 1. heightmap
    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN))
    hm_h = hb.max_height_mm()
    print(f"[1] HEIGHTMAP : {hm_h:.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    # 2. bbox-EP
    t = time.perf_counter()
    _, ob = place_extreme_point(parts, lambda: OccupancyBin3D(nx, nx, nz_limit=400, pitch=PITCH))
    bbox_h = ob.height_mm()
    print(f"[2] BBOX-EP   : {bbox_h:.1f} mm  ({time.perf_counter()-t:.0f}s, dol {ob.fill_ratio()*100:.1f}%)", flush=True)

    # 3. cavity-EP
    t = time.perf_counter()
    _, oc = place_extreme_point(parts, lambda: OccupancyBin3D(nx, nx, nz_limit=400, pitch=PITCH, cavity=True))
    cav_h = oc.height_mm()
    print(f"[3] CAVITY-EP : {cav_h:.1f} mm  ({time.perf_counter()-t:.0f}s, dol {oc.fill_ratio()*100:.1f}%)", flush=True)

    print("-" * 64)
    print(f"  heightmap {hm_h:.1f} | bbox-EP {bbox_h:.1f} | cavity-EP {cav_h:.1f}")
    best = min(hm_h, bbox_h, cav_h)
    if cav_h <= best + 0.5 and cav_h < hm_h - 0.5:
        print(f"  -> [GO] cavity-EP en iyi, heightmap'i %{(hm_h-cav_h)/hm_h*100:.1f} gecti")
    elif cav_h < bbox_h - 0.5:
        print(f"  -> cavity bbox-EP'yi gecti ama heightmap'i gecemedi")
    else:
        print(f"  -> [NO-GO] cavity ~esit; gercek-veri oyugunu pratikte alamadi")
    print("=" * 64)


if __name__ == "__main__":
    main()
