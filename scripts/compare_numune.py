"""compare_numune.py — hoca numuneleri DBLF vs SA karşılaştırma raporu.

Önkoşul (iki koşu, run3d — final konfigürasyon 2026-06-12: taban 335x335,
pitch 1.5, margin 1 voxel = garantili >=1 mm boşluk, slice voxelization,
z limiti 600 mm, hibrit poz seti = kısa plakalara (n3/n6) dik serbest):
  python -m src.nesting3d.run3d --scenario numune --algo dblf --pitch 1.5 \
      --orient hybrid --export-stl --check-clearance --out results/numune_dblf
  python -m src.nesting3d.run3d --scenario numune --algo sa --iters 2000 \
      --pitch 1.5 --orient hybrid --seed 13 --export-stl --check-clearance \
      --out results/numune_sa

Çıktılar (results/):
  numune_comparison.png   yan yana DBLF / SA yerleşimi + metrik bar grafiği
  numune_comparison.md    metrik tablosu + parça envanteri (rapora kopyalanabilir)
  numune_parts.csv        parça envanteri (ad, adet, boyutlar, hacim, üçgen)
  numune_overview.png     8 numunenin galeri görseli (adet + boyut etiketli)

Çalıştır:  python scripts/compare_numune.py
"""

import csv
import json
from pathlib import Path

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.models import numune_model_set  # noqa: E402
from src.nesting3d.visualize3d import MODEL_COLORS  # noqa: E402
_RES = _ROOT / "results"
DBLF_DIR = _RES / "numune_dblf"
SA_DIR = _RES / "numune_sa"

DBLF_C = "#DD8452"
SA_C = "#55A868"
PITCH = 1.5
PLATE = 335.0   # hoca makinesi tabanı (2026-06-11); z limiti 600 mm
MARGIN_MM = 1.5  # margin 1 voxel @ pitch 1.5
MAX_Z = 600.0


def _read_summary(run_dir: Path) -> dict:
    rows = list(csv.DictReader(open(run_dir / "summary_3d.csv", encoding="utf-8")))
    return {r["algo"]: r for r in rows if r["scenario"] == "numune"}


def part_inventory(models: list[tuple]) -> list[dict]:
    """Parça envanteri: gerçek mm boyutları + hacim (orijinal mesh'ten)."""
    rows = []
    for name, mesh, qty, _disp in models:
        e = mesh.extents
        rows.append({
            "parça": name,
            "dosya": f"{name[1:]}.stl",
            "adet": qty,
            "x_mm": round(float(e[0]), 1),
            "y_mm": round(float(e[1]), 1),
            "z_mm": round(float(e[2]), 1),
            "hacim_mm3": round(float(mesh.volume), 0),
            "üçgen": len(mesh.faces),
        })
    return rows


def overview_figure(models: list[tuple], out: Path) -> None:
    """8 numunenin galerisi (display mesh — render hızı için decimated)."""
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
            f"{name} ({name[1:]}.stl)  ×{qty}\n"
            f"{ext[0]:.1f}×{ext[1]:.1f}×{ext[2]:.1f} mm",
            fontsize=11,
        )
    fig.suptitle("Numune seti — hoca parçaları, gerçek boyutlar (2026-06-10)",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Yazildi: {out}")


def comparison_figure(dblf: dict, sa: dict, out: Path) -> None:
    """Üst sıra: iki yerleşim render'ı yan yana; alt sıra: metrik barları."""
    fig = plt.figure(figsize=(13, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=(1.7, 1.0))

    for col, (run_dir, row, label) in enumerate((
        (DBLF_DIR, dblf, "DBLF baseline"),
        (SA_DIR, sa, "SA (en iyi)"),
    )):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(plt.imread(run_dir / "nesting3d_numune.png"))
        ax.axis("off")
        ax.set_title(
            f"{label} — yükseklik {float(row['height_mm']):.1f} mm, "
            f"density {float(row['density']):.3f}",
            fontsize=12,
        )

    labels = ["DBLF", "SA"]
    for col, (key, title, fmt) in enumerate((
        ("height_mm", "bin yüksekliği (mm) — alçak = iyi", "{:.1f}"),
        ("density", "packing density — yüksek = iyi", "{:.3f}"),
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
        f"Numune seti (48 gerçek parça, {PLATE:.0f}x{PLATE:.0f} mm taban, "
        f"pitch {PITCH} mm) — SA kazancı {gain:+.1f} mm",
        fontsize=14,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print(f"Yazildi: {out}")


def write_report(dblf: dict, sa: dict, parts: list[dict]) -> None:
    csv_path = _RES / "numune_parts.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(parts[0].keys()))
        w.writeheader()
        w.writerows(parts)
    print(f"Yazildi: {csv_path}")

    gain = float(dblf["height_mm"]) - float(sa["height_mm"])
    md = _RES / "numune_comparison.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# Numune Seti — 3D Nesting Sonuçları\n\n")
        f.write(f"Hoca numuneleri (8 model, toplam {sum(p['adet'] for p in parts)} "
                f"parça), gerçek mm boyutlarıyla.  Taban {PLATE:.0f}x{PLATE:.0f} mm, "
                f"z limiti {MAX_Z:.0f} mm (hoca makinesi, 2026-06-11), "
                f"pitch {PITCH} mm, margin 1 voxel (garantili >= 1 mm parça arası "
                f"boşluk), slice voxelization, hibrit poz seti (kısa plakalar "
                f"n3/n6 dik durabilir — uzun plakalar n7/n8 yalnız yatık).  "
                f"STL çıktısı devoxelize edilmiş ORİJİNAL mesh'lerden üretilir "
                f"(kabartma yazılar korunur).\n\n")
        for run_dir, label in ((DBLF_DIR, "DBLF"), (SA_DIR, "SA")):
            cj = run_dir / "clearance_numune.json"
            if cj.exists():
                c = json.load(open(cj, encoding="utf-8"))
                durum = "OK" if c["ok"] else "İHLAL"
                f.write(f"Ölçülen min parça arası mesafe ({label}): "
                        f"**{c['min_mm']:.2f} mm** — {durum} (eşik 1 mm)\n\n")
        f.write("## Parça envanteri\n\n")
        f.write("| parça | dosya | adet | x (mm) | y (mm) | z (mm) | hacim (mm³) | üçgen |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for p in parts:
            f.write(f"| {p['parça']} | {p['dosya']} | {p['adet']} | {p['x_mm']} "
                    f"| {p['y_mm']} | {p['z_mm']} | {p['hacim_mm3']:.0f} "
                    f"| {p['üçgen']} |\n")
        f.write("\n## DBLF vs SA\n\n")
        f.write("| algo | parça | yükseklik (mm) | density | süre (s) | iterasyon |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in (dblf, sa):
            f.write(f"| {r['algo'].upper()} | {r['parts']} | {r['height_mm']} "
                    f"| {r['density']} | {r['time_s']} | {r['iters']} |\n")
        f.write(f"\nSA kazancı: **{gain:+.1f} mm** "
                f"({gain / float(dblf['height_mm']) * 100:.1f}%)\n")
    print(f"Yazildi: {md}")


def main() -> None:
    dblf = _read_summary(DBLF_DIR)["dblf"]
    sa = _read_summary(SA_DIR)["sa"]
    models = numune_model_set()
    parts = part_inventory(models)
    overview_figure(models, _RES / "numune_overview.png")
    comparison_figure(dblf, sa, _RES / "numune_comparison.png")
    write_report(dblf, sa, parts)


if __name__ == "__main__":
    main()
