"""c3_speed.py — Faz 4: NFV-decode HIZ profili + hedefli hizlandirma.

Plan2 NFV decode ~985s/iter -> metaheuristic/fine pratik degil. Bu script ONCE profiller
(fftconvolve payi, parca-basina sure, secilen z dagilimi, z_limit dagilimi), sonra hedefli
hizlandirmayi DOGRULAR (hizli-decode == yavas-decode BIREBIR — kalite-koruma).

Testbed: m2 cavity-dominant Plan2 subset (24 parca, hizli). Mode:
  profile : yavas (mevcut) decode'u instrument et -> darbogaz raporu
  verify  : hizli decode == yavas decode birebir mi (kalite-koruma testi)
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import scipy.fft as _sfft
from scipy.signal import fftconvolve

_sfft.set_workers(max(1, (__import__("os").cpu_count() or 2)))  # cok-cekirdekli FFT
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
PITCH, N_OR, MARGIN = 2.0, 4, 1
MODE = sys.argv[1] if len(sys.argv) > 1 else "profile"

QTY = {
    "PO-TR154979-17747_P282335": 3, "part284676_06B23B8_model_r_0": 4,
    "part282114_07D4114_model_r_0": 3, "PO-TR154989-17667_P282407": 4,
    "PO-TR156122-17810_P284641": 4, "part282115_07D4113": 3,
    "PO-TR154979-17747_P282334": 3,
}

QTY_FULL = {  # Plan2 tam set (226 parca) — mode=plan2fast
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}

_t_fft = [0.0]
_n_fft = [0]


def nfv_corr(occ, grid):
    t = time.perf_counter()
    C = fftconvolve(occ.astype(np.float64), grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    _t_fft[0] += time.perf_counter() - t
    _n_fft[0] += 1
    return C


def _blb(mask):
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def decode_slow(parts, nx, ny, log=None):
    """Mevcut decode: her parca x orient fftconvolve(occ[:,:,:z_limit]). order=largest-first, serbest oi."""
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            z_limit = min(ob.occupancy.shape[2], cur_max + fh + 1)
            o = _blb(nfv_corr(ob.occupancy[:, :, :z_limit], orient.grid) < 0.5)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            fb = _drop_fallback(ob, part); (x, y, z), oi = fb
            best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
        if log is not None:
            log.append((cur_max, z, ob.occupancy.shape[2]))
    return ob.height_mm()


def blb_nfv_fast(ob, orient):
    """KADEMELI z-dilim: kucuk dilimle basla, feasible bulununca DUR. BLB min-z aradigindan
    kucuk dilimde bulunan feasible GLOBAL MIN'dir (buyuk dilim sadece daha yuksek z ekler) ->
    sonuc decode_slow ile BIREBIR ayni, ama fftconvolve cogu parcada ~fh+4 derinlik (102 degil)."""
    fw, fd, fh = orient.grid.shape
    nz = ob.occupancy.shape[2]
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        o = _blb(nfv_corr(ob.occupancy[:, :, :z_lim], orient.grid) < 0.5)
        if o is not None:
            return o  # bu dilimdeki min z = global min (BLB)
        if z_lim >= nz:
            return None
        z_cap *= 2


def decode_fast(parts, nx, ny):
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            o = blb_nfv_fast(ob, orient)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            fb = _drop_fallback(ob, part); (x, y, z), oi = fb
            best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
    return ob.height_mm()


def main():
    print("=" * 64)
    print(f"C3 SPEED  mode={MODE}  (m2 subset)")
    print("=" * 64, flush=True)
    qty = QTY_FULL if MODE == "plan2fast" else QTY
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, qty, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"testbed: {len(parts)} parca, taban {nx}x{ny}", flush=True)

    if MODE == "plan2fast":
        t = time.perf_counter()
        h = decode_fast(parts, nx, ny)
        dt = time.perf_counter() - t
        print(f"  decode_fast (Plan2): {h:.1f} mm  ({dt:.0f}s, fft {_t_fft[0]:.0f}s)", flush=True)
        print(f"  referans: slow 985s/decode, heightmap 740, NFV-greedy(slow) 556, Magics 492")
        if abs(h - 556.0) < 0.5:
            print(f"  -> 556 KORUNDU + {985/max(dt,1e-9):.1f}x hizli (kalite-koruma gecti)")
        else:
            print(f"  -> [DIKKAT] height {h:.1f} != 556 — kademeli dilim Plan2'de farkli sonuc (incele)")
        return

    if MODE == "profile":
        log = []
        t = time.perf_counter()
        h = decode_slow(parts, nx, ny, log=log)
        dt = time.perf_counter() - t
        zs = [z for _, z, _ in log]
        curs = [c for c, _, _ in log]
        print(f"  decode: {h:.1f} mm, {dt:.1f}s toplam", flush=True)
        print(f"  fftconvolve: {_t_fft[0]:.1f}s ({_t_fft[0]/dt*100:.0f}% of decode), {_n_fft[0]} cagri, ort {_t_fft[0]/max(_n_fft[0],1)*1000:.0f}ms/cagri")
        print(f"  secilen z (parca yerlesim): min={min(zs)} max={max(zs)} ort={np.mean(zs):.1f} median={np.median(zs):.0f}")
        print(f"  cur_max ilerleme: son={curs[-1]} (z_limit son parca ~{curs[-1]}+fh)")
        nlow = sum(1 for z in zs if z <= 3)
        print(f"  z<=3 (taban/dusuk) yerlesen: {nlow}/{len(zs)} (%{nlow/len(zs)*100:.0f}) -> z-erken-cikis potansiyeli")
        print("-" * 64)
        print("  -> fftconvolve baskinsa: O-FFT paylasimi / z-incremental / bbox-kirpma hedefle")

    elif MODE == "verify":
        _t_fft[0] = 0.0; _n_fft[0] = 0
        t = time.perf_counter()
        h_slow = decode_slow(parts, nx, ny)
        dt_slow = time.perf_counter() - t
        fft_slow = _t_fft[0]
        _t_fft[0] = 0.0; _n_fft[0] = 0
        t = time.perf_counter()
        h_fast = decode_fast(parts, nx, ny)
        dt_fast = time.perf_counter() - t
        print(f"  decode_slow: {h_slow:.1f} mm  ({dt_slow:.1f}s, fft {fft_slow:.1f}s)", flush=True)
        print(f"  decode_fast: {h_fast:.1f} mm  ({dt_fast:.1f}s, fft {_t_fft[0]:.1f}s)", flush=True)
        print("-" * 64)
        if abs(h_slow - h_fast) < 0.01:
            print(f"  -> [DOGRU] birebir ayni ({h_slow:.1f}) + {dt_slow/max(dt_fast,1e-9):.1f}x HIZLI (kalite-koruma gecti)")
        else:
            print(f"  -> [HATA] sonuc farkli ({h_slow:.1f} vs {h_fast:.1f}) — kademeli dilim BLB'yi bozuyor, DUR")


if __name__ == "__main__":
    main()
