"""visualize3d.py — matplotlib renders of a 3D nesting result (PLAN_3D.md §3).

Two outputs, matching the 2D pipeline's visual vocabulary:
  render_layout      — the placed meshes inside the bin wireframe (PNG)
  render_convergence — SA best-so-far height per iteration (PNG)

Meshes are drawn as Poly3DCollections of their actual (low-poly) triangles —
the procedural models are box/annulus composites, so triangle counts stay in
the low thousands even for the 42-part stress scenario.
"""

from pathlib import Path
from typing import Dict, List, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.voxelize import VoxelPart

MODEL_COLORS = {
    "chair": "#4C72B0", "bracket": "#DD8452", "ring": "#55A868",
    # numune seti (hoca parçaları, 2026-06-10)
    "n1": "#4C72B0", "n2": "#DD8452", "n3": "#55A868", "n4": "#C44E52",
    "n5": "#8C6BB1", "n6": "#937860", "n7": "#DA8BC3", "n8": "#64B5CD",
}
_FALLBACK = "#8172B3"


def _bin_wireframe(ax, w: float, d: float, h: float) -> None:
    """Dashed wireframe of the used envelope (base fixed, height = result)."""
    for z in (0.0, h):
        ax.plot([0, w, w, 0, 0], [0, 0, d, d, 0], [z] * 5,
                color="0.35", lw=0.9, ls="--")
    for x, y in ((0, 0), (w, 0), (w, d), (0, d)):
        ax.plot([x, x], [y, y], [0, h], color="0.35", lw=0.9, ls="--")


def render_layout(
    placements: List[Placement3D],
    parts_by_id: Dict[str, VoxelPart],
    bin3d: Bin3D,
    out_path: Path | str,
    title: str = "",
) -> Path:
    """Render the placed meshes + bin envelope to a PNG."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")

    for pl, mesh in zip(placements, placed_meshes(placements, parts_by_id,
                                                  bin3d.pitch)):
        color = MODEL_COLORS.get(pl.name, _FALLBACK)
        tri = mesh.vertices[mesh.faces]
        ax.add_collection3d(
            Poly3DCollection(tri, facecolor=color, edgecolor="0.25",
                             linewidths=0.15, alpha=0.95)
        )

    w, d = bin3d.plate_w_mm, bin3d.plate_d_mm
    h = max(bin3d.max_height_mm(), 1.0)
    _bin_wireframe(ax, w, d, h)

    ax.set_xlim(0, w)
    ax.set_ylim(0, d)
    ax.set_zlim(0, max(h * 1.15, 30))
    ax.set_box_aspect((w, d, max(h * 1.15, 30)))
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_zlabel("z (mm)")
    ax.set_title(
        title or f"3D nesting — {len(placements)} parça, "
        f"yükseklik {bin3d.max_height_mm():.1f} mm"
    )
    present = sorted({pl.name for pl in placements})
    handles = [
        plt.Line2D([0], [0], marker="s", color="none", markersize=10,
                   markerfacecolor=MODEL_COLORS.get(n, _FALLBACK), label=n)
        for n in present
    ]
    ax.legend(handles=handles, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def render_convergence(
    history: Sequence[float],
    baseline_height_mm: float,
    out_path: Path | str,
    title: str = "SA yakınsama — bin yüksekliği (mm)",
) -> Path:
    """Best-so-far height per SA iteration, with the DBLF baseline marked."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(range(len(history)), history, color="#4C72B0", lw=1.6,
            label="SA best-so-far")
    ax.axhline(baseline_height_mm, color="#DD8452", ls="--", lw=1.2,
               label=f"DBLF baseline ({baseline_height_mm:.1f} mm)")
    ax.set_xlabel("iterasyon")
    ax.set_ylabel("bin yüksekliği (mm)")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
