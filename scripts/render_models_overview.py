"""render_models_overview.py — sunum için 3 modelin tanıtım görseli.

results/models_overview.png: chair / bracket / ring yan yana, adetleriyle.
Çalıştır:  python scripts/render_models_overview.py
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.models import SCENARIOS, model_set  # noqa: E402
from src.nesting3d.visualize3d import MODEL_COLORS  # noqa: E402

OUT = _ROOT / "results" / "models_overview.png"


def main() -> None:
    models = model_set("default")
    fig = plt.figure(figsize=(12, 4.2))
    for k, (name, mesh, qty) in enumerate(models):
        ax = fig.add_subplot(1, 3, k + 1, projection="3d")
        tri = mesh.vertices[mesh.faces]
        ax.add_collection3d(
            Poly3DCollection(tri, facecolor=MODEL_COLORS[name],
                             edgecolor="0.25", linewidths=0.3, alpha=0.95)
        )
        ext = mesh.extents
        lim = float(max(ext))
        ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.set_zlim(0, lim)
        ax.set_box_aspect((1, 1, 1))
        ax.set_axis_off()
        ax.set_title(
            f"{name}  ×{qty}\n"
            f"{ext[0]:.0f}×{ext[1]:.0f}×{ext[2]:.0f} mm",
            fontsize=13,
        )
    fig.suptitle("Parça seti — hoca direktifi adetleriyle (default senaryo)",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"Yazildi: {OUT}")


if __name__ == "__main__":
    main()
