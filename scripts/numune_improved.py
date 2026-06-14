"""numune_improved.py — Numune'yi GELİŞMİŞ motorla koş, 181.5 mm rekorunu kırmaya çalış.

Rekor kurulumu (repro_numune.py ile birebir): pitch 1.5, plate 335, margin 1,
hibrit orientations, 8-poz master. DEĞİŞEN: çözücü — tek-seed SA (rekor) yerine
bugünkü gelişmeler:
  1. SA seed 13 baseline       — sanity (181.5 üretmeli)
  2. SA t0="auto" (adaptif)    — R2
  3. MultiStartSA fresh seeds  — R4 (rekor en iyi seed'di; taze seed'ler kırar mı?)
  4. ALNS                      — yeni çözücü (numune'de YAVAŞ, küçük bütçe, EN SON)

Her sonuç anında yazılır + 181.5 ile kıyaslanır. Arka planda koşar (uzun).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities
from src.nesting3d.solvers.sa_solver import SASolver, MultiStartSA
from src.nesting3d.solvers.alns_solver import ALNSSolver

PITCH, PLATE, MARGIN, N_OR = 1.5, 335.0, 1, 8
RECORD = 181.5


def line(msg=""):
    print(msg, flush=True)


def report(name, height, baseline, secs):
    delta = height - RECORD
    mark = "🏆 REKOR KIRILDI" if delta < -0.05 else ("= rekorla aynı" if abs(delta) <= 0.5 else "rekorun üstünde")
    line(f"  [{name}] {height:.1f} mm | DBLF→{baseline-height:+.1f} | rekor(181.5)→{delta:+.1f} mm  {mark}  ({secs:.0f}s)")


def main():
    t_all = time.perf_counter()
    line("=" * 64)
    line("numune_improved.py — gelişmiş motorla 181.5 mm'yi kırma denemesi")
    line(f"kurulum: pitch={PITCH} plate={PLATE} margin={MARGIN} hibrit poz")
    line("=" * 64)

    if not NUMUNE_DIR.exists():
        line(f"HATA: {NUMUNE_DIR} yok"); sys.exit(2)

    line("voxelize (hibrit, ~1-2 dk)...")
    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), PITCH, n_orientations=N_OR,
                              margin=MARGIN, method="slice",
                              orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    line(f"  {len(parts)} parça ({time.perf_counter()-t:.0f}s)")
    mk = lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN)

    t = time.perf_counter()
    _, bb = dblf(parts, mk)
    base = bb.max_height_mm()
    line(f"  DBLF baseline: {base:.1f} mm ({time.perf_counter()-t:.1f}s)")
    line("")
    line("--- gelişmiş çözücüler ---")

    # 1) SA seed 13 — sanity (rekoru üretmeli)
    t = time.perf_counter()
    r = SASolver(t0=3.0).solve(parts, mk, budget=2000, seed=13)
    report("SA s13 (sanity)", r.height_mm, base, time.perf_counter()-t)

    # 2) SA adaptif t0
    t = time.perf_counter()
    r = SASolver(t0="auto").solve(parts, mk, budget=2000, seed=13)
    report("SA auto-t0", r.height_mm, base, time.perf_counter()-t)

    # 3) MultiStartSA — 4 taze seed (her biri 2000 iter)
    t = time.perf_counter()
    r = MultiStartSA(seed_base=777, n_starts=4, t0="auto").solve(parts, mk, budget=8000, seed=13)
    report("MultiStartSA x4", r.height_mm, base, time.perf_counter()-t)
    line(f"      (median={r.meta['median_height_mm']:.1f} best={r.meta['best_height_mm']:.1f} "
         f"std={r.meta['std_height_mm']:.1f} seeds={r.meta['all_heights_mm']})")

    # 4) ALNS — numune'de yavaş, küçük bütçe, EN SON
    line("  ALNS başlıyor (numune'de yavaş, sabırlı ol)...")
    t = time.perf_counter()
    r = ALNSSolver().solve(parts, mk, budget=120, seed=42)
    report("ALNS b120", r.height_mm, base, time.perf_counter()-t)

    line("")
    line(f"TOPLAM süre: {(time.perf_counter()-t_all)/60:.1f} dk")
    line("=" * 64)


if __name__ == "__main__":
    main()
