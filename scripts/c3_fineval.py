"""c3_fineval.py — Faz B: NFV ÜRETİMİ geçer mi? (aynı pitch'te NFV vs üretim vs heightmap)

KULLANICI SORUSU (B): NFV cavity ham heightmap'i geçiyor (+%9-25, genellik kapısı), ama
ÜRETİM = coarse_to_fine+SA (Plan2 fine 0.5mm = 621). NFV bunu da geçer mi? Genellik kapısı
kaba 2.0mm'deydi; bu, DAHA İNCE pitch'te (1.5/1.0mm) ADİL kıyas yapar:
  - heightmap (dblf)             : ham üstten-düşürme tabanı
  - NFV-greedy (xy-bbox decode)  : cavity yöntemi
  - üretim (solve_coarse_to_fine): mevcut motor (portföy+SA), AYNI pitch
Hepsi aynı pitch -> elma-elma. + referans: eski üretim fine 621, Magics 492.

NFV < üretim ise -> NFV gerçek kalite kazancı, bağlamaya (A) değer.
NFV >= üretim ise -> cavity kaba'da iyi ama üretimin SA'sı fine'da kapatıyor; (A) sorgulanır.

arg: pitch (mm), örn 1.5 veya 1.0. ÜRETİME DOKUNMAZ (src/ salt-okunur çağrı).
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
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
N_OR, MARGIN = 4, 1
PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 40
MAGICS, PROD_FINE = 492.39, 621.0

QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}


def _blb(mask):
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any)); sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0))); xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _fft(occ, grid):
    return fftconvolve(occ.astype(np.float64), grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid") < 0.5


def _blb_xybbox(ob, orient):
    """c3_speed2 ile aynı: xy-bbox kırpmalı kademeli z-dilim NFV-BLB."""
    occ = ob.occupancy; fw, fd, fh = orient.grid.shape; nx, ny, nz = occ.shape
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap); sub = occ[:, :, :z_lim]
        mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
        if min(mshape) <= 0:
            o = None
        elif not sub.any():
            o = (0, 0, 0)
        else:
            xs = np.where(sub.any(axis=(1, 2)))[0]; ys = np.where(sub.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1; y0, y1 = int(ys[0]), int(ys[-1]) + 1
            cx0 = max(0, x0 - (fw - 1)); cx1 = min(nx, x1 + (fw - 1))
            cy0 = max(0, y0 - (fd - 1)); cy1 = min(ny, y1 + (fd - 1))
            crop = sub[cx0:cx1, cy0:cy1, :]
            mask = np.ones(mshape, bool)
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                Cc = _fft(crop, orient.grid)
                gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                bx, by = gx1 - cx0, gy1 - cy0
                if bx > 0 and by > 0:
                    mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
            o = _blb(mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def nfv_decode(parts, nx, ny):
    ob = OccupancyBin3D(nx, ny, nz_limit=int(800 * 2.0 / PITCH), pitch=PITCH)
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels(); best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            o = _blb_xybbox(ob, orient)
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


def main():
    print("=" * 70)
    print(f"C3 FAZ B — fine doğrulama  pitch={PITCH}mm  budget={BUDGET}")
    print(f"  referans: eski üretim fine(0.5) {PROD_FINE} | Magics {MAGICS}")
    print("=" * 70, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"voxelize: {len(parts)} parça, {nx}x{ny} ({time.perf_counter()-t:.0f}s)", flush=True)

    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[1] heightmap (dblf)      : {hm:7.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    t = time.perf_counter()
    nfv = nfv_decode(parts, nx, ny)
    print(f"[2] NFV-greedy (cavity)   : {nfv:7.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    t = time.perf_counter()
    prod = solve_coarse_to_fine(res.instance, plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                                coarse_pitch=PITCH, fine_pitch=PITCH, budget=BUDGET,
                                n_orientations=N_OR)
    ph = prod.height_mm
    print(f"[3] üretim (coarse+SA)    : {ph:7.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    print("-" * 70)
    print(f"  pitch={PITCH} | heightmap={hm:.1f} | NFV={nfv:.1f} | üretim={ph:.1f} | Magics={MAGICS}")
    print(f"  NFV vs heightmap: {(hm-nfv)/hm*100:+.1f}%   NFV vs üretim: {(ph-nfv)/ph*100:+.1f}%")
    if nfv < ph - 0.5:
        print(f"  -> [GO] NFV ÜRETİMİ geçti (%{(ph-nfv)/ph*100:.1f}) -> bağlamaya (A) değer; Magics'e %{(nfv-MAGICS)/MAGICS*100:.0f} kala")
    elif nfv < ph + 0.5:
        print(f"  -> NFV ~üretim (berabere) -> kaba kazanç fine'da kapanıyor; (A) marjinal")
    else:
        print(f"  -> NFV üretimden KÖTÜ -> üretimin SA'sı fine'da öne geçiyor; (A) sorgulanır")
    print("=" * 70)


if __name__ == "__main__":
    main()
