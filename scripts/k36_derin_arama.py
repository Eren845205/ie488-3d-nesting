# -*- coding: utf-8 -*-
"""k36_derin_arama.py — K-36: plan3 NFV+R10 DERIN ARAMA (seed + pitch).

Hedef: 618.1 (b+c)-legal sampiyonu 593 (manuel) yonune itmek. Iki boyut:
  1) SEED taramasi (7, 13, 99, 2025; referans 42=618.1) — heightmap'te seed
     farki 18mm olcmustu (685 vs 703); NFV kavite kararlari da seed'e bagli.
  2) PITCH derinlestirme (fine_pitch=2.0; default turetim 2.50, grid ~22.5M
     <= butce 34M) — kaviteler daha ince cozulur; en iyi seed'le kosulur.
Her bacak: solve_nfv(ham, exit_guard YOK) -> 5-yon (b) + R10 rot (b+c, sokum-
fizigi erode) -> legal(b+c). K-34 kaniti: rot-sokum kilit vergisini siliyor.

Kiyas: sampiyon 618.1 / exit_guard 680 / heightmap 735 / manuel 593.
RAM zinciri: k35_host_rz.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k36_derin_arama    SAF ASCII.
Duman: python -m scripts.k36_derin_arama smoke
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

LOG = Path(__file__).parent / "k36_derin_arama.log"
BEKLE = Path(__file__).parent / "k35_host_rz.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF = 618.1          # seed 42 @default pitch (K-34)
SEEDS = (7, 13, 99, 2025)
DERIN_PITCH = 2.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bekle():
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            return
        if tur % 10 == 0:
            log(f"k35 bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)


def _bacak(inst, n_total, etiket, seed, fine_pitch=None):
    """Tek derin-arama bacagi: NFV ham + (b) + (b+c). Doner legal_bc|None."""
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                      quality="max", seed=seed, clearance_mm=2.0,
                      no_go_bounds=NOGO, fine_pitch=fine_pitch)
    except Exception as e:
        log(f"[{etiket}] EXCEPTION: {type(e).__name__}: {e}")
        return None
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"[{etiket}] NFV: h={hv:.1f}  pitch={px}  "
        f"({(time.perf_counter() - t) / 60:.1f} dk)")
    if hv >= REF:
        # rot denetimi pahali — referansi gecemeyen bacakta atlanir (h zaten
        # alt-sinir; kilit denetimi yuksekligi DUSUREMEZ)
        log(f"[{etiket}] h >= ref {REF} — rot denetimi atlandi")
        return None
    r5 = check_separability_5dir(pls, parts)
    t = time.perf_counter()
    rot = check_separability_rot(pls, parts, max_grid_vox=560,
                                 sure_butcesi_s=240.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"[{etiket}] (b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  "
        f"cert={len(rot.certificates)}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    meshes = placed_meshes(pls, parts, px)
    rep = min_clearance(meshes)
    legal_bc, reason = legal_of(hv, len(pls), n_total, float(rep.min_mm),
                                int(rot.n_locked), clearance_req=2.0)
    log(f"[{etiket}] SONUC: h={hv:.1f}  clear={rep.min_mm:.3f}  legal(b+c)="
        f"{legal_bc if legal_bc is not None else 'INVALID(' + str(reason) + ')'}")
    if legal_bc is not None and hv < REF:
        out = _ROOT / "results" / f"plan3_nfv_derin_{etiket}_{legal_bc:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"[{etiket}] STL: {out}")
    return legal_bc


def _duman():
    log("DUMAN: import + parametre yolu")
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    assert n_total == 109 and clearance_to_voxels(2.0, 0.625) == (4, 4)
    log("DUMAN OK")


def main():
    LOG.write_text("", encoding="utf-8")
    if "smoke" in sys.argv[1:]:
        _duman()
        return
    log("K-36 DERIN ARAMA — plan3 NFV+R10 (ref 618.1 @s42 / manuel 593)")
    _bekle()
    log("k35 bitti — derin arama basliyor")
    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)

    sonuclar = {"s42_ref": REF}
    for seed in SEEDS:
        sonuclar[f"s{seed}"] = _bacak(inst, n_total, f"s{seed}", seed)
    # pitch bacagi: en iyi seed (ref dahil) ile
    en_iyi = min((v, k) for k, v in sonuclar.items() if v is not None)
    en_seed = 42 if en_iyi[1] == "s42_ref" else int(en_iyi[1][1:])
    log(f"pitch bacagi: en iyi {en_iyi[1]}={en_iyi[0]:.1f} -> "
        f"fine_pitch={DERIN_PITCH} @s{en_seed}")
    sonuclar[f"p{DERIN_PITCH}_s{en_seed}"] = _bacak(
        inst, n_total, f"p{DERIN_PITCH}_s{en_seed}", en_seed,
        fine_pitch=DERIN_PITCH)

    ozet = " | ".join(f"{k}={v:.1f}" if v is not None else f"{k}=X"
                      for k, v in sonuclar.items())
    kazanan = min((v, k) for k, v in sonuclar.items() if v is not None)
    log(f"OZET: {ozet}")
    log(f"HUKUM-VERISI: kazanan {kazanan[1]}={kazanan[0]:.1f} | ref 618.1 | "
        f"manuel 593 -> {'REKOR' if kazanan[0] < REF else 'ref gecilemedi'}"
        f"{' + 593 ALTINA INDI' if kazanan[0] < 593.0 else ''}")
    log("BITTI")


if __name__ == "__main__":
    main()
