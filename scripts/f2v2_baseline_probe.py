# -*- coding: utf-8 -*-
"""f2v2_baseline_probe.py — F2-v2 raporu icin KONTROL baseline'lari (plan3, native plaka 279.70).

Amac: sky-corridor legal=1145.6mm sayisini adil yorumlamak. Ayni makine/voxelize/replay ile:
  (A) ILLEGAL NFV @clearance_mm=0.0  -> tarihsel ~844 referansini uret (makine + decode sagligi).
  (B) ILLEGAL NFV @clearance_mm=1.0  -> ADIL illegal baseline (sky-corridor ile ayni clearance).
Boylece: sky-corridor bedeli = (legal 1145.6) - (B illegal). heightmap 701 ayrica legal-referans.

SAF ASCII. Log: scripts/f2v2_baseline_probe.log. Kosum: python -m scripts.f2v2_baseline_probe
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.nfv_solve import solve_nfv  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from scripts.eval_gate import _load_instance  # noqa: E402

LOG = Path(__file__).parent / "f2v2_baseline_probe.log"


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def run(tag, inst, pw, pd, n_total, clearance):
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, seed=42,
                  quality="fast", clearance_mm=clearance)
    dt = time.perf_counter() - t
    pitch = float(r.fine_pitch)
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch)
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    log("")
    log(f"[{tag}] (ILLEGAL uretim NFV, clearance_mm={clearance})")
    log(f"       yukseklik={float(r.height_mm):.1f}mm  yerlesen={r.n_placed}/{n_total}  "
        f"pitch={pitch:.3f}  ({dt:.0f}s)")
    log(f"       min_clearance={rep.min_mm:.3f}mm  kilit={acc.n_locked}/{acc.n_parts}  "
        f"grup={len(acc.locked_groups)}")
    return float(r.height_mm), acc.n_locked


def main():
    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("F2-v2 KONTROL BASELINE — plan3 ILLEGAL NFV (clearance 0.0 ve 1.0)")
    log("=" * 78)
    inst = _load_instance("plan3")
    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plan3: plaka={pw:.2f}x{pd:.2f}mm  parca_sayisi={n_total}")

    h0, k0 = run("A c=0.0", inst, pw, pd, n_total, 0.0)
    h1, k1 = run("B c=1.0", inst, pw, pd, n_total, 1.0)

    log("")
    log("KIYAS:")
    log(f"  A illegal NFV c=0.0 : {h0:.1f}mm  ({k0} kilit)  [tarihsel ~844 referans]")
    log(f"  B illegal NFV c=1.0 : {h1:.1f}mm  ({k1} kilit)  [ADIL illegal baseline]")
    log(f"  sky-corridor legal  : 1145.6mm (0 kilit)  [f2v2_prototip settleON]")
    log(f"  -> sky-corridor bedeli (legal - B) = {1145.6 - h1:+.1f}mm")
    log(f"  heightmap legal ref : 701mm ; Magics : 593mm")
    log("")
    log("BITTI")


if __name__ == "__main__":
    main()
