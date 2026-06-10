"""bench.py — Benchmark runner for the IE 488 nesting prototype.

Runs BL and BFD heuristics across 3 part sets x 2 rotation modes = 12 scenarios.
Outputs:
  results/summary.csv        — machine-readable table (9 columns per PLAN §9)
  results/summary.md         — human-readable markdown table (12 rows)
  results/bl_<set>_<rot>.png — BL placement PNG per scenario (6 total)
  results/bfd_<set>_<rot>.png — BFD placement PNG per scenario (6 new)
  results/comparison_bar.png — BL vs BFD utilization bar chart

Columns (summary.csv / summary.md):
  algo, set, rotation, parts_in, placed, unplaced, utilization, waste, time_ms

Dispatch map (Blok 3 builder note fulfilled):
  ALGOS = {"bl": bottom_left, "bfd": best_fit_decreasing}

Usage:
    python src/bench.py
    python src/bench.py --plate-w 220 --plate-h 220 --margin 1

No pandas dependency — uses stdlib csv module only.
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
from src.part import Part
from src.plate import Plate
from src.visualize import render


_SETS = ["small", "medium", "stress"]
_ROTATIONS = ["on", "off"]

_SET_TO_CSV = {
    "small": "data/test_set_small.csv",
    "medium": "data/test_set_medium.csv",
    "stress": "data/test_set_stress.csv",
}

_CSV_COLUMNS = [
    "algo", "set", "rotation", "parts_in",
    "placed", "unplaced", "utilization", "waste", "time_ms",
]

ALGOS = {
    "bl": bottom_left,
    "bfd": best_fit_decreasing,
}


def _apply_rotation(parts, rotate_on: bool):
    """Return parts with rotatable overridden when rotation is disabled."""
    if rotate_on:
        return parts
    return [
        Part(p.id, p.width_mm, p.height_mm, p.qty, False)
        for p in parts
    ]


def _run_scenario(algo_name: str, algo_fn, part_set: str, rotation: str, plate: Plate):
    """Run one scenario and return a result dict."""
    csv_path = _PROJECT_ROOT / _SET_TO_CSV[part_set]
    parts_raw = load_parts(csv_path)
    rotate_on = rotation == "on"
    parts = _apply_rotation(parts_raw, rotate_on)

    t0 = time.perf_counter()
    placements, unplaced_ids = algo_fn(parts, plate)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    util = utilization_pct(placements, plate)
    waste = 100.0 - util

    return {
        "algo": algo_name,
        "set": part_set,
        "rotation": rotation,
        "parts_in": len(parts),
        "placed": len(placements),
        "unplaced": len(unplaced_ids),
        "utilization": round(util, 2),
        "waste": round(waste, 2),
        "time_ms": round(elapsed_ms, 1),
        # internal — for PNG generation
        "_placements": placements,
        "_plate": plate,
    }


def _write_summary_csv(rows, out_path: Path) -> None:
    """Write rows to summary.csv using stdlib csv module."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in _CSV_COLUMNS})


def _write_summary_md(rows, out_path: Path) -> None:
    """Write rows to summary.md as a human-readable markdown table."""
    header = "| algo | set | rotation | parts_in | placed | unplaced | utilization | waste | time_ms |"
    separator = "|------|-----|----------|----------|--------|----------|-------------|-------|---------|"
    lines = [header, separator]
    for row in rows:
        line = (
            f"| {row['algo']} "
            f"| {row['set']} "
            f"| {row['rotation']} "
            f"| {row['parts_in']} "
            f"| {row['placed']} "
            f"| {row['unplaced']} "
            f"| {row['utilization']:.2f}% "
            f"| {row['waste']:.2f}% "
            f"| {row['time_ms']:.1f} |"
        )
        lines.append(line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_comparison_bar(rows, out_path: Path) -> None:
    """Write BL vs BFD utilization bar chart to comparison_bar.png.

    6 groups on the x-axis (set x rotation), each group has 2 bars (BL, BFD).
    Y-axis: utilization %.
    """
    groups = [f"{s}_{r}" for s in _SETS for r in _ROTATIONS]

    # Build lookup: (algo, set, rotation) -> utilization
    util_map = {}
    for row in rows:
        key = (row["algo"], row["set"], row["rotation"])
        util_map[key] = row["utilization"]

    bl_utils = [util_map.get(("bl", s, r), 0.0) for s, r in
                [(s, r) for s in _SETS for r in _ROTATIONS]]
    bfd_utils = [util_map.get(("bfd", s, r), 0.0) for s, r in
                 [(s, r) for s in _SETS for r in _ROTATIONS]]

    x = np.arange(len(groups))
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    bars_bl = ax.bar(x - bar_width / 2, bl_utils, bar_width,
                     label="BL (Bottom-Left)", color="#4e79a7", alpha=0.9)
    bars_bfd = ax.bar(x + bar_width / 2, bfd_utils, bar_width,
                      label="BFD (Best-Fit Decreasing)", color="#f28e2b", alpha=0.9)

    ax.set_xlabel("Scenario (set_rotation)")
    ax.set_ylabel("Utilization (%)")
    ax.set_title("BL vs BFD — Utilization Comparison (220x220 mm plate)")
    ax.set_xticks(x)
    ax.set_xticklabels(groups, rotation=15, ha="right")
    ax.set_ylim(0, 105)
    ax.legend()
    ax.yaxis.grid(True, linestyle="--", alpha=0.5)

    # Label each bar with its value
    for bar in bars_bl:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, h + 0.5,
                f"{h:.1f}%", ha="center", va="bottom", fontsize=7)
    for bar in bars_bfd:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2.0, h + 0.5,
                f"{h:.1f}%", ha="center", va="bottom", fontsize=7)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="IE 488 Nesting Benchmark — BL + BFD across 3 sets x 2 rotations."
    )
    parser.add_argument("--plate-w", type=float, default=220.0)
    parser.add_argument("--plate-h", type=float, default=220.0)
    parser.add_argument("--margin", type=float, default=1.0)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    plate = Plate(
        width_mm=args.plate_w,
        height_mm=args.plate_h,
        margin_mm=args.margin,
    )

    results_dir = _PROJECT_ROOT / "results"
    rows = []

    for algo_name, algo_fn in ALGOS.items():
        for part_set in _SETS:
            for rotation in _ROTATIONS:
                print(
                    f"Running: {algo_name}  set={part_set}  rotation={rotation} ...",
                    end=" ", flush=True,
                )
                result = _run_scenario(algo_name, algo_fn, part_set, rotation, plate)
                rows.append(result)
                print(
                    f"placed={result['placed']}/{result['parts_in']}  "
                    f"util={result['utilization']:.1f}%  "
                    f"time={result['time_ms']:.1f}ms"
                )

                # Emit placement PNG
                png_path = results_dir / f"{algo_name}_{part_set}_{rotation}.png"
                algo_label = algo_name.upper()
                title = (
                    f"{algo_label} Nesting — {part_set} set  |  rotation={rotation}  |  "
                    f"util={result['utilization']:.1f}%  unplaced={result['unplaced']}"
                )
                render(result["_placements"], result["_plate"], png_path, title)
                print(f"  -> {png_path}")

    # Write tabular outputs
    summary_csv = results_dir / "summary.csv"
    summary_md = results_dir / "summary.md"

    _write_summary_csv(rows, summary_csv)
    _write_summary_md(rows, summary_md)

    # Write comparison bar chart
    comparison_bar = results_dir / "comparison_bar.png"
    _write_comparison_bar(rows, comparison_bar)

    print(f"\nResults written:")
    print(f"  {summary_csv}")
    print(f"  {summary_md}")
    print(f"  {comparison_bar}")
    print(f"  12 placement PNGs in {results_dir}/")


if __name__ == "__main__":
    main()
