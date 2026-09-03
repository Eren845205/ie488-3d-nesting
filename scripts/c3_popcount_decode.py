"""c3_popcount_decode.py — HIBRIT decode (az-dolu parca->sparse, cok-dolu->FFT) GERCEK olcum.

Mikro-benchmark (c3_popcount.py) GO verdi: kucuk parca + genis occ = 6.67x + BIREBIR. Ama mikro =
UST SINIR (occ-FFT dersi: mikro != gercek decode). Bu prob hibrit feasibility'yi TAM decode_gpu'ya
sokar, Plan2'de gercek decode suresi + BIREBIR 522 kapisi olcer. FFT-only baz ile karsilastir.

HIBRIT: parca dolu-voxel sayisi < THRESH -> sparse-shift korelasyon (EXACT, FFT'siz); degilse FFT.
Feasibility disinda her sey decode_gpu birebir (xy-bbox crop, kademeli z-dilim, BLB tie-break).
sparse ve FFT AYNI feasible mask verir (mikro'da array_equal kanitli) -> yukseklik BIREBIR olmali.

KAZANC ESIGI: hibrit Plan2 522 birebir + belirgin hizli (>%10) -> THRESH tara + cross-dataset -> src.
522 sapmasi -> birebirlik bug (DUR). Hicbir THRESH'te net hiz yok -> NO-GO (xy-bbox crop kucuk
parcada da kucuk, mikro genis-occ avantaji decode'da gerceklesmedi).

URETIME DOKUNMAZ (scripts/ deney). [[feedback-windows-stdout-ascii]] ASCII print.
Kullanim: python scripts/c3_popcount_decode.py [plan2|plan1|plan3]
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
from src.nesting3d.parallel_decode import _nz_limit

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
CFG = {
    "plan2": {"dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19), "pitch": 2.0, "qty": {
        "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
        "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
        "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
        "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
        "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
        "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
        "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
        "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}},
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "plate": None, "pitch": 2.54, "qty": None},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "plate": None, "pitch": 2.5, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def _blb_gpu(cp, mask):
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(cp.argmax(sl.any(axis=0)))
    xstar = int(cp.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _feas_crop_fft(cp, crop, grid_flip, gshape):
    """FFT valid-correlation feasible mask (crop bolgesi). decode_gpu birebir."""
    fw, fd, fh = gshape
    full = (crop.shape[0] + fw - 1, crop.shape[1] + fd - 1, crop.shape[2] + fh - 1)
    C = cp.fft.irfftn(cp.fft.rfftn(crop.astype(cp.float64), s=full) *
                      cp.fft.rfftn(grid_flip, s=full), s=full)
    return C[fw - 1:crop.shape[0], fd - 1:crop.shape[1], fh - 1:crop.shape[2]] < 0.5


def _feas_crop_sparse(cp, crop, filled, cshape):
    """Sparse-shift valid-correlation feasible mask (crop bolgesi). EXACT, FFT ile birebir.
    cshape = (crop.shape - gshape + 1). filled: (n,3) dolu voxel offsetleri."""
    mx, my, mz = cshape
    overlap = cp.zeros(cshape, dtype=cp.int32)
    cb = crop  # zaten bool
    for dx, dy, dz in filled:
        overlap += cb[dx:dx + mx, dy:dy + my, dz:dz + mz]
    return overlap == 0


def _blb_xybbox_hybrid(cp, occ, grid_flip, gshape, filled, use_sparse):
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
                cshape = (crop.shape[0] - fw + 1, crop.shape[1] - fd + 1, crop.shape[2] - fh + 1)
                if use_sparse:
                    Cc = _feas_crop_sparse(cp, crop, filled, cshape)
                else:
                    Cc = _feas_crop_fft(cp, crop, grid_flip, gshape)
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


def decode_gpu_hybrid(parts, nx, ny, pitch, thresh):
    """thresh: dolu-voxel < thresh -> sparse, degilse FFT. thresh=0 -> hep FFT (baz). thresh=inf -> hep sparse."""
    cp = probe_cupy()
    if cp is None:
        raise RuntimeError("cupy/GPU yok")
    try:
        cp.fft.config.get_plan_cache().set_size(4)
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()
    occ = cp.zeros((nx, ny, _nz_limit(pitch)), dtype=cp.bool_)
    gc = {}
    sparse_used = 0; fft_used = 0

    def _grids(orient):
        k = id(orient)
        g = gc.get(k)
        if g is None:
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            nfill = int(orient.grid.sum())
            filled = [tuple(int(v) for v in r) for r in np.argwhere(orient.grid)]
            g = (gb, gf, orient.grid.shape, nfill, filled)
            gc[k] = g
        return g

    cur_max = 0; n = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            gb, gf, gshape, nfill, filled = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            use_sparse = nfill < thresh
            o = _blb_xybbox_hybrid(cp, occ, gf, gshape, filled, use_sparse)
            if o is None:
                continue
            if use_sparse:
                sparse_used += 1
            else:
                fft_used += 1
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            raise RuntimeError(f"drop gerekti (parca {part.id})")
        oi, x, y, z = best
        gb, _, gshape, _, _ = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh)
        n += 1
        if n % 4 == 0:
            mempool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    return cur_max * pitch, sparse_used, fft_used


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    c = CFG[ds]
    pitch = c["pitch"]
    caps = probe_capabilities()
    print("=" * 80)
    print(f"HIBRIT DECODE (sparse/FFT) — {ds} @{pitch}mm n=8 — {caps.summary()}")
    print("=" * 80, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    qty = c["qty"] or {f.stem: 1 for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"popdec_{ds}"}
    if c["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    inst = build_instance_from_order(stl_map, qty, **kwargs).instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    nx, ny = int(pw // pitch), int(pd // pitch)
    parts = to_voxel_parts(inst, pitch, n_orientations=8, margin=1)
    print(f"instance: {len(parts)} parca, plaka {pw:.0f}x{pd:.0f}mm, grid {nx}x{ny}", flush=True)

    # baz: thresh=0 (hep FFT) = decode_gpu birebir
    t = time.perf_counter()
    h0, s0, f0 = decode_gpu_hybrid(parts, nx, ny, pitch, thresh=0)
    el0 = time.perf_counter() - t
    print(f"  [BAZ FFT-only] {h0:.1f}mm  ({el0:.0f}s)  (sparse={s0} fft={f0})", flush=True)

    print("-" * 80)
    print(f"  {'THRESH':>8} {'H(mm)':>9} {'birebir':>8} {'sure':>7} {'hizlanma':>9} {'sparse/fft':>12}")
    best_spd = 0.0; best_ok = False
    for thresh in (50, 100, 200, 500):
        t = time.perf_counter()
        hk, sk, fk = decode_gpu_hybrid(parts, nx, ny, pitch, thresh=thresh)
        elk = time.perf_counter() - t
        ident = abs(hk - h0) < 1e-6
        spd = el0 / elk if elk > 0 else 0
        if ident and spd > best_spd:
            best_spd = spd; best_ok = True
        flag = "" if ident else "  !522-SAPMA"
        print(f"  {thresh:>8} {hk:>9.1f} {str(ident):>8} {elk:>6.0f}s {spd:>8.2f}x "
              f"{sk:>5}/{fk:<5}{flag}", flush=True)

    print("-" * 80)
    if best_ok and best_spd > 1.10:
        verdict = f"GO (birebir + {best_spd:.2f}x hiz -> cross-dataset test et)"
    elif best_ok:
        verdict = f"ZAYIF (birebir ama hiz {best_spd:.2f}x < %10 -> marjinal)"
    else:
        verdict = "NO-GO / BUG (birebir THRESH yok)"
    print(f"  VERDICT: {verdict}")
    print("=" * 80)


if __name__ == "__main__":
    main()
