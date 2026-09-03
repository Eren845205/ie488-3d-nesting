"""c3_dispatch.py — Faz 4: probe→strateji dispatcher + Kol B/C.

PLAN (composed-churning-token.md, Katman 2 dispatcher): donanımı çalışma anında algıla, en hızlı
KANITLANMIŞ yolu seç, hata/yetmezlikte zarifçe düş. DİSPATCHER İNCELİĞİ (RESUME §11): GPU seçilince
NAIVE backend DEĞİL **GPU-resident** yolu kullanılır (naive ölçekte 0.65× kaybediyordu).

Strateji karar ağacı:
  GPU + fp64        -> GPU-resident decode (c3_gpu_resident); OOM/hata → CPU Kol A'ya DÜŞ
  çok-çekirdek CPU  -> CPU Kol A orient-thread (c3_par_a parallel)
  1-2 çekirdek      -> seri decode (fallback)

Kol C (sweep): pitch/konfig listesi üzerinde bağımsız decode (cluster'da SLURM --array; burada seri
döngü prototipi). Kol B (multi-start): NFV-greedy deterministik → multi-start = farklı SIRA; Plan2
kaba'da marjinal (handoff: SA 556→556) → minimal, opt-in, not'lu.

ÜRETİME DOKUNMAZ (scripts/). Birebir 556 korunur (hangi yol seçilirse seçilsin aynı sonuç).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

try:  # Windows cp1254 konsolu '→' (U+2192) kodlayamıyor; utf-8'e geç (pipe/redirect güvenli)
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.c3_backend import probe_capabilities, get_backend, _scipy_feasible_mask
from scripts.c3_par_a import decode as cpu_decode, load, QTY, QTY_FULL

# VRAM güvenlik tahmini: occupancy + FFT geçicileri için kabaca occ_bytes × emniyet.
# Yetmezse GPU denenmez (ölç-önce + plan #5 VRAM tavanı).
_GPU_SAFETY = 6.0


def _est_occ_bytes(nx, ny, pitch):
    nz = int(800 * 2.0 / pitch)
    return nx * ny * nz  # bool = 1 byte/voxel


def choose_strategy(nx, ny, pitch, caps=None):
    """probe→(strateji_adı, gerekçe). Sadece SEÇİM (çalıştırmaz). Birebir sonucu etkilemez (hız seçimi)."""
    caps = caps or probe_capabilities()
    if caps.gpu and caps.gpu_fp64:
        return "gpu-resident", f"GPU+fp64 var ({caps.summary()}); GPU-resident dene (OOM→CPU fallback)"
    if caps.cpu_count > 2:
        return "cpu-kolA", f"GPU yok, {caps.cpu_count} çekirdek → CPU Kol A orient-thread"
    return "serial", f"{caps.cpu_count} çekirdek → seri (fallback)"


def best_decode(parts, nx, ny, pitch=2.0, *, force=None, verbose=True):
    """Donanıma göre en hızlı KANITLANMIŞ yolu seç + graceful fallback. Döner: (height, strateji)."""
    caps = probe_capabilities()
    strat = force or choose_strategy(nx, ny, pitch, caps)[0]
    if verbose:
        _, why = choose_strategy(nx, ny, pitch, caps)
        print(f"  [dispatch] strateji={strat} | {why}", flush=True)

    if strat == "gpu-resident":
        # VRAM kaba kontrol + dene; OOM/hata (drop fallback dahil) → CPU Kol A
        try:
            from scripts.c3_gpu_resident import decode_gpu
            return decode_gpu(parts, nx, ny, pitch=pitch), "gpu-resident"
        except Exception as e:
            if verbose:
                print(f"  [dispatch] GPU-resident BAŞARISIZ ({type(e).__name__}) → CPU Kol A'ya düşülüyor", flush=True)
            strat = "cpu-kolA"

    fm, _ = get_backend("scipy")  # CPU yolunda scipy (GPU naive'i ölçekte kaybediyor)
    if strat == "cpu-kolA":
        return cpu_decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch), "cpu-kolA"
    return cpu_decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=pitch), "serial"


# ---- Kol C: sweep (bağımsız konfig'ler; cluster'da SLURM --array) ----
def sweep(configs, verbose=True):
    """configs: [(etiket, qty, pitch), ...]. Her biri bağımsız best_decode. Cluster'da job-array."""
    rows = []
    for label, qty, pitch in configs:
        parts, nx, ny = load(qty, pitch)
        t = time.perf_counter()
        h, strat = best_decode(parts, nx, ny, pitch=pitch, verbose=verbose)
        dt = time.perf_counter() - t
        rows.append((label, pitch, len(parts), h, strat, dt))
        if verbose:
            print(f"  [sweep] {label} pitch={pitch}: {h:.1f} mm ({strat}, {dt:.1f}s)", flush=True)
    return rows


# ---- Kol B: multi-start (minimal, marjinal — handoff: Plan2 kaba'da SA 556→556) ----
def multistart(parts, nx, ny, pitch=2.0, k=3, verbose=True):
    """NFV-greedy deterministik → farklı SIRA ile K decode, en iyiyi al. NOT: Plan2 kaba'da kazanç
    marjinal (handoff). Gerçek değeri ince pitch/sıra-duyarlı veride; ölç-önce. Birebir-DEĞİL (arama)."""
    import random
    fm, _ = get_backend("scipy")
    best_h = None
    base = sorted(parts, key=lambda vp: -vp.volume_voxels)
    for i in range(k):
        if i == 0:
            order = base                      # i=0 = kanonik (en-büyük-önce) = referans
        else:
            rng = random.Random(1000 + i)     # seed prompt/index ile (deterministik tekrar)
            order = base[:]; rng.shuffle(order)
        h = cpu_decode(order, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch)
        if best_h is None or h < best_h:
            best_h = h
        if verbose:
            tag = "kanonik" if i == 0 else f"shuffle{i}"
            print(f"  [multistart] {tag}: {h:.1f} mm  (en iyi {best_h:.1f})", flush=True)
    return best_h


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print("=" * 66)
    print(f"C3 DISPATCH  mode={mode}")
    caps = probe_capabilities()
    print(f"  {caps.summary()}")
    print("=" * 66, flush=True)

    if mode == "auto":          # tek decode, oto-strateji (Plan2)
        parts, nx, ny = load(QTY_FULL, 2.0)
        t = time.perf_counter()
        h, strat = best_decode(parts, nx, ny, pitch=2.0)
        print(f"  -> {h:.1f} mm via {strat} ({time.perf_counter()-t:.1f}s)")
    elif mode == "sweep":       # Kol C: pitch sweep Plan2
        rows = sweep([("plan2@2.0", QTY_FULL, 2.0), ("subset@2.0", QTY, 2.0)])
        print("-" * 66)
        for label, pitch, n, h, strat, dt in rows:
            print(f"  {label:14s} n={n:3d} {h:7.1f} mm  {strat:12s} {dt:5.1f}s")
    elif mode == "multistart":  # Kol B (subset, hızlı)
        parts, nx, ny = load(QTY, 2.0)
        h = multistart(parts, nx, ny, pitch=2.0, k=3)
        print(f"  -> multistart en iyi: {h:.1f} mm")
    else:
        print("bilinmeyen mod (auto|sweep|multistart)")


if __name__ == "__main__":
    main()
