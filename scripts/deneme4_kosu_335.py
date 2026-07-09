# -*- coding: utf-8 -*-
"""deneme4_kosu_335.py — Deneme4 @335x335 + NO-GO (hoca 2026-07-07 kesin kosul).

Hoca cevabi 2026-07-07: TUM setler 335x335 + NO-GO kolonu (x[185.1,215.2]
y[0.2,45.3] tam yukseklik). Eski 264mm sonucu 325+nogo'suz idi -> Magics 250.24
ile adil kiyas icin bu kosu sart. Uretim zinciri deneme5_kosu ile BIREBIR
(family routing + suggest_pitch + clearance 1.0) + legal metrik + STL.
Kosum: python -m scripts.deneme4_kosu_335   SAF ASCII.
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
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.adaptive_params import predict_nfv_benefit
from src.nesting3d.tuner import build_menu
from scripts.eval_gate import legal_of
from scripts.c3_generality import DATASETS
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM, COARSE_BUDGET

LOG = Path(__file__).parent / "deneme4_kosu_335.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))   # _nogo_area.stl bounds (mm)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("DENEME4 @335x335 + NO-GO — Magics 250.24 adil kiyas")
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    qty = cfg["qty"]
    res = build_instance_from_order(
        stl_map, qty,
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4_335",
        container_w_mm=PLATE[0], container_d_mm=PLATE[1])
    inst = res.instance
    n_total = sum(int(p.qty) for p in inst.parts)
    dec = predict_nfv_benefit(inst, family_routing=True)
    wall = bool(getattr(dec, "wall_aware", False))
    pitch = suggest_pitch(inst, wall_aware=wall)
    log(f"n_total={n_total}  routing wall_aware={wall}  pitch={pitch}")

    for ad, ng in (("NOGO'LU", NOGO), ("nogo'suz", None)):
        t = time.perf_counter()
        kw = dict(coarse_pitch=None, fine_pitch=pitch, budget=COARSE_BUDGET,
                  seed=42, drop_cache=wall, skip_fine_angle=wall,
                  clearance_mm=WEB_MIN_CLEARANCE_MM, no_go_bounds=ng)
        if wall:
            kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
        r = solve_coarse_to_fine(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1], **kw)
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                                 float(rep.min_mm), int(acc.n_locked))
        viol = 0
        if ng is not None:
            px = float(r.fine_pitch)
            for p in r.placements:
                g = r.fine_voxel_parts[p.part_id].orientations[p.orientation_idx].grid
                x0, x1 = p.x * px, (p.x + g.shape[0]) * px
                y0, y1 = p.y * px, (p.y + g.shape[1]) * px
                if x0 < NOGO[1][0] and x1 > NOGO[0][0] and y0 < NOGO[1][1] and y1 > NOGO[0][1]:
                    viol += 1
        log(f"[{ad}] h={float(r.height_mm):.1f}  legal="
            f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
            f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
            f"  yerlesen={r.n_placed}/{n_total}  nogo_bbox_kesisim={viol}"
            f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
        if legal is not None and ng is not None:
            out = _ROOT / "results" / f"deneme4_nogo335_{legal:.1f}mm.stl"
            out.parent.mkdir(exist_ok=True)
            trimesh.util.concatenate(meshes).export(out)
            log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
