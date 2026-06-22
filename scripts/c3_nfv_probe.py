"""c3_nfv_probe.py — Faz 0: gercek geometrik NFV correlation DOGRULUK + HIZ mikro-probe.

NFV (No-Fit-Voxel): bir parca P'nin occupancy O'ya gore cakismasiz gidebilecegi TUM (x,y,z)
origin'leri = korelasyon C[x,y,z] = sum_{a,b,c} O[x+a,y+b,z+c]*P[a,b,c]; C==0 -> feasible.

Dogru scipy cagrisi (KRITIK): ndimage.correlate merkezleme/origin-offset belirsizligi yuzunden
KULLANILMAZ. scipy.signal.fftconvolve(O, P[::-1,::-1,::-1], mode='valid') -> cikti sekli tam
(nx-fw+1, ny-fd+1, nz-fh+1), origin DOGRUDAN indeks. FFT float gurultusu icin tam-0 yerine
C < 0.5 esigi (P bool, en kucuk gercek cakisma = 1.0).

GO: FFT-valid (esik 0.5) = OccupancyBin3D.is_feasible oracle ile %100 ayni VE tek-parca NFV < ~1s.
NO-GO/fallback: gurultu esiklenemezse signal.correlate(..., method='direct') integer yolu.
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
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point

PITCH, PLATE, MARGIN, N_OR = 2.0, 335.0, 1, 8
SEED = 42
N_SAMPLES = 200  # oracle karsilastirma origin sayisi


def nfv_feasible_mask(occ: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """C < 0.5 olan origin'ler feasible. Cikti sekli (nx-fw+1, ny-fd+1, nz-fh+1)."""
    C = fftconvolve(occ.astype(np.float64),
                    grid[::-1, ::-1, ::-1].astype(np.float64),
                    mode="valid")
    return C < 0.5


def main():
    print("=" * 64)
    print(f"C3 FAZ 0 — NFV correlation probe (pitch={PITCH}, n_or={N_OR})")
    print("=" * 64, flush=True)

    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)
    nx = int(PLATE // PITCH)

    rng = random.Random(SEED)

    # --- Iki occupancy senaryosu: (a) bos bin, (b) ~10 parca yerlesmis bin ---
    scenarios = []
    # (a) bos
    ob_empty = OccupancyBin3D(nx, nx, nz_limit=200, pitch=PITCH)
    scenarios.append(("bos-bin", ob_empty))
    # (b) ~10 parca yerlesmis (cavity'siz EP packer ile gercekci occupancy)
    subset = sorted(parts, key=lambda vp: -vp.volume_voxels)[:10]
    _, ob_full = place_extreme_point(subset, lambda: OccupancyBin3D(nx, nx, nz_limit=400, pitch=PITCH))
    scenarios.append(("dolu-bin(10p)", ob_full))

    # --- Test parcalari: en buyuk 5 parcanin orientation 0 + 1 grid'leri ---
    test_orients = []
    for p in sorted(parts, key=lambda vp: -vp.volume_voxels)[:5]:
        for oi in (0, min(1, len(p.orientations) - 1)):
            test_orients.append((p, oi, p.orientations[oi]))

    total_mismatch = 0
    total_checks = 0
    max_t = 0.0
    for sc_name, ob in scenarios:
        occ = ob.occupancy
        for p, oi, orient in test_orients:
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > nx or fh > occ.shape[2]:
                continue
            t = time.perf_counter()
            mask = nfv_feasible_mask(occ, orient.grid)
            dt = time.perf_counter() - t
            max_t = max(max_t, dt)
            mx, my, mz = mask.shape  # = (nx-fw+1, ny-fd+1, nz-fh+1)
            if mx <= 0 or my <= 0 or mz <= 0:
                continue
            # ~N_SAMPLES rastgele origin'de oracle (is_feasible) ile bire-bir karsilastir
            mism = 0
            for _ in range(N_SAMPLES):
                x = rng.randrange(mx); y = rng.randrange(my); z = rng.randrange(mz)
                fft_feas = bool(mask[x, y, z])
                oracle = ob.is_feasible(orient, x, y, z)
                total_checks += 1
                if fft_feas != oracle:
                    mism += 1
            total_mismatch += mism
            if mism:
                print(f"  [MISMATCH] {sc_name} {p.name[:18]} oi={oi}: {mism}/{N_SAMPLES}", flush=True)

    print("-" * 64)
    print(f"oracle karsilastirma: {total_checks} origin, {total_mismatch} MISMATCH")
    print(f"en buyuk tek-parca NFV suresi: {max_t*1000:.1f} ms")
    go_doğru = (total_mismatch == 0)
    go_hız = (max_t < 1.0)
    if go_doğru and go_hız:
        print("  -> [GO] FFT-NFV oracle ile %100 ayni + tek-parca < 1s")
    elif not go_doğru:
        print("  -> [NO-GO] mismatch var -> indeksleme/esik sorunu; integer-direct fallback gerek")
    else:
        print(f"  -> [KISMI] dogru ama yavas ({max_t:.2f}s) -> Faz 4 hiz / sub-top dilim")
    print("=" * 64)


if __name__ == "__main__":
    main()
