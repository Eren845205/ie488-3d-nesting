"""bench_meta.py — Benchmark the Simulated Annealing layer against the baselines.

Runs, for each part set (rotation ON):
  - BL  (Bottom-Left, longest-edge sort)        — baseline
  - BFD (Best-Fit Decreasing, skyline)          — baseline
  - SA  (Simulated Annealing over part order)   — contribution

Outputs:
  results/meta_summary.csv          — machine-readable comparison table
  results/meta_summary.md           — human-readable markdown table
  results/sa_<set>.png              — SA best-found placement per set
  results/sa_convergence.png        — utilization vs iteration (one line per set)
  results/comparison_with_sa.png    — BL vs BFD vs SA grouped bar chart

No pandas; stdlib csv + matplotlib only.  Reproducible: fixed seed per set.

Usage:
    python src/bench_meta.py
"""

import argparse
import csv
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.bl import bottom_left, utilization_pct
from src.bfd import best_fit_decreasing
from src.loader import load_parts
from src.metaheuristic import simulated_annealing
from src.plate import Plate
from src.visualize import render


_SETS = ["small", "medium", "stress"]
_SET_TO_CSV = {
    "small": "data/test_set_small.csv",
    "medium": "data/test_set_medium.csv",
    "stress": "data/test_set_stress.csv",
}

# SA iterations per set.  Small needs almost none (all parts already fit);
# medium and stress get a larger budget because part selection/ordering matters.
_ITERATIONS = {
    "small": 800,
    "medium": 3000,
    "stress": 6000,
}

_SEED = 42

_CSV_COLUMNS = [
    "set", "parts_in", "demand_pct",
    "bl_util", "bfd_util", "sa_init_util", "sa_util",
    "gain_vs_best_baseline_pp", "sa_placed", "sa_time_ms",
]


def _demand_pct(parts, plate) -> float:
    total = sum(p.width_mm * p.height_mm for p in parts)
    return 100.0 * total / (plate.width_mm * plate.height_mm)


def _run_set(part_set: str, plate: Plate):
    csv_path = _PROJECT_ROOT / _SET_TO_CSV[part_set]
    parts = load_parts(csv_path)

    bl_p, _ = bottom_left(parts, plate)
    bl_u = utilization_pct(bl_p, plate)

    bfd_p, _ = best_fit_decreasing(parts, plate)
    bfd_u = utilization_pct(bfd_p, plate)

    t0 = time.perf_counter()
    sa = simulated_annealing(
        parts, plate, seed=_SEED, iterations=_ITERATIONS[part_set]
    )
    sa_ms = (time.perf_counter() - t0) * 1000.0

    best_baseline = max(bl_u, bfd_u)
    row = {
        "set": part_set,
        "parts_in": len(parts),
        "demand_pct": round(_demand_pct(parts, plate), 1),
        "bl_util": round(bl_u, 2),
        "bfd_util": round(bfd_u, 2),
        "sa_init_util": round(sa.initial_utilization, 2),
        "sa_util": round(sa.best_utilization, 2),
        "gain_vs_best_baseline_pp": round(sa.best_utilization - best_baseline, 2),
        "sa_placed": len(sa.placements),
        "sa_time_ms": round(sa_ms, 0),
        "_sa": sa,
        "_plate": plate,
    }
    return row


def _write_csv(rows, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in _CSV_COLUMNS})


def _write_md(rows, out_path: Path) -> None:
    header = (
        "| set | parts | demand % | BL % | BFD % | SA init % | SA % | "
        "gain vs best baseline | SA placed | SA time (ms) |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|---|"
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"| {r['set']} | {r['parts_in']} | {r['demand_pct']:.0f}% "
            f"| {r['bl_util']:.2f} | {r['bfd_util']:.2f} | {r['sa_init_util']:.2f} "
            f"| **{r['sa_util']:.2f}** | +{r['gain_vs_best_baseline_pp']:.2f} pp "
            f"| {r['sa_placed']} | {r['sa_time_ms']:.0f} |"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_convergence(rows, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = {"small": "#59a14f", "medium": "#4e79a7", "stress": "#e15759"}
    for r in rows:
        hist = r["_sa"].history
        ax.plot(
            range(len(hist)), hist,
            label=f"{r['set']} (init {r['sa_init_util']:.1f}% → {r['sa_util']:.1f}%)",
            color=colors.get(r["set"]), linewidth=1.8,
        )
    ax.set_xlabel("SA iterasyonu")
    ax.set_ylabel("En iyi doluluk (%)")
    ax.set_title("Simulated Annealing — Yakınsama (best-so-far doluluk)")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _write_comparison(rows, out_path: Path) -> None:
    sets = [r["set"] for r in rows]
    bl = [r["bl_util"] for r in rows]
    bfd = [r["bfd_util"] for r in rows]
    sa = [r["sa_util"] for r in rows]

    x = np.arange(len(sets))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9, 5))
    b1 = ax.bar(x - w, bl, w, label="BL (baseline)", color="#4e79a7")
    b2 = ax.bar(x, bfd, w, label="BFD (baseline)", color="#f28e2b")
    b3 = ax.bar(x + w, sa, w, label="SA (optimizasyon)", color="#59a14f")

    ax.set_xlabel("Parça seti")
    ax.set_ylabel("Doluluk (%)")
    ax.set_title("BL vs BFD vs SA — Doluluk Karşılaştırması (rotation on, 220×220 mm)")
    ax.set_xticks(x)
    ax.set_xticklabels(sets)
    ax.set_ylim(0, 105)
    ax.legend()
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)
    for bars in (b1, b2, b3):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=7)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SA vs baseline benchmark.")
    parser.add_argument("--plate-w", type=float, default=220.0)
    parser.add_argument("--plate-h", type=float, default=220.0)
    parser.add_argument("--margin", type=float, default=1.0)
    args = parser.parse_args(argv)

    plate = Plate(width_mm=args.plate_w, height_mm=args.plate_h, margin_mm=args.margin)
    results_dir = _PROJECT_ROOT / "results"

    rows = []
    for part_set in _SETS:
        print(f"Running SA: set={part_set} iters={_ITERATIONS[part_set]} ...",
              end=" ", flush=True)
        row = _run_set(part_set, plate)
        rows.append(row)
        print(
            f"BL={row['bl_util']:.1f} BFD={row['bfd_util']:.1f} "
            f"SA={row['sa_util']:.1f} (+{row['gain_vs_best_baseline_pp']:.1f}pp) "
            f"{row['sa_time_ms']:.0f}ms"
        )
        # SA placement visual
        png = results_dir / f"sa_{part_set}.png"
        title = (
            f"SA Nesting — {part_set} set  |  util={row['sa_util']:.1f}%  "
            f"placed={row['sa_placed']}  (baseline best {max(row['bl_util'], row['bfd_util']):.1f}%)"
        )
        render(row["_sa"].placements, plate, png, title)
        print(f"  -> {png}")

    _write_csv(rows, results_dir / "meta_summary.csv")
    _write_md(rows, results_dir / "meta_summary.md")
    _write_convergence(rows, results_dir / "sa_convergence.png")
    _write_comparison(rows, results_dir / "comparison_with_sa.png")

    print("\nResults written:")
    print(f"  {results_dir / 'meta_summary.csv'}")
    print(f"  {results_dir / 'meta_summary.md'}")
    print(f"  {results_dir / 'sa_convergence.png'}")
    print(f"  {results_dir / 'comparison_with_sa.png'}")
    print(f"  sa_<set>.png placement visuals in {results_dir}/")


if __name__ == "__main__":
    main()
