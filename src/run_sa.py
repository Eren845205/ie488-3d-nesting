"""run_sa.py — Single-set Simulated Annealing demo (live).

Runs the SA optimization layer on one part set, prints the baseline-vs-SA
comparison, and saves the optimized placement visual.  Fast enough on the
medium set (~3 s) for a live demonstration.

Usage:
    python src/run_sa.py --set medium
    python src/run_sa.py --set stress --iterations 6000
"""

import argparse
import sys
import time
from pathlib import Path

_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.bl import bottom_left, utilization_pct
from src.bfd import best_fit_decreasing
from src.loader import load_parts
from src.metaheuristic import simulated_annealing
from src.plate import Plate
from src.visualize import render

_SET_TO_CSV = {
    "small": "data/test_set_small.csv",
    "medium": "data/test_set_medium.csv",
    "stress": "data/test_set_stress.csv",
}
_DEFAULT_ITERS = {"small": 800, "medium": 3000, "stress": 6000}


def _parse_args(argv=None):
    p = argparse.ArgumentParser(description="Simulated Annealing nesting demo.")
    p.add_argument("--set", dest="part_set", choices=["small", "medium", "stress"],
                   default="medium")
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--plate-w", type=float, default=220.0)
    p.add_argument("--plate-h", type=float, default=220.0)
    p.add_argument("--margin", type=float, default=1.0)
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    plate = Plate(width_mm=args.plate_w, height_mm=args.plate_h, margin_mm=args.margin)
    iters = args.iterations or _DEFAULT_ITERS[args.part_set]

    parts = load_parts(_PROJECT_ROOT / _SET_TO_CSV[args.part_set])

    bl_p, _ = bottom_left(parts, plate)
    bl_u = utilization_pct(bl_p, plate)
    bfd_p, _ = best_fit_decreasing(parts, plate)
    bfd_u = utilization_pct(bfd_p, plate)
    best_baseline = max(bl_u, bfd_u)

    print(f"Set            : {args.part_set} ({len(parts)} parca)")
    print(f"Baseline BL    : {bl_u:.2f}%")
    print(f"Baseline BFD   : {bfd_u:.2f}%")
    print(f"En iyi baseline: {best_baseline:.2f}%")
    print(f"SA calisiyor   : {iters} iterasyon (seed {args.seed}) ...")

    t0 = time.perf_counter()
    sa = simulated_annealing(parts, plate, seed=args.seed, iterations=iters)
    dt = time.perf_counter() - t0

    print(f"SA sonuc       : {sa.best_utilization:.2f}%  "
          f"(baslangic {sa.initial_utilization:.2f}%)")
    print(f"KAZANC         : +{sa.best_utilization - best_baseline:.2f} puan")
    print(f"Yerlesen parca : {len(sa.placements)} / {len(parts)}")
    print(f"Sure           : {dt:.1f} s")

    out_png = _PROJECT_ROOT / "results" / f"sa_{args.part_set}.png"
    title = (
        f"SA Nesting — {args.part_set} set  |  util={sa.best_utilization:.1f}%  "
        f"placed={len(sa.placements)}  (baseline best {best_baseline:.1f}%)"
    )
    render(sa.placements, plate, out_png, title)
    print(f"Gorsel         : {out_png}")


if __name__ == "__main__":
    main()
