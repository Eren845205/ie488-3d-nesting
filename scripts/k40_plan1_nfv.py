# -*- coding: utf-8 -*-
"""k40_plan1_nfv.py — K-40: plan1 NFV ILK PROB (kavite kaldiraci — piramit ici + bel-kenetleme).

Gerekce (2026-07-11): plan1'de tilt (K-28/37) ve Rz (K-35) kaldiraclari tukendi
(~129 soft / 141 hard taban gorunumu) AMA NFV plan1'de HIC denenmedi. Anatomi:
  - pyramid_with_doors x5 (59x88x88) KAPILI/BOS — ic-ice izinli (hoca): icine
    L-bracket x22 (7x19x30) / kucuk parca gomme = NFV kavite-decode isi.
  - bobbin x30 flansli — yan komsu bel-kenetleme katman yuksekligi dusurur.
  - doluluk %11 (manuel 110.41'de bile) — sikisma alani var.
Iki bacak: (A) hard-nogo y<=45 (serhsiz; kiyas 141.0) → (B) soft-nogo y<=33
(T=12mm giris serhi, hoca cevap 9; kiyas 129.0). fine_pitch=None → otomatik
(TAPER 2.5mm inceligi pitch'i kendisi sectirir).
RAM zinciri: k39_plan2_nfv.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k40_plan1_nfv    SAF ASCII.
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

LOG = Path(__file__).parent / "k40_plan1_nfv.log"
BEKLE = Path(__file__).parent / "k39_plan2_nfv.log"
PLATE = (335.0, 335.0)
NOGO_HARD = ((152.5, 0.2), (185.5, 45.0))
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))   # T=12mm giris serhi (hoca cevap 9)
BACAKLAR = (
    ("nfv_hard", NOGO_HARD, 141.0, ""),
    ("nfv_soft", NOGO_SOFT, 129.0, "  [SERH: soft-nogo T=12mm, hoca cevap 9]"),
)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bacak(inst, n_total, etiket, nogo, ref, serh):
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=42, clearance_mm=2.0,
                      no_go_bounds=nogo)
    except Exception as e:
        log(f"[{etiket}] EXCEPTION: {type(e).__name__}: {e}")
        return
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"[{etiket}] NFV: h={hv:.1f}  pitch={px}  yerlesen={len(pls)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=240.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"[{etiket}] (b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  "
        f"cert={len(rot.certificates)}")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_b, _ = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                          int(r5.n_locked), clearance_req=2.0)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"[{etiket}] SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b)="
        f"{legal_b if legal_b is not None else 'INVALID'}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}"
        f"{serh}")
    log(f"[{etiket}] HUKUM-VERISI: {hv:.1f} | ref {ref} | manuel 110.41 -> "
        f"{'REKOR' if (legal_bc is not None and hv < ref) else 'ref gecilemedi'}")
    if legal_bc is not None and hv < ref:
        out = _ROOT / "results" / f"plan1_{etiket}_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-40 PLAN1 NFV ILK PROB (hard ref 141.0 / soft ref 129.0 / manuel 110.41)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k39 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k39 bitti — plan1 NFV probu basliyor")

    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plan1: {n_total} parca hedef")
    for etiket, nogo, ref, serh in BACAKLAR:
        _bacak(inst, n_total, etiket, nogo, ref, serh)
    log("BITTI")


if __name__ == "__main__":
    main()
