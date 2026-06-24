"""c3_occfft_proto.py — (A) occ-FFT paylasimi GPU PROTOTIP: BIREBIR mi + GERCEK kazanc ne?

Profil (c3_occfft_profile) occ-FFT'yi decode'un ~%30'u + n=8 ust-sinir ~%26 dedi (GENEL: plan1/2/3
ayni). Bu PROTOTIP ust-sinir DEGIL gercek olcum: mevcut decode_gpu (baseline, oryant basina ayri
occ-FFT) vs decode_gpu_shared (parca basina ORTAK crop -> occ-FFT 1 kez, oryantlar paylasir).

ORTAK CROP birebir korur:
  - xy-bbox max-kernel ile genisler (kucuk kernelli oryant icin fazladan kenar; valid bolge AYNI).
  - ortak full = crop + max_kernel - 1; her oryant kendi kernel'ini bu full'a sifir-pad eder
    (lineer konvolusyonu degistirmez; 'valid' dilim [fw-1:cropx ...] kendi kernel'ine gore kesilir).
  - ortak z_cap = max_fh + 4; BLB min-z secer -> fazla ust dilim min-z'yi DEGISTIRMEZ.
KAPI: h_shared == h_base her veride (1e-6). Bozulursa NO-GO. + sure kiyas (gercek hizlanma).

URETIME DOKUNMAZ — scripts/. Kullanim: python scripts/c3_occfft_proto.py [plan1|plan2|plan3|all] [n]
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
PLAN2_QTY = {"P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}
DATASETS = {
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "wd": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan2": {"dir": VERILER / "Plan2" / "Plan2", "wd": (328.74, 328.19), "qty": PLAN2_QTY},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "wd": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def decode_gpu_shared(parts, nx, ny, pitch, return_placements=False):
    """(A) PROTOTIP: parca basina ORTAK crop -> occ-FFT 1 kez, oryantlar paylasir. decode_gpu ile
    BIREBIR hedefli (ayni occ, ayni BLB, ayni reduce). cupy yoksa RuntimeError."""
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

    placements = []
    cur_max = 0
    n_placed = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        # eligible oryantlar + max kernel
        elig = []
        for oi, orient in enumerate(part.orientations):
            _, gf, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            elig.append((oi, gf, (fw, fd, fh)))
        if not elig:
            raise RuntimeError(f"shared decode drop (parca {part.id})")
        max_fw = max(e[2][0] for e in elig)
        max_fd = max(e[2][1] for e in elig)
        max_fh = max(e[2][2] for e in elig)

        best_key = None; best = None
        z_cap = max_fh + 4
        while best is None:
            z_lim = min(nz, z_cap)
            sub = occ[:, :, :z_lim]
            if not bool(sub.any()):
                # bos dilim: her oryant icin o=(0,0,0) (mshape gecerliyse)
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
                # ORTAK crop: max kernel ile genislet
                cx0 = max(0, x0 - (max_fw - 1)); cx1 = min(nx, x1 + (max_fw - 1))
                cy0 = max(0, y0 - (max_fd - 1)); cy1 = min(ny, y1 + (max_fd - 1))
                crop = sub[cx0:cx1, cy0:cy1, :]
                cropx, cropy, cropz = crop.shape
                full = (cropx + max_fw - 1, cropy + max_fd - 1, cropz + max_fh - 1)
                # occ-FFT BIR KEZ (paylasilir)
                Fcrop = cp.fft.rfftn(crop.astype(cp.float64), s=full)
                for oi, gf, (fw, fd, fh) in elig:
                    mshape = (nx - fw + 1, ny - fd + 1, z_lim - fh + 1)
                    if mshape[0] <= 0 or mshape[1] <= 0 or mshape[2] <= 0:
                        continue
                    mask = cp.ones(mshape, dtype=cp.bool_)
                    if cropx >= fw and cropy >= fd:
                        Fk = cp.fft.rfftn(gf, s=full)
                        C = cp.fft.irfftn(Fcrop * Fk, s=full)
                        Cc = (C[fw - 1:cropx, fd - 1:cropy, fh - 1:cropz] < 0.5)
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
                raise RuntimeError(f"shared decode drop (parca {part.id}, z dolu)")
            z_cap *= 2

        oi, x, y, z = best
        gb, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh)
        n_placed += 1
        if return_placements:
            placements.append((part.id, oi, x, y, z))
        if n_placed % 4 == 0:
            mempool.free_all_blocks()

    cp.cuda.Stream.null.synchronize()
    h = cur_max * pitch
    return (h, placements) if return_placements else h


def _load(ds):
    c = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {}
    if c["wd"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["wd"]
    res = build_instance_from_order(stl_map, c["qty"],
                                    persist_dir=_ROOT / "data" / "mail_stl" / f"occproto_{ds}", **kwargs)
    return res.instance


def run_one(ds, caps, n_or):
    print(f"\n{'=' * 74}\n[{ds}] n={n_or}", flush=True)
    inst = _load(ds)
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, feasible, _ = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd, ram_bytes=caps.ram_bytes)
    parts = to_voxel_parts(inst, pitch, n_orientations=n_or, margin=MARGIN)
    nx, ny = int(pw // pitch), int(pd // pitch)
    print(f"  pitch={pitch:.2f} | {len(parts)} parca {nx}x{ny}vox", flush=True)

    # baseline
    t = time.perf_counter()
    h_base = decode_gpu(parts, nx, ny, pitch=pitch)
    t_base = time.perf_counter() - t
    print(f"  baseline (oryant-basina occ-FFT): {h_base:.2f}mm  ({t_base:.1f}s)", flush=True)

    # shared (A)
    t = time.perf_counter()
    h_shared = decode_gpu_shared(parts, nx, ny, pitch)
    t_shared = time.perf_counter() - t
    print(f"  shared   (A: ortak-crop occ-FFT): {h_shared:.2f}mm  ({t_shared:.1f}s)", flush=True)

    birebir = abs(h_base - h_shared) < 1e-6
    spd = t_base / t_shared if t_shared else 0
    print(f"  --> BIREBIR: {'EVET' if birebir else 'HAYIR (NO-GO!)'} | "
          f"hizlanma: {spd:.2f}x ({(1 - t_shared / t_base) * 100:+.0f}% sure)", flush=True)
    return ds, n_or, h_base, h_shared, t_base, t_shared, birebir


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    n_or = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    caps = probe_capabilities()
    print("=" * 74)
    print(f"(A) occ-FFT PAYLASIMI GPU PROTOTIP — {caps.summary()}")
    print("=" * 74, flush=True)
    if not (caps.gpu and caps.gpu_fp64):
        print("GPU/fp64 yok — prototip GPU gerektirir. CIK.", flush=True)
        return
    todo = ["plan1", "plan2", "plan3"] if arg == "all" else [arg]
    rows = []
    for ds in todo:
        try:
            rows.append(run_one(ds, caps, n_or))
        except Exception as e:
            import traceback
            print(f"\n[{ds}] HATA: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    print(f"\n{'=' * 74}\nOZET — (A) GERCEK kazanc + BIREBIR (her veride GO mu?)")
    print(f"{'veri':>7} | {'n':>2} | {'base mm':>8} | {'shared mm':>9} | {'birebir':>7} | "
          f"{'base s':>7} | {'shared s':>8} | {'hizlanma':>8}")
    all_go = True
    for ds, n, hb, hs, tb, ts, bb in rows:
        spd = tb / ts if ts else 0
        go = bb and ts < tb
        all_go = all_go and go
        print(f"{ds:>7} | {n:>2} | {hb:8.2f} | {hs:9.2f} | {'EVET' if bb else 'HAYIR':>7} | "
              f"{tb:6.1f}s | {ts:7.1f}s | {spd:7.2f}x", flush=True)
    print(f"\nKARAR: birebir HER veride EVET + hizlanma HER veride >1x ise -> (A) URETIME DEGER.")
    print(f"       Bu kosu: {'TUM VERILERDE GO' if all_go else 'EN AZ BIR VERIDE NO-GO -> dur, incele'}")
    print("=" * 74)


if __name__ == "__main__":
    main()
