"""capabilities.py — donanım yetenek probe'u (paralel NFV decode için).

Çalışma anında makineyi yokla: kaç çekirdek, ne kadar RAM, kullanılabilir GPU (cupy+fp64),
hızlı FFT kütüphanesi (mkl_fft/pyfftw), SLURM. Buna göre parallel_decode dispatcher en hızlı
KANITLANMIŞ yolu seçer; hiçbiri yoksa zarifçe scipy/CPU'ya düşer.

TASARIM: tüm opsiyonel bağımlılıklar (cupy/mkl_fft/pyfftw/psutil) LAZY import + try/except —
yoksa fallback, ASLA hata. Windows-safe (os.sched_getaffinity yok). requirements.txt'e DOKUNULMAZ.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional


def probe_cupy():
    """cupy + GPU gerçekten kullanılabilir mi? (import + cihaz + f64 cuFFT smoke). Döner: cp | None.
    SADECE cupy.fft denenir (cupyx.scipy.signal'in ağır cublas/cusparse zinciri YOK)."""
    try:
        import cupy as cp  # type: ignore
        if cp.cuda.runtime.getDeviceCount() <= 0:
            return None
        _ = cp.fft.rfftn(cp.zeros((4, 4, 4), dtype=cp.float64))  # cuFFT gerçekten yüklenir-çalışır mı
        return cp
    except Exception:
        return None


def probe_fast_backend():
    """mkl_fft / pyfftw scipy-arayüzü var mı? Döner: (scipy_fft_backend_modülü, ad) | (None, None)."""
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
    """best-effort toplam RAM; yeni hard-dep YOK (psutil → /proc/meminfo → Windows ctypes → default)."""
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
        return (f"cpu={self.cpu_count} ram={self.ram_bytes / 1e9:.1f}GB gpu={self.gpu}"
                f"(fp64={self.gpu_fp64}) fast_fft={self.fast_name or '-'} slurm={self.slurm}")


_CACHE: Optional[Capabilities] = None


def probe_capabilities(*, refresh: bool = False) -> Capabilities:
    """Makineyi yokla (bir kez, cache'li). refresh=True ile yeniden ölç."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE
    cp = probe_cupy()
    gpu = cp is not None
    gpu_fp64 = False
    if gpu:
        try:
            _ = cp.zeros(4, dtype=cp.float64) + 1.0  # f64 gerçekten çalışıyor mu
            gpu_fp64 = True
        except Exception:
            gpu_fp64 = False
    fast, fname = probe_fast_backend()
    _CACHE = Capabilities(
        cpu_count=_affinity_cpu_count(),
        ram_bytes=_ram_bytes(),
        gpu=gpu, gpu_fp64=gpu_fp64,
        fast_fft=fast is not None, fast_name=fname,
        slurm=bool(os.environ.get("SLURM_JOB_ID") or os.environ.get("SLURM_ARRAY_TASK_ID")),
    )
    return _CACHE
