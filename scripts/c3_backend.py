"""c3_backend.py — Faz 0: FFT-korelasyon backend soyutlaması + capability probe.

PLAN (composed-churning-token.md, Katman 1+2): NFV decode'un feasibility primitifini
(`fftconvolve(occ,grid[::-1,::-1,::-1],'valid') < 0.5`) tek dar fonksiyona indir; arkasına
takılabilir backend'ler koy (scipy=referans / mkl_fft|pyfftw=fast / cupy=GPU), hepsi BİREBİR
aynı boolean mask üretsin. Donanımı çalışma anında algıla, yoksa sessizce scipy'ye düş.

xy-bbox kırpma + kademeli z-dilim + BLB seçimi (deterministik index mantığı) BURADA tek-kaynak
tutulur (`blb_xybbox`) — seri ve paralel decode AYNI fonksiyonu çağırır → birebir-koruma garanti.

ÜRETİME DOKUNMAZ: deney katmanı (scripts/). src/ Faz 5'e kadar değişmez.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import scipy.fft as _sfft
from scipy.signal import fftconvolve

# ======================================================================
# Katman 1 — feasible_mask primitifi + backend registry
# ======================================================================

FeasibleMaskFn = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _scipy_feasible_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """REFERANS ORACLE. c3_speed2._fft ile birebir: konvolüsyon<0.5 → feasible bool mask.
    occ/grid 0/1 olduğundan gerçek konvolüsyon = tamsayı çakışma sayısı; f64 gürültüsü ≪0.5
    → eşik birebir (feasible ⟺ sayı==0)."""
    C = fftconvolve(occ_sub.astype(np.float64),
                    grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
    return C < 0.5


def _make_fast_feasible_mask(scipy_backend) -> FeasibleMaskFn:
    """FastCPU (mkl_fft / pyfftw): scipy.fft.set_backend ile SADECE transform motoru değişir;
    scipy'nin f64 'valid' boru hattı byte-byte korunur → birebir-risk minimum. (Faz 2 kapısı:
    array_equal vs scipy zorunlu.)"""
    def fast_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
        with _sfft.set_backend(scipy_backend):
            C = fftconvolve(occ_sub.astype(np.float64),
                            grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
        return C < 0.5
    return fast_mask


def _make_cupy_feasible_mask(cupy_mod) -> FeasibleMaskFn:
    """GPU. SADECE cupy.fft (cuFFT) kullanır — cupyx.scipy.signal'in cublas/cusparse/cusolver
    bağımlılık zincirini ATLAR (manuel fftconvolve 'valid'). f64 ZORUNLU (f32 gürültüsü büyük
    N'de 0.5'i aşıp kararı çevirir = birebir BOZAR).
    fftconvolve(occ, grid[::-1,::-1,::-1], 'valid') = irfftn(rfftn(occ)·rfftn(grid_flip)) → valid dilim.
    NOT: naive — her çağrıda host↔device transfer. Faz 3'te occupancy GPU-resident olacak."""
    cp = cupy_mod
    def cupy_mask(occ_sub: np.ndarray, grid: np.ndarray) -> np.ndarray:
        s1 = np.array(occ_sub.shape); s2 = np.array(grid.shape)
        full = tuple(int(v) for v in (s1 + s2 - 1))
        g_occ = cp.asarray(occ_sub, dtype=cp.float64)
        g_ker = cp.asarray(grid[::-1, ::-1, ::-1], dtype=cp.float64)
        C = cp.fft.irfftn(cp.fft.rfftn(g_occ, s=full) * cp.fft.rfftn(g_ker, s=full), s=full)
        # 'valid' dilim: full[s2-1 : s1] → shape s1-s2+1
        valid = C[s2[0]-1:s1[0], s2[1]-1:s1[1], s2[2]-1:s1[2]]
        return cp.asnumpy(valid < 0.5)
    return cupy_mask


# --- backend probe + registry (graceful fallback) ---

def _probe_fast_backend():
    """mkl_fft / pyfftw scipy-arayüzü var mı? Yoksa None (scipy'ye düş)."""
    try:
        import mkl_fft._scipy_fft as _mkl  # type: ignore
        return _mkl, "mkl_fft"
    except Exception:
        pass
    try:
        import mkl_fft.interfaces.scipy_fft as _mkl2  # type: ignore
        return _mkl2, "mkl_fft"
    except Exception:
        pass
    try:
        import pyfftw.interfaces.scipy_fft as _pf  # type: ignore
        return _pf, "pyfftw"
    except Exception:
        pass
    return None, None


def _probe_cupy():
    """cupy + GPU gerçekten kullanılabilir mi? (import + cihaz + f64 allocate + cuFFT smoke).
    SADECE cupy.fft denenir (cupyx.scipy.signal'in ağır bağımlılık zinciri YOK). Döner: cp | None."""
    try:
        import cupy as cp  # type: ignore
        if cp.cuda.runtime.getDeviceCount() <= 0:
            return None
        _ = cp.fft.rfftn(cp.zeros((4, 4, 4), dtype=cp.float64))  # cuFFT gerçekten yüklen-çalışır mı
        return cp
    except Exception:
        return None


def get_backend(name: Optional[str] = None) -> tuple[FeasibleMaskFn, str]:
    """feasible_mask + ad döner. name=None → oto (GPU→FastCPU→Scipy). NFV_BACKEND env override.
    İstenen backend yoksa SESSİZCE scipy'ye düşer (hata değil = graceful fallback)."""
    req = (name or os.environ.get("NFV_BACKEND", "auto")).lower()

    if req in ("cupy", "gpu", "auto"):
        cp = _probe_cupy()
        if cp is not None:
            return _make_cupy_feasible_mask(cp), "cupy"
        if req in ("cupy", "gpu"):
            print("  [backend] cupy/GPU bulunamadı → scipy'ye düşülüyor")

    if req in ("fast", "mkl", "mkl_fft", "pyfftw", "auto"):
        be, bename = _probe_fast_backend()
        if be is not None:
            return _make_fast_feasible_mask(be), bename
        if req in ("fast", "mkl", "mkl_fft", "pyfftw"):
            print("  [backend] mkl_fft/pyfftw bulunamadı → scipy'ye düşülüyor")

    return _scipy_feasible_mask, "scipy"


# ======================================================================
# Katman 1 — deterministik BLB mantığı (TEK KAYNAK, seri+paralel paylaşır)
# ======================================================================

def blb(mask: np.ndarray):
    """Bottom-Left-Back: feasible mask'te en küçük z, sonra y, sonra x. c3_speed2._blb birebir."""
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def blb_xybbox(occ: np.ndarray, grid: np.ndarray, feasible_mask: FeasibleMaskFn):
    """xy-bbox kırpmalı kademeli z-dilim NFV-BLB. c3_speed2._blb_nfv_xybbox ile BİREBİR;
    fark sadece feasibility çağrısının backend'e soyutlanması (mantık aynı). occ READ-ONLY."""
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
            if crop.shape[0] >= fw and crop.shape[1] >= fd:
                Ccrop = feasible_mask(crop, grid)
            else:
                Ccrop = None
            mask = np.ones(mshape, dtype=bool)
            if Ccrop is not None:
                gx0 = cx0; gx1 = min(cx0 + Ccrop.shape[0], mshape[0])
                gy0 = cy0; gy1 = min(cy0 + Ccrop.shape[1], mshape[1])
                bx = gx1 - gx0; by = gy1 - gy0
                if bx > 0 and by > 0:
                    mask[gx0:gx1, gy0:gy1, :] = Ccrop[:bx, :by, :]
            o = blb(mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


# ======================================================================
# Katman 2 — Capability probe (Windows-safe, graceful)
# ======================================================================

@dataclass
class Capabilities:
    cpu_count: int
    ram_bytes: int
    gpu: bool
    gpu_fp64: bool
    fast_fft: bool
    fast_name: Optional[str]
    slurm: bool

    def summary(self) -> str:
        ram_gb = self.ram_bytes / 1e9
        return (f"cpu={self.cpu_count} ram={ram_gb:.1f}GB gpu={self.gpu}"
                f"(fp64={self.gpu_fp64}) fast_fft={self.fast_name or '-'} slurm={self.slurm}")


def _affinity_cpu_count() -> int:
    """cgroup/SLURM'e saygılı çekirdek sayısı. Windows'ta sched_getaffinity YOK → cpu_count."""
    n = None
    sca = getattr(os, "sched_getaffinity", None)
    if sca is not None:
        try:
            n = len(sca(0))
        except Exception:
            n = None
    if n is None:
        env = os.environ.get("SLURM_CPUS_PER_TASK")
        if env and env.isdigit():
            n = int(env)
    if n is None:
        n = os.cpu_count() or 1
    return max(1, n)


def _ram_bytes() -> int:
    """best-effort RAM; yeni hard-dep YOK (psutil → /proc/meminfo → Windows ctypes → default)."""
    try:
        import psutil  # type: ignore
        return int(psutil.virtual_memory().total)
    except Exception:
        pass
    try:  # Linux
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    try:  # Windows
        import ctypes
        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = _MS(); ms.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return int(ms.ullTotalPhys)
    except Exception:
        pass
    return 4 * 1024 ** 3  # muhafazakâr default 4GB


def probe_capabilities() -> Capabilities:
    cp = _probe_cupy()
    gpu = cp is not None
    gpu_fp64 = False
    if gpu:
        try:
            _ = cp.zeros(4, dtype=cp.float64) + 1.0  # f64 gerçekten çalışıyor mu
            gpu_fp64 = True
        except Exception:
            gpu_fp64 = False
    fast, fname = _probe_fast_backend()
    return Capabilities(
        cpu_count=_affinity_cpu_count(),
        ram_bytes=_ram_bytes(),
        gpu=gpu, gpu_fp64=gpu_fp64,
        fast_fft=fast is not None, fast_name=fname,
        slurm=bool(os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_ARRAY_TASK_ID")),
    )


if __name__ == "__main__":
    caps = probe_capabilities()
    print("Capabilities:", caps.summary())
    fn, name = get_backend()
    print("Seçilen backend:", name)
    # küçük birebir smoke testi: rastgele occ/grid, fast/gpu varsa scipy ile array_equal
    rng = np.random.default_rng(0)
    occ = (rng.random((20, 18, 16)) < 0.3)
    grid = (rng.random((5, 4, 3)) < 0.5)
    ref = _scipy_feasible_mask(occ, grid)
    got = fn(occ, grid)
    print(f"smoke array_equal(scipy, {name}):", bool(np.array_equal(ref, got)))
