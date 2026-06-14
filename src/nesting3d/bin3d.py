"""bin3d.py — open-top bin with heightmap state (PLAN_3D.md §2.3, §2.4).

The bin has a fixed base (plate_w x plate_d mm, voxelized at `pitch`) and an
unbounded height — the quantity being minimized.  State is a 2D heightmap
H[x, y] (int, voxel units): the top of the tallest occupied voxel per column.

Known, accepted limitation (PLAN_3D.md §2.4): a heightmap cannot slide parts
into cavities under overhangs.  Honest trade-off for fast SA decodes.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from src.nesting3d.voxelize import Orientation, VoxelPart



@dataclass
class Placement3D:
    """One placed part: voxel cell (x, y, z) of its grid's (0,0,0) corner."""

    part_id: str
    name: str
    x: int
    y: int
    z: int
    orientation_idx: int


class Bin3D:
    """Heightmap bin. All placement math is in voxel units; mm at the edges."""

    def __init__(self, plate_w_mm: float = 220.0, plate_d_mm: float = 220.0,
                 pitch: float = 220.0 / 64, z_clearance: int = 0):
        self.plate_w_mm = float(plate_w_mm)
        self.plate_d_mm = float(plate_d_mm)
        self.pitch = float(pitch)
        # z_clearance: parça başka parça ÜZERİNE oturduğunda araya konan boş
        # hücre sayısı (voxel).  Yatay boşluk voxelize._dilate'te; dikey boşluk
        # burada tek taraflı verilir — çift taraflı z-dilation'dan yarı maliyet
        # (hoca min 1 mm şartı, 2026-06-11).  Plakaya oturan parça (drop z=0)
        # yükseltilmez.
        self.z_clearance = int(z_clearance)
        self.nx = int(plate_w_mm // pitch)
        self.ny = int(plate_d_mm // pitch)
        self.height = np.zeros((self.nx, self.ny), dtype=np.int32)
        self.placements: List[Placement3D] = []
        self.placed_voxels: int = 0

    # -- placement ----------------------------------------------------------

    def drop_map(self, orient: Orientation) -> Optional[np.ndarray]:
        """Drop-z for EVERY feasible (x, y) of this orientation, vectorized.

        Returns an (nx-fw+1, ny-fh+1) int array, or None when the footprint
        does not fit the base at all.  Z[x, y] = the rest height of the part's
        grid origin if dropped at (x, y):
            max over filled columns (i, j) of H[x+i, y+j] - bottom[i, j]
        """
        fw, fh = orient.filled.shape
        npx, npy = self.nx - fw + 1, self.ny - fh + 1
        if npx <= 0 or npy <= 0:
            return None

        # Hizli yol: dolu-dikdortgen footprint + tek-deger taban (KUTU parcalar)
        # → ayrik kayan-maksimum, ~25x hizli. Konkav footprint / degisken taban
        # (numune STL) None doner ve genel donguye duser. Sonuc bire bir ayni.
        fast = self._drop_map_fast(orient, npx, npy)
        if fast is not None:
            return fast

        Z = np.zeros((npx, npy), dtype=np.int32)
        cols_i, cols_j = np.nonzero(orient.filled)
        for i, j, b in zip(cols_i, cols_j, orient.bottom[cols_i, cols_j]):
            np.maximum(Z, self.height[i:i + npx, j:j + npy] - b, out=Z)
        np.maximum(Z, 0, out=Z)
        if self.z_clearance:
            Z[Z > 0] += self.z_clearance  # parça üstüne oturma -> dikey boşluk
        return Z

    def _drop_map_fast(self, orient: Orientation, npx: int, npy: int
                       ) -> Optional[np.ndarray]:
        """drop_map'in hizli yolu — sadece dolu-dikdortgen + tek-deger taban.

        Kutu parcalar icin (filled tamamen dolu, bottom her kolonda ayni deger
        b0) drop_map = H'nin (fw x fh) sol-hizali penceresi uzerinde kayan-
        maksimum eksi b0. Islem AYRILABILIR: once eksen0 boyunca fw kaydirma,
        sonra eksen1 boyunca fh kaydirma — her biri O(npx*npy) numpy maksimumu.
        Toplam O((fw+fh)*npx*npy), dongunun O(fw*fh*npx*npy)'sine kiyasla cok
        daha ucuz. Kaydirma kurulumu sol-hizali valid pencereyi INSA YOLUYLA
        garantiler (merkezleme/offset belirsizligi YOK); sonuc genel donguyle
        bire bir ayni.
        """
        filled = orient.filled
        if not filled.all():
            return None  # konkav footprint → genel yol
        bottom = orient.bottom
        b0 = int(bottom.flat[0])
        if not (bottom == b0).all():
            return None  # degisken taban → genel yol

        fw, fh = filled.shape
        H = self.height
        # Eksen0: m0[x, :] = max_{k in [0,fw)} H[x+k, :], x in [0, npx)
        m0 = H[:npx].copy()
        for k in range(1, fw):
            np.maximum(m0, H[k:k + npx], out=m0)
        # Eksen1: Z[x, y] = max_{k in [0,fh)} m0[x, y+k], y in [0, npy)
        Z = m0[:, :npy].copy()
        for k in range(1, fh):
            np.maximum(Z, m0[:, k:k + npy], out=Z)

        if b0:
            Z -= b0
        np.maximum(Z, 0, out=Z)
        if self.z_clearance:
            Z[Z > 0] += self.z_clearance
        return Z

    def drop_z(self, orient: Orientation, x: int, y: int) -> int:
        """Drop-z for a single (x, y) — used by tests and spot checks."""
        f = orient.filled
        sub = self.height[x:x + f.shape[0], y:y + f.shape[1]]
        vals = sub[f] - orient.bottom[f]
        z = max(int(vals.max()), 0)
        if self.z_clearance and z > 0:
            z += self.z_clearance
        return z

    def place(self, part: VoxelPart, orientation_idx: int,
              x: int, y: int, z: int) -> Placement3D:
        """Commit a placement: raise the heightmap by the part's top profile."""
        orient = part.orientations[orientation_idx]
        f = orient.filled
        fw, fh = f.shape
        sub = self.height[x:x + fw, y:y + fh]
        np.copyto(sub, np.maximum(sub, z + orient.top), where=f)

        p = Placement3D(part.id, part.name, x, y, z, orientation_idx)
        self.placements.append(p)
        self.placed_voxels += orient.voxel_count
        return p

    # -- metrics (PLAN_3D.md §2.6) -------------------------------------------

    def max_height_voxels(self) -> int:
        return int(self.height.max())

    def max_height_mm(self) -> float:
        return self.max_height_voxels() * self.pitch

    def mean_height_mm(self) -> float:
        """Average column height."""
        return float(self.height.mean()) * self.pitch

    def rms_height_mm(self) -> float:
        """Root-mean-square column height — the SA tie-breaker (compactness).

        Quadratic on purpose: a part standing tall on the floor and the same
        part lying flat can occupy the SAME column-volume (mean gives no
        gradient between them), but RMS strictly prefers the flat, spread-out
        pose.  That gradient is what lets SA walk off the max-height plateau.
        """
        h = self.height.astype(np.float64)
        return float(np.sqrt((h * h).mean())) * self.pitch

    def packing_density(self) -> float:
        """Placed part volume / used envelope (base area x max height)."""
        h = self.max_height_mm()
        if h <= 0:
            return 0.0
        envelope = self.plate_w_mm * self.plate_d_mm * h
        return self.placed_voxels * self.pitch ** 3 / envelope
