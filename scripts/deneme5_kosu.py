# -*- coding: utf-8 -*-
"""deneme5_kosu.py — Deneme5 ILK olcum: 335x335 plaka + NO-GO area (hoca kisiti).

Veri: data/mail_stl/deneme5 (12 tip / 352 parca; _nogo_area.stl x[185,215] y[0,45]
tum yukseklik). Plaka: 335x335 (152.5+30+152.5 cizim teyidi; Deneme4 makinesi).
Iki kosu: no-go'LU (gercek kosul) + no-go'SUZ (kiyas). Uretim zinciri
(family routing + suggest_pitch + clearance 1.0) + legal metrik + STL.
NOT: yeni gercek veri = registry'de HELD-OUT dogar; bu kosu URETIM/teslim
kosusudur, tuning verisi DEGILDIR (ANAYASA A3).
Kosum: python -m scripts.deneme5_kosu   SAF ASCII.
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
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM, COARSE_BUDGET

LOG = Path(__file__).parent / "deneme5_kosu.log"
D = _ROOT / "data" / "mail_stl" / "deneme5"
PLATE = (335.0, 335.0)
NOGO = ((185.1, 0.2), (215.2, 45.3))   # _nogo_area.stl bounds (mm)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("DENEME5 ILK KOSU — 335x335 + NO-GO" )
    qty = {}
    for line in (D / "_adet_listesi.txt").read_text(encoding="utf-8").splitlines():
        if " - " in line:
            ad, s = line.rsplit(" - ", 1)
            qty[ad.strip()] = int(s)
    stl_map = {f.stem: f.read_bytes() for f in sorted(D.glob("*.stl"))
               if not f.stem.startswith("_")}
    log(f"{len(stl_map)} tip STL, adet toplami={sum(qty.values())}")
    res = build_instance_from_order(stl_map, qty,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme5",
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
        # no-go ihlal kontrolu (bbox): hicbir yerlesim x[185.1,215.2]xy[0,45.3] icine tasmamali
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
            out = _ROOT / "results" / f"deneme5_nogo_{legal:.1f}mm.stl"
            out.parent.mkdir(exist_ok=True)
            trimesh.util.concatenate(meshes).export(out)
            log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
