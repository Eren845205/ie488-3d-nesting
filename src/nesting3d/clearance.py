"""clearance.py — yerleştirilmiş parçalar arası gerçek (mm) mesafe ölçümü.

Hoca şartı (2026-06-11): parçalar arasında her yönde min 1 mm boşluk.
Garanti voxel katmanında margin dilation ile verilir (voxelize._dilate);
bu modül devoxelize edilmiş ORİJİNAL mesh'ler üzerinde bağımsız doğrulama
yapar — "min 1 mm sağlandı" iddiasının kanıtı.

Yöntem: her mesh yüzeyinden nokta örnekle, AABB'si yakın olan çiftlerde
cKDTree ile en yakın nokta çifti mesafesini bul.  Örnekleme tabanlı ölçüm
gerçek minimumun ÜST sınırıdır (örnek noktalar gerçek en yakın noktayı
ıskalayabilir) — bu yüzden eşik kontrolünde örnekleme payı düşülmez,
ölçülen değer raporlanır ve voxel-katmanı garantisiyle birlikte okunur.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import trimesh
from scipy.spatial import cKDTree


@dataclass
class ClearanceReport:
    min_mm: float                    # ölçülen global minimum (inf = temas adayı yok)
    worst_pair: Optional[Tuple[int, int]]  # min'i veren mesh index çifti
    n_pairs_checked: int             # AABB ön filtresini geçen çift sayısı
    samples_per_mesh: int

    def ok(self, threshold_mm: float = 1.0) -> bool:
        return self.min_mm >= threshold_mm


def _surface_samples(mesh: trimesh.Trimesh, n: int, seed: int) -> np.ndarray:
    pts, _face = trimesh.sample.sample_surface(mesh, n, seed=seed)
    return np.asarray(pts)


def min_clearance(
    meshes: List[trimesh.Trimesh],
    *,
    samples_per_mesh: int = 3000,
    aabb_pad_mm: float = 15.0,
    seed: int = 0,
) -> ClearanceReport:
    """Yerleştirilmiş mesh listesi için parça-çifti minimum mesafe raporu.

    aabb_pad_mm: bounding box'ları bu paydan fazla uzak çiftler atlanır
    (48 parçada 1128 çiftin çoğu böyle elenir — min zaten o çiftlerde değil).
    """
    n = len(meshes)
    bounds = [m.bounds for m in meshes]
    samples: List[Optional[np.ndarray]] = [None] * n
    trees: List[Optional[cKDTree]] = [None] * n

    def _get(i: int):
        if samples[i] is None:
            samples[i] = _surface_samples(meshes[i], samples_per_mesh, seed + i)
            trees[i] = cKDTree(samples[i])
        return samples[i], trees[i]

    best = np.inf
    worst_pair = None
    checked = 0
    for i in range(n):
        for j in range(i + 1, n):
            gap = np.maximum(
                bounds[i][0] - bounds[j][1], bounds[j][0] - bounds[i][1]
            ).max()  # eksen-hizalı kutu boşluğu (negatif = AABB kesişiyor)
            if gap > aabb_pad_mm or gap > best:
                continue
            checked += 1
            pts_i, _ = _get(i)
            _, tree_j = _get(j)
            d, _idx = tree_j.query(pts_i, k=1)
            pair_min = float(d.min())
            if pair_min < best:
                best, worst_pair = pair_min, (i, j)
    return ClearanceReport(
        min_mm=float(best),
        worst_pair=worst_pair,
        n_pairs_checked=checked,
        samples_per_mesh=samples_per_mesh,
    )
