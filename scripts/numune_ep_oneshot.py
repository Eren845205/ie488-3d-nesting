"""numune_ep_oneshot.py — EP one-shot constructive numune'de heightmap'i geçiyor mu?

Cavity analizi: numune heightmap çözümü zarfının %49.3'ünü çıkıntı-altı boşluğa
israf ediyor. SORU: extreme-point one-shot (tek pass, çıkıntı boşluğunu kullanır)
heightmap DBLF'yi geçer mi? Aynı pitch'te adil kıyas.

Caveat (dürüst): (1) EP clearance'ı heightmap'in z_clearance'ından farklı olabilir
(parçalar margin-dilate, shell gap sağlar ama heightmap ek z_clearance ekler) ->
EP biraz daha agresif olabilir; (2) EP üretimi bbox-köşe tabanlı (kutu-odaklı) —
düzensiz parçaların cavity'sini tam kullanamayabilir. Yani EP %49 tavanın bir
kısmını alır. Sonucun BÜYÜKLÜĞÜ hangisinin baskın olduğunu söyler.
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
RECORD = 181.5


def main():
    if not NUMUNE_DIR.exists():
        print("Numuneler/ yok"); sys.exit(2)
    print("=" * 60)
    print(f"EP one-shot vs heightmap (numune, pitch={PITCH})")
    print("=" * 60, flush=True)

    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"voxelize: {len(parts)} parça ({time.perf_counter()-t:.0f}s)", flush=True)

    # Heightmap DBLF referansı
    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN))
    hm_h = hb.max_height_mm()
    print(f"HEIGHTMAP DBLF: {hm_h:.1f} mm ({time.perf_counter()-t:.1f}s)", flush=True)

    # EP one-shot
    nx = int(PLATE // PITCH)
    print(f"EP one-shot başlıyor (taban {nx}x{nx}, tek pass — sabırlı ol)...", flush=True)
    t = time.perf_counter()
    _, ob = place_extreme_point(parts, lambda: OccupancyBin3D(nx, nx, nz_limit=400, pitch=PITCH))
    ep_h = ob.height_mm()
    ep_t = time.perf_counter() - t
    print(f"EXTREME-POINT : {ep_h:.1f} mm ({ep_t:.0f}s, doluluk {ob.fill_ratio()*100:.1f}%)", flush=True)

    print()
    print("--- KARŞILAŞTIRMA (aynı pitch=2) ---")
    print(f"  heightmap DBLF : {hm_h:.1f} mm")
    print(f"  extreme-point  : {ep_h:.1f} mm")
    diff = (hm_h - ep_h) / hm_h * 100
    if ep_h < hm_h - 0.5:
        print(f"  -> EP %{diff:.1f} DAHA SIKI paketledi (çıkıntı boşluğunu kullandı) 🏆")
    elif ep_h > hm_h + 0.5:
        print(f"  -> EP %{-diff:.1f} daha kötü (bbox-EP üretimi düzensiz parçada zayıf)")
    else:
        print(f"  -> ~eşit (EP cavity'yi pratikte kullanamadı)")
    print(f"  (referans: SA rekoru pitch 1.5'te 181.5 mm — pitch farkı yüzünden direkt kıyas değil)")
    print("=" * 60)


if __name__ == "__main__":
    main()
