# -*- coding: utf-8 -*-
"""nfv_fix_probe.py — EVAL-1 fix dogrulamasi: plan1/plan3 solve_nfv(clearance_mm=1.0).

ONCE (teshis): plan1 120.7mm ILLEGAL (clearance 0.083 + 81 kilit tek grup),
plan3 (kapi kosusu) clearance 0.055 + 87 kilit. Fix sonrasi beklenti:
min_clearance >= 1.0 VE kilitlerin buyuk kismi erir (sikisik-temas hipotezi);
yukseklik yukari gider (DURUST maliyet — kayip degil).

Kosum: python -m scripts.nfv_fix_probe   (~3-6 dk)  SAF ASCII.
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

LOG = Path(__file__).parent / "nfv_fix_probe.log"
ONCE = {"plan1": (120.7, 0.083, 81), "plan3": (None, 0.055, 87)}


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("NFV FIX PROBU — solve_nfv(clearance_mm=1.0)  [EVAL-1 dogrulama]")
    log("=" * 78)
    for ds in ("plan1", "plan3"):
        t = time.perf_counter()
        inst = _load_instance(ds)
        pw = float(inst.container.width_mm)
        pd = float(inst.container.depth_mm)
        n_total = sum(int(p.qty) for p in inst.parts)
        r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, seed=42,
                      quality="fast", clearance_mm=1.0)
        pitch = float(r.fine_pitch)
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch)
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        oh, oc, ok_ = ONCE[ds]
        log("")
        log(f"[{ds}] yukseklik={float(r.height_mm):.1f}mm"
            + (f" (ILLEGAL onceki {oh})" if oh else "")
            + f"  yerlesen={r.n_placed}/{n_total}  pitch={pitch:.3f}  "
            f"({time.perf_counter() - t:.0f}s)")
        log(f"       min_clearance={rep.min_mm:.3f}mm  (once {oc})  "
            f"{'OK>=1' if rep.min_mm >= 1.0 else '!!! HALA IHLAL'}")
        log(f"       kilit={acc.n_locked}/{acc.n_parts}  (once {ok_})  "
            f"grup={len(acc.locked_groups)}"
            + (f" boylar={sorted((len(g) for g in acc.locked_groups), reverse=True)[:6]}"
               if acc.locked_groups else ""))
        legal = (r.n_placed == n_total and rep.min_mm >= 1.0
                 and acc.n_locked == 0)
        log(f"       LEGAL_HEIGHT: "
            + (f"{float(r.height_mm):.1f}mm" if legal else
               "INVALID (kalan sebepler yukarida)"))
    log("")
    log("BITTI")


if __name__ == "__main__":
    main()
