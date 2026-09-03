"""numune_cavity_analysis.py — Numune heightmap çözümü ne kadarını çıkıntı-boşluğuna israf ediyor?

Karar sorusu: extreme-point numune'ye DEĞER mi? = heightmap çözümünün altında
ENCLOSED (çıkıntı altı, kapalı) boşluk var mı, ne kadar? Bu boşluk EP'nin
kurtarabileceği hacim. Kaba pitch (hız — israf-oranı yapısal, pitch-bağımsız değil
ama temsili). Slow 1.5mm değil, koşan deneyi yormasın.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities

PITCH, PLATE, MARGIN, N_OR = 2.0, 335.0, 1, 8   # ince parça (1.59mm) için pitch<=~3; 2.0 hızlı+güvenli


def main():
    if not NUMUNE_DIR.exists():
        print("Numuneler/ yok"); sys.exit(2)
    print(f"Numune cavity analizi (pitch={PITCH} kaba, hibrit)")
    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"  {len(parts)} parça voxelize ({time.perf_counter()-t:.0f}s)")
    mk = lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN)
    placements, bb = dblf(parts, mk)
    print(f"  DBLF yüksekliği: {bb.max_height_mm():.1f} mm")

    # 3D occupancy'yi placement'lardan yeniden kur
    by_id = {p.id: p for p in parts}
    nx, ny = bb.nx, bb.ny
    nz = bb.max_height_voxels() + 2
    occ = np.zeros((nx, ny, nz), dtype=bool)
    for pl in placements:
        g = by_id[pl.part_id].orientations[pl.orientation_idx].grid
        gw, gd, gh = g.shape
        occ[pl.x:pl.x+gw, pl.y:pl.y+gd, pl.z:pl.z+gh] |= g

    occupied = int(occ.sum())
    # Her sütunda en üst dolu z -> o sütunda altındaki BOŞ voxel'ler = çıkıntı/kapalı boşluk
    cavity = 0
    col_top = np.full((nx, ny), -1, dtype=int)
    occ_z_any = occ.any(axis=2)
    for x in range(nx):
        for y in range(ny):
            if not occ_z_any[x, y]:
                continue
            col = occ[x, y]
            top = np.max(np.nonzero(col))  # en üst dolu z
            col_top[x, y] = top
            cavity += (top + 1) - int(col[:top+1].sum())  # tepe altındaki boşluklar

    envelope = nx * ny * (col_top.max() + 1) if col_top.max() >= 0 else 1
    used_cols = int(occ_z_any.sum())
    print()
    print(f"  Konteyner taban voxel: {nx}x{ny} = {nx*ny}  (dolu sütun: {used_cols})")
    print(f"  Zarf (envelope) hacmi : {envelope:,} voxel")
    print(f"  Dolu (occupied)       : {occupied:,} voxel ({occupied/envelope*100:.1f}% zarfın)")
    print(f"  ÇIKINTI-ALTI BOŞLUK   : {cavity:,} voxel")
    print(f"    -> zarfın %{cavity/envelope*100:.1f}'i  |  dolu hacmin %{cavity/max(occupied,1)*100:.1f}'i")
    print()
    pct = cavity / envelope * 100
    if pct >= 5:
        print(f"  KARAR: çıkıntı israfı %{pct:.1f} >= %5 -> extreme-point numune için DEĞER (kurtarılabilir hacim ciddi)")
    else:
        print(f"  KARAR: çıkıntı israfı %{pct:.1f} < %5 -> EP numune'de az kazandırır; heightmap zaten iyi")
    print(f"  (Not: bu kurtarılabilir TAVAN; EP pratikte bunun bir kısmını alır)")


if __name__ == "__main__":
    main()
