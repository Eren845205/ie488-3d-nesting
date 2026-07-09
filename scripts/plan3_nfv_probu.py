# -*- coding: utf-8 -*-
"""plan3_nfv_probu.py — PLAN3 NFV POTANSIYEL OLCUMU (kullanici karari
2026-07-08: 'hoca plan3'u onemsiyor' — deneme4 genel probunun plan3 ayagi).

Soru: NFV kalite modu plan3'te kac mm kazandirir ve kilitler 5-yon sokumde
gercekci mi? NOT: solve_nfv NO-GO DESTEKLEMIYOR (no-go NFV'den sonra eklendi)
-> A/B iki kol da NO-GO'SUZ 335x335 kosulur; delta gercekse no-go destegi
sonraki yatirim. Kiyas ayni kosulda oldugu icin DURUST.

Kollar:
  A) baseline: uretim zinciri n24 (queue kos() recetesi, no_go=None)
  B) NFV: solve_nfv quality=max (AX24 24 poz), clearance ayni
Her kol: legal metrik (+Z kilit) + B icin 5-YON sokum analizi
(ayrilabilirlik_probu._sirali_sokum yeniden kullanilir).

RAM zinciri: ayrilabilirlik_probu.log son satiri BITTI olana kadar bekler
(o da ax24 kuyrugunu bekliyor). Kosum: python -m scripts.detach_run
plan3_nfv_probu   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.instances.pitch import suggest_pitch
from scripts.eval_gate import _load_instance, legal_of
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM, COARSE_BUDGET
from scripts.ayrilabilirlik_probu import _sirali_sokum, _yonlu, YONLER

LOG = Path(__file__).parent / "plan3_nfv_probu.log"
BEKLE = Path(__file__).parent / "ayrilabilirlik_probu.log"
PLATE = (335.0, 335.0)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _olc(r, n_total, etiket):
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"[{etiket}] h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit_+Z={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}")
    return meshes, acc


def _bes_yon(r, etiket):
    """NFV yerlesiminde 5-yon sokum: +Z kilitlerinin kaci yan cekmeyle cozulur?"""
    t = time.perf_counter()
    sahneler = {yon: [] for yon in YONLER}
    for pl in r.placements:
        grid = r.fine_voxel_parts[pl.part_id].orientations[pl.orientation_idx].grid
        for yon in YONLER:
            sahneler[yon].append(_yonlu(pl.part_id, grid, pl.x, pl.y, pl.z, yon))
    cikan, kalan = _sirali_sokum(sahneler)
    yon_sayim = {}
    for _pid, yon in cikan:
        yon_sayim[yon] = yon_sayim.get(yon, 0) + 1
    log(f"[{etiket}] 5-YON sokum: kilit={len(kalan)}/{len(r.placements)}"
        f"  yon-dagilimi={yon_sayim}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    return len(kalan)


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN3 NFV PROBU — 335 NO-GO'SUZ A/B (NFV no-go desteklemiyor; not dusuldu)")
    def _onceki_bitti():
        if not BEKLE.exists():
            return False
        satirlar = [s.strip() for s in
                    BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if s.strip()]
        return bool(satirlar) and satirlar[-1] == "BITTI"

    tur = 0
    while not _onceki_bitti():
        if tur % 10 == 0:
            log(f"d4 ayrilabilirlik probu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("onceki prob bitti — plan3 NFV probu basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)

    # A) baseline: uretim zinciri n24, NO-GO'SUZ (kiyas ayni kosulda)
    t = time.perf_counter()
    rA = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        coarse_pitch=None, fine_pitch=pitch, budget=COARSE_BUDGET, seed=42,
        n_orientations=24, drop_cache=True,
        clearance_mm=WEB_MIN_CLEARANCE_MM)
    log(f"[A_zincir_n24] sure={(time.perf_counter() - t) / 60:.1f} dk")
    _olc(rA, n_total, "A_zincir_n24")

    # B) NFV kalite modu (AX24), ayni clearance
    t = time.perf_counter()
    rB = solve_nfv(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        quality="max", seed=42, clearance_mm=WEB_MIN_CLEARANCE_MM)
    log(f"[B_nfv_max] sure={(time.perf_counter() - t) / 60:.1f} dk")
    meshesB, accB = _olc(rB, n_total, "B_nfv_max")
    kilit5 = _bes_yon(rB, "B_nfv_max")

    hA, hB = float(rA.height_mm), float(rB.height_mm)
    log(f"HUKUM-VERISI: zincir={hA:.1f} vs NFV={hB:.1f} (delta {hB - hA:+.1f}mm,"
        f" %{(hB / hA - 1) * 100:+.1f})  NFV kilit +Z={accB.n_locked}"
        f" -> 5-yon={kilit5} (fark = yan-cekmeyle kurtulan)")
    out = _ROOT / "results" / f"plan3_nfv_probu_{hB:.1f}mm.stl"
    trimesh.util.concatenate(meshesB).export(out)
    log(f"NFV STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
