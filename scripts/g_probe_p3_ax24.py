# -*- coding: utf-8 -*-
"""g_probe_p3_ax24.py — Paket G ucuz-dogrulama (2026-08-31; Eren 'en iyiyi
uretime bagla' talimati; YONTEM §2D plani adim-1).

Hipotez: plan3 makasi (~30mm; uretim 607,5 [fast] vs sampiyon 577,62
[K-49d = AX24 + R11-v4]) buyuk olcude QUALITY secimi. Test: uretim yolunun
BIREBIR kosullarinda (eval_gate ile ayni: NOGO_STD, clearance 2.0, r11-auto,
rot-auto, pitch=clearance) quality'yi MAX'a zorla ve legal yuksekligi olc.

[plan3 @ solve_nfv_kalite | no-go VAR | quality=MAX(AX24) | zincir YOK |
 plaka 335x335 | pitch 2,0]  — kosul-imzasi (P-6.5a).

Kosum: D:\\ie488'den detached (Start-Process); log stdout. SAF ASCII.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.eval_gate import NOGO_STD, _load_instance  # noqa: E402


def main() -> int:
    from src.nesting3d.nfv_solve import solve_nfv_kalite
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    print(f"G-PROBE plan3 AX24: n={n_total} plaka={pw}x{pd} nogo={NOGO_STD}",
          flush=True)
    t0 = time.time()
    res, tel = solve_nfv_kalite(
        inst, plate_w_mm=pw, plate_d_mm=pd, clearance_mm=2.0,
        no_go_bounds=NOGO_STD, quality="max", seed=42,
        n_orientations=None, r11="auto", rot_kabul="auto")
    print(f"solve bitti {time.time()-t0:.0f}s h={float(res.height_mm)}",
          flush=True)
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.continuous_settle import (kilit_5yon_meshes,
                                                 kilit_rot_meshes)
    from src.nesting3d.export_stl import placed_meshes
    meshes = placed_meshes(list(res.placements), res.fine_voxel_parts,
                           float(res.fine_pitch))
    rep = min_clearance(meshes, samples_per_mesh=6000)
    k5 = int(kilit_5yon_meshes(meshes))
    rot = None
    if k5 > 0:
        try:
            rr = kilit_rot_meshes(meshes)
            rot = int(rr.n_locked)
        except Exception as exc:
            print(f"rot denetimi hata: {exc}", flush=True)
    print(f"SONUC h={float(res.height_mm)} n={int(res.n_placed)}/{n_total} "
          f"clear={float(rep.min_mm):.3f} kilit5={k5} rot={rot}", flush=True)
    print("BITTI", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
