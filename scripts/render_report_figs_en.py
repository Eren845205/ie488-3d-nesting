"""render_report_figs_en.py — English-labelled report figures.

Regenerates the report figures with English text WITHOUT re-running the SA
search. Layout figures are rendered directly from the placed-scene STL files
(decimated for display); the overview is rebuilt from the original part meshes;
the comparison reads heights/densities from the run summaries.

Outputs (results/report_figs_en/):
  fig1_overview.png        eight part models, dimensions + quantities
  fig3_dblf_layout.png     DBLF baseline scene (214.5 mm)
  fig4_sa_layout.png       final SA scene (181.5 mm)
  fig5_comparison.png      DBLF vs SA: layouts + height/density bars
  fig6_tilt_layout.png     tilted-rack experiment (181.5 mm)

Run:  python scripts/render_report_figs_en.py
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.models import numune_model_set  # noqa: E402
from src.nesting3d.visualize3d import MODEL_COLORS  # noqa: E402

_RES = _ROOT / "results"
_OUT = _RES / "report_figs_en"
_OUT.mkdir(parents=True, exist_ok=True)

DBLF_DIR = _RES / "numune_dblf"
SA_DIR = _RES / "numune_sa"
TILT_DIR = _RES / "_tilt_s42"

DBLF_C = "#DD8452"
SA_C = "#55A868"
PLATE = 335.0
PITCH = 1.5

# distinct palette for scene components (cycled)
_PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8C6BB1",
            "#937860", "#DA8BC3", "#64B5CD", "#CCB974", "#8172B3"]
_TARGET_FACES = 1200  # per-component decimation budget for display


def _read_summary(run_dir: Path) -> dict:
    rows = list(csv.DictReader(open(run_dir / "summary_3d.csv", encoding="utf-8")))
    return {r["algo"]: r for r in rows if r["scenario"] == "numune"}


def _load_scene_components(stl_path: Path):
    """Load a placed-scene STL and return decimated connected components."""
    mesh = trimesh.load(stl_path, process=False)
    if isinstance(mesh, trimesh.Scene):
        mesh = mesh.to_geometry()
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        parts = [mesh]
    out = []
    for p in parts:
        if len(p.faces) > _TARGET_FACES:
            try:
                p = p.simplify_quadric_decimation(face_count=_TARGET_FACES)
            except Exception:
                pass
        out.append(p)
    return out


def _draw_scene(ax, components, height_mm: float) -> None:
    """Draw decimated components + envelope wireframe onto a 3D axis."""
    all_v = np.vstack([c.vertices for c in components])
    mins = all_v.min(axis=0)
    for k, comp in enumerate(components):
        tri = (comp.vertices - mins)[comp.faces]
        ax.add_collection3d(
            Poly3DCollection(tri, facecolor=_PALETTE[k % len(_PALETTE)],
                             edgecolor="0.3", linewidths=0.05, alpha=0.95)
        )
    span = (all_v.max(axis=0) - mins)
    w, d = float(span[0]), float(span[1])
    h = max(height_mm, float(span[2]), 1.0)
    for z in (0.0, h):
        ax.plot([0, w, w, 0, 0], [0, 0, d, d, 0], [z] * 5,
                color="0.35", lw=0.9, ls="--")
    for x, y in ((0, 0), (w, 0), (w, d), (0, d)):
        ax.plot([x, x], [y, y], [0, h], color="0.35", lw=0.9, ls="--")
    ax.set_xlim(0, w); ax.set_ylim(0, d); ax.set_zlim(0, h * 1.1)
    ax.set_box_aspect((w, d, h * 1.1))
    ax.set_xlabel("x (mm)"); ax.set_ylabel("y (mm)"); ax.set_zlabel("z (mm)")


def layout_figure(stl_path: Path, height_mm: float, title: str, out: Path):
    comps = _load_scene_components(stl_path)
    fig = plt.figure(figsize=(9, 7))
    ax = fig.add_subplot(projection="3d")
    _draw_scene(ax, comps, height_mm)
    ax.set_title(title, fontsize=12)
    ax.view_init(elev=22, azim=-60)
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(f"Written: {out}  ({len(comps)} components)")


def overview_figure(out: Path):
    models = numune_model_set()
    fig = plt.figure(figsize=(14, 7.5))
    for k, (name, mesh, qty, disp) in enumerate(models):
        ax = fig.add_subplot(2, 4, k + 1, projection="3d")
        tri = disp.vertices[disp.faces]
        ax.add_collection3d(
            Poly3DCollection(tri, facecolor=MODEL_COLORS.get(name, "#8172B3"),
                             edgecolor="0.25", linewidths=0.1, alpha=0.95)
        )
        ext = mesh.extents
        lim = float(max(ext))
        ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_zlim(0, lim)
        ax.set_box_aspect((1, 1, 1))
        ax.set_axis_off()
        ax.set_title(
            f"{name} ({name[1:]}.stl)  x{qty}\n"
            f"{ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm",
            fontsize=11,
        )
    fig.suptitle("Production set — eight part models, real dimensions and "
                 "quantities (48 parts in total)", fontsize=14)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Written: {out}")


def comparison_figure(dblf: dict, sa: dict, out: Path):
    dblf_comps = _load_scene_components(DBLF_DIR / "nesting3d_result_numune.stl")
    sa_stl = SA_DIR / "nesting3d_result_numune_compact.stl"
    if not sa_stl.exists():
        sa_stl = SA_DIR / "nesting3d_result_numune.stl"
    sa_comps = _load_scene_components(sa_stl)

    fig = plt.figure(figsize=(13, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=(1.7, 1.0))

    for col, (comps, row, label) in enumerate((
        (dblf_comps, dblf, "DBLF baseline"),
        (sa_comps, sa, "Final SA (hybrid)"),
    )):
        ax = fig.add_subplot(gs[0, col], projection="3d")
        _draw_scene(ax, comps, float(row["height_mm"]))
        ax.view_init(elev=22, azim=-60)
        ax.set_title(
            f"{label} — height {float(row['height_mm']):.1f} mm, "
            f"density {float(row['density']):.3f}", fontsize=12,
        )

    labels = ["DBLF", "SA"]
    for col, (key, title, fmt) in enumerate((
        ("height_mm", "Build height (mm) — lower is better", "{:.1f}"),
        ("density", "Packing density — higher is better", "{:.3f}"),
    )):
        ax = fig.add_subplot(gs[1, col])
        vals = [float(dblf[key]), float(sa[key])]
        bars = ax.bar(labels, vals, 0.55, color=(DBLF_C, SA_C))
        for rect, v in zip(bars, vals):
            ax.annotate(fmt.format(v),
                        (rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        ha="center", va="bottom", fontsize=12, fontweight="bold")
        ax.set_title(title, fontsize=12)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, max(vals) * 1.2)

    gain = float(dblf["height_mm"]) - float(sa["height_mm"])
    fig.suptitle(
        f"48-part set, {PLATE:.0f} x {PLATE:.0f} mm plate, {PITCH} mm "
        f"resolution — SA gain {gain:+.1f} mm", fontsize=14,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Written: {out}")


def main():
    dblf = _read_summary(DBLF_DIR)["dblf"]
    sa = _read_summary(SA_DIR)["sa"]

    overview_figure(_OUT / "fig1_overview.png")
    layout_figure(DBLF_DIR / "nesting3d_result_numune.stl",
                  float(dblf["height_mm"]),
                  "DBLF baseline layout — height 214.5 mm, density 0.189",
                  _OUT / "fig3_dblf_layout.png")
    sa_stl = SA_DIR / "nesting3d_result_numune_compact.stl"
    if not sa_stl.exists():
        sa_stl = SA_DIR / "nesting3d_result_numune.stl"
    layout_figure(sa_stl, float(sa["height_mm"]),
                  "Final SA layout (hybrid orientations) — height 181.5 mm, "
                  "density 0.229", _OUT / "fig4_sa_layout.png")
    comparison_figure(dblf, sa, _OUT / "fig5_comparison.png")
    layout_figure(TILT_DIR / "nesting3d_result_numune.stl", 181.5,
                  "Tilted-rack experiment — plates leaning 20-35 deg, "
                  "height 181.5 mm", _OUT / "fig6_tilt_layout.png")


if __name__ == "__main__":
    main()
