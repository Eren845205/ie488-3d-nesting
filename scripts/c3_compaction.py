"""c3_compaction.py — GLOBAL COMPACTION (top-K eject + best-fit repack) kalite probu.

SORU (literatur A2, CGF global compaction): layout BITTIKTEN sonra parcalari sokup daha iyi
bosluga sokmak Magics acigini kapatir mi? Bizim denedigimiz SA/ALNS = SIRA (largest-first zaten
optimal -> 0); tie-break = tek-parca-yerel (zstar sabit -> 0). Bu farkli: COK-PARCA, layout-sonrasi.

MONOTONIKLIK TEOREMI (kod-oncesi analiz): bir parca yerlestirildiginde occ'ta yalniz daha buyukler
vardi, greedy minimal z+fh'ye koydu; sonraki parcalar occ'u yalniz BUYUTTU. -> TEK parcayi sokup
geri koymak (occ artik daha dolu) z+fh'yi ASLA dusurmez = tie-break gibi kesin 0. Gercek kazanc
ancak >=2 parcayi BIRLIKTE eject edip occ'u gercekten kucultunce gelir (tavan parcalari birbirinin
yerini acar). Tek anlamli serbestlik: repack SIRASI -> best-fit (largest-first'ten farkli, o olu).

PROB: bazi coz (occ-resident GPU) -> tavana en cok katki veren K parcayi (z+fh azalan) eject et ->
occ_rest'e best-fit (her adimda min-z+fh oturani sec) repack -> yeni H. K = {2,5,10,20,40} tara.
SANITY: largest-first repack ile K=tum -> baz birebir. KAZANC ESIGI: >%2 + pozitif -> cross-dataset
-> src. Hicbir K'da kazanc yoksa -> global compaction (bu greedy+diskret dunyada) da olu = kapanis.

OLC-ONCE, URETIME DOKUNMAZ (scripts/ deney). [[feedback-windows-stdout-ascii]] ASCII print.
Kullanim: python scripts/c3_compaction.py [plan2|plan1|plan3]
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


# --------------------------------------------------------------------------
# GPU feasibility (parallel_decode._blb_xybbox_gpu birebir kopya: en dusuk zstar poz)
# --------------------------------------------------------------------------

def _blb_xybbox_gpu(cp, occ, grid_flip, gshape):
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
            o = _blb_gpu(cp, mask)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def _blb_gpu(cp, mask):
    z_any = mask.any(axis=(0, 1))
    if not bool(z_any.any()):
        return None
    zstar = int(cp.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(cp.argmax(sl.any(axis=0)))
    xstar = int(cp.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


class GpuSolver:
    """occ-resident GPU NFV cozucu + eject/reinsert destekli (compaction icin)."""

    def __init__(self, parts, nx, ny, pitch):
        cp = probe_cupy()
        if cp is None:
            raise RuntimeError("cupy/GPU yok")
        self.cp = cp
        try:
            cp.fft.config.get_plan_cache().set_size(4)
        except Exception:
            pass
        self.mempool = cp.get_default_memory_pool()
        self.parts = parts
        self.nx, self.ny, self.pitch = nx, ny, pitch
        self.occ = cp.zeros((nx, ny, _nz_limit(pitch)), dtype=cp.bool_)
        self._gc = {}
        # placements: liste of dict {pi, oi, x, y, z, fh}  (pi=parts indeksi)
        self.placements = []

    def _grids(self, part_idx, oi):
        orient = self.parts[part_idx].orientations[oi]
        k = (part_idx, oi)
        g = self._gc.get(k)
        if g is None:
            cp = self.cp
            gb = cp.asarray(orient.grid, dtype=cp.bool_)
            gf = cp.asarray(orient.grid[::-1, ::-1, ::-1], dtype=cp.float64)
            g = (gb, gf, orient.grid.shape)
            self._gc[k] = g
        return g

    def _best_pos(self, part_idx, cur_max):
        """Bir parca icin tum oryantasyonlarda en iyi (min-key) poz. Greedy ile BIREBIR key."""
        best_key = None; best = None
        for oi, orient in enumerate(self.parts[part_idx].orientations):
            _, gf, gshape = self._grids(part_idx, oi)
            fw, fd, fh = gshape
            if fw > self.nx or fd > self.ny:
                continue
            o = _blb_xybbox_gpu(self.cp, self.occ, gf, gshape)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2], fh)
        return best_key, best

    def _add(self, pi, oi, x, y, z, fh):
        gb, _, _ = self._grids(pi, oi)
        fw, fd, _ = self.parts[pi].orientations[oi].grid.shape
        self.occ[x:x + fw, y:y + fd, z:z + fh] |= gb

    def _remove(self, pl):
        gb, _, _ = self._grids(pl["pi"], pl["oi"])
        x, y, z, fh = pl["x"], pl["y"], pl["z"], pl["fh"]
        fw, fd, _ = self.parts[pl["pi"]].orientations[pl["oi"]].grid.shape
        # cakisma yok (feasible garanti) -> temiz cikarma
        self.occ[x:x + fw, y:y + fd, z:z + fh] &= ~gb

    def height_voxels(self):
        return max((p["z"] + p["fh"] for p in self.placements), default=0)

    def solve_base(self):
        """Largest-first greedy (decode_gpu birebir)."""
        cur_max = 0
        n = 0
        order = sorted(range(len(self.parts)), key=lambda i: -self.parts[i].volume_voxels)
        for pi in order:
            _, best = self._best_pos(pi, cur_max)
            if best is None:
                raise RuntimeError(f"drop gerekti (parca {self.parts[pi].id})")
            oi, x, y, z, fh = best
            self._add(pi, oi, x, y, z, fh)
            self.placements.append({"pi": pi, "oi": oi, "x": x, "y": y, "z": z, "fh": fh})
            cur_max = max(cur_max, z + fh)
            n += 1
            if n % 4 == 0:
                self.mempool.free_all_blocks()
        self.cp.cuda.Stream.null.synchronize()
        return self.height_voxels()

    def compact_topk(self, k, policy="bestfit"):
        """Tavana en cok katki veren K parcayi eject + repack. policy='bestfit'|'largest'.
        Yeni height_voxels doner. occ + placements GUNCELLENIR (yikici; clone'da cagir)."""
        cp = self.cp
        # eject: z+fh azalan ilk K
        order = sorted(self.placements, key=lambda p: -(p["z"] + p["fh"]))
        ejected = order[:k]
        keep = order[k:]
        for pl in ejected:
            self._remove(pl)
        self.placements = list(keep)
        # occ_rest max yukseklik
        cur_max = self.height_voxels()
        pending = [pl["pi"] for pl in ejected]
        if policy == "largest":
            pending.sort(key=lambda pi: -self.parts[pi].volume_voxels)
            for pi in pending:
                _, best = self._best_pos(pi, cur_max)
                if best is None:
                    raise RuntimeError(f"repack drop (parca {self.parts[pi].id})")
                oi, x, y, z, fh = best
                self._add(pi, oi, x, y, z, fh)
                self.placements.append({"pi": pi, "oi": oi, "x": x, "y": y, "z": z, "fh": fh})
                cur_max = max(cur_max, z + fh)
        else:  # bestfit: her adimda kalan parcalardan min-key olani sec
            remaining = list(pending)
            while remaining:
                pick = None; pick_best = None; pick_key = None
                for pi in remaining:
                    key, best = self._best_pos(pi, cur_max)
                    if best is None:
                        continue
                    if pick_key is None or key < pick_key:
                        pick_key, pick_best, pick = key, best, pi
                if pick is None:
                    raise RuntimeError("repack bestfit drop (tum kalanlar infeasible)")
                oi, x, y, z, fh = pick_best
                self._add(pick, oi, x, y, z, fh)
                self.placements.append({"pi": pick, "oi": oi, "x": x, "y": y, "z": z, "fh": fh})
                cur_max = max(cur_max, z + fh)
                remaining.remove(pick)
        self.cp.cuda.Stream.null.synchronize()
        self.mempool.free_all_blocks()
        return self.height_voxels()

    def clone_state(self):
        """occ + placements snapshot (compaction'i bozmadan tekrar denemek icin)."""
        return self.occ.copy(), [dict(p) for p in self.placements]

    def restore_state(self, snap):
        occ, pls = snap
        self.occ = occ.copy()
        self.placements = [dict(p) for p in pls]


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    c = CFG[ds]
    pitch = c["pitch"]
    caps = probe_capabilities()
    print("=" * 78)
    print(f"GLOBAL COMPACTION PROBU — {ds} @{pitch}mm n=8 — {caps.summary()}")
    print("=" * 78, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    qty = c["qty"] or {f.stem: 1 for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"compact_{ds}"}
    if c["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    inst = build_instance_from_order(stl_map, qty, **kwargs).instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    nx, ny = int(pw // pitch), int(pd // pitch)
    parts = to_voxel_parts(inst, pitch, n_orientations=8, margin=1)
    print(f"instance: {len(parts)} parca, plaka {pw:.0f}x{pd:.0f}mm, grid {nx}x{ny}", flush=True)

    solver = GpuSolver(parts, nx, ny, pitch)
    t = time.perf_counter()
    h0 = solver.solve_base()
    el0 = time.perf_counter() - t
    base_mm = h0 * pitch
    print(f"  [BAZ greedy] {base_mm:.1f}mm  ({el0:.0f}s)  (h={h0} voxel)", flush=True)

    snap = solver.clone_state()  # her K denemesinde bu duruma don

    # SANITY: largest-first repack K=tum -> baz birebir olmali
    solver.restore_state(snap)
    hs = solver.compact_topk(len(parts), policy="largest") * pitch
    print(f"  [sanity largest K=all] {hs:.1f}mm  (baz={base_mm:.1f}, fark={base_mm-hs:+.1f})", flush=True)

    print("-" * 78)
    print(f"  {'K':>5} {'policy':>9} {'H(mm)':>9} {'kazanc':>9} {'sure':>7}")
    best_gain = 0.0
    for k in (2, 5, 10, 20, 40):
        if k > len(parts):
            continue
        for policy in ("bestfit",):
            solver.restore_state(snap)
            tk = time.perf_counter()
            hk = solver.compact_topk(k, policy=policy) * pitch
            elk = time.perf_counter() - tk
            gain = (base_mm - hk) / base_mm * 100
            best_gain = max(best_gain, gain)
            print(f"  {k:>5} {policy:>9} {hk:>9.1f} {gain:>+8.1f}% {elk:>6.0f}s", flush=True)

    print("-" * 78)
    mtarget = "492mm (Plan2)" if ds == "plan2" else "—"
    print(f"  baz={base_mm:.1f}mm  en-iyi-kazanc={best_gain:+.1f}%  Magics {ds}: {mtarget}")
    verdict = "GO (cross-dataset test et)" if best_gain > 2.0 else "NO-GO (compaction olu kanit)"
    print(f"  VERDICT: {verdict}")
    print("=" * 78)


if __name__ == "__main__":
    main()
