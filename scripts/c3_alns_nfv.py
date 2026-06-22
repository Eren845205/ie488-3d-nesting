"""c3_alns_nfv.py — Faz 2: NFV-decode'u GLOBAL ARAMAYA bağla (miyopiyi kır).

Faz 1 kanıtı: gercek NFV-decode SIRAYA DUYARLI (spread %9.7; M2'deki ~%0'in aksine) ama
NFV-greedy (186) heightmap'i (180) geçemiyor -> constructive miyopik. Bu, global aramanın
(sira+orientation uzerinde) tam yeri.

Bu MVP: M2'nin SA-over-order yapisi (swap/insert/reverse + orientation-flip) AMA decode =
NFV (M2'den TEK fark — ve belirleyici fark, cunku M2 EP-cavity duyarsizdi). Solution =
List[(part, oi)]; decode her parcayi SABIT oi ile NFV-BLB yerlestirir (tek orientation/parca
-> Faz 1'in 8-orient decode'undan ~8x hizli).

"Asla heightmap'ten kotu degil" iki katman:
  1. best floor = min(heightmap-DBLF, NFV-greedy-init); kabul edilen aday floor'u bozsa bile best korunur.
  2. NFV-decode'da feasible origin yoksa _drop_fallback (garantili heightmap-drop) -> tek decode patlamaz.

GO: SA-NFV < min(heightmap 180, NFV-greedy 186) belirgin -> global arama miyopiyi kirdi,
    tam ALNS + Plan2'ye olcekle. NO-GO: SA-NFV ~ NFV-greedy -> ayar/ALNS dene veya bırak.
"""
from __future__ import annotations
import sys, time, math, random
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from scipy.signal import fftconvolve
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

PITCH, PLATE, MARGIN, N_OR = 2.0, 335.0, 1, 8
SEED = 42
HEIGHTMAP_REF = 180.0
ITERS = int(sys.argv[1]) if len(sys.argv) > 1 else 60


def nfv_mask(occ, grid):
    C = fftconvolve(occ.astype(np.float64), grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    return C < 0.5


def _blb(mask):
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def decode_fixed(solution, nx, ny):
    """solution = [(part, oi)] sirali. Her parcayi SABIT oi ile NFV-BLB yerlestir."""
    ob = OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH)
    for part, oi in solution:
        orient = part.orientations[oi]
        fw, fd, fh = orient.grid.shape
        cur_max = ob.max_height_voxels()
        placed = False
        if fw <= nx and fd <= ny:
            z_limit = min(ob.occupancy.shape[2], cur_max + fh + 1)
            o = _blb(nfv_mask(ob.occupancy[:, :, :z_limit], orient.grid))
            if o is not None:
                ob.place(orient, o[0], o[1], o[2])
                placed = True
        if not placed:
            # garantili heightmap-drop (Solution oi sabit degilse _drop_fallback tum oi dener;
            # burada sabit oi icin manuel: drop sadece bu orient ile)
            fb = _drop_fallback(ob, _SinglePart(part, oi))
            (x, y, z), _doi = fb
            ob.place(orient, x, y, z)
    return ob.height_mm()


class _SinglePart:
    """_drop_fallback'in tek-orientation gormesi icin sarmalayici (Solution oi'sini sabitler)."""
    def __init__(self, part, oi):
        self.id = part.id
        self.orientations = [part.orientations[oi]]


def greedy_decode_free(order, nx, ny):
    """Faz 1 serbest-oi greedy: her parca icin EN IYI orientation+origin (NFV-BLB lex).
    Doner (chosen_solution=[(part,oi)], height) — SA icin iyi baslangic (Faz 1: ~186)."""
    ob = OccupancyBin3D(nx, ny, nz_limit=400, pitch=PITCH)
    chosen = []
    for part in order:
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            z_limit = min(ob.occupancy.shape[2], cur_max + fh + 1)
            o = _blb(nfv_mask(ob.occupancy[:, :, :z_limit], orient.grid))
            if o is None:
                continue
            key = (o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o)
        if best is None:
            fb = _drop_fallback(ob, part); (x, y, z), doi = fb
            best = (doi, (x, y, z))
        oi, (x, y, z) = best
        ob.place(part.orientations[oi], x, y, z)
        chosen.append((part, oi))
    return chosen, ob.height_mm()


def neighbour(sol, rng):
    n = len(sol); new = list(sol)
    m = rng.random()
    if m < 0.45 and n >= 2:        # swap
        i, j = rng.randrange(n), rng.randrange(n)
        new[i], new[j] = new[j], new[i]
    elif m < 0.65 and n >= 2:      # insert
        i = rng.randrange(n); e = new.pop(i); new.insert(rng.randrange(n), e)
    elif m < 0.80 and n >= 2:      # reverse segment
        i, j = sorted((rng.randrange(n), rng.randrange(n)))
        new[i:j + 1] = list(reversed(new[i:j + 1]))
    else:                          # orientation flip
        i = rng.randrange(n)
        p, _oi = new[i]
        new[i] = (p, rng.randrange(len(p.orientations)))
    return new


def main():
    print("=" * 64)
    print(f"C3 FAZ 2 — SA-over-(order+orient) + NFV-decode  (pitch={PITCH}, iters={ITERS})")
    print(f"  floor referans: heightmap {HEIGHTMAP_REF} | NFV-greedy(Faz1) 186")
    print("=" * 64, flush=True)

    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    print(f"voxelize: {len(parts)} parca ({time.perf_counter()-t:.0f}s)", flush=True)
    nx = int(PLATE // PITCH)

    # heightmap floor (mevcut uretim)
    _, hb = dblf(parts, lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[heightmap-DBLF] {hm:.1f} mm", flush=True)

    # init solution: Faz 1 serbest-oi greedy (sira+secilen orientation) — iyi baslangic (~186)
    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    t = time.perf_counter()
    sol, cur_h = greedy_decode_free(largest, nx, nx)
    print(f"[NFV-greedy init] {cur_h:.1f} mm  (serbest-oi, {time.perf_counter()-t:.0f}s)", flush=True)
    t = time.perf_counter()
    _verify = decode_fixed(sol, nx, nx)  # sabit-oi decode init ile tutarli mi (sağlama)
    dt = time.perf_counter() - t
    print(f"[decode_fixed sağlama] {_verify:.1f} mm  ({dt:.0f}s/decode -> ~{dt*ITERS:.0f}s SA tahmin)", flush=True)

    floor = min(hm, cur_h)  # best asla bunu gecemez (katman 1)
    rng = random.Random(SEED)
    best, best_h = list(sol), cur_h
    t0, tmin = 4.0, 0.1
    cooling = (tmin / t0) ** (1.0 / max(ITERS - 1, 1))
    temp = t0
    t_start = time.perf_counter()
    for k in range(ITERS):
        cand = neighbour(sol, rng)
        ch = decode_fixed(cand, nx, nx)
        d = ch - cur_h
        if d <= 0 or rng.random() < math.exp(-d / max(temp, 1e-9)):
            sol, cur_h = cand, ch
            if cur_h < best_h:
                best_h = cur_h; best = list(sol)
        temp *= cooling
        if (k + 1) % 10 == 0:
            print(f"  iter {k+1}/{ITERS}: cur={cur_h:.1f} best={best_h:.1f} ({time.perf_counter()-t_start:.0f}s)", flush=True)

    result = min(best_h, floor)  # floor garantisi (katman 1)
    print("-" * 64)
    print(f"  heightmap {hm:.1f} | NFV-greedy-init {min(floor,cur_h):.1f} | SA-NFV best {best_h:.1f} | guard'li {result:.1f}")
    base = min(hm, 186.0)
    if best_h < base - 0.5:
        print(f"  -> [GO] SA-NFV floor'u %{(base-best_h)/base*100:.1f} GECTI -> miyopi kirildi! tam ALNS + Plan2.")
    else:
        print(f"  -> [NO-GO/zayif] SA-NFV floor'u gecemedi -> ayar (iter/komsu/enerji) veya tam ALNS dene.")
    print("=" * 64)


if __name__ == "__main__":
    main()
