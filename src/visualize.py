"""visualize.py — Matplotlib rendering for the IE 488 nesting prototype.

Produces a single PNG per scenario showing:
  - Plate boundary (black border, light-grey fill)
  - Usable-area boundary (dashed grey)
  - Hatched background on the usable area to highlight empty/waste space
  - Each placed part as a coloured rectangle with its ID label
  - Title with utilization and unplaced count

Usage (module):
    from src.visualize import render
    render(placements, plate, output_path, title)

Usage (CLI):
    Not a standalone script — called by run.py and bench.py.

Architectural note (flagged):
  Empty space is highlighted by drawing a hatched Rectangle over the entire
  usable area before drawing parts.  This is simpler than computing true free
  rectangles and satisfies the "yeterince guzel yeterli" (good enough) rule
  from PLAN.md §11 Blok 3 risk note.
"""

from pathlib import Path
from typing import List

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — safe on headless/OneDrive paths
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

from src.bl import Placement
from src.plate import Plate


_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
    "#d4e157", "#26c6da", "#7e57c2", "#ef5350", "#66bb6a",
]


def render(
    placements: List[Placement],
    plate: Plate,
    output_path: Path,
    title: str,
) -> None:
    """Render placement result to a PNG file.

    Args:
        placements: list of placed Placement instances.
        plate: Plate defining dimensions and margin.
        output_path: destination PNG path (parent dirs created if needed).
        title: figure title string.
    """
    fig, ax = plt.subplots(figsize=(7, 7))

    # ---- Plate boundary ----
    plate_rect = mpatches.Rectangle(
        (0, 0), plate.width_mm, plate.height_mm,
        linewidth=2, edgecolor="black", facecolor="#f5f5f5",
        zorder=0,
    )
    ax.add_patch(plate_rect)

    # ---- Usable area: hatched background (empty/waste highlight) ----
    m = plate.margin_mm
    usable_w = plate.width_mm - 2 * m
    usable_h = plate.height_mm - 2 * m
    hatch_rect = mpatches.Rectangle(
        (m, m), usable_w, usable_h,
        linewidth=1, edgecolor="#cccccc", facecolor="#e8e8e8",
        hatch="///", linestyle="--",
        zorder=1,
    )
    ax.add_patch(hatch_rect)

    # ---- Placed parts (drawn on top of hatch) ----
    for i, p in enumerate(placements):
        color = _COLORS[i % len(_COLORS)]
        rect = mpatches.Rectangle(
            (p.x, p.y), p.width, p.height,
            linewidth=1, edgecolor="black", facecolor=color, alpha=0.85,
            zorder=2,
        )
        ax.add_patch(rect)
        # ID label at centre of bounding box
        ax.text(
            p.x + p.width / 2,
            p.y + p.height / 2,
            p.part_id,
            ha="center", va="center",
            fontsize=7, fontweight="bold", color="white",
            zorder=3,
        )

    ax.set_xlim(0, plate.width_mm)
    ax.set_ylim(0, plate.height_mm)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(title, fontsize=9)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
