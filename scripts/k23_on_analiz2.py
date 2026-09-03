# -*- coding: utf-8 -*-
"""k23_on_analiz2.py — K-23 TESHIS-2: bos canlarin ici drop'a ACIK MI?

on_analiz bulgusu: 6 ASY tabanda TEK (tepe 87.5) dururken kule 282'ye cikti.
Greedy min-z_top kurali bos can icine girebilseydi (z_top ~98) kuleyi ASLA
uzatmazdi. Iki hipotez:
  (A) bos can icleri drop'a KAPALI (duvar-arasi giris ofseti komsularca
      bloke / rim'e oturuyor) -> kule ZORUNLU -> K-23 sira-yoluyla cozulmez
      (282 = 6GB kabuk tavani, yapisal).
  (B) icler ACIKTI ama greedy baska nedenle girmedi -> duzeltilebilir
      artefakt -> guclu kaldirac (decode/tie-break isi).

Yontem: pickle sirasinin ilk 64'u (2 ROBT + 62 ASY) replay -> o andaki bin'e
fazladan bir ASY icin drop_map (4 poz) -> (1) global en iyi z_top; (2) her
BOS-TEK canin bbox penceresi icindeki en iyi z_top. Pencere-min ~ can tepe +
zincir-adimi (~10mm) ise IC ACIK (B); ~ can tepe + govde (~87mm) ise RIM (A).

Kosum: python -m scripts.k23_on_analiz2   (~1-2 dk)  SAF ASCII. Rapor-only.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "k23_on_analiz2.log"
PITCH = 0.5
ASY = "ASY-0176446"
N_HEAD = 64  # 2 ROBT + 62 ASY


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("K-23 TESHIS-2 — bos can icleri drop'a acik mi? (ASY-blogu ani, 64 replay)")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]
    head = pls[:N_HEAD]
    assert sum(1 for p in head if p.name == ASY) == 62, "ilk 64 bekleneni tutmuyor"

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    pw = float(res.instance.container.width_mm)
    pd = float(res.instance.container.depth_mm)

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n=4 ({time.perf_counter() - t:.0f}s)")

    b = Bin3D(pw, pd, PITCH, z_clearance=1)
    for p in head:
        b.place(lookup[p.part_id], p.orientation_idx, p.x, p.y, p.z)
    log(f"64-replay ani: bin tepe = {b.max_height_mm():.1f}mm")

    # bos-tek canlar: on_analiz kokleri (taban 0, tepe 87.5, halka=1)
    idle_ids = ["ASY-0176446_02", "ASY-0176446_05", "ASY-0176446_06",
                "ASY-0176446_07", "ASY-0176446_08", "ASY-0176446_09"]
    idle = {}
    for p in head:
        if p.part_id in idle_ids:
            g = lookup[p.part_id].orientations[p.orientation_idx].grid
            idle[p.part_id] = (p.x, p.x + g.shape[0], p.y, p.y + g.shape[1],
                               p.z, p.z + g.shape[2])

    probe = lookup[f"{ASY}_01"]  # ozdes tip — herhangi bir ASY grid'i
    log("")
    log("fazladan ASY icin drop_map (4 poz):")
    global_best = None
    win_best = {pid: None for pid in idle}
    for oi, orient in enumerate(probe.orientations):
        Z = b.drop_map(orient)
        if Z is None:
            continue
        fw, fh_ = orient.filled.shape
        zt = Z + orient.grid.shape[2]
        gb = int(zt.min())
        if global_best is None or gb < global_best[0]:
            global_best = (gb, oi)
        for pid, (x0, x1, y0, y1, _z0, _z1) in idle.items():
            # pencere: origin adaylari, footprint'i can bbox'iyla kesisenler
            ax0 = max(0, x0 - fw + 1); ax1 = min(zt.shape[0], x1)
            ay0 = max(0, y0 - fh_ + 1); ay1 = min(zt.shape[1], y1)
            if ax0 >= ax1 or ay0 >= ay1:
                continue
            wmin = int(zt[ax0:ax1, ay0:ay1].min())
            if win_best[pid] is None or wmin < win_best[pid][0]:
                win_best[pid] = (wmin, oi)

    log(f"  GLOBAL en iyi z_top: {global_best[0] * PITCH:.1f}mm (oi {global_best[1]})")
    log("")
    log("  bos-tek can pencereleri (can tepesi 87.5; IC ACIK olsaydi ~98 beklenir):")
    acik = 0
    for pid, wb in sorted(win_best.items()):
        if wb is None:
            log(f"    {pid}: pencerede aday yok")
            continue
        v = wb[0] * PITCH
        durum = "IC ACIK (B)" if v < 87.5 + 40 else "RIM/BLOKE (A)"
        if v < 87.5 + 40:
            acik += 1
        log(f"    {pid}: pencere-min z_top = {v:.1f}mm (oi {wb[1]}) -> {durum}")

    log("")
    if acik == 0:
        log("HUKUM: (A) — bos can icleri drop'a KAPALI; 282 kulesi ZORUNLUYDU.")
        log("        K-23 sira-permutasyonu dusuk umutlu; kabuk tavani yapisal.")
    else:
        log(f"HUKUM: (B) sinyali — {acik}/6 can ici ERISILEBILIR gorunuyor; "
            "greedy artefakti var, decode/tie-break kaldiraci arastirilmali.")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
