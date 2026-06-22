"""m6_plan2_hybrid.py — KARAR: hibrit (cavity-EP + drop) GERÇEK Plan2'de.

M1 NO-GO idi: Plan2 kaba heightmap 740 | bbox-EP 672 | cavity-EP 802 (felaket).
Tanı (m4/m5): cavity-EP felaketi = aday-uretimi eksikligi (drop aday degildi →
buyuk parca dikeye zorlaniyordu), gercek cavity miyopisi DEGIL. Hibrit (drop her
zaman aday) bunu cozer: cavity ASLA heightmap'ten kotu olamaz + firsat varsa kazanir.

KARAR: hibrit <= heightmap (740) ise M1 felaketi cozuldu. hibrit < bbox-EP (672)
ise cavity gercek-veri oyugunu aliyor → entegrasyona deger. Plan2'de bol kucuk
dolgu (NYLON×93 vs) var → cavity firsati gercek (Magics 492 bunu kullaniyor).
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
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point, _drop_fallback

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


def best_ep(ob, part, cur_max):
    eps = sorted(ob.extreme_points, key=lambda e: (e[2], e[1], e[0]))
    best_key = None; best = None
    for oi, orient in enumerate(part.orientations):
        fh = orient.grid.shape[2]
        for ep in eps:
            ex, ey, ez = ep
            if ob.is_feasible(orient, ex, ey, ez):
                zt = ez + fh
                key = (max(zt, cur_max), zt, ez, ey, ex, oi)
                if best_key is None or key < best_key:
                    best_key, best = key, (ep, oi)
                break
    return (best_key, best) if best else (None, None)


def decode_hybrid(parts, nx, ny):
    ordered = sorted(parts, key=lambda vp: -vp.volume_voxels)
    ob = OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH, cavity=True, cavity_cap=CAVITY_CAP)
    n_cav = 0
    for part in ordered:
        cur_max = ob.max_height_voxels()
        ep_key, ep_best = best_ep(ob, part, cur_max)
        (dx, dy, dz), doi = _drop_fallback(ob, part)
        dfh = part.orientations[doi].grid.shape[2]
        drop_key = (max(dz + dfh, cur_max), dz + dfh, dz, dy, dx, doi)
        if ep_key is not None and ep_key < drop_key:
            ep, oi = ep_best
            ob.place(part.orientations[oi], ep[0], ep[1], ep[2])
            if ep[2] < cur_max:
                n_cav += 1
        else:
            ob.place(part.orientations[doi], dx, dy, dz)
    return ob.height_mm(), n_cav, ob.fill_ratio()


def main():
    print("=" * 66)
    print(f"M6 Plan2 HIBRIT  (KABA pitch={PITCH}, n_or={N_OR})")
    print(f"  referans: Magics {MAGICS_H} | bbox-tabani {BBOX_FLOOR} | biz(fine) 621")
    print(f"  M1 olcum: heightmap 740 | bbox-EP 672 | cavity-EP 802 (felaket)")
    print("=" * 66, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")
    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)

    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm_h = hb.max_height_mm()
    print(f"[1] HEIGHTMAP : {hm_h:.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    t = time.perf_counter()
    h, ncav, fr = decode_hybrid(parts, nx, ny)
    print(f"[4] HIBRIT    : {h:.1f} mm  ({time.perf_counter()-t:.0f}s, dol {fr*100:.1f}%, cavity-kullanim={ncav})", flush=True)

    print("-" * 66)
    print(f"  heightmap {hm_h:.1f} | hibrit {h:.1f}  (M1 cavity-EP 802 idi)")
    if h <= hm_h + 0.5 and h < 800:
        print(f"  -> M1 felaketi (802) COZULDU: hibrit heightmap'i gecmiyor ({h:.1f} <= {hm_h:.1f})")
    if h < hm_h - 0.5:
        print(f"  -> [GO] hibrit heightmap'i %{(hm_h-h)/hm_h*100:.1f} GECTI -- cavity gercek-veri oyugunu aliyor")
    else:
        print(f"  -> hibrit ~heightmap: cavity bu kaba pitch'te tavani dusurmuyor (fine'da tekrar bak)")
    print("=" * 66)


if __name__ == "__main__":
    main()
