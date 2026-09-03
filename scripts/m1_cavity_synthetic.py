"""m1_cavity_synthetic.py — Cavity-EP mekanizma kanıtı (sentetik, hızlı).

GO/NO-GO #0: cavity aday üretimi GERÇEKTEN oyuğa (çıkıntı altına) yerleştiriyor mu?

Π-şekilli (köprü/çatı) bir ilk parça → altında kapalı bir oyuk bırakır. Sonra
küçük bir kutu parça. bbox-köşe EP oyuğa GİREMEZ (aday yok) → çatının üstüne istifler.
cavity EP oyuk tabanını aday olarak görür → altına kayar. Yükseklik farkı mekanizmayı
kanıtlar (gerçek hoca verisinden BAĞIMSIZ, saniyeler).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.voxelize import Orientation, VoxelPart
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point


def make_orient(grid: np.ndarray) -> Orientation:
    grid = grid.astype(bool)
    nz = grid.shape[2]
    filled = grid.any(axis=2)
    idx = np.arange(nz)
    # bottom = first True z per col; top = last True z + 1
    has = filled
    z_any = grid * idx[None, None, :]
    top = np.where(has, z_any.max(axis=2) + 1, 0).astype(np.int32)
    z_big = np.where(grid, idx[None, None, :], nz)
    bottom = np.where(has, z_big.min(axis=2), 0).astype(np.int32)
    return Orientation(
        rot_matrix=np.eye(4), voxel_origin=np.zeros(3), grid=grid,
        filled=filled, bottom=bottom, top=top, voxel_count=int(grid.sum()),
    )


def make_part(pid: str, grid: np.ndarray) -> VoxelPart:
    return VoxelPart(id=pid, name=pid, mesh=None,
                     orientations=[make_orient(grid)],
                     volume_voxels=int(grid.sum()))


def build_pi(nx=7, depth=2, h_pillar=3, h_roof=2) -> np.ndarray:
    """Π / köprü: iki ayak + üstte çatı, ortada oyuk."""
    nz = h_pillar + h_roof
    g = np.zeros((nx, depth, nz), dtype=bool)
    g[0, :, 0:h_pillar] = True          # sol ayak
    g[nx - 1, :, 0:h_pillar] = True      # sağ ayak
    g[:, :, h_pillar:nz] = True          # çatı (tüm x)
    return g


def run(cavity: bool):
    pi = make_part("PI", build_pi())
    # küçük kutu: oyuğa (genişlik nx-2, çatı altı yükseklik h_pillar) sığar
    box = make_part("BOX", np.ones((3, 2, 2), dtype=bool))
    parts = [pi, box]  # PI büyük → largest-first onu önce koyar
    # Bin tam Π ayak izi (7x2): yanal kaçış YOK — tek alçak seçenek oyuk.
    bin_factory = lambda: OccupancyBin3D(7, 2, nz_limit=40, pitch=1.0,
                                         cavity=cavity)
    placements, ob = place_extreme_point(parts, bin_factory)
    return placements, ob


def main():
    print("=" * 60)
    print("M1 sentetik GO/NO-GO: cavity-EP oyuğa giriyor mu?")
    print("=" * 60)
    for cavity in (False, True):
        pls, ob = run(cavity)
        box = next(p for p in pls if p.part_id == "BOX")
        tag = "CAVITY  " if cavity else "BBOX-EP "
        print(f"\n[{tag}] yükseklik = {ob.max_height_voxels()} voxel "
              f"({ob.height_mm():.0f} mm), doluluk {ob.fill_ratio()*100:.0f}%")
        print(f"          BOX yerleşimi: (x={box.x}, y={box.y}, z={box.z})")
        if box.z <= 2:
            print("          -> BOX OYUGA GIRDI (z dusuk, cati alti) [GO]")
        else:
            print("          -> BOX cati ustune istifledi (oyuga giremedi)")
    print("\n" + "=" * 60)
    print("Beklenen: bbox-EP istifler (yüksek), cavity oyuğa girer (alçak).")
    print("=" * 60)


if __name__ == "__main__":
    main()
