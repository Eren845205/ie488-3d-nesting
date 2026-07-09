# -*- coding: utf-8 -*-
"""plan1_uretim335.py — Plan1 GERCEK URETIM (dblf_only x5 seed) @335+NOGO (durust sayi).

Kaba prototip (dblf@1.0) 303.0 verdi ama plan1 eski-plaka uretim default'u
125.0 idi -> 303 temsili DEGIL. Bu kosu uretim zinciri (routing + portfoy +
coarse-to-fine) ile 335+nogo sayisini olcer. TEK sapma: fine_pitch=1.0 ZORLANIR
(fit-guard elle: suggest_pitch kaba pitch'te baseplate 330.2 sigmiyor —
YAPILACAKLAR 4.6'nin otomatiklestirecegi davranis).
Kosum: python -m scripts.plan1_uretim335   SAF ASCII.
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

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 42
LOG = Path(__file__).parent / f"plan1_s{SEED}_335.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
FIT_GUARD_PITCH = 1.0   # baseplate 330.2mm ancak bu cozunurlukte sigar


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log(f"PLAN1 TEK-SEED s{SEED} (dblf_only+drop_cache) @335+NOGO")
    cfg = DATASETS["plan1"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"],
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_plan1_335",
        container_w_mm=PLATE[0], container_d_mm=PLATE[1])
    inst = res.instance
    n_total = sum(int(p.qty) for p in inst.parts)
    dec = predict_nfv_benefit(inst, family_routing=True)
    wall = bool(getattr(dec, "wall_aware", False))
    onerilen = suggest_pitch(inst, wall_aware=wall)
    pitch = FIT_GUARD_PITCH if onerilen > FIT_GUARD_PITCH else onerilen
    log(f"n_total={n_total}  wall_aware={wall}  suggest_pitch={onerilen}  kullanilan={pitch} (fit-guard)")

    t = time.perf_counter()
    # coarse_pitch=fine: otomatik kaba pitch'te baseplate SIGMIYOR (ilk kosu
    # AssertionError ile oldu) — fit-guard coarse asamaya da uygulanmali.
    kw = dict(coarse_pitch=pitch, fine_pitch=pitch, budget=COARSE_BUDGET,
              seed=42, drop_cache=wall, skip_fine_angle=wall,
              clearance_mm=WEB_MIN_CLEARANCE_MM, no_go_bounds=NOGO)
    if wall:
        kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}
    kw["menu"] = {"dblf_only": build_menu()["dblf_only"]}  # tam-portfoy@1.0 = 8h+ (olculdu)
    kw["seed"] = SEED
    kw["drop_cache"] = True   # H-16 bit-ozdes onbellek (E2E kanitli) — hiz
    try:
        r = solve_coarse_to_fine(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1], **kw)
    except Exception as e:
        log(f"EXCEPTION: {e}")
        log("BITTI")
        return
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"SONUC: h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    if legal is not None:
        out = _ROOT / "results" / f"plan1_uretim335_s{SEED}_{legal:.1f}mm.stl"
        out.parent.mkdir(exist_ok=True)
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
