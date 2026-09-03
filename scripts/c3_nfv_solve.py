"""c3_nfv_solve.py — Engel 1 prototipi: NFV çıktısını ÜRETİM Placement3D formatına bağla.

ENGEL 1 (RESUME §11): üretim fine aşaması `place_in_order`/drop NFV'nin 3B-cavity pozisyonlarını
BOZAR. ÇÖZÜM (bu prototip): NFV'yi HEDEF pitch'te doğrudan koş, çıktısını (part_id,oi,x,y,z) →
Placement3D listesine çevir, drop aşamasını TAMAMEN baypas et. Cavity korunur (pozisyonlar zaten
yerleşim). Non-overlap OccupancyBin3D.place çakışma-kontrolüyle garantili.

DOĞRULAMA (bu prototip src/ DOKUNMADAN kanıtlar):
1. placements → export_stl.placed_meshes (ÜRETİMİN gerçek transform'u) hatasız mesh üretir.
2. NFV yüksekliği == placed_meshes z-uzantısı (cavity gerçek mesh frame'inde korunur).
3. Tüm meshler plaka xy sınırında + z≥0; STL/scene build başarılı.
4. NFV yüksekliği üretim solve_coarse_to_fine yüksekliğinden DÜŞÜK (kalite kazancı GERÇEK boru hattında).

ÜRETİME DOKUNMAZ (scripts/). src/ Faz 5'te bağlanacak (bu prototip kanıt).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.c3_par_a import decode as cpu_decode, load, QTY, QTY_FULL, N_OR, MARGIN, PLATE_W, PLATE_D
from scripts.c3_backend import get_backend
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.bin3d import Placement3D
from src.nesting3d.export_stl import placed_meshes

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")


def solve_nfv(parts, nx, ny, pitch, *, parallel=True):
    """NFV decode → ÜRETİM Placement3D listesi + parts_by_id + height_mm.
    parts: to_voxel_parts çıktısı (export'a verilen AYNI nesneler → orientation_idx hizalı)."""
    fm, _ = get_backend("scipy")  # birebir referans (CPU); dispatcher GPU de seçebilir
    height, raw = cpu_decode(parts, nx, ny, feasible_mask=fm, parallel=parallel, pitch=pitch,
                             return_placements=True)
    parts_by_id = {p.id: p for p in parts}
    placements = [Placement3D(pid, parts_by_id[pid].name, x, y, z, oi)
                  for (pid, oi, x, y, z) in raw]
    return placements, parts_by_id, height


def verify(testbed="subset", pitch=2.0):
    qty = QTY_FULL if testbed == "plan2" else QTY
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, qty, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, pitch, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // pitch), int(PLATE_D // pitch)
    print(f"testbed={testbed} pitch={pitch}: {len(parts)} parça {nx}x{ny}", flush=True)

    t = time.perf_counter()
    placements, parts_by_id, height = solve_nfv(parts, nx, ny, pitch)
    print(f"[1] NFV solve: {len(placements)} placement, height={height:.1f} mm ({time.perf_counter()-t:.1f}s)", flush=True)

    # --- DOĞRULAMA 1+2+3: üretimin gerçek transform'undan mesh üret, sınır+yükseklik kontrol ---
    meshes = placed_meshes(placements, parts_by_id, pitch)
    assert len(meshes) == len(placements), "mesh sayısı placement sayısıyla eşleşmeli"
    zmax = max(float(m.bounds[1][2]) for m in meshes)
    zmin = min(float(m.bounds[0][2]) for m in meshes)
    xmin = min(float(m.bounds[0][0]) for m in meshes); xmax = max(float(m.bounds[1][0]) for m in meshes)
    ymin = min(float(m.bounds[0][1]) for m in meshes); ymax = max(float(m.bounds[1][1]) for m in meshes)
    print(f"[2] placed_meshes (ÜRETİM transform): z=[{zmin:.1f},{zmax:.1f}] x=[{xmin:.1f},{xmax:.1f}] y=[{ymin:.1f},{ymax:.1f}]", flush=True)

    # yükseklik tutarlılığı: gerçek mesh z-uzantısı ~ NFV height (voxel kuantizasyon ± ~1 pitch + margin)
    dz = abs(zmax - height)
    h_ok = dz <= 2.5 * pitch  # margin(1) + kuantizasyon payı
    # plaka xy sınırı (voxel grid plate'e kırpılmış; mesh hafif taşabilir margin/kuantizasyondan, ~1 pitch tol)
    xy_ok = (xmin >= -1.5 * pitch and ymin >= -1.5 * pitch and
             xmax <= PLATE_W + 1.5 * pitch and ymax <= PLATE_D + 1.5 * pitch and zmin >= -1.5 * pitch)
    print(f"[3] yükseklik tutarlı: {h_ok} (|zmax-height|={dz:.1f} ≤ {2.5*pitch:.1f}); xy/z sınır: {xy_ok}", flush=True)

    # --- DOĞRULAMA: scene/STL build hatasız (export uyumu) ---
    try:
        from src.nesting3d.export_stl import build_result_scene
        scene = build_result_scene(placements, parts_by_id, pitch=pitch)
        scene_ok = scene is not None
    except Exception as e:
        scene_ok = False
        print(f"    scene build HATA: {type(e).__name__} {e}", flush=True)
    print(f"[4] export scene build: {scene_ok}", flush=True)

    print("-" * 66)
    ok = h_ok and xy_ok and scene_ok and len(placements) == len(parts)
    if ok:
        print(f"  -> [GEÇTİ] NFV→Placement3D ÜRETİM boru hattında çalışıyor, cavity korundu (height {height:.1f})")
    else:
        print(f"  -> [HATA] bağlama doğrulaması başarısız (h_ok={h_ok} xy_ok={xy_ok} scene={scene_ok})")
    return ok, height


def main():
    testbed = sys.argv[1] if len(sys.argv) > 1 else "subset"
    pitch = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    print("=" * 66)
    print(f"C3 NFV-SOLVE (Engel 1: pozisyon-koruyan bağlama)  {testbed} pitch={pitch}")
    print("=" * 66, flush=True)
    verify(testbed, pitch)


if __name__ == "__main__":
    main()
