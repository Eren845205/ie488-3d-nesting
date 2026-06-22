"""c3_speed2.py — Faz C (hız): xy-bbox kırpma ile fftconvolve hızlandırma.

Faz4 (c3_speed.py) kademeli z-dilim ile 985->376s (2.6x) yaptı; fftconvolve hâlâ %99.
Bu script SONRAKİ hız kolu = XY-BBOX KIRPMA. Kanıt: C[x,y,z] = parça@origin ile occupancy
çakışması; occupancy yalnız DOLU bölgede !=0, dışarıda C=0 (=feasible). Bu yüzden fftconvolve'u
yalnız (dolu-bbox + parça-ayağı kadar genişletilmiş) bölgede hesapla, dışarıyı feasible işaretle.
Erken parçalarda (dolu-bbox küçük) devasa hızlanır; geç parçalarda bbox~tam plaka -> kayıp yok.

KALİTE-KORUMA: decode_xybbox == decode_fast BİREBİR olmalı (matematiksel özdeş; sadece sıfır
bölgenin FFT'si atlanıyor). verify mode bunu test eder. Bozarsa DUR.

Mode:
  verify   : decode_fast == decode_xybbox birebir mi + hız (m2 subset, hızlı)
  plan2    : decode_xybbox Plan2 tam set (556 korunmalı + decode_fast'tan hızlı mı)
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import scipy.fft as _sfft
from scipy.signal import fftconvolve

_sfft.set_workers(max(1, (__import__("os").cpu_count() or 2)))
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
PITCH, N_OR, MARGIN = 2.0, 4, 1
MODE = sys.argv[1] if len(sys.argv) > 1 else "verify"

QTY = {  # m2 cavity-dominant subset (24 parça, hızlı)
    "PO-TR154979-17747_P282335": 3, "part284676_06B23B8_model_r_0": 4,
    "part282114_07D4114_model_r_0": 3, "PO-TR154989-17667_P282407": 4,
    "PO-TR156122-17810_P284641": 4, "part282115_07D4113": 3,
    "PO-TR154979-17747_P282334": 3,
}
QTY_FULL = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}

_t_fft = [0.0]; _n_fft = [0]


def _fft(occ, grid):
    t = time.perf_counter()
    C = fftconvolve(occ.astype(np.float64), grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    _t_fft[0] += time.perf_counter() - t; _n_fft[0] += 1
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


# ---- BASELINE (c3_speed.decode_fast ile birebir aynı) ----
def _blb_nfv_fast(ob, orient):
    fw, fd, fh = orient.grid.shape
    nz = ob.occupancy.shape[2]
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        o = _blb(_fft(ob.occupancy[:, :, :z_lim], orient.grid) < 0.5)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


# ---- YENİ: xy-bbox kırpma ----
def _blb_nfv_xybbox(ob, orient):
    """fftconvolve yalnız (dolu-xy-bbox ± (parça-ayağı-1)) bölgesinde. Dışı C=0=feasible.
    Sonuç _blb_nfv_fast ile BİREBİR (sıfır occupancy bölgesi convolution'a katkı vermez)."""
    occ = ob.occupancy
    fw, fd, fh = orient.grid.shape
    nx, ny, nz = occ.shape
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        sub = occ[:, :, :z_lim]
        # valid-origin mask tam boyutu (plaka sınırını kodlar):
        mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
        if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
            o = None
        elif not sub.any():
            # tamamen boş dilim -> her origin feasible -> BLB = (0,0,0)
            o = (0, 0, 0)
        else:
            xs = np.where(sub.any(axis=(1, 2)))[0]
            ys = np.where(sub.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            # parça-ayağı kadar (fw-1, fd-1) iki taraflı genişlet, plakaya kırp
            cx0 = max(0, x0 - (fw - 1)); cx1 = min(nx, x1 + (fw - 1))
            cy0 = max(0, y0 - (fd - 1)); cy1 = min(ny, y1 + (fd - 1))
            crop = sub[cx0:cx1, cy0:cy1, :]
            # crop 'valid' origin'leri (crop-yerel), global = + (cx0, cy0, 0)
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                Ccrop = _fft(crop, orient.grid) < 0.5  # (cx1-cx0-fw+1, cy1-cy0-fd+1, z_lim-fh+1)
            else:
                Ccrop = None
            # tam mask: dolu-bbox dışı feasible (True)
            mask = np.ones(mshape, dtype=bool)
            if Ccrop is not None:
                gx0 = cx0; gx1 = cx0 + Ccrop.shape[0]
                gy0 = cy0; gy1 = cy0 + Ccrop.shape[1]
                # global origin pencerelerini mask sınırına kırp (üst sınır mshape)
                gx1 = min(gx1, mshape[0]); gy1 = min(gy1, mshape[1])
                bx = gx1 - gx0; by = gy1 - gy0
                if bx > 0 and by > 0:
                    mask[gx0:gx1, gy0:gy1, :] = Ccrop[:bx, :by, :]
            o = _blb(mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def _decode(parts, nx, ny, blb_fn):
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            o = blb_fn(ob, orient)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            (x, y, z), oi = _drop_fallback(ob, part); best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
    return ob.height_mm()


def _load(qty):
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, qty, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    return parts, int(PLATE_W // PITCH), int(PLATE_D // PITCH)


def main():
    print("=" * 66)
    print(f"C3 SPEED2 (xy-bbox kırpma)  mode={MODE}")
    print("=" * 66, flush=True)

    if MODE == "verify":
        parts, nx, ny = _load(QTY)
        print(f"testbed: {len(parts)} parça, {nx}x{ny}", flush=True)
        _t_fft[0] = 0; _n_fft[0] = 0
        t = time.perf_counter(); h0 = _decode(parts, nx, ny, _blb_nfv_fast); dt0 = time.perf_counter()-t; f0 = _t_fft[0]
        _t_fft[0] = 0; _n_fft[0] = 0
        t = time.perf_counter(); h1 = _decode(parts, nx, ny, _blb_nfv_xybbox); dt1 = time.perf_counter()-t; f1 = _t_fft[0]
        print(f"  decode_fast  : {h0:.1f} mm  ({dt0:.1f}s, fft {f0:.1f}s)", flush=True)
        print(f"  decode_xybbox: {h1:.1f} mm  ({dt1:.1f}s, fft {f1:.1f}s)", flush=True)
        print("-" * 66)
        if abs(h0 - h1) < 0.01:
            print(f"  -> [DOĞRU] birebir aynı ({h0:.1f}) + {dt0/max(dt1,1e-9):.2f}x hızlı (kalite-koruma geçti)")
        else:
            print(f"  -> [HATA] FARKLI ({h0:.1f} vs {h1:.1f}) — xy-bbox BLB'yi bozuyor, DUR")
    elif MODE == "plan2":
        parts, nx, ny = _load(QTY_FULL)
        print(f"testbed: {len(parts)} parça (Plan2 tam), {nx}x{ny}", flush=True)
        t = time.perf_counter(); h = _decode(parts, nx, ny, _blb_nfv_xybbox); dt = time.perf_counter()-t
        print(f"  decode_xybbox (Plan2): {h:.1f} mm  ({dt:.0f}s, fft {_t_fft[0]:.0f}s = %{_t_fft[0]/dt*100:.0f})", flush=True)
        print(f"  referans: Faz4 decode_fast 376s/556, heightmap 740, Magics 492")
        if abs(h - 556.0) < 0.5:
            print(f"  -> 556 KORUNDU + {376/max(dt,1e-9):.2f}x (decode_fast'a göre)")
        else:
            print(f"  -> [DİKKAT] {h:.1f} != 556 — incele")


if __name__ == "__main__":
    main()
