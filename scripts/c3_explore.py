"""c3_explore.py — Faz 2 paralel kesif: 3 lever ayni anda (kullanici: zaman kaybetme).

Faz 2 bulgusu: SA-over-order + NFV-decode 184'te yakinsadi (floor 180'i gecemedi). Teshis:
darbogaz sirali-greedy DECODE (arama degil). Bu script 3 lever'i AYRI surec olarak paralel test eder:

  mode=bestfit : NFV + SUPPORT-MAX secim (BLB yerine) — parcayi en cok desteklenen feasible
                 konuma koy (asili kalmasin). Decode TAVANINI test eder. numune, largest+5perm.
                 support[x,y,z] = corr[x,y,z-1] (parca 1 asagida cakisma = alt-temas); z=0 zemin.
                 Tek correlation hem feasibility (corr<0.5) hem support verir.
  mode=alns    : ALNS-lite destroy-repair (worst-k removal -> basa tasi -> tam decode). numune.
  mode=plan2   : SA-NFV (decode_fixed) ASIL cavity verisi Plan2'de. yavas, dusuk budget.

GO: herhangi biri floor'u (numune 180 / Plan2 740) belirgin gecerse o lever kazaniyor.
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
MODE = sys.argv[1] if len(sys.argv) > 1 else "bestfit"
ITERS = int(sys.argv[2]) if len(sys.argv) > 2 else 60

# Plan2 (mode=plan2)
PLAN2_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLAN2_W, PLAN2_D = 328.74, 328.19
PLAN2_QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}


def nfv_corr(occ, grid):
    return fftconvolve(occ.astype(np.float64), grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")


def _blb_from_mask(mask):
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _support_origin(corr):
    """feasible (corr<0.5) origin'ler arasindan SUPPORT-MAX (tie: kucuk z). Yoksa None.
    support[x,y,z] = corr[x,y,z-1] (parca 1 asagida cakisma = alt-temas); z=0 -> zemin (buyuk)."""
    feas = corr < 0.5
    if not feas.any():
        return None
    mx, my, mz = corr.shape
    support = np.full(corr.shape, -1.0)
    support[:, :, 1:] = corr[:, :, :-1]
    support[:, :, 0] = 1e6  # zemin = tam destek
    support = np.where(feas, support, -np.inf)
    zidx = np.arange(mz, dtype=np.float64)
    score = support - 1e-6 * zidx[None, None, :]  # tie-break: kucuk z
    flat = int(np.argmax(score))
    x, y, z = np.unravel_index(flat, score.shape)
    return int(x), int(y), int(z)


def _make_bin(nx, ny):
    return OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)


def decode(order_oi, nx, ny, rule):
    """order_oi: [(part, oi_or_None)]. oi=None -> serbest (en iyi oi). rule: blb|support|fixed."""
    ob = _make_bin(nx, ny)
    chosen = []
    for part, fixed_oi in order_oi:
        cur_max = ob.max_height_voxels()
        oi_range = [fixed_oi] if fixed_oi is not None else range(len(part.orientations))
        best_key = None; best = None
        for oi in oi_range:
            orient = part.orientations[oi]
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            z_limit = min(ob.occupancy.shape[2], cur_max + fh + 1)
            corr = nfv_corr(ob.occupancy[:, :, :z_limit], orient.grid)
            if rule == "support":
                o = _support_origin(corr)
            else:  # blb / fixed
                o = _blb_from_mask(corr < 0.5)
            if o is None:
                continue
            x, y, z = o
            key = (max(z + fh, cur_max), z + fh, z, y, x, oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, x, y, z)
        if best is None:
            fb = _drop_fallback(ob, part if fixed_oi is None else _Single(part, fixed_oi))
            (x, y, z), doi = fb
            oi = fixed_oi if fixed_oi is not None else doi
            best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
        chosen.append((part, oi))
    return ob.height_mm(), chosen


class _Single:
    def __init__(self, part, oi):
        self.id = part.id
        self.orientations = [part.orientations[oi]]


def _load_numune():
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR, margin=MARGIN,
                              method="slice", orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    return parts, int(PLATE // PITCH), int(PLATE // PITCH), PLATE, PLATE


def _load_plan2():
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order
    from src.nesting3d.instances.format import to_voxel_parts
    stl_map = {f.stem: f.read_bytes() for f in sorted(PLAN2_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, PLAN2_QTY, container_w_mm=PLAN2_W, container_d_mm=PLAN2_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4, margin=MARGIN)
    return parts, int(PLAN2_W // PITCH), int(PLAN2_D // PITCH), PLAN2_W, PLAN2_D


def main():
    print("=" * 64)
    print(f"C3 EXPLORE  mode={MODE}  iters={ITERS}  pitch={PITCH}")
    print("=" * 64, flush=True)
    t = time.perf_counter()
    if MODE == "plan2":
        parts, nx, ny, pw, pd = _load_plan2()
    else:
        parts, nx, ny, pw, pd = _load_numune()
    print(f"voxelize: {len(parts)} parca, taban {nx}x{ny} ({time.perf_counter()-t:.0f}s)", flush=True)

    _, hb = dblf(parts, lambda: Bin3D(pw, pd, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[heightmap] {hm:.1f} mm", flush=True)

    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    rng = random.Random(SEED)

    if MODE == "bestfit":
        # support-max decode, largest + 5 perm (tavan + duyarlilik)
        orders = [("largest", largest)] + [(f"rand{s}", _shuf(parts, rng)) for s in range(5)]
        hs = []
        for name, order in orders:
            t = time.perf_counter()
            h, _ = decode([(p, None) for p in order], nx, ny, "support")
            hs.append(h)
            print(f"  bestfit {name:9s}: {h:6.1f} mm ({time.perf_counter()-t:.0f}s)", flush=True)
        lf = hs[0]; spread = (max(hs) - min(hs)) / min(hs) * 100
        print(f"  -> bestfit largest={lf:.1f}, spread={spread:.1f}%, heightmap={hm:.1f}")
        _verdict(lf, hm)

    elif MODE == "alns":
        # ALNS-lite: worst-k destroy -> basa tasi -> tam decode (fixed oi)
        t = time.perf_counter()
        cur_h, sol = decode([(p, None) for p in largest], nx, ny, "blb")
        print(f"  init {cur_h:.1f} ({time.perf_counter()-t:.0f}s)", flush=True)
        best, best_h = list(sol), cur_h
        t0, tmin = 4.0, 0.1
        cooling = (tmin / t0) ** (1.0 / max(ITERS - 1, 1)); temp = t0
        ts = time.perf_counter()
        for k in range(ITERS):
            kdes = rng.randint(2, max(2, len(sol) // 6))
            # worst-k: init decode'da yuksek yerlesenler ~ buyuk parcalar; basitce rastgele k al, basa tasi
            idxs = sorted(rng.sample(range(len(sol)), kdes))
            moved = [sol[i] for i in idxs]
            rest = [sol[i] for i in range(len(sol)) if i not in set(idxs)]
            rng.shuffle(moved)
            cand = moved + rest
            ch, cand2 = decode([(p, oi) for p, oi in cand], nx, ny, "fixed")
            d = ch - cur_h
            if d <= 0 or rng.random() < math.exp(-d / max(temp, 1e-9)):
                sol, cur_h = cand2, ch
                if cur_h < best_h:
                    best_h, best = cur_h, list(sol)
            temp *= cooling
            if (k + 1) % 10 == 0:
                print(f"  iter {k+1}/{ITERS}: cur={cur_h:.1f} best={best_h:.1f} ({time.perf_counter()-ts:.0f}s)", flush=True)
        print(f"  -> ALNS best={best_h:.1f}, heightmap={hm:.1f}")
        _verdict(best_h, hm)

    elif MODE == "plan2":
        # SA-NFV fixed-oi, asil Plan2 verisi
        t = time.perf_counter()
        cur_h, sol = decode([(p, None) for p in largest], nx, ny, "blb")
        dt = time.perf_counter() - t
        print(f"  NFV-greedy init {cur_h:.1f} ({dt:.0f}s/decode -> ~{dt*ITERS:.0f}s SA tahmin)", flush=True)
        best, best_h = list(sol), cur_h
        t0, tmin = 6.0, 0.2
        cooling = (tmin / t0) ** (1.0 / max(ITERS - 1, 1)); temp = t0
        ts = time.perf_counter()
        for k in range(ITERS):
            cand = _neighbour([(p, oi) for p, oi in sol], rng)
            ch, cand2 = decode(cand, nx, ny, "fixed")
            d = ch - cur_h
            if d <= 0 or rng.random() < math.exp(-d / max(temp, 1e-9)):
                sol, cur_h = cand2, ch
                if cur_h < best_h:
                    best_h, best = cur_h, list(sol)
            temp *= cooling
            print(f"  iter {k+1}/{ITERS}: cur={cur_h:.1f} best={best_h:.1f} ({time.perf_counter()-ts:.0f}s)", flush=True)
        print(f"  -> Plan2 SA-NFV best={best_h:.1f}, heightmap={hm:.1f}, Magics=492.39")
        _verdict(best_h, hm)
    print("=" * 64)


def _shuf(parts, rng):
    o = list(parts); rng.shuffle(o); return o


def _neighbour(sol, rng):
    n = len(sol); new = list(sol)
    m = rng.random()
    if m < 0.45 and n >= 2:
        i, j = rng.randrange(n), rng.randrange(n); new[i], new[j] = new[j], new[i]
    elif m < 0.65 and n >= 2:
        i = rng.randrange(n); e = new.pop(i); new.insert(rng.randrange(n), e)
    elif m < 0.80 and n >= 2:
        i, j = sorted((rng.randrange(n), rng.randrange(n))); new[i:j + 1] = list(reversed(new[i:j + 1]))
    else:
        i = rng.randrange(n); p, _oi = new[i]; new[i] = (p, rng.randrange(len(p.orientations)))
    return new


def _verdict(h, hm):
    if h < hm - 0.5:
        print(f"  -> [GO] floor'u (%{(hm-h)/hm*100:.1f}) GECTI")
    else:
        print(f"  -> [NO-GO] floor'u ({hm:.1f}) gecemedi")


if __name__ == "__main__":
    main()
