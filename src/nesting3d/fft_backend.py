"""fft_backend.py — NFV feasibility primitifi + takılabilir FFT backend'leri.

NFV decode'un çekirdeği: bir oryantasyonun her (x,y,z) konumunda parçanın occupancy ile çakışıp
çakışmadığı = `fftconvolve(occ, grid[::-1,::-1,::-1], 'valid') < 0.5` (occ/grid 0/1 → konvolüsyon =
tamsayı çakışma sayısı; f64 gürültüsü ≪0.5 → eşik birebir, feasible ⟺ sayı==0).

Backend'ler aynı boolean mask'i üretir: scipy (referans, hep var) / mkl_fft|pyfftw (CPU-hızlı) /
cupy (GPU). KRİTİK: scipy global state mutasyonu YOK — set_backend yalnız closure İÇİNDE (scoped);
opsiyonel kütüphaneler lazy import + fallback (yoksa scipy). xy-bbox kırpma + kademeli z-dilim + BLB
deterministik index mantığı BURADA tek-kaynak (seri ve paralel decode aynı `blb_xybbox`'ı çağırır).
"""
from __future__ import annotations
import os
from typing import Callable, Optional

import numpy as np
import scipy.fft as _sfft
from scipy.signal import fftconvolve

from src.nesting3d.capabilities import probe_cupy, probe_fast_backend

FeasibleMaskFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


# --------------------------------------------------------------------------
# Backend implementasyonları (hepsi AYNI boolean mask → birebir)
# --------------------------------------------------------------------------

def _scipy_feasible_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """REFERANS ORACLE. fftconvolve<0.5 → feasible bool mask."""
    C = fftconvolve(occ_sub.astype(np.float64),
                    grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    return C < 0.5


def _make_fast_feasible_mask(scipy_backend) -> FeasibleMaskFn:
    """mkl_fft/pyfftw: scipy.fft.set_backend ile SADECE transform motoru değişir (scoped, f64 boru
    hattı korunur → birebir-risk minimum)."""
    def fast_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
        with _sfft.set_backend(scipy_backend):
            C = fftconvolve(occ_sub.astype(np.float64),
                            grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
        return C < 0.5
    return fast_mask


def _make_cupy_feasible_mask(cp) -> FeasibleMaskFn:
    """GPU. SADECE cupy.fft (cuFFT) — cupyx.scipy.signal'in cublas/cusparse zincirini ATLAR (manuel
    fftconvolve 'valid'). f64 ZORUNLU (f32 gürültüsü büyük N'de 0.5'i aşıp kararı çevirir = birebir
    BOZAR). NOT: naive (her çağrı host↔device transfer); GPU-resident yol parallel_decode'da."""
    def cupy_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
        s1 = np.array(occ_sub.shape); s2 = np.array(grid.shape)
        full = tuple(int(v) for v in (s1 + s2 - 1))
        g_occ = cp.asarray(occ_sub, dtype=cp.float64)
        g_ker = cp.asarray(grid[::-1, ::-1, ::-1], dtype=cp.float64)
        C = cp.fft.irfftn(cp.fft.rfftn(g_occ, s=full) * cp.fft.rfftn(g_ker, s=full), s=full)
        valid = C[s2[0] - 1:s1[0], s2[1] - 1:s1[1], s2[2] - 1:s1[2]]
        return cp.asnumpy(valid < 0.5)
    return cupy_mask


def get_backend(name: Optional[str] = None) -> tuple[FeasibleMaskFn, str]:
    """feasible_mask + ad döner. name=None → oto (GPU→FastCPU→Scipy). NFV_BACKEND env override.
    İstenen yoksa SESSİZCE scipy'ye düşer (graceful fallback, ASLA hata)."""
    req = (name or os.environ.get("NFV_BACKEND", "auto")).lower()

    if req in ("cupy", "gpu", "auto"):
        cp = probe_cupy()
        if cp is not None:
            return _make_cupy_feasible_mask(cp), "cupy"

    if req in ("fast", "mkl", "mkl_fft", "pyfftw", "auto"):
        be, bename = probe_fast_backend()
        if be is not None:
            return _make_fast_feasible_mask(be), bename

    return _scipy_feasible_mask, "scipy"


# --------------------------------------------------------------------------
# Deterministik BLB mantığı (TEK KAYNAK — seri+paralel decode paylaşır)
# --------------------------------------------------------------------------

def blb(mask: np.ndarray):
    """Bottom-Left-Back: feasible mask'te en küçük z, sonra y, sonra x."""
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def blb_xybbox(occ: np.ndarray, grid: np.ndarray, feasible_mask: FeasibleMaskFn):
    """xy-bbox kırpmalı kademeli z-dilim NFV-BLB. occ READ-ONLY (paralel-güvenli).
    fftconvolve yalnız (dolu-xy-bbox ± parça-ayağı) bölgesinde; dışı feasible (sıfır occ katkısı yok)."""
    fw, fd, fh = grid.shape
    nx, ny, nz = occ.shape
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        sub = occ[:, :, :z_lim]
        mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
        if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
            o = None
        elif not sub.any():
            o = (0, 0, 0)
        else:
            xs = np.where(sub.any(axis=(1, 2)))[0]
            ys = np.where(sub.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            cx0 = max(0, x0 - (fw - 1)); cx1 = min(nx, x1 + (fw - 1))
            cy0 = max(0, y0 - (fd - 1)); cy1 = min(ny, y1 + (fd - 1))
            crop = sub[cx0:cx1, cy0:cy1, :]
            mask = np.ones(mshape, dtype=bool)
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                Cc = feasible_mask(crop, grid)
                gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                bx = gx1 - cx0; by = gy1 - cy0
                if bx > 0 and by > 0:
                    mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
            o = blb(mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2
