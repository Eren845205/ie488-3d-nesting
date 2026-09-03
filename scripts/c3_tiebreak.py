"""c3_tiebreak.py — NFV yerleştirme-noktası TIE-BREAK kalite kaldıracı (Magics açığı, son ucuz aday).

SORU: Parametre eksenleri (pitch, n, sıra) 6GB'de tükendi (pitch eğrisi doygun, n=8->12 %1.1,
SA/multi-start ölü). Kalan tek ucuz algoritma kaldıracı: greedy'nin YERLEŞTİRME-NOKTASI seçimi.
Mevcut decode tie-break key `(max(z+fh,cur_max), z+fh, z, y, x, oi)` -> mevcut zarf (cur_max) içine
sığan TÜM pozisyonlar EŞİT-skorlu, aralarından "köşe" (min y,x) seçiliyor. Magics "free void fill"
prensibi: bu eşit-skorlu pozisyonlar arasında EN İYİ OTURAN'ı (en çok alttan destek) seçmek,
yüksekliği bozmadan gelecek parçalara daha düzenli boşluk bırakıp greedy myopia'yı azaltabilir.

ÖLÇ-ÖNCE: baz BLB (522 bilinen) vs max-support tie-break. Kazanç eşiği: belirgin (>%2) + pozitif.
Kazanırsa cross-dataset (plan1/plan3) -> src. Kazanmazsa: tie-break kaldıracı da ölü = kapanış kanıtı.

ÜRETİME DOKUNMAZ — scripts/ deney. decode_gpu'nun tie-break-parametreli kopyası.
Kullanım: python scripts/c3_tiebreak.py [plan2|plan1|plan3]
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


def _blb_xybbox_gpu_tb(cp, occ, grid_flip, foot_flip, gshape, mode):
    """_blb_xybbox_gpu + tie-break modu. mode='blb' birebir mevcut davranış; 'support' aynı en-düşük-z
    diliminde feasible noktalar arasında footprint'i en çok alttan-desteklenen (x,y)'yi seçer.
    foot_flip: parçanın xy-gölgesi (fw,fd) ::-1,::-1 ters (support konvolüsyonu için), float64."""
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
                full = (crop.shape[0] + fw - 1, crop.shape[1] + fd - 1, crop.shape[2] + fh - 1)
                C = cp.fft.irfftn(cp.fft.rfftn(crop.astype(cp.float64), s=full) *
                                  cp.fft.rfftn(grid_flip, s=full), s=full)
                Cc = (C[fw - 1:crop.shape[0], fd - 1:crop.shape[1], fh - 1:crop.shape[2]] < 0.5)
                gx1 = min(cx0 + Cc.shape[0], mshape[0]); gy1 = min(cy0 + Cc.shape[1], mshape[1])
                bx = gx1 - cx0; by = gy1 - cy0
                if bx > 0 and by > 0:
                    mask[cx0:gx1, cy0:gy1, :] = Cc[:bx, :by, :]
            o = _select_gpu(cp, mask, occ, foot_flip, gshape, mode)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def _select_gpu(cp, mask, occ, foot_flip, gshape, mode):
    """mask (feasible bool, mshape) -> (x,y,z). En düşük z-dilim (zstar) HER MODDA korunur (yükseklik).
    mode='blb': o dilimde min-y,min-x köşe (mevcut davranış). 'support': o dilimde feasible noktalar
    arasında footprint altındaki occ-sum (support) max; eşitlikte köşe."""
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]  # (mx, my) feasible at zstar
    if mode == "blb" or zstar == 0:
        # zstar==0: taban, her yerde tam destek -> support ayırt etmez, köşeye düş (birebir taban davranışı)
        ystar = int(cp.argmax(sl.any(axis=0)))
        xstar = int(cp.argmax(sl[:, ystar]))
        return xstar, ystar, zstar
    # support: parça footprint'i (foot_flip) altındaki occ[zstar-1] dilimiyle korelasyon
    fw, fd, fh = gshape
    mx, my = sl.shape
    below = occ[:, :, zstar - 1].astype(cp.float64)  # (nx, ny)
    full = (below.shape[0] + fw - 1, below.shape[1] + fd - 1)
    S = cp.fft.irfftn(cp.fft.rfftn(below, s=full) * cp.fft.rfftn(foot_flip, s=full), s=full)
    sup = S[fw - 1:fw - 1 + mx, fd - 1:fd - 1 + my]  # (mx, my) origin başına footprint-altı occ-sum
    sup = cp.where(sl, sup, -1.0)  # infeasible noktaları ele
    # En yüksek support; eşitlikte köşe (min x sonra min y) -> deterministik. argmax C-order ilk = min x,min y.
    flat = int(cp.argmax(sup))
    xstar, ystar = int(flat // my), int(flat % my)
    return xstar, ystar, zstar


def decode_gpu_tb(parts, nx, ny, pitch, mode):
    """GPU-resident NFV decode, tie-break modlu (decode_gpu kopyası). mode='blb'|'support'."""
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
            foot = orient.grid.any(axis=2)  # xy-gölge (fw,fd)
            ff = cp.asarray(foot[::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, ff, orient.grid.shape)
            grid_cache[k] = g
        return g

    cur_max = 0
    n_placed = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            _, gf, ff, gshape = _grids(orient)
            fw, fd, fh = gshape
            if fw > nx or fd > ny:
                continue
            o = _blb_xybbox_gpu_tb(cp, occ, gf, ff, gshape, mode)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            raise RuntimeError(f"drop gerekti (parça {part.id})")
        oi, x, y, z = best
        gb, _, _, gshape = _grids(part.orientations[oi])
        fw, fd, fh = gshape
        occ[x:x + fw, y:y + fd, z:z + fh] |= gb
        cur_max = max(cur_max, z + fh)
        n_placed += 1
        if n_placed % 4 == 0:
            mempool.free_all_blocks()
    cp.cuda.Stream.null.synchronize()
    return cur_max * pitch


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    c = CFG[ds]
    pitch = c["pitch"]
    caps = probe_capabilities()
    print("=" * 74)
    print(f"NFV TIE-BREAK KALDIRACI — {ds} @{pitch}mm n=8 — {caps.summary()}")
    print("=" * 74, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    qty = c["qty"] or {f.stem: 1 for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"tiebreak_{ds}"}
    if c["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    inst = build_instance_from_order(stl_map, qty, **kwargs).instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    nx, ny = int(pw // pitch), int(pd // pitch)
    parts = to_voxel_parts(inst, pitch, n_orientations=8, margin=1)
    print(f"instance: {len(parts)} parça, plaka {pw:.0f}x{pd:.0f}mm, grid {nx}x{ny}", flush=True)

    res = {}
    for mode in ("blb", "support"):
        t = time.perf_counter()
        h = decode_gpu_tb(parts, nx, ny, pitch, mode)
        el = time.perf_counter() - t
        res[mode] = (h, el)
        print(f"  [{mode:>8}] {h:.1f}mm  ({el:.0f}s)", flush=True)

    print("-" * 74)
    hb, _ = res["blb"]; hs, _ = res["support"]
    d = (hb - hs) / hb * 100
    print(f"  baz BLB={hb:.1f}mm  support={hs:.1f}mm  fark={d:+.1f}%  (+ = support kazandı)")
    print(f"  Magics {ds} hedefi: " + ("492mm (Plan2)" if ds == "plan2" else "—"))
    print("=" * 74)


if __name__ == "__main__":
    main()
