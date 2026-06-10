"""render_comparison_3d.py — DBLF vs SA karşılaştırma bar grafiği (3D faz).

2D destedeki comparison_with_sa.png'nin 3D karşılığı.  Veriyi
results/summary_3d.csv'den okur (önce run3d --scenario all koşulmuş olmalı).

Çalıştır:  python scripts/render_comparison_3d.py
Çıktı   :  results/comparison_3d.png
"""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

_ROOT = Path(__file__).resolve().parent.parent
_RES = _ROOT / "results"
OUT = _RES / "comparison_3d.png"

DBLF_C = "#DD8452"
SA_C = "#55A868"


def main() -> None:
    rows = list(csv.DictReader(open(_RES / "summary_3d.csv", encoding="utf-8")))
    scenarios = []
    for r in rows:
        if r["scenario"] not in scenarios:
            scenarios.append(r["scenario"])
    by = {(r["scenario"], r["algo"]): r for r in rows}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    x = range(len(scenarios))
    bw = 0.36

    for ax, key, label, fmt in (
        (ax1, "height_mm", "bin yüksekliği (mm) — alçak = iyi", "{:.1f}"),
        (ax2, "density", "packing density — yüksek = iyi", "{:.3f}"),
    ):
        dblf_v = [float(by[(s, "dblf")][key]) for s in scenarios]
        sa_v = [float(by[(s, "sa")][key]) for s in scenarios]
        b1 = ax.bar([i - bw / 2 for i in x], dblf_v, bw, label="DBLF baseline",
                    color=DBLF_C)
        b2 = ax.bar([i + bw / 2 for i in x], sa_v, bw, label="SA", color=SA_C)
        for bars in (b1, b2):
            for rect in bars:
                ax.annotate(fmt.format(rect.get_height()),
                            (rect.get_x() + rect.get_width() / 2,
                             rect.get_height()),
                            ha="center", va="bottom", fontsize=11,
                            fontweight="bold")
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{s}\n({by[(s, 'dblf')]['parts']} parça)"
                            for s in scenarios], fontsize=11)
        ax.set_title(label, fontsize=12)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylim(0, max(dblf_v + sa_v) * 1.18)
        ax.legend(fontsize=10)

    # SA kazancını vurgula (stress)
    if ("stress", "sa") in by:
        gain = float(by[("stress", "dblf")]["height_mm"]) - \
               float(by[("stress", "sa")]["height_mm"])
        if gain > 0:
            ax1.annotate(f"−{gain:.1f} mm", xy=(1 + bw / 2, float(
                by[("stress", "sa")]["height_mm"]) / 2),
                ha="center", fontsize=13, fontweight="bold", color="white")

    fig.suptitle("3D Nesting — DBLF baseline vs Simulated Annealing", fontsize=14)
    fig.tight_layout()
    fig.savefig(OUT, dpi=150)
    print(f"Yazildi: {OUT}")


if __name__ == "__main__":
    main()
