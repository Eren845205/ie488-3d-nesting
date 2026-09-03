"""c3_gpu_resident.py — Faz 3+: GPU-resident occupancy NFV decode (transfer tuzağını kaldırır).

BULGU (blyfs1jg8): naive cupy backend Plan2'de 0.65× (CPU-paralelden YAVAŞ) — her feasible_mask
çağrısında büyüyen occupancy crop'u host↔device kopyalanıyor = planın #1 riski "GPU per-place
transfer tuzağı". AZALTMA: occupancy CİHAZDA resident kalsın; place in-device |=; feasible+BLB
tamamen GPU'da; SADECE 3-int (oi,x,y,z) host'a döner. Grid'ler bir kez GPU'ya cache'lenir.

KALİTE-KORUMA: decode_gpu == scipy seri decode BİREBİR (aynı blb_xybbox mantığı + aynı key reduce;
f64 → mask identical). verify modu Plan2 556'yı doğrular.

ÜRETİME DOKUNMAZ (scripts/). cupy yoksa çalışmaz (bu script GPU-özel; üretim yolu c3_par_a fallback'li).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.c3_par_a import load, QTY, QTY_FULL, N_OR
from scripts.c3_backend import _probe_cupy, _scipy_feasible_mask
from scripts.c3_par_a import decode as cpu_decode

PITCH = 2.0


def _feasible_gpu(cp, occ_sub, grid_flip, full):
    """fftconvolve(occ, grid[::-1], 'valid')<0.5, tamamen GPU'da (cuFFT). full = s1+s2-1."""
    C = cp.fft.irfftn(cp.fft.rfftn(occ_sub, s=full) * cp.fft.rfftn(grid_flip, s=full), s=full)
    return C


def _blb_gpu(cp, mask):
    """BLB: en küçük z, sonra y, sonra x. cupy'de; ints döner (küçük scalar sync)."""
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(cp.argmax(sl.any(axis=0)))
    xstar = int(cp.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _blb_xybbox_gpu(cp, occ, grid_flip, gshape):
    """c3_backend.blb_xybbox'ın GPU-resident eşi. occ cihazda (mutasyon YOK burada).
    grid_flip = cihazdaki grid[::-1,::-1,::-1] (cache'li)."""
    fw, fd, fh = gshape
    nx, ny, nz = occ.shape
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        sub = occ[:, :, :z_lim]
        mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
        if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
            o = None
        elif not bool(sub.any()):
            o = (0, 0, 0)
        else:
            xs = cp.where(sub.any(axis=(1, 2)))[0]
            ys = cp.where(sub.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            cx0 = max(0, x0 - (fw - 1)); cx1 = min(nx, x1 + (fw - 1))
            cy0 = max(0, y0 - (fd - 1)); cy1 = min(ny, y1 + (fd - 1))
            crop = sub[cx0:cx1, cy0:cy1, :]
            mask = cp.ones(mshape, dtype=cp.bool_)
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                full = (crop.shape[0] + fw - 1, crop.shape[1] + fd - 1, crop.shape[2] + fh - 1)
                C = _feasible_gpu(cp, crop.astype(cp.float64), grid_flip, full)
                Cc = (C[fw - 1:crop.shape[0], fd - 1:crop.shape[1], fh - 1:crop.shape[2]] < 0.5)
                gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                bx = gx1 - cx0; by = gy1 - cy0
                if bx > 0 and by > 0:
                    mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
            o = _blb_gpu(cp, mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def decode_gpu(parts, nx, ny, pitch=PITCH, return_placements=False):
    """GPU-resident NFV decode. occupancy tek seferlik cihazda allocate; grid'ler cache'li;
    her parçada feasible+BLB GPU'da; place in-device; host'a yalnız (oi,x,y,z). BİREBİR (scipy seri)."""
    cp = _probe_cupy()
    if cp is None:
        raise RuntimeError("cupy/GPU yok — bu script GPU-özel (üretim yolu c3_par_a fallback'li)")

    # cuFFT plan cache'i SAYICA sınırla (farklı boyutlu 900+ plan birikimi = OOM). memsize
    # sınırlama YOK (tek büyük plan reddedilmesin); biriktirme sayı sınırı + periyodik free ile durur.
    try:
        cp.fft.config.get_plan_cache().set_size(4)
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()

    nz = int(800 * 2.0 / pitch)
    occ = cp.zeros((nx, ny, nz), dtype=cp.bool_)   # RESIDENT — bir kez allocate (~21MB @2mm)
    grid_cache = {}   # id(orient) -> (grid_gpu_bool, grid_flip_f64, shape)

    def _grids(orient):
        k = id(orient)
        g = grid_cache.get(k)
        if g is None:
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, orient.grid.shape)
            grid_cache[k] = g
        return g

    placements = []
    cur_max = 0
    n_placed = 0
    sorted_parts = sorted(parts, key=lambda vp: -vp.volume_voxels)
    for part in sorted_parts:
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            gb, gf, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            o = _blb_xybbox_gpu(cp, occ, gf, gshape)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            raise RuntimeError(f"GPU decode fallback gerekti (parça {part.id}) — prototip drop'u "
                               f"desteklemiyor; CPU yolunu kullan")
        oi, x, y, z = best
        gb, gf, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb     # in-device mutasyon (transfer YOK)
        cur_max = max(cur_max, z + fh)
        n_placed += 1
        if return_placements:
            placements.append((part.id, oi, x, y, z))
        # FFT geçici belleklerini sık serbest bırak (parçalanma/OOM önle, 6GB tüketici GPU)
        if n_placed % 4 == 0:
            mempool.free_all_blocks()

    cp.cuda.Stream.null.synchronize()
    h = cur_max * pitch
    return (h, placements) if return_placements else h


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    qty = QTY_FULL if mode in ("plan2", "verify") else QTY
    parts, nx, ny = load(qty, PITCH)
    print("=" * 66)
    print(f"C3 GPU-RESIDENT  mode={mode}  {len(parts)} parça {nx}x{ny}")
    print("=" * 66, flush=True)

    # warm-up (JIT + cuFFT plan decode dışı)
    cp = _probe_cupy()
    if cp is not None:
        _ = decode_gpu(parts[:3], nx, ny)

    t = time.perf_counter(); hg = decode_gpu(parts, nx, ny); dtg = time.perf_counter() - t
    print(f"  GPU-resident : {hg:.1f} mm  {dtg:.1f}s", flush=True)

    t = time.perf_counter()
    hs = cpu_decode(parts, nx, ny, feasible_mask=_scipy_feasible_mask, parallel=True, pitch=PITCH)
    dts = time.perf_counter() - t
    print(f"  scipy paralel: {hs:.1f} mm  {dts:.1f}s (Kol A, CPU)", flush=True)

    print("-" * 66)
    if abs(hg - hs) < 0.01:
        print(f"  -> [DOĞRU] birebir ({hg:.1f}) + GPU {dts/max(dtg,1e-9):.2f}x CPU-paralelden")
    else:
        print(f"  -> [HATA] FARKLI GPU={hg:.1f} CPU={hs:.1f} — DUR")


if __name__ == "__main__":
    main()
