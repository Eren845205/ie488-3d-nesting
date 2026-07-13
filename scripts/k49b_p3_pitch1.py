# -*- coding: utf-8 -*-
"""k49b_p3_pitch1.py — K-49b: plan3 @pitch-1.0 (KOSULLU manuel-gecme probu).

On-tahmin (2026-07-13): p3 grid-cache @1.0 ~3.57GB f64 + occ 0.18 + FFT slab
-> default 1536MB slab butcesiyle ~5.25GB = 6GB VRAM SINIRINDA. Bu yuzden
NFV_FFT_GPU_BUDGET_MB=768 ile kosulur (H-17 env dugmesi; slab yariya iner,
toplam ~4.5GB). Kalibrasyon: ayni hesap p2'de 7.3GB (crash etti ✓) d5'te
2GB (gecti ✓) veriyor — tahmin guvenilir.
KOSUL: k49a (p3+R11) MANUEL GECILDI hukmu verdiyse bu prob GEREKSIZ — kendini
iptal eder (log'a yazar, BITTI der). Aksi halde @1.0 ham NFV kosar.
Zincir: k49a_p3_r11.log BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k49b_p3_pitch1    SAF ASCII.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

os.environ.setdefault("NFV_FFT_GPU_BUDGET_MB", "768")  # SINIRDA VRAM icin yarim slab

import trimesh
from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.clearance import min_clearance
from src.nesting3d.coarse_to_fine import clearance_to_voxels
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance, legal_of
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k49b_p3_pitch1.log"
BEKLE = Path(__file__).parent / "k49a_p3_r11.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
PITCH = 1.0
REF = 598.5
MANUEL = 593.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-49b PLAN3 @1.0 — kosullu prob (ref 598.5 / manuel 593; slab=768MB)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k49a bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    k49a_log = BEKLE.read_text(encoding="utf-8", errors="ignore")
    if "MANUEL GECILDI" in k49a_log:
        log("k49a manueli GECTI — @1.0 probu GEREKSIZ (vergi odenmez), iptal")
        log("BITTI")
        return
    log("k49a manueli gecemedi — plan3 @1.0 basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=NOGO, fine_pitch=PITCH, exit_guard=False)
    except Exception as e:
        log(f"EXCEPTION: {type(e).__name__}: {e}")
        log("HUKUM-VERISI: bacak olu -> ref gecilemedi")
        log("BITTI")
        return
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    sure_dk = (time.perf_counter() - t) / 60
    log(f"NFV: h={hv:.1f}  yerlesen={len(pls)}/{n_total}  ({sure_dk:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=600.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"(b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  cert={len(rot.certificates)}")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes, samples_per_mesh=6000)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    if legal_bc is not None:
        kaydet("plan3", "nfv", "ham@1.0", hv, len(pls), n_total,
               float(rep.min_mm), int(rot.n_locked), sure_dk * 60,
               kosu_id="K-49b/ham", log_yolu="scripts/k49b_p3_pitch1.log",
               pitch=PITCH, seed=42, instance=inst,
               b_kilit=int(r5.n_locked), cert=len(rot.certificates))
        log("telemetri v2 satiri yazildi")
        if hv < REF:
            out = _ROOT / "results" / f"plan3_p1_ham_{legal_bc:.1f}mm.stl"
            trimesh.util.concatenate(meshes).export(out)
            log(f"STL: {out}")
    log(f"HUKUM-VERISI: h={hv:.1f} | ref 598.5 | manuel {MANUEL} -> "
        + ("MANUEL GECILDI (p3)" if (legal_bc is not None and hv < MANUEL)
           else ("REKOR" if (legal_bc is not None and hv < REF) else "ref gecilemedi")))
    log("BITTI")


if __name__ == "__main__":
    main()
