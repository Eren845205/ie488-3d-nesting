# -*- coding: utf-8 -*-
"""plan3_acili_prob.py — PLAN3 ACILI-POZ (fine_angle) PROBU: rotasyon acigi olcumu.

Hipotez (2026-07-07): Magics 593'un sirri cubuklari CAPRAZ yatirmak; bizim
eksen-hizali legal en iyi 718 (+%21). Motorun opt-in fine_angle mekanizmasi
(z-ekseni aci taramasi) planlarda HIC olculmedi — bu prob onu olcer.

Kosum: python -m scripts.plan3_acili_prob   (sure belirsiz — aci taramasi
pahali; her konfig ayri loglanir)   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.pitch import suggest_pitch
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "plan3_acili_prob.log"
PLATE = (328.74, 328.19)
REF = {"legal718": 718.0, "magics": 593.0}

CONFIGS = [  # (ad, fine_angle_window, step) — kucukten buyuge, erken sinyal
    ("w15_s5", 15.0, 5.0),
    ("w45_s15", 45.0, 15.0),
    ("w90_s15", 90.0, 15.0),
]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN3 ACILI-POZ PROBU — ref legal=718.0 / Magics=593.0 / sinir=600")
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    for ad, win, step in CONFIGS:
        t = time.perf_counter()
        try:
            r = solve_coarse_to_fine(
                inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                coarse_pitch=None, fine_pitch=pitch, budget=70, seed=42,
                n_orientations=8, clearance_mm=1.0,
                fine_angle_window=win, fine_angle_step=step,
                fine_angle_axes="z")
        except Exception as e:
            log(f"[{ad}] EXCEPTION: {e}")
            continue
        n_placed = int(getattr(r, "n_placed", len(r.placements)))
        meshes = placed_meshes(r.placements, r.fine_voxel_parts,
                               float(r.fine_pitch))
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        legal, reason = legal_of(float(r.height_mm), n_placed, n_total,
                                 float(rep.min_mm), int(acc.n_locked))
        log(f"[{ad}] h={float(r.height_mm):.1f}  legal="
            f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
            f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
            f"  aci_kullanildi={getattr(r, 'fine_angle_used', '?')}"
            f"  ({(time.perf_counter() - t) / 60:.1f} dk)"
            + ("  <600 SINIR ALTI!" if float(r.height_mm) <= 600 else ""))
    log("BITTI")


if __name__ == "__main__":
    main()
