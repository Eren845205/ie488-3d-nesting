# -*- coding: utf-8 -*-
"""h15_on_analiz.py — H-15 ON-ANALIZ: fine drop dongusunun maliyet profili.

K-20 dersi: 131dk'nin maliyeti drop dongusu. Bu prob HANGI yolun yandigini
ve hangi kaldiracin (dirty-cache / algoritmik / GPU) ne kadar pay hedefledigini
OLCER (tahmin degil).

Yontem: K-19 v2 pickle sirasi replay edilir (place() ucuz); her S'inci parcada
yerlestirme ANINDAKI bin'e o parcanin gercek pozuyla drop_map cagrilir ve:
  - sure, fast-path uygunlugu (_drop_map_fast None mu), K (dolu kolon),
    footprint bbox, aday-sayisi (npx*npy) kaydedilir.
Tip-bazli ortalama x adet = donguye ekstrapolasyon; gercek 6270s ile kiyas.
Ek: tip-bitisik bloklar (ayni tip ardisik) -> dirty-cache kaldiracinin
teorik kapsami (ilk cagri haric ayni-tip cagrilarin payi).

Kosum: python -m scripts.h15_on_analiz [S=15]   (~8-12 dk)  SAF ASCII.
"""
from __future__ import annotations

import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "h15_on_analiz.log"
PITCH = 0.5
STRIDE = int(sys.argv[1]) if len(sys.argv) > 1 else 15
GERCEK_LOOP_S = 6270.0  # zincir testi olcumu (104.5 dk, ayni yol)


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log(f"H-15 ON-ANALIZ — fine drop profili (K-19 v2 replay, stride={STRIDE})")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    pw = float(res.instance.container.width_mm)
    pd = float(res.instance.container.depth_mm)

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n=4 ({time.perf_counter() - t:.0f}s)")

    b = Bin3D(pw, pd, PITCH, z_clearance=1)
    stats = defaultdict(list)   # tip -> [(t_drop, fast?, K, cand)]
    counts = defaultdict(int)   # tip -> toplam adet (dongudeki cagri sayisi)
    for k, p in enumerate(pls):
        part = lookup[p.part_id]
        orient = part.orientations[p.orientation_idx]
        counts[p.name] += 1
        if k % STRIDE == 0 or k < 2:  # ROBT'lar (k=0,1) daima olculur
            fw, fh = orient.filled.shape
            npx, npy = b.nx - fw + 1, b.ny - fh + 1
            t0 = time.perf_counter()
            fast = b._drop_map_fast(orient, npx, npy)
            t_fast = time.perf_counter() - t0
            if fast is None:
                t0 = time.perf_counter()
                b._drop_map_general(orient, npx, npy)
                t_call = time.perf_counter() - t0
            else:
                t_call = t_fast
            K = int(orient.filled.sum())
            stats[p.name].append((t_call, fast is not None, K, npx * npy))
        b.place(part, p.orientation_idx, p.x, p.y, p.z)

    assert abs(b.max_height_mm() - float(data["height_mm"])) < 1e-6, "replay bozuk"
    log(f"replay dogru (282.0) | olculen cagri: {sum(len(v) for v in stats.values())}")
    log("")
    log("TIP-BAZLI PROFIL (fine dongusu parca basina TEK poz cagirir):")
    log("  tip | adet | orneklem | fast% | ort-sure | K(dolu kolon) | tahmini pay")
    proj_total = 0.0
    proj_by_type = {}
    for nm in sorted(stats, key=lambda n: -np.mean([s[0] for s in stats[n]]) * counts[n]):
        ss = stats[nm]
        ts = np.array([s[0] for s in ss])
        fastp = 100.0 * sum(1 for s in ss if s[1]) / len(ss)
        Ks = int(np.median([s[2] for s in ss]))
        proj = float(ts.mean()) * counts[nm]
        proj_by_type[nm] = proj
        proj_total += proj
        log(f"  {nm[:40]:40s} {counts[nm]:4d} {len(ss):4d}  %{fastp:3.0f}"
            f"  {ts.mean():6.2f}s  K={Ks:6d}  ~{proj:6.0f}s")
    log(f"  EKSTRAPOLASYON TOPLAM: ~{proj_total:.0f}s "
        f"(gercek zincir-testi dongusu ~{GERCEK_LOOP_S:.0f}s; oran "
        f"{proj_total / GERCEK_LOOP_S:.2f})")

    # dirty-cache kaldiraci: tip-bitisik bloklarda ilk cagri haric hepsi
    # onceki drop_map'in yerel guncellemesiyle degistirilebilir.
    log("")
    log("KALDIRAC KAPSAMI:")
    cachable = 0.0
    prev = None
    for p in pls:
        nm = p.name
        t_est = float(np.mean([s[0] for s in stats[nm]])) if nm in stats else 0.0
        if prev == nm:
            cachable += t_est
        prev = nm
    log(f"  [1] dirty-cache (ayni tip ardisik, ilk haric): ~{cachable:.0f}s "
        f"= toplamin %{100 * cachable / max(proj_total, 1e-9):.0f}'i")
    gen_pay = sum(proj_by_type[nm] for nm in proj_by_type
                  if not any(s[1] for s in stats[nm]))
    log(f"  [2] genel-yol payi (algoritmik/GPU hedefi): ~{gen_pay:.0f}s "
        f"= toplamin %{100 * gen_pay / max(proj_total, 1e-9):.0f}'i")
    log("")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
