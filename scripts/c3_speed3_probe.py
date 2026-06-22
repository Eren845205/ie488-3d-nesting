"""c3_speed3_probe.py — bit-pack GERÇEKTEN FFT'yi geçer mi? TEK MİKRO-PROBE (ÖLÇ-ÖNCE).

Hipotez (kullanıcıya revize): kademeli z-dilim z'yi zaten minimize etti; kalan maliyet
YOĞUN XY-korelasyonu (164x164). Bit-pack yalnız z'yi sıkıştırır -> xy'ye yardım etmez.
Bu probe: gerçek mid-decode occupancy'de TEK (occ,part) için fftconvolve süresi vs
bit-pack (uint64 z-paketleme + solid-kolon döngüsü) collision-map süresi. Aynı feasible
set + hangisi hızlı? Bit-pack belirgin hızlı DEĞİLSE -> rewrite boşa, parallellik gerçek kol.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from scipy.signal import fftconvolve
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D, PITCH, N_OR, MARGIN = 328.74, 328.19, 2.0, 4, 1
QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "PARCA_NYLON-12_KABLO_KORUMA": 60, "PO-TR154989-17667_P282407": 20,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
}


def fft_feas(occ, grid, z_lim):
    C = fftconvolve(occ[:, :, :z_lim].astype(np.float64),
                    grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    return C < 0.5


def bitpack_feas(occ, grid, z_lim):
    """occ[:,:,:z_lim] (nx,ny,z) ve grid (fw,fd,fh) -> feasible (nx-fw+1,ny-fd+1,z-fh+1).
    z-ekseni uint64 paketle; her parça solid-kolonu için (occ_words AND part_shifted) OR-reduce."""
    nx, ny, _ = occ.shape
    fw, fd, fh = grid.shape
    mz = z_lim - fh + 1
    if mz <= 0:
        return np.zeros((nx - fw + 1, ny - fd + 1, 0), bool)
    occz = occ[:, :, :z_lim]
    W = (z_lim + 63) // 64
    # occ paketle: (nx,ny,W) uint64
    pad = np.zeros((nx, ny, W * 64), bool); pad[:, :, :z_lim] = occz
    pr = pad.reshape(nx, ny, W, 64)
    wts = (np.uint64(1) << np.arange(64, dtype=np.uint64))
    occ_w = np.zeros((nx, ny, W), np.uint64)
    for i in range(64):
        occ_w |= (pr[:, :, :, i].astype(np.uint64) << np.uint64(i))
    # parça solid kolonlar (a,b) -> z-bit listesi
    cols = []
    for a in range(fw):
        for b in range(fd):
            zb = np.where(grid[a, b, :])[0]
            if zb.size:
                cols.append((a, b, zb))
    ox, oy = nx - fw + 1, ny - fd + 1
    feas = np.zeros((ox, oy, mz), bool)
    # her aday z için collision (ascending değil — adil tam-map kıyası, FFT de tam-map)
    for zz in range(mz):
        collide = np.zeros((ox, oy), bool)
        for (a, b, zbits) in cols:
            absz = zbits + zz
            ww = absz >> 6; bb = (absz & 63).astype(np.uint64)
            # her dokunulan word için scalar mask
            seen = {}
            for w_i, b_i in zip(ww, bb):
                seen[int(w_i)] = seen.get(int(w_i), np.uint64(0)) | (np.uint64(1) << b_i)
            sub = occ_w[a:a + ox, b:b + oy, :]
            for w_i, m in seen.items():
                collide |= (sub[:, :, w_i] & m) != 0
            if collide.all():
                break
        feas[:, :, zz] = ~collide
    return feas


def main():
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"{len(parts)} parça, {nx}x{ny}", flush=True)

    # mid-decode occ kur — GERÇEKÇİ: NFV-BLB ile ilk yarıyı düzgün yerleştir (z_lim gerçekçi)
    def _blb(mask):
        z_any = mask.any(axis=(0, 1))
        if not z_any.any():
            return None
        zstar = int(np.argmax(z_any)); sl = mask[:, :, zstar]
        ystar = int(np.argmax(sl.any(axis=0))); xstar = int(np.argmax(sl[:, ystar]))
        return xstar, ystar, zstar

    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    ordered = sorted(parts, key=lambda vp: -vp.volume_voxels)
    for part in ordered[:len(ordered) // 2]:
        cur = ob.max_height_voxels(); best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            nz = ob.occupancy.shape[2]; z_cap = fh + 4; o = None
            while True:
                zl = min(nz, z_cap)
                o = _blb(fft_feas(ob.occupancy, orient.grid, zl))
                if o is not None or zl >= nz:
                    break
                z_cap *= 2
            if o is None:
                continue
            key = (max(o[2] + fh, cur), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            continue
        oi, x, y, z = best; ob.place(part.orientations[oi], x, y, z)
    cur_max = ob.max_height_voxels()
    occ = ob.occupancy
    print(f"mid-decode occ: cur_max={cur_max}, occ.shape={occ.shape}, doluluk={occ.mean()*100:.1f}%", flush=True)

    # birkaç parçada fftconvolve vs bitpack
    print(f"{'parça':28s} {'z_lim':>6s} {'FFT(ms)':>9s} {'bitpack(ms)':>12s} {'eşit?':>6s} {'kolon':>6s}")
    for part in ordered[:6]:
        orient = part.orientations[0]
        fw, fd, fh = orient.grid.shape
        z_lim = min(occ.shape[2], cur_max + fh + 1)
        t = time.perf_counter(); f1 = fft_feas(occ, orient.grid, z_lim); t1 = (time.perf_counter() - t) * 1000
        t = time.perf_counter(); f2 = bitpack_feas(occ, orient.grid, z_lim); t2 = (time.perf_counter() - t) * 1000
        eq = bool(f1.shape == f2.shape and np.array_equal(f1, f2))
        ncol = int(orient.grid.any(axis=2).sum())
        print(f"{part.name[:28]:28s} {z_lim:6d} {t1:9.1f} {t2:12.1f} {str(eq):>6s} {ncol:6d}", flush=True)
    print("-" * 70)
    print("Bitpack FFT'den BELİRGİN hızlı değilse -> rewrite boşa; gerçek kol = parallellik.")


if __name__ == "__main__":
    main()
