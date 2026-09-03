"""c3_nfv_orderprobe.py — Faz 1 ★KRİTİK KAPI: gercek NFV-decode SIRAYA DUYARLI MI?

M2'de cavity-decode siraya DUYARSIZDI (6 sira -> 5'i ayni 300) -> order-arama ise yaramaz.
Bu, EP-cavity adaylariyla siniliydi. Bu probe GERCEK geometrik NFV (tum feasible origin uzayi,
fftconvolve) + bottom-left-back decode'u ayni soruyla test eder.

NFV-greedy decode: place_extreme_point iskeleti; TEK fark aday uretimi = EP-set yerine Faz 0'in
FFT-NFV feasible origin uzayi. Yerlestirme mevcut OccupancyBin3D.place ile.

IKI OLCUT AYRI:
 1. Sira-duyarlilik: largest-first + 5 rastgele permutasyon -> 6 yukseklik. spread=(max-min)/min.
    spread >= %2 -> DUYARLI.
 2. Heightmap-kiyas: NFV-greedy(largest-first) vs numune heightmap (Faz -1 = 180mm).

KARAR MATRISI:
  sira-duyarsiz            -> NO-GO, C3 OLU (ALNS sirayi degistirir ama sonuc sabit). DUR.
  duyarli + NFV<heightmap  -> CIFT GO (Faz 2-3 tam hiz)
  duyarli + NFV>=heightmap -> SARTLI GO (constructive miyopik ama sira onemli; ALNS'in yeri)
"""
from __future__ import annotations
import sys, time, random
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from scipy.signal import fftconvolve
from src.nesting3d.models import NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities
from src.nesting3d.extreme_point import OccupancyBin3D

PITCH, PLATE, MARGIN, N_OR = 2.0, 335.0, 1, 8
SEED = 42
HEIGHTMAP_REF = 180.0  # Faz -1 numune baseline


def nfv_feasible_mask(occ: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """C < 0.5 feasible. Cikti (nx-fw+1, ny-fd+1, nz-fh+1). (Faz 0 ile ayni.)"""
    C = fftconvolve(occ.astype(np.float64),
                    grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    return C < 0.5


def _blb_origin(mask: np.ndarray):
    """mask icinde bottom-left-back (min z, sonra min y, min x) feasible origin. Yoksa None.
    argwhere'siz (bos bin'de ~3M origin patlamasin) — any/argmax ile vektorize."""
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]            # (mx, my)
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def nfv_greedy_decode(parts, order, nx, ny, rule):
    pos = {id(p): i for i, p in enumerate(order)}
    ordered = sorted(parts, key=lambda vp: pos[id(vp)])
    ob = OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH)
    for part in ordered:
        cur_max = ob.max_height_voxels()
        best_key = None
        best = None  # (oi, x, y, z)
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            # SUB-TOP DILIM (Faz 4 hizindan one alindi — Faz 1 aksi halde kosamaz):
            # BLB zaten en dusuk z'yi secer; occupancy'nin envelope-ustu kismi (cur_max
            # ustu) asla secilmez. z_limit=cur_max+fh+1 dilimi sonucu DEGISTIRMEZ ama
            # erken parcalarda (cur_max kucuk) fftconvolve'u devasa hizlandirir.
            z_limit = min(ob.occupancy.shape[2], cur_max + fh + 1)
            mask = nfv_feasible_mask(ob.occupancy[:, :, :z_limit], orient.grid)
            o = _blb_origin(mask)
            if o is None:
                continue
            x, y, z = o
            zt = z + fh
            if rule == "lex":
                key = (zt, z, y, x, oi)
            else:  # cavity: envelope-ici tercih
                key = (max(zt, cur_max), zt, z, y, x, oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, x, y, z)
        if best is None:
            raise RuntimeError(f"{part.name}: hicbir orientation feasible degil (beklenmez)")
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
    return ob.height_mm()


def main():
    print("=" * 64)
    print(f"C3 FAZ 1 — NFV-decode SIRA-DUYARLILIK KAPISI (pitch={PITCH}, n_or={N_OR})")
    print(f"  heightmap referans (Faz -1) = {HEIGHTMAP_REF} mm")
    print("=" * 64, flush=True)

    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)
    nx = int(PLATE // PITCH)

    rng = random.Random(SEED)
    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    orders = [("largest", largest)]
    for s in range(5):
        o = list(parts); rng.shuffle(o)
        orders.append((f"rand{s}", o))

    for rule in ("lex", "cavity"):
        print(f"\n--- seçim kuralı: {rule} ---", flush=True)
        heights = []
        for name, order in orders:
            t = time.perf_counter()
            h = nfv_greedy_decode(parts, order, nx, nx, rule)
            heights.append(h)
            print(f"  {name:9s}: {h:6.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)
        hmin, hmax = min(heights), max(heights)
        spread = (hmax - hmin) / hmin * 100 if hmin else 0.0
        distinct = len(set(round(h, 1) for h in heights))
        lf = heights[0]  # largest-first
        print(f"  -> distinct={distinct}/6, spread={spread:.1f}%, largest-first={lf:.1f}mm")
        duyarli = spread >= 2.0
        gecti = lf < HEIGHTMAP_REF - 0.5
        if not duyarli:
            print(f"  -> [{rule}] SIRA-DUYARSIZ (spread<%2) — bu kuralda order-arama ise yaramaz")
        elif gecti:
            print(f"  -> [{rule}] DUYARLI + heightmap'i GECTI -> ÇİFT GO")
        else:
            print(f"  -> [{rule}] DUYARLI ama heightmap'i geçemedi -> ŞARTLI GO (ALNS'in yeri)")

    print("=" * 64)
    print("Genel karar: herhangi bir kuralda DUYARLI ise Faz 2 (ALNS) anlamli.")
    print("Iki kuralda da DUYARSIZ ise -> C3 OLU, raporla DUR.")
    print("=" * 64)


if __name__ == "__main__":
    main()
