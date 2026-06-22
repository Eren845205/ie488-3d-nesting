"""m5_hybrid.py — Adım C1.5: cavity-EP + heightmap-drop HİBRİT.

Tanı (m4): order/seçim/beam hepsi 300'de takıldı çünkü AYNI eksik EP-aday havuzunu
kullanıyorlardı. Kök neden: en büyük parçanın 3. kopyası için YATIK (78mm) bir EP
adayı yok → packer dikeye (300mm) zorlanıyor. heightmap (216) drop_map ile yatığı
ilk kopyaların üstüne düz indirebiliyor.

HİBRİT: her parça için aday havuzu = {cavity-EP adayları} ∪ {heightmap-drop pozisyonu}.
İkisinden global yüksekliği (max(z_top,cur_max)) minimize edeni seç. Garanti: cavity
ASLA heightmap'ten kötü olamaz (drop her zaman aday) + cavity fırsatı varsa kazanır.

GO: hibrit <= heightmap (216) VE bir kısım parçada cavity kullanıp < 216 yaparsa →
    cavity GERÇEKTEN işe yarıyor, sadece aday üretimi eksikmiş. Entegrasyona değer.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
QTY = {
    "PO-TR154979-17747_P282335": 3, "part284676_06B23B8_model_r_0": 4,
    "part282114_07D4114_model_r_0": 3, "PO-TR154989-17667_P282407": 4,
    "PO-TR156122-17810_P284641": 4, "part282115_07D4113": 3,
    "PO-TR154979-17747_P282334": 3,
}
PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
N_OR = 4
MARGIN = 1
CAP = 4000


def best_ep(ob, part, cur_max):
    """Cavity-EP havuzundan en iyi (global_key, ep, oi). Yoksa None."""
    eps = sorted(ob.extreme_points, key=lambda e: (e[2], e[1], e[0]))
    best_key = None; best = None
    for oi, orient in enumerate(part.orientations):
        fw, fd, fh = orient.grid.shape
        for ep in eps:
            ex, ey, ez = ep
            if ob.is_feasible(orient, ex, ey, ez):
                zt = ez + fh
                key = (max(zt, cur_max), zt, ez, ey, ex, oi)
                if best_key is None or key < best_key:
                    best_key, best = key, (ep, oi)
                break  # ilk feasible bu orient için min
    return (best_key, best) if best else (None, None)


def decode_hybrid(parts, order, nx, ny, use_cavity=True):
    pos = {id(p): i for i, p in enumerate(order)}
    ordered = sorted(parts, key=lambda vp: pos[id(vp)])
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH, cavity=True, cavity_cap=CAP)
    n_cav = 0
    for part in ordered:
        cur_max = ob.max_height_voxels()
        # aday 1: cavity-EP
        ep_key, ep_best = best_ep(ob, part, cur_max) if use_cavity else (None, None)
        # aday 2: heightmap-drop (her zaman feasible)
        (dx, dy, dz), doi = _drop_fallback(ob, part)
        dfh = part.orientations[doi].grid.shape[2]
        dzt = dz + dfh
        drop_key = (max(dzt, cur_max), dzt, dz, dy, dx, doi)
        # global-min seç
        if ep_key is not None and ep_key < drop_key:
            ep, oi = ep_best
            ob.place(part.orientations[oi], ep[0], ep[1], ep[2])
            # cavity kullanıldı mı? (drop'tan daha alçak global yükseklik VEYA z<cur_max)
            if ep[2] < cur_max:
                n_cav += 1
        else:
            ob.place(part.orientations[doi], dx, dy, dz)
    return ob.height_mm(), n_cav


def main():
    print("=" * 70)
    print(f"M5 HIBRIT (cavity-EP + drop) GO/NO-GO  (pitch={PITCH})")
    print("=" * 70, flush=True)
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"testbed: {len(parts)} parca, taban {nx}x{ny}", flush=True)

    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[heightmap]        {hm:.1f} mm  ({time.perf_counter()-t:.1f}s)  <- referans", flush=True)

    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    t = time.perf_counter()
    h_nc, _ = decode_hybrid(parts, largest, nx, ny, use_cavity=False)
    print(f"[hibrit no-cavity] {h_nc:.1f} mm  ({time.perf_counter()-t:.1f}s)  (drop-only saglama)", flush=True)
    t = time.perf_counter()
    h, ncav = decode_hybrid(parts, largest, nx, ny, use_cavity=True)
    flag = "  *** heightmap'i GECTI -> GO ***" if h < hm - 0.5 else ""
    print(f"[hibrit cavity]    {h:.1f} mm  ({time.perf_counter()-t:.1f}s)  cavity-kullanim={ncav}{flag}", flush=True)
    print("-" * 70)
    print(f"  heightmap {hm:.1f} | hibrit {h:.1f}  -> fark {hm-h:+.1f} mm")
    print("GO: hibrit < heightmap -> cavity gercekten kazaniyor, aday-uretimi eksikmis.")
    print("=" * 70)


if __name__ == "__main__":
    main()
