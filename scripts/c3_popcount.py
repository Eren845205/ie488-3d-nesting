"""c3_popcount.py — HIZ probu: binary/sparse korelasyon vs FFT (kaliteyi bozmayan, EXACT).

SORU (literatur B1): NFV feasibility = occ ile parca grid'inin valid-correlation'i (overlap==0).
Su an fp64 FFT (irfftn(rfftn(occ)*rfftn(grid_flip))). Parcalar %93 BOS (cavity-zengin) -> cakisma
testini parcanin DOLU voxelleri uzerinden yapmak (sparse-shift: her dolu voxel icin occ'u kaydir-topla)
fp64 FFT'siz, EXACT (0/1 icin kayipsiz). Kucuk/seyrek parcada FFT'yi yenebilir mi? Hibrit: kucuk
parca->sparse, buyuk->FFT.

DIKKAT — "bit-pack NO-GO"dan FARKLI: o occupancy'yi bit-pack SAKLAMAKTI; bu korelasyonu sparse-shift
HESAPLAMAK. Denenmedi.

OLC-ONCE: gercek Plan2 parcalari, boyut siniflari (kucuk/orta/buyuk) x iki occ-xy rejimi (dar=erken
decode / genis=gec decode). Her kombinasyonda: FFT-corr vs sparse-corr SURE (M tekrar) + BIREBIRLIK
kapisi (feasible set array_equal). filled-voxel sayisi raporlanir (hibrit esigi icin). KAZANC: bir
parca-boyut sinifinda sparse FFT'den belirgin hizli + birebir -> hibrit decode'a deger. Hicbir sinifta
degilse -> NO-GO (FFT zaten optimal).

URETIME DOKUNMAZ (scripts/ deney). [[feedback-windows-stdout-ascii]] ASCII print.
Kullanim: python scripts/c3_popcount.py [plan2|plan1|plan3]
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
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "plate": None, "pitch": 2.5, "qty": None},
}


def fft_corr(cp, occ_f, grid_flip_f, gshape):
    """FFT valid-correlation -> feasible bool (mevcut decode yontemi birebir). occ_f, grid_flip_f float64."""
    fw, fd, fh = gshape
    nx, ny, nz = occ_f.shape
    full = (nx, ny, nz)  # occ zaten crop kabul; grid_flip s=full ile padlenir
    C = cp.fft.irfftn(cp.fft.rfftn(occ_f, s=full) * cp.fft.rfftn(grid_flip_f, s=full), s=full)
    # valid bolge: offset (x,y,z) icin korelasyon C[fw-1+x, fd-1+y, fh-1+z]
    Cc = C[fw - 1:nx, fd - 1:ny, fh - 1:nz]
    return Cc < 0.5


def sparse_corr(cp, occ_b, filled, mshape):
    """Sparse-shift valid-correlation -> feasible bool. occ_b bool, filled: (n,3) int dolu voxel offsetleri.
    overlap(x,y,z) = sum_{(dx,dy,dz) in filled} occ[x+dx, y+dy, z+dz]; feasible <=> overlap==0. EXACT."""
    mx, my, mz = mshape
    overlap = cp.zeros(mshape, dtype=cp.int32)
    for dx, dy, dz in filled:
        overlap += occ_b[dx:dx + mx, dy:dy + my, dz:dz + mz]
    return overlap == 0


def bench_one(cp, grid, occ_xy, reps):
    """Bir parca-grid + occ-xy boyutu icin FFT vs sparse sure + birebirlik. occ z = fh+4 (decode dilimi)."""
    fw, fd, fh = grid.shape
    nz = fh + 4
    nx = max(fw, occ_xy)
    ny = max(fd, occ_xy)
    mshape = (nx - fw + 1, ny - fd + 1, nz - fh + 1)
    # temsili occ: %8 dolu rastgele (icerik sureyi etkilemez, sadece birebirlik kapisi icin)
    rng = np.random.default_rng(42)
    occ_np = (rng.random((nx, ny, nz)) < 0.08)
    occ_b = cp.asarray(occ_np, dtype=cp.bool_)
    occ_f = occ_b.astype(cp.float64)
    grid_flip_f = cp.asarray(grid[::-1, ::-1, ::-1], dtype=cp.float64)
    filled = cp.asarray(np.argwhere(grid), dtype=cp.int32)
    filled_list = [tuple(int(v) for v in r) for r in np.argwhere(grid)]
    n_filled = len(filled_list)

    # birebirlik
    f_fft = fft_corr(cp, occ_f, grid_flip_f, grid.shape)
    f_sp = sparse_corr(cp, occ_b, filled_list, mshape)
    cp.cuda.Stream.null.synchronize()
    identical = bool(cp.array_equal(f_fft, f_sp))

    # warmup
    fft_corr(cp, occ_f, grid_flip_f, grid.shape)
    sparse_corr(cp, occ_b, filled_list, mshape)
    cp.cuda.Stream.null.synchronize()

    t = time.perf_counter()
    for _ in range(reps):
        fft_corr(cp, occ_f, grid_flip_f, grid.shape)
    cp.cuda.Stream.null.synchronize()
    t_fft = (time.perf_counter() - t) / reps * 1000  # ms

    t = time.perf_counter()
    for _ in range(reps):
        sparse_corr(cp, occ_b, filled_list, mshape)
    cp.cuda.Stream.null.synchronize()
    t_sp = (time.perf_counter() - t) / reps * 1000

    return n_filled, mshape, t_fft, t_sp, identical


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    c = CFG[ds]
    pitch = c["pitch"]
    caps = probe_capabilities()
    cp = probe_cupy()
    if cp is None:
        print("GPU/cupy YOK — bu prob GPU gerektirir")
        return
    print("=" * 80)
    print(f"BINARY/SPARSE KORELASYON vs FFT — {ds} @{pitch}mm — {caps.summary()}")
    print("=" * 80, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    qty = c["qty"] or {f.stem: 1 for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"popcount_{ds}"}
    if c["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    inst = build_instance_from_order(stl_map, qty, **kwargs).instance
    parts = to_voxel_parts(inst, pitch, n_orientations=8, margin=1)

    # parca boyut siniflari: orient[0] grid bbox hacmine gore sirala -> kucuk/orta/buyuk temsilci
    uniq = {}
    for p in parts:
        g = p.orientations[0].grid
        uniq[p.id] = g  # ayni id'li tekrarlar ayni grid
    items = sorted(uniq.items(), key=lambda kv: int(kv[1].size))
    picks = []
    if items:
        picks = [("kucuk", items[0]), ("orta", items[len(items) // 2]), ("buyuk", items[-1])]
    print(f"instance: {len(parts)} parca, {len(items)} essiz parca-tipi", flush=True)
    print(f"  bbox voxel araligi: {items[0][1].size} .. {items[-1][1].size}", flush=True)
    print("-" * 80)
    print(f"  {'sinif':>6} {'parca':>26} {'bbox':>14} {'dolu':>7} {'doluluk':>7} "
          f"{'occ-xy':>7} {'FFT(ms)':>9} {'sparse(ms)':>11} {'hizlanma':>9} {'birebir':>8}")

    reps = 30
    any_win = False
    for cls, (pid, grid) in picks:
        fw, fd, fh = grid.shape
        bbox = grid.size
        nfill = int(grid.sum())
        dens = nfill / bbox * 100
        for occ_xy in (fw + 8, 164):  # dar (erken decode) / genis (gec decode, ~tam plaka)
            n_filled, mshape, t_fft, t_sp, ident = bench_one(cp, grid, occ_xy, reps)
            spd = t_fft / t_sp if t_sp > 0 else 0
            if spd > 1.0 and ident:
                any_win = True
            rej = " " if ident else " !FARK"
            print(f"  {cls:>6} {pid[:26]:>26} {fw}x{fd}x{fh:<4} {nfill:>7} {dens:>6.1f}% "
                  f"{occ_xy:>7} {t_fft:>9.2f} {t_sp:>11.2f} {spd:>8.2f}x {str(ident):>8}{rej}", flush=True)

    print("-" * 80)
    verdict = ("GO (sparse bir sinifta FFT'yi yendi + birebir -> hibrit decode'a deger)"
               if any_win else "NO-GO (FFT her sinifta >= sparse, hibrit kazanc yok)")
    print(f"  VERDICT: {verdict}")
    print("=" * 80)


if __name__ == "__main__":
    main()
