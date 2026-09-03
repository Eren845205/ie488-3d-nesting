# -*- coding: utf-8 -*-
"""k39_plan2_nfv.py — K-39: plan2 NFV ILK PROB (en buyuk bakir alan).

Gerekce (2026-07-10): plan2 heightmap sampiyonu 618.0 LEGAL (2mm, 0 kilit,
manuel 492.39'a +%25.5) — MUTLAK acik en buyuk (126mm) ve NFV plan2'de HIC
denenmedi. plan3'te NFV heightmap'i ~-%12 yendi; ayni oran ~545-560 demek.
Manuel yerlesim taktigi (Plan2.jpg): silindirler DIK kume, buyuk govdeler
ust-uste duz istif, kanatlar yan-yana dik ic-ice — kavite-dostu desen = NFV'nin
guclu oldugu sinif. fine_pitch=None -> suggest_nfv_pitch (plan2 ince parcalari
pitch'i kendi secer; acik override YOK — ilk prob otomatik yolda).
RAM zinciri: k38_pitch175.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k39_plan2_nfv    SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.clearance import min_clearance
from src.nesting3d.coarse_to_fine import clearance_to_voxels
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "k39_plan2_nfv.log"
BEKLE = Path(__file__).parent / "k38_pitch175.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF_HEIGHTMAP = 618.0
REF_MANUEL = 492.39


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-39 PLAN2 NFV ILK PROB (heightmap ref 618.0 / manuel 492.39)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k38 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k38 bitti — plan2 NFV probu basliyor")

    inst = _load_instance("plan2")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plan2: {n_total} parca hedef")
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=NOGO)
    except Exception as e:
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        log("BITTI")
        return
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"NFV: h={hv:.1f}  pitch={px}  yerlesen={len(pls)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=480.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"(b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  "
        f"cert={len(rot.certificates)}")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b)="
        f"{legal_b if legal_b is not None else 'INVALID'}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    log(f"HUKUM-VERISI: plan2_nfv={hv:.1f} | heightmap 618.0 | manuel 492.39 -> "
        f"{'REKOR' if (legal_bc is not None and hv < REF_HEIGHTMAP) else 'ref gecilemedi'}")
    if legal_bc is not None and hv < REF_HEIGHTMAP:
        out = _ROOT / "results" / f"plan2_nfv_prob_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
