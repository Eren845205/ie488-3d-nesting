# -*- coding: utf-8 -*-
"""replan13_nogo.py — Plan1 + Plan3 YENIDEN: 335x335 + NO-GO (hoca 'replan' talebi).

NOT/RISK: Plan1 baseplate_v2 (330.2x302.0) yatay HER konumda no-go bbox'iyla
cakisir (335-330=5mm oynama; no-go x[185,215] y[0,45]) -> yatay basilamayabilir;
kosu bunu ACIGA CIKARIR (sentinel yukseklik = imkansiz isareti). SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.adaptive_params import predict_nfv_benefit
from src.nesting3d.tuner import build_menu
from scripts.eval_gate import _load_instance, legal_of
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM, COARSE_BUDGET

LOG = Path(__file__).parent / "replan13_nogo.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
SENTINEL_MM = 100000.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("REPLAN1+3 — 335x335 + NO-GO (hoca replan talebi)")
    for ds in ("plan3", "plan1"):
        t = time.perf_counter()
        inst = _load_instance(ds)
        n_total = sum(int(p.qty) for p in inst.parts)
        wall = bool(getattr(predict_nfv_benefit(inst, family_routing=True),
                            "wall_aware", False))
        pitch = suggest_pitch(inst, wall_aware=wall)
        kw = dict(coarse_pitch=None, fine_pitch=pitch, budget=COARSE_BUDGET,
                  seed=42, drop_cache=wall, skip_fine_angle=wall,
                  clearance_mm=WEB_MIN_CLEARANCE_MM, no_go_bounds=NOGO)
        if wall:
            kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
        try:
            r = solve_coarse_to_fine(inst, plate_w_mm=PLATE[0],
                                     plate_d_mm=PLATE[1], **kw)
        except Exception as e:
            log(f"[{ds}] EXCEPTION: {e}")
            continue
        h = float(r.height_mm)
        if h > SENTINEL_MM:
            log(f"[{ds}] IMKANSIZ: bir parca no-go ile cakismadan yerlesemiyor "
                f"(sentinel h={h:.0f}) — hocaya rapor edilmeli")
            continue
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        legal, reason = legal_of(h, int(r.n_placed), n_total,
                                 float(rep.min_mm), int(acc.n_locked))
        log(f"[{ds}] h={h:.1f}  legal="
            f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
            f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}  "
            f"yerlesen={r.n_placed}/{n_total}  pitch={pitch:.3f}  "
            f"({(time.perf_counter() - t) / 60:.1f} dk)")
        if legal is not None:
            out = _ROOT / "results" / f"{ds}_nogo335_{legal:.1f}mm.stl"
            out.parent.mkdir(exist_ok=True)
            trimesh.util.concatenate(meshes).export(out)
            log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
