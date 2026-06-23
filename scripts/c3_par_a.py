"""c3_par_a.py — Faz 1: Kol A orient-thread NFV decode (paralel, BİREBİR-koruyan).

PLAN (composed-churning-token.md, Katman 3 / Kol A): greedy dış döngü (parçalar) ZORUNLU SIRALI;
bir parçanın oryantasyonları BAĞIMSIZ → ThreadPoolExecutor ile paralel feasibility, ana-thread'de
`oi`-sıralı `min(key)` reduce → tamamlanma sırasından bağımsız → SERİ İLE BİREBİR.

Tasarım kararları (plandan):
- Decode boyunca TEK reused ThreadPoolExecutor (parça-başı pool overhead'i amortize).
- scoped `with set_workers(1)`: orient-thread × FFT-içi-worker oversubscribe ETMESİN
  (n_or FFT × 1 worker; modül-düzey set_workers(cpu_count) global mutasyonundan KAÇIN).
- Küçük/boş parçada threading atla (overhead baskın) — SADECE hız; sonuç değişmez.
- feasibility c3_backend.feasible_mask'e soyut; blb_xybbox tek-kaynak (seri+paralel paylaşır).

ÜRETİME DOKUNMAZ (scripts/). src/ Faz 5'e kadar değişmez.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import scipy.fft as _sfft

from scripts.c3_backend import get_backend, blb_xybbox, probe_capabilities
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
N_OR, MARGIN = 4, 1

QTY = {  # m2 cavity-dominant subset (hızlı doğrulama)
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


def _eligible_orients(part, nx, ny):
    """Plakaya sığan oryantasyonlar (oi, orient). Sığmayan elenir (seri+paralel aynı süzgeç)."""
    out = []
    for oi, orient in enumerate(part.orientations):
        fw, fd, _ = orient.grid.shape
        if fw > nx or fd > ny:
            continue
        out.append((oi, orient))
    return out


def _reduce_best(results, cur_max):
    """oi-sıralı deterministik min(key). results: list[(oi, o, fh)]. c3_speed2.py:152 key birebir."""
    best_key = None; best = None
    for oi, o, fh in results:
        if o is None:
            continue
        key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
        if best_key is None or key < best_key:
            best_key, best = key, (oi, o[0], o[1], o[2])
    return best


def _worth_threading(ob, n_eligible) -> bool:
    """SADECE hız heuristiği (sonucu DEĞİŞTİRMEZ). Boş/erken bin'de FFT trivial → seri ucuz.
    Yerleşim başladıysa (height>0) ve ≥2 aday orient varsa paralel kazanır."""
    return n_eligible >= 2 and ob.max_height_voxels() > 0


def decode(parts, nx, ny, *, feasible_mask=None, parallel=False, n_threads=None, pitch=2.0,
           return_placements=False, fft_workers=None):
    """NFV-greedy decode. parallel=False → seri; True → Kol A orient-thread.
    İki yol da AYNI blb_xybbox + AYNI reduce → BİREBİR. Döner: height_mm (+ ops. placements).
    fft_workers: scipy.fft.set_workers değeri (None → oto: paralel=1, seri=cpu_count).
    Oversubscribe probe için bench fft_workers=cpu_count + parallel=True geçer."""
    if feasible_mask is None:
        feasible_mask, _ = get_backend()
    ob = OccupancyBin3D(nx, ny, nz_limit=int(800 * 2.0 / pitch), pitch=pitch)
    placements = []
    sorted_parts = sorted(parts, key=lambda vp: -vp.volume_voxels)

    cpu = probe_capabilities().cpu_count
    nt = (n_threads or min(N_OR, cpu)) if parallel else 1
    # ÇEKİRDEK BÖLÜŞÜMÜ (oversubscribe yok, çekirdek-doluluk var): n_thread × per_fft ≈ cpu.
    # paralel: n_or orient-thread × (cpu//n_or) FFT-worker = cpu; seri: 1 thread × cpu FFT-worker.
    # set_workers WORKER İÇİNDE uygulanır (ThreadPoolExecutor contextvar propagate ETMEZ).
    if fft_workers is not None:
        per_fft = fft_workers
    elif parallel:
        per_fft = max(1, cpu // nt)
    else:
        per_fft = cpu

    def _blb_w(occ, grid):
        with _sfft.set_workers(per_fft):
            return blb_xybbox(occ, grid, feasible_mask)

    executor = None
    try:
        if parallel:
            executor = ThreadPoolExecutor(max_workers=nt)
        for part in sorted_parts:
            cur_max = ob.max_height_voxels()
            elig = _eligible_orients(part, nx, ny)

            if parallel and _worth_threading(ob, len(elig)):
                occ = ob.occupancy  # paylaşımlı READ-ONLY (place join sonrası ana-thread'de)
                def work(item):
                    oi, orient = item
                    return (oi, _blb_w(occ, orient.grid), orient.grid.shape[2])
                results = list(executor.map(work, elig))  # sıra-koruyan
            else:
                results = [(oi, _blb_w(ob.occupancy, orient.grid), orient.grid.shape[2])
                           for oi, orient in elig]

            best = _reduce_best(results, cur_max)
            if best is None:
                (x, y, z), oi = _drop_fallback(ob, part); best = (oi, x, y, z)
            oi, x, y, z = best
            ob.place(part.orientations[oi], x, y, z)
            if return_placements:
                placements.append((part.id, oi, x, y, z))
    finally:
        if executor is not None:
            executor.shutdown(wait=True)

    h = ob.height_mm()
    return (h, placements) if return_placements else h


def load(qty, pitch):
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, qty, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, pitch, n_orientations=N_OR, margin=MARGIN)
    return parts, int(PLATE_W // pitch), int(PLATE_D // pitch)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "self"
    pitch = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    caps = probe_capabilities()
    print("=" * 66)
    print(f"C3 PAR_A (Kol A orient-thread)  mode={mode} pitch={pitch}")
    print(f"  {caps.summary()}")
    print("=" * 66, flush=True)

    qty = QTY_FULL if mode == "plan2" else QTY
    parts, nx, ny = load(qty, pitch)
    print(f"testbed: {len(parts)} parça, {nx}x{ny}", flush=True)

    fm, bename = get_backend()
    print(f"backend: {bename}", flush=True)

    t = time.perf_counter(); hs = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=pitch)
    dts = time.perf_counter() - t
    print(f"  seri    : {hs:.1f} mm  ({dts:.1f}s)", flush=True)

    t = time.perf_counter(); hp = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch)
    dtp = time.perf_counter() - t
    print(f"  paralel : {hp:.1f} mm  ({dtp:.1f}s, {caps.cpu_count} cpu)", flush=True)

    print("-" * 66)
    if abs(hs - hp) < 0.01:
        print(f"  -> [DOĞRU] birebir aynı ({hs:.1f}) + {dts/max(dtp,1e-9):.2f}x hızlı")
    else:
        print(f"  -> [HATA] FARKLI seri={hs:.1f} paralel={hp:.1f} — Kol A bozuyor, DUR")


if __name__ == "__main__":
    main()
