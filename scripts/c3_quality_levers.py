"""c3_quality_levers.py — NFV kalite kaldıraçları: oryantasyon (n) + multi-start sıra (backlog: Magics açığı).

SORU: NFV-greedy'yi Magics'e yaklaştırmak için (a) daha çok oryantasyon (n=4->8) ve (b) multi-start
(farklı yerleştirme sırası, en iyiyi al) ne kadar kazandırır? İkisi de ÖLÇ-ÖNCE — kazanç varsa src'ye
(adaptif n + multi-start) taşınır. Plan2 @2.0mm kaba (hızlı, trend için yeterli; 556 bilinen baz).

ÜRETİME DOKUNMAZ — scripts/. GPU-resident decode (sıralama-parametreli kopya).
Kullanım: python scripts/c3_quality_levers.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.capabilities import probe_capabilities, probe_cupy
from src.nesting3d.parallel_decode import _blb_xybbox_gpu, _nz_limit

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
PITCH = 2.0
PLAN2_QTY = {"P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}


def decode_gpu_ordered(parts, nx, ny, pitch, order):
    """GPU-resident NFV decode, parça işleme SIRASI dışarıdan verilir (multi-start için).
    order: parts indeksleri listesi. parallel_decode.decode_gpu'nun sıra-parametreli kopyası."""
    cp = probe_cupy()
    if cp is None:
        raise RuntimeError("GPU yok")
    try:
        cp.fft.config.get_plan_cache().set_size(4)
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()
    occ = cp.zeros((nx, ny, _nz_limit(pitch)), dtype=cp.bool_)
    grid_cache = {}

    def _grids(orient):
        k = id(orient)
        g = grid_cache.get(k)
        if g is None:
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, orient.grid.shape)
            grid_cache[k] = g
        return g

    cur_max = 0
    n_placed = 0
    for idx in order:
        part = parts[idx]
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            _, gf, gshape = _grids(orient)
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
            raise RuntimeError(f"drop gerekti (parça {part.id})")
        oi, x, y, z = best
        gb, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh)
        n_placed += 1
        if n_placed % 4 == 0:
            mempool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    return cur_max * pitch


def largest_first_order(parts):
    return sorted(range(len(parts)), key=lambda i: -parts[i].volume_voxels)


def jittered_order(parts, seed):
    """Largest-first + hacme deterministik jitter (multi-start sıra çeşitliliği)."""
    vols = np.array([p.volume_voxels for p in parts], dtype=float)
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(0.85, 1.15, size=len(parts))  # ±%15 hacim perturbasyonu
    return sorted(range(len(parts)), key=lambda i: -vols[i] * jitter[i])


def main():
    caps = probe_capabilities()
    print("=" * 72)
    print(f"NFV KALİTE KALDIRAÇLARI — Plan2 @{PITCH}mm — {caps.summary()}")
    print("=" * 72, flush=True)
    stl_map = {f.stem: f.read_bytes() for f in sorted((VERILER / "Plan2" / "Plan2").glob("*.stl"))}
    inst = build_instance_from_order(stl_map, PLAN2_QTY,
                                     persist_dir=_ROOT / "data" / "mail_stl" / "qlevers",
                                     container_w_mm=328.74, container_d_mm=328.19).instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)

    results = {}
    for n_or in (4, 8):
        parts = to_voxel_parts(inst, PITCH, n_orientations=n_or, margin=1)
        t = time.perf_counter()
        h = decode_gpu_ordered(parts, nx, ny, PITCH, largest_first_order(parts))
        el = time.perf_counter() - t
        results[f"n={n_or} largest-first"] = (h, el)
        print(f"  [n={n_or}] largest-first: {h:.1f}mm  ({el:.0f}s)", flush=True)

    # Multi-start: n=4, K farklı jitter sırası
    parts4 = to_voxel_parts(inst, PITCH, n_orientations=4, margin=1)
    best_ms = None; t0 = time.perf_counter()
    K = 6
    for k in range(K):
        order = largest_first_order(parts4) if k == 0 else jittered_order(parts4, seed=100 + k)
        h = decode_gpu_ordered(parts4, nx, ny, PITCH, order)
        tag = "largest-first" if k == 0 else f"jitter-{k}"
        print(f"    multi-start[{tag}]: {h:.1f}mm", flush=True)
        if best_ms is None or h < best_ms:
            best_ms = h
    results[f"n=4 multi-start(K={K})"] = (best_ms, time.perf_counter() - t0)
    print(f"  [n=4] multi-start K={K} EN İYİ: {best_ms:.1f}mm  ({time.perf_counter() - t0:.0f}s)", flush=True)

    # n=8 + multi-start kombinasyon
    best_combo = None; t0 = time.perf_counter()
    for k in range(K):
        parts = to_voxel_parts(inst, PITCH, n_orientations=8, margin=1)
        order = largest_first_order(parts) if k == 0 else jittered_order(parts, seed=200 + k)
        h = decode_gpu_ordered(parts, nx, ny, PITCH, order)
        if best_combo is None or h < best_combo:
            best_combo = h
    results[f"n=8 multi-start(K={K})"] = (best_combo, time.perf_counter() - t0)
    print(f"  [n=8] multi-start K={K} EN İYİ: {best_combo:.1f}mm  ({time.perf_counter() - t0:.0f}s)", flush=True)

    print("-" * 72)
    base = results["n=4 largest-first"][0]
    print(f"{'yöntem':>26} | {'mm':>7} | {'baz(n=4)-e':>10} | {'süre':>7}")
    for name, (h, el) in results.items():
        d = (base - h) / base * 100
        print(f"{name:>26} | {h:7.1f} | {d:+9.1f}% | {el:6.0f}s")
    print(f"\n  Magics Plan2 = 492mm (hedef). baz n=4 = {base:.0f}mm.", flush=True)
    print("=" * 72)


if __name__ == "__main__":
    main()
