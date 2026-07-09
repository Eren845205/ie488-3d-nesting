# -*- coding: utf-8 -*-
"""plan3_nfv_nogo.py — PLAN3 NFV @335+NO-GO (kullanici talimati 2026-07-09:
'no-go olmadan anlami yok, hepsine eklenecek').

NFV'ye no-go destegi EKLENDI (OccupancyBin3D/decode/decode_gpu/fine_settle
tam-yukseklik muhur; 4 yeni test + 94 NFV regresyonu yesil). Bu kosu artik
GERCEK makine kosulunda olculur:
  NFV quality=max @335+NOGO + 5-yon sokum
  Kiyaslar: zincir n24 @335+NOGO = 719 (olculdu) / rekor 685 / Magics 593
  (dun gece no-go'suz NFV 606.9 idi — no-go bedeli bu kosuyla gorulur)

RAM zinciri: plan1_hedefli_tilt.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run plan3_nfv_nogo   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import _load_instance, legal_of
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
from scripts.plan3_nfv_probu import _bes_yon, log as _eski_log

LOG = Path(__file__).parent / "plan3_nfv_nogo.log"
BEKLE = Path(__file__).parent / "plan1_hedefli_tilt.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN3 NFV @335+NOGO — gercek makine kosulu (zincir 719 / rekor 685 / Magics 593)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"tilt kosusu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — NFV+nogo kosusu basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        quality="max", seed=42, clearance_mm=WEB_MIN_CLEARANCE_MM,
        no_go_bounds=NOGO)
    log(f"[nfv_nogo] sure={(time.perf_counter() - t) / 60:.1f} dk")
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"[nfv_nogo] h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit_+Z={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}")
    kilit5 = _bes_yon(r, "nfv_nogo")
    h = float(r.height_mm)
    log(f"HUKUM-VERISI: NFV+nogo={h:.1f} (nogo'suz 606.9; zincir+nogo 719;"
        f" rekor 685; Magics 593 -> +%{(h / 593.0 - 1) * 100:.1f})"
        f"  kilit +Z={acc.n_locked} / 5-yon={kilit5}")
    out = _ROOT / "results" / f"plan3_nfv_nogo335_{h:.1f}mm.stl"
    trimesh.util.concatenate(meshes).export(out)
    log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
