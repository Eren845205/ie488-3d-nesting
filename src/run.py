"""run.py — CLI entry point for the IE 488 nesting prototype.

Usage:
    python src/run.py --algo bl --set small
    python src/run.py --algo bfd --set small
    python src/run.py --algo bl --set medium --rotation off
    python src/run.py --algo bfd --set stress --plate-w 220 --plate-h 220 --rotation on

--set accepts {small, medium, stress}; --rotation {on, off} (default on).
PNG output: results/<algo>_<set>_<rotation>.png
"""

import argparse
import sys
import time
from pathlib import Path

# Resolve project root relative to this script so imports work both from
# the project root and from any working directory.
_SRC_DIR = Path(__file__).parent
_PROJECT_ROOT = _SRC_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.bl import bottom_left, utilization_pct
from src.bfd import best_fit_decreasing
from src.loader import load_parts
from src.plate import Plate
from src.visualize import render


_SET_TO_CSV = {
    "small": "data/test_set_small.csv",
    "medium": "data/test_set_medium.csv",
    "stress": "data/test_set_stress.csv",
}

_ALGO_DISPATCH = {
    "bl": bottom_left,
    "bfd": best_fit_decreasing,
}


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="IE 488 Nesting Prototype — BL and BFD heuristics."
    )
    parser.add_argument(
        "--algo",
        choices=["bl", "bfd"],
        required=True,
        help="Algorithm to run: 'bl' (Bottom-Left) or 'bfd' (Best-Fit Decreasing).",
    )
    parser.add_argument(
        "--set",
        dest="part_set",
        choices=["small", "medium", "stress"],
        required=True,
        help="Part set to use: small (10), medium (25), or stress (50) parts.",
    )
    parser.add_argument(
        "--plate-w",
        type=float,
        default=220.0,
        help="Plate width in mm (default 220).",
    )
    parser.add_argument(
        "--plate-h",
        type=float,
        default=220.0,
        help="Plate height in mm (default 220).",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=1.0,
        help="Part-to-part and part-to-edge margin in mm (default 1).",
    )
    parser.add_argument(
        "--rotation",
        choices=["on", "off"],
        default="on",
        help="Enable or disable 90-degree rotation (default on).",
    )
    return parser.parse_args(argv)


def _apply_rotation_flag(parts, rotate_on: bool):
    """Override Part.rotatable based on CLI flag if rotation is disabled."""
    if rotate_on:
        return parts
    from src.part import Part
    return [
        Part(p.id, p.width_mm, p.height_mm, p.qty, False)
        for p in parts
    ]


def main(argv=None):
    args = _parse_args(argv)

    plate = Plate(
        width_mm=args.plate_w,
        height_mm=args.plate_h,
        margin_mm=args.margin,
    )

    csv_rel = _SET_TO_CSV[args.part_set]
    csv_path = _PROJECT_ROOT / csv_rel

    parts = load_parts(csv_path)
    rotate_on = args.rotation == "on"
    parts = _apply_rotation_flag(parts, rotate_on)

    algo_fn = _ALGO_DISPATCH[args.algo]

    t0 = time.perf_counter()
    placements, unplaced = algo_fn(parts, plate)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    util = utilization_pct(placements, plate)
    waste = 100.0 - util

    print(f"Algorithm   : {args.algo.upper()}")
    print(f"Part set    : {args.part_set}")
    print(f"Plate       : {plate.width_mm} x {plate.height_mm} mm  (margin {plate.margin_mm} mm)")
    print(f"Rotation    : {'on' if rotate_on else 'off'}")
    print(f"Parts in    : {len(parts)}")
    print(f"Placed      : {len(placements)}")
    print(f"Unplaced    : {len(unplaced)}  {unplaced if unplaced else ''}")
    print(f"Utilization : {util:.2f}%")
    print(f"Waste       : {waste:.2f}%")
    print(f"Time        : {elapsed_ms:.1f} ms")

    rot_label = "on" if rotate_on else "off"
    output_png = _PROJECT_ROOT / "results" / f"{args.algo}_{args.part_set}_{rot_label}.png"
    algo_label = args.algo.upper()
    title = (
        f"{algo_label} Nesting — {args.part_set} set  |  rotation={rot_label}  |  "
        f"util={util:.1f}%  unplaced={len(unplaced)}"
    )
    render(placements, plate, output_png, title)
    print(f"Visual      : {output_png}")


if __name__ == "__main__":
    main()
