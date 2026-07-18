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
# H-17: FFT bellek tavani — eksen-adaptif dilimli 'valid' konvolusyon
# --------------------------------------------------------------------------
# K-39/K-39b koku: fftconvolve TAM-BOY padded f64 tamponlari acar (pitch 1.0
# plakada (486,432,625)=1001MiB tekil alloc, tepe ~5GB -> MemoryError).
# 'valid' cikti eksen boyunca dilimlenebilir: cikti[i] yalniz occ[i:i+ker]
# penceresine bagli -> dilim basina ayri (kucuk) FFT, KARAR BIREBIR (cakisma
# sayisi tamsayi, f64 FFT hatasi ~1e-11 << 0.5 esik payi; olcum 2026-07-12
# bench_zchunk: orta boy maske birebir, tepe 608->179MB).
# Eksen secimi: out/ker orani en buyuk eksen (kanat: z; dikey cubuk: x —
# yanlis eksen dilimlemek overlap yuzunden kazandirmaz, olcum: cubukta
# z-dilim 2.5GB, x-dilim ~1GB). Butce SABIT default + env override —
# canli RAM'den TURETILMEZ (determinizm: ayni girdi -> ayni plan -> ayni
# yerlesim; A-serisi ilkesi). Tam-boy tahmin butceye sigarsa dilimsiz eski
# yol secilir -> mevcut @2mm sampiyon kosulari bit-ozdes kalir.
NFV_FFT_BUDGET_MB_DEFAULT = 768.0        # CPU tampon butcesi (bench: zc~64 -> tepe ~0.9GB)
NFV_FFT_GPU_BUDGET_MB_DEFAULT = 1536.0   # GPU (6GB VRAM kartta occ+cache disinda guvenli pay)
_FFT_BUF_FACTOR = 5.0  # olculen tepe / raw-padded-f64 orani (bench 2026-07-12: 4.6-7.0 bandi)


def _fft_budget_bytes(gpu: bool = False) -> float:
    env = os.environ.get("NFV_FFT_GPU_BUDGET_MB" if gpu else "NFV_FFT_BUDGET_MB")
    if env:
        try:
            return float(env) * 1e6
        except ValueError:
            pass
    return (NFV_FFT_GPU_BUDGET_MB_DEFAULT if gpu else NFV_FFT_BUDGET_MB_DEFAULT) * 1e6


def _padded_bytes(shape) -> float:
    """fftconvolve ic tamponu tahmini: next_fast_len'li full-boy f64 * tampon katsayisi."""
    cells = 1.0
    for n in shape:
        cells *= _sfft.next_fast_len(int(n), True)
    return cells * 8.0 * _FFT_BUF_FACTOR


def plan_fft_chunks(occ_shape, ker_shape, budget_bytes: Optional[float] = None):
    """Dilim plani: None -> tam-boy sigar (eski yol, bit-ozdes). (eksen, cikti_dilimi) -> dilimle.

    Deterministik: yalniz sekiller + butce (sabit/env) girdi; canli RAM okunmaz."""
    if budget_bytes is None:
        budget_bytes = _fft_budget_bytes()
    full = tuple(int(o) + int(k) - 1 for o, k in zip(occ_shape, ker_shape))
    if _padded_bytes(full) <= budget_bytes:
        return None
    out = tuple(int(o) - int(k) + 1 for o, k in zip(occ_shape, ker_shape))
    if min(out) <= 0:
        return None  # patolojik (cagiran mshape>0 garanti eder) — tam-boy birak
    # out/ker orani en buyuk eksen = dilim basina overlap vergisi (ker-1) en dusuk
    axis = max(range(3), key=lambda a: (out[a] / ker_shape[a], -a))
    if out[axis] <= 1:
        return None  # dilimlenecek genislik yok
    diger = 1.0
    for a in range(3):
        if a != axis:
            diger *= _sfft.next_fast_len(full[a], True)
    per_unit = diger * 8.0 * _FFT_BUF_FACTOR
    chunk = int(budget_bytes / per_unit) - int(ker_shape[axis]) + 1
    chunk = max(1, min(chunk, out[axis]))
    if chunk >= out[axis]:
        return None  # tek dilim = tam-boy
    return axis, chunk


def chunked_feasible_mask(base_fn: FeasibleMaskFn, occ: np.ndarray, grid: np.ndarray,
                          budget_bytes: Optional[float] = None) -> np.ndarray:
    """base_fn'i (herhangi bir backend maskesi) gerekirse eksen-dilimli uygula. Karar birebir."""
    plan = plan_fft_chunks(occ.shape, grid.shape, budget_bytes)
    if plan is None:
        return base_fn(occ, grid)
    axis, chunk = plan
    k = int(grid.shape[axis])
    out_n = int(occ.shape[axis]) - k + 1
    parcalar = []
    for s0 in range(0, out_n, chunk):
        s1 = min(s0 + chunk, out_n)
        sl = [slice(None)] * 3
        sl[axis] = slice(s0, s1 + k - 1)
        parcalar.append(base_fn(occ[tuple(sl)], grid))
    return np.concatenate(parcalar, axis=axis)


def _wrap_chunked(base_fn: FeasibleMaskFn) -> FeasibleMaskFn:
    def wrapped(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
        return chunked_feasible_mask(base_fn, occ_sub, grid)
    return wrapped


def gpu_conv_valid_chunked(cp, crop, grid_flip, gshape,
                           budget_bytes: Optional[float] = None,
                           fast_len: bool = False):
    """GPU-resident 'valid' feasibility karari (<0.5) — gerekirse eksen-dilimli.

    crop: cihazda bool occupancy kirpigi; grid_flip: cihazda ters-cevrili f64 kernel.
    Donus cihazda bool mask (host transferi YOK — GPU-resident semantik korunur).
    Dilimsiz dal mevcut _blb_xybbox_gpu konvolusyonuyla ayni matematik (bit-ozdes).

    fast_len (K-57 adayi, default False = eski yol BIREBIR): FFT boyutunu
    scipy.fft.next_fast_len ile cuFFT-dostu kompozite yuvarla (2^a·3^b·5^c·7^d).
    Sifir-padding buyur ama LINEER konvolusyonun valid bolgesi ayni matematik
    (wrap yok; kirpma indeksleri degismez) -> KARAR-birebir; yalniz FFT ic
    yuvarlamasi ~1e-12 duzeyinde degisebilir, 0-vs->=1 tamsayi karari icin
    yapisal tolerans 0.5. Olcum kapisiyla dogrulanmadan uretim yolu ACILMAZ."""
    if budget_bytes is None:
        budget_bytes = _fft_budget_bytes(gpu=True)
    fw, fd, fh = (int(g) for g in gshape)

    def _conv(sub):
        full = tuple(int(sub.shape[i]) + (fw, fd, fh)[i] - 1 for i in range(3))
        if fast_len:
            from scipy.fft import next_fast_len as _nfl
            fshape = tuple(int(_nfl(n)) for n in full)
        else:
            fshape = full
        C = cp.fft.irfftn(cp.fft.rfftn(sub.astype(cp.float64), s=fshape) *
                          cp.fft.rfftn(grid_flip, s=fshape), s=fshape)
        return C[fw - 1:sub.shape[0], fd - 1:sub.shape[1], fh - 1:sub.shape[2]] < 0.5

    plan = plan_fft_chunks(tuple(int(s) for s in crop.shape), (fw, fd, fh), budget_bytes)
    if plan is None:
        return _conv(crop)
    axis, chunk = plan
    k = (fw, fd, fh)[axis]
    out_n = int(crop.shape[axis]) - k + 1
    parcalar = []
    for s0 in range(0, out_n, chunk):
        s1 = min(s0 + chunk, out_n)
        sl = [slice(None)] * 3
        sl[axis] = slice(s0, s1 + k - 1)
        parcalar.append(_conv(crop[tuple(sl)]))
    return cp.concatenate(parcalar, axis=axis)


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
    İstenen yoksa SESSİZCE scipy'ye düşer (graceful fallback, ASLA hata).
    H-17: tüm backend'ler dilim-sarmalı — tam-boy bütçeye sığarsa dilimsiz (bit-özdeş)."""
    req = (name or os.environ.get("NFV_BACKEND", "auto")).lower()

    if req in ("cupy", "gpu", "auto"):
        cp = probe_cupy()
        if cp is not None:
            return _wrap_chunked(_make_cupy_feasible_mask(cp)), "cupy"

    if req in ("fast", "mkl", "mkl_fft", "pyfftw", "auto"):
        be, bename = probe_fast_backend()
        if be is not None:
            return _wrap_chunked(_make_fast_feasible_mask(be)), bename

    return _wrap_chunked(_scipy_feasible_mask), "scipy"


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
