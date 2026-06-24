"""c3_occfft_batched.py — (A-batched) GPU BATCHED rfftn prototip: launch-overhead amortismani.

7b/7c: naif ortak-crop occ-FFT paylasimi birebir AMA genel degil (plan1 2.22x, plan3 0.96x); kok neden
GPU mikro-mimaride, basit modelle ongorulemiyor. BU varyant: occ-FFT yine 1 kez (ortak crop), AMA
kernel-FFT + irfftn'i n AYRI cagri yerine 1 BATCHED cagri yap (cupy rfftn axes=(1,2,3), ilk eksen
batch) -> launch sayisi n+1'den ~3'e duser. Sisme zemini AYNI (homojen boyut -> ortak full'a pad).
HIPOTEZ: plan1 launch-baskin (kucuk FFT) -> daha da iyi; plan3 hesap-baskin (yuksek istif) -> belirsiz.

BIREBIR hedefli (decode_gpu baseline ile ayni occ/BLB/reduce). KAPI: h_batched==h_base her veride.
URETIME DOKUNMAZ — scripts/. Kullanim: python scripts/c3_occfft_batched.py [plan1|plan3|all] [n]
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities, probe_cupy
from src.nesting3d.parallel_decode import decode_gpu, _blb_gpu, _nz_limit

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
MARGIN = 1
DATASETS = {
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "wd": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "wd": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def decode_gpu_batched(parts, nx, ny, pitch):
    """(A-batched): parca basina ortak-crop occ-FFT (1 kez) + BATCHED kernel-FFT/irfftn. BIREBIR hedef."""
    cp = probe_cupy()
    if cp is None:
        raise RuntimeError("cupy/GPU yok")
    try:
        cp.fft.config.get_plan_cache().set_size(8)
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()
    occ = cp.zeros((nx, ny, _nz_limit(pitch)), dtype=cp.bool_)
    nz = occ.shape[2]
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

    cur_max = 0; n_placed = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        elig = []
        for oi, orient in enumerate(part.orientations):
            _, gf, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            elig.append((oi, gf, (fw, fd, fh)))
        if not elig:
            raise RuntimeError(f"batched drop (parca {part.id})")
        max_fw = max(e[2][0] for e in elig); max_fd = max(e[2][1] for e in elig)
        max_fh = max(e[2][2] for e in elig)

        best_key = None; best = None
        z_cap = max_fh + 4
        while best is None:
            z_lim = min(nz, z_cap)
            sub = occ[:, :, :z_lim]
            if not bool(sub.any()):
                for oi, gf, (fw, fd, fh) in elig:
                    if (nx - fw + 1) <= 0 or (ny - fd + 1) <= 0 or (z_lim - fh + 1) <= 0:
                        continue
                    o = (0, 0, 0)
                    key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
                    if best_key is None or key < best_key:
                        best_key, best = key, (oi, o[0], o[1], o[2])
            else:
                xs = cp.where(sub.any(axis=(1, 2)))[0]
                ys = cp.where(sub.any(axis=(0, 2)))[0]
                x0, x1 = int(xs[0]), int(xs[-1]) + 1
                y0, y1 = int(ys[0]), int(ys[-1]) + 1
                cx0 = max(0, x0 - (max_fw - 1)); cx1 = min(nx, x1 + (max_fw - 1))
                cy0 = max(0, y0 - (max_fd - 1)); cy1 = min(ny, y1 + (max_fd - 1))
                crop = sub[cx0:cx1, cy0:cy1, :]
                cx, cy, cz = crop.shape
                full = (cx + max_fw - 1, cy + max_fd - 1, cz + max_fh - 1)
                fitted = [(oi, gf, k) for oi, gf, k in elig if cx >= k[0] and cy >= k[1]]
                if not fitted:
                    if z_lim >= nz:
                        raise RuntimeError(f"batched drop (parca {part.id})")
                    z_cap *= 2; continue
                Fcrop = cp.fft.rfftn(crop.astype(cp.float64), s=full)  # occ-FFT 1 KEZ
                # BATCHED kernel: ortak full'a pad + tek rfftn (axes=1,2,3)
                K = cp.zeros((len(fitted),) + full, dtype=cp.float64)
                for i, (oi, gf, (fw, fd, fh)) in enumerate(fitted):
                    K[i, :fw, :fd, :fh] = gf
                FK = cp.fft.rfftn(K, s=full, axes=(1, 2, 3))         # BATCHED kernel-FFT
                Cs = cp.fft.irfftn(Fcrop[None] * FK, s=full, axes=(1, 2, 3))  # BATCHED ters
                for i, (oi, gf, (fw, fd, fh)) in enumerate(fitted):
                    mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
                    if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
                        continue
                    mask = cp.ones(mshape, dtype=cp.bool_)
                    Cc = (Cs[i, fw - 1:cx, fd - 1:cy, fh - 1:cz] < 0.5)
                    gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                    bx = gx1 - cx0; by = gy1 - cy0
                    if bx > 0 and by > 0:
                        mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
                    o = _blb_gpu(cp, mask)
                    if o is None:
                        continue
                    key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
                    if best_key is None or key < best_key:
                        best_key, best = key, (oi, o[0], o[1], o[2])
            if best is not None:
                break
            if z_lim >= nz:
                raise RuntimeError(f"batched drop (parca {part.id}, z dolu)")
            z_cap *= 2

        oi, x, y, z = best
        gb, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh); n_placed += 1
        if n_placed % 4 == 0:
            mempool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    return cur_max * pitch


def _load(ds):
    c = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {}
    if c["wd"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["wd"]
    res = build_instance_from_order(stl_map, c["qty"],
                                    persist_dir=_ROOT / "data" / "mail_stl" / f"batched_{ds}", **kwargs)
    return res.instance


def run_one(ds, caps, n_or):
    print(f"\n{'=' * 74}\n[{ds}] n={n_or}", flush=True)
    inst = _load(ds)
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, _, _ = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd, ram_bytes=caps.ram_bytes)
    parts = to_voxel_parts(inst, pitch, n_orientations=n_or, margin=MARGIN)
    nx, ny = int(pw // pitch), int(pd // pitch)
    print(f"  pitch={pitch:.2f} | {len(parts)} parca {nx}x{ny}vox", flush=True)

    t = time.perf_counter(); h_base = decode_gpu(parts, nx, ny, pitch=pitch); t_base = time.perf_counter() - t
    print(f"  baseline (oryant-basina): {h_base:.2f}mm  ({t_base:.1f}s)", flush=True)
    t = time.perf_counter(); h_b = decode_gpu_batched(parts, nx, ny, pitch); t_b = time.perf_counter() - t
    print(f"  batched  (A-batched)    : {h_b:.2f}mm  ({t_b:.1f}s)", flush=True)
    birebir = abs(h_base - h_b) < 1e-6
    spd = t_base / t_b if t_b else 0
    print(f"  --> BIREBIR: {'EVET' if birebir else 'HAYIR (NO-GO!)'} | hizlanma: {spd:.2f}x "
          f"({(1 - t_b / t_base) * 100:+.0f}% sure)", flush=True)
    return ds, n_or, h_base, h_b, t_base, t_b, birebir


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    n_or = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    caps = probe_capabilities()
    print("=" * 74)
    print(f"(A-batched) GPU BATCHED rfftn PROTOTIP — {caps.summary()}")
    print("=" * 74, flush=True)
    if not (caps.gpu and caps.gpu_fp64):
        print("GPU yok — CIK.", flush=True); return
    todo = ["plan1", "plan3"] if arg == "all" else [arg]
    rows = []
    for ds in todo:
        try:
            rows.append(run_one(ds, caps, n_or))
        except Exception as e:
            import traceback
            print(f"\n[{ds}] HATA: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    print(f"\n{'=' * 74}\nOZET — (A-batched) BIREBIR + cross-dataset GO?")
    print(f"{'veri':>7} | {'base mm':>8} | {'batch mm':>8} | {'birebir':>7} | {'base s':>7} | "
          f"{'batch s':>7} | {'hizlanma':>8}")
    all_go = True
    for ds, n, hb, hx, tb, tx, bb in rows:
        spd = tb / tx if tx else 0; go = bb and tx < tb; all_go = all_go and go
        print(f"{ds:>7} | {hb:8.2f} | {hx:8.2f} | {'EVET' if bb else 'HAYIR':>7} | {tb:6.1f}s | "
              f"{tx:6.1f}s | {spd:7.2f}x", flush=True)
    print(f"\nKARAR: {'HER veride birebir + hizlanma>1x -> URETIME DEGER' if all_go else 'EN AZ BIR VERIDE NO-GO -> (A) ailesi kapanir'}")
    print("=" * 74)


if __name__ == "__main__":
    main()
