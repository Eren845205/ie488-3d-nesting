"""c3_vdb_memprofile.py — VDB/sparse-occ FİZİBİLİTE: bellek darboğazı NEREDE? (occ array mı FFT mi)

SORU (literatur B2): VDB/OpenVDB sparse occupancy belleği aktif-voxelle ölçekler -> OOM'u gevşetir ->
daha ince pitch (0.5mm) -> dolaylı kalite (Magics 0.5mm). AMA: VDB'nin tek faydası BELLEK, ve NFV
feasibility FFT (dense) gerektirir (sparse-FFT B4'te "yaklaşık" diye elendi). VDB ancak occupancy
ARRAY'i darboğazsa yardım eder; darboğaz FFT geçici array'leriyse VDB BOŞA gider (FFT dense, sparse
edilemez). ÖLÇ-ÖNCE: VDB kurmadan, darboğazı ÖLÇ.

PROFİL: Plan2'de pitch sweep (2.0/1.5/1.0). Her pitch: occ-array bytes (kesin hesap) + decode peak GPU
bellek (cupy mempool.total_bytes max, gerçekçi free_all_blocks ile) + OOM noktası. ANALİZ: peak >> occ
ise -> FFT-baskın -> VDB occupancy çözmez (NO-GO ön-analiz). peak ~ occ ise -> occ-baskın -> VDB değer.

URETIME DOKUNMAZ (scripts/ deney). [[feedback-windows-stdout-ascii]] ASCII print.
Kullanım: python scripts/c3_vdb_memprofile.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.capabilities import probe_capabilities, probe_cupy
from src.nesting3d.parallel_decode import _nz_limit

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
PLAN2 = {"dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19), "qty": {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}}


def _blb_gpu(cp, mask):
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(cp.argmax(sl.any(axis=0)))
    xstar = int(cp.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _blb_xybbox_gpu(cp, occ, grid_flip, gshape, peak):
    """decode_gpu birebir + crop FFT anında peak bellek örnekle (FFT geçici array'leri yakalansin)."""
    fw, fd, fh = gshape
    nx, ny, nz = occ.shape
    z_cap = fh + 4
    mempool = cp.get_default_memory_pool()
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
                full = (crop.shape[0] + fw - 1, crop.shape[1] + fd - 1, crop.shape[2] + fh - 1)
                C = cp.fft.irfftn(cp.fft.rfftn(crop.astype(cp.float64), s=full) *
                                  cp.fft.rfftn(grid_flip, s=full), s=full)
                peak[0] = max(peak[0], mempool.total_bytes())  # FFT geçici peak ANINDA
                Cc = (C[fw - 1:crop.shape[0], fd - 1:crop.shape[1], fh - 1:crop.shape[2]] < 0.5)
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


def decode_profile(parts, nx, ny, pitch):
    cp = probe_cupy()
    try:
        cp.fft.config.get_plan_cache().set_size(4)
    except Exception:
        pass
    mempool = cp.get_default_memory_pool()
    mempool.free_all_blocks()
    nz = _nz_limit(pitch)
    occ_bytes = nx * ny * nz  # bool = 1 byte/voxel
    occ = cp.zeros((nx, ny, nz), dtype=cp.bool_)
    gc = {}
    peak = [mempool.total_bytes()]

    def _grids(orient):
        k = id(orient)
        g = gc.get(k)
        if g is None:
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, orient.grid.shape)
            gc[k] = g
        return g

    cur_max = 0; n = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            _, gf, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            o = _blb_xybbox_gpu(cp, occ, gf, gshape, peak)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            raise RuntimeError(f"drop (parca {part.id})")
        oi, x, y, z = best
        gb, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh)
        peak[0] = max(peak[0], mempool.total_bytes())
        n += 1
        if n % 4 == 0:
            mempool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    return cur_max * pitch, occ_bytes, peak[0]


def main():
    caps = probe_capabilities()
    cp = probe_cupy()
    if cp is None:
        print("GPU/cupy YOK")
        return
    print("=" * 84)
    print(f"VDB/SPARSE-OCC FİZİBİLİTE: bellek darboğazı NEREDE — Plan2 — {caps.summary()}")
    print("=" * 84, flush=True)

    c = PLAN2
    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / "vdbmem_plan2",
              "container_w_mm": c["plate"][0], "container_d_mm": c["plate"][1]}
    inst = build_instance_from_order(stl_map, c["qty"], **kwargs).instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)

    print(f"  {'pitch':>6} {'grid(nx,ny,nz)':>18} {'occ-array':>11} {'peak-GPU':>11} "
          f"{'peak/occ':>9} {'H(mm)':>8} {'durum':>16}")
    print("-" * 84)
    MB = 1024 * 1024
    for pitch in (2.0, 1.5, 1.0, 0.5):
        nx, ny = int(pw // pitch), int(pd // pitch)
        nz = _nz_limit(pitch)
        occ_mb = nx * ny * nz / MB
        try:
            parts = to_voxel_parts(inst, pitch, n_orientations=8, margin=1)
        except Exception as e:
            print(f"  {pitch:>6} voxelize HATA: {type(e).__name__}", flush=True)
            continue
        try:
            t = time.perf_counter()
            h, ob, pk = decode_profile(parts, nx, ny, pitch)
            el = time.perf_counter() - t
            ratio = pk / (ob) if ob else 0
            print(f"  {pitch:>6} {f'{nx}x{ny}x{nz}':>18} {occ_mb:>9.1f}MB {pk/MB:>9.1f}MB "
                  f"{ratio:>8.1f}x {h:>8.1f} {f'OK ({el:.0f}s)':>16}", flush=True)
        except Exception as e:
            nm = type(e).__name__
            durum = "OOM" if "OutOfMemory" in nm or "alloc" in str(e).lower() else nm
            print(f"  {pitch:>6} {f'{nx}x{ny}x{nz}':>18} {occ_mb:>9.1f}MB {'-':>11} "
                  f"{'-':>9} {'-':>8} {durum:>16}", flush=True)
        cp.get_default_memory_pool().free_all_blocks()

    print("-" * 84)
    print("  YORUM: peak/occ >> 1 -> FFT geçici array'leri baskın -> VDB occupancy darboğazı ÇÖZMEZ")
    print("         (FFT dense gerektirir, sparse edilemez). peak/occ ~ 1 -> occ baskın -> VDB değer.")
    print("=" * 84)


if __name__ == "__main__":
    main()
