# -*- coding: utf-8 -*-
"""g_probe_4set_max.py — KARAR-G kaniti: 4 dev-set (plan1/plan2/plan3/deneme4
+ deneme5) URETIM kosullarinda quality=MAX (AX24) olcumu (2026-08-31 gece;
Eren: "en iyi algoritmayi verecegiz — fast sacmaligi ne").

Her set icin [set @ solve_nfv_kalite | NOGO_STD | quality=MAX | zincirsiz |
plaka 335x335 | pitch 2,0] kosulur; legal yukseklik + sure + rot-sokum +
FAST kapi-baseline'iyla fark tablolanir. Default-flip KANIT tablosu (A1):
yukseklik kazanci vs sure bedeli. Setler SIRALI; her set oncesi RAM/GPU
kapisi; bekci ebeveyn-monitorde. SAF ASCII.

Kosum: detached (Start-Process) D:\\ie488'den; log logs/g4max.out.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.eval_gate import NOGO_STD, _load_instance  # noqa: E402

BASELINE_FAST = {"plan1": 140.21, "plan2": 521.18, "plan3": 607.50,
                 "deneme4": 215.87, "deneme5": None}
OUT = _ROOT / "results" / "g_probe_4set_max.json"
SETLER = ("plan3", "plan2", "plan1", "deneme4", "deneme5")


def _olc(res, n_total):
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.continuous_settle import (kilit_5yon_meshes,
                                                 kilit_rot_meshes)
    from src.nesting3d.export_stl import placed_meshes
    meshes = placed_meshes(list(res.placements), res.fine_voxel_parts,
                           float(res.fine_pitch))
    rep = min_clearance(meshes, samples_per_mesh=6000)
    k5 = int(kilit_5yon_meshes(meshes))
    rot = cert = None
    if k5 > 0:
        rr = kilit_rot_meshes(meshes)
        rot = int(rr.n_locked)
        cert = len(getattr(rr, "certificates", None) or [])
    legal = (int(res.n_placed) == n_total and float(rep.min_mm) >= 2.0
             and (k5 == 0 or rot == 0))
    return {"h": float(res.height_mm), "n": int(res.n_placed),
            "n_total": n_total, "clear": round(float(rep.min_mm), 3),
            "k5": k5, "rot": rot, "cert": cert, "legal": legal}


def main() -> int:
    from src.nesting3d.nfv_solve import solve_nfv_kalite
    sonuclar = {}
    for s in SETLER:
        print(f"[{s}] yukleniyor...", flush=True)
        try:
            inst = _load_instance(s)
        except Exception as exc:
            sonuclar[s] = {"hata": f"instance: {exc}"}
            continue
        n_total = sum(int(p.qty) for p in inst.parts)
        pw = float(inst.container.width_mm)
        pd = float(inst.container.depth_mm)
        t0 = time.time()
        try:
            res, tel = solve_nfv_kalite(
                inst, plate_w_mm=pw, plate_d_mm=pd, clearance_mm=2.0,
                no_go_bounds=NOGO_STD, quality="max", seed=42,
                n_orientations=None, r11="auto", rot_kabul="auto")
            o = _olc(res, n_total)
            o["sure_s"] = round(time.time() - t0, 1)
            o["fast_baseline"] = BASELINE_FAST.get(s)
            if o["fast_baseline"]:
                o["kazanc_mm"] = round(o["fast_baseline"] - o["h"], 2)
            sonuclar[s] = o
            print(f"[{s}] MAX: h={o['h']} legal={o['legal']} "
                  f"clear={o['clear']} k5={o['k5']} rot={o['rot']} "
                  f"sure={o['sure_s']}s fast_base={o['fast_baseline']}",
                  flush=True)
        except Exception as exc:
            sonuclar[s] = {"hata": str(exc),
                           "sure_s": round(time.time() - t0, 1)}
            print(f"[{s}] HATA: {exc}", flush=True)
        OUT.write_text(json.dumps(sonuclar, indent=1, ensure_ascii=True),
                       encoding="utf-8")
    print("BITTI", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
