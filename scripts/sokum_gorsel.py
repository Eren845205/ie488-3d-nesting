# -*- coding: utf-8 -*-
"""sokum_gorsel.py — k47c sokum-plani JSON'undan hoca paketi gorseli (PNG).

Ust gorunum (XY): plaka + yasak bolge + parca ayak izleri.
  gri  = duz cekmeyle cikan parcalar
  kirmizi = dondurme-sokum sertifikali parcalar (ok = cekme yonu,
            sayi = sokum sirasindaki yeri)
Kosum: python -m scripts.sokum_gorsel results/k47c_d4_sokum_plani.json
Cikti: ayni ada .png    SAF ASCII stdout.
"""
from __future__ import annotations
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

_OK = {"+X": (1, 0), "-X": (-1, 0), "+Y": (0, 1), "-Y": (0, -1)}


def main(json_path: str):
    src = Path(json_path)
    d = json.loads(src.read_text(encoding="utf-8"))
    px = float(d["pitch_mm"])
    pw, pd = d["plate"]
    certs = d["certificates"]
    sira = {pid: i + 1 for i, pid in enumerate(
        [p for p in d["removable_order"] if p in certs])}

    fig, ax = plt.subplots(figsize=(11, 11))
    ax.add_patch(Rectangle((0, 0), pw, pd, fill=False, lw=1.5, ec="black"))
    (x0, y0), (x1, y1) = d["no_go_bounds"]
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                           fc="#f4c7c3", ec="#c0392b", lw=1.0, alpha=0.9))
    ax.text((x0 + x1) / 2, y1 + 4, "yasak\nbölge", ha="center", va="bottom",
            fontsize=8, color="#c0392b")

    n_gri = n_kir = 0
    for p in d["placements"]:
        gx, gy = p["x"] * px, p["y"] * px
        gw, gd = p["grid_shape"][0] * px, p["grid_shape"][1] * px
        pid = p["part_id"]
        if pid in certs:
            n_kir += 1
            ax.add_patch(Rectangle((gx, gy), gw, gd, fc="#e74c3c", ec="#922b21",
                                   lw=0.8, alpha=0.75, zorder=3))
            c = certs[pid]
            cxm, cym = gx + gw / 2, gy + gd / 2
            no = sira.get(pid)
            if no is not None:
                ax.text(cxm, cym, str(no), ha="center", va="center",
                        fontsize=6.5, color="white", weight="bold", zorder=5)
            yon = c["yon"]
            if yon in _OK:
                dx, dy = _OK[yon]
                ax.annotate("", xy=(cxm + dx * (gw / 2 + 6), cym + dy * (gd / 2 + 6)),
                            xytext=(cxm + dx * gw / 2 * 0.6, cym + dy * gd / 2 * 0.6),
                            arrowprops=dict(arrowstyle="-|>", color="#922b21",
                                            lw=1.4), zorder=4)
            else:  # +Z: ust gorunumde nokta-halka
                ax.plot(cxm, cym + gd / 4, marker="o", ms=4, mfc="none",
                        mec="#922b21", mew=1.2, zorder=4)
        else:
            n_gri += 1
            ax.add_patch(Rectangle((gx, gy), gw, gd, fc="#d5d8dc", ec="#909497",
                                   lw=0.4, alpha=0.8, zorder=2))

    ax.set_xlim(-12, pw + 12)
    ax.set_ylim(-12, pd + 30)
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(
        f"Deneme4 — {d['h_mm']:.1f} mm yerleşim, söküm planı (üst görünüm)\n"
        f"{n_gri} parça düz çekme (gri) · {n_kir} parça sertifikalı döndürme-söküm "
        f"(kırmızı; sayı = söküm sırası, ok = çekme yönü, halka = +Z)",
        fontsize=11)
    out = src.with_suffix(".png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    print(f"PNG: {out}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("kullanim: python -m scripts.sokum_gorsel <json>")
        sys.exit(2)
    main(sys.argv[1])
