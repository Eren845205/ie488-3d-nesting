# -*- coding: utf-8 -*-
"""k47c_d4_cert_dump.py — K-46 231.5 yerlesiminin deterministik replay'i +
sokum-plani verisi dokumu (hoca paketi gorseli icin).

K-46 ham bacagi (seed=42) yalniz cert SAYISINI loglamisti; gorsel icin
sertifika DETAYLARI (eksen/aci/yon/lift + removable_order + kilitli gruplar)
lazim. solve_nfv deterministik: ayni parametre -> ayni 231.5 yerlesimi.
Cikti: results/k47c_d4_sokum_plani.json (+ dogrulama loglari).
Kosum: python -m scripts.detach_run k47c_d4_cert_dump    SAF ASCII.
"""
from __future__ import annotations
import json, sys, time
from dataclasses import asdict
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.rotation_extract import check_separability_rot
from src.nesting3d.coarse_to_fine import clearance_to_voxels
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance

LOG = Path(__file__).parent / "k47c_d4_cert_dump.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
BEKLENEN_H = 231.5   # K-46 ham — replay bunu birebir vermeli, yoksa UYARI
OUT = _ROOT / "results" / "k47c_d4_sokum_plani.json"


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-47c D4 CERT DUMP — K-46 ham 231.5 replay + sokum plani dokumu")
    inst = _load_instance("deneme4")
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"deneme4: {n_total} parca hedef")
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=False)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"replay: h={hv:.1f}  pitch={px}  yerlesen={len(pls)}/{n_total}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    if abs(hv - BEKLENEN_H) > 1e-6:
        log(f"UYARI: replay {hv:.1f} != beklenen {BEKLENEN_H} — determinizm sorunu, dokum yine de yaziliyor")
    r5 = check_separability_5dir(pls, parts)
    rot = check_separability_rot(pls, parts, max_grid_vox=800,
                                 sure_butcesi_s=600.0,
                                 erode_clearance_vox=clearance_to_voxels(2.0, px))
    log(f"(b) kilit={r5.n_locked}  (b+c) kilit={rot.n_locked}  cert={len(rot.certificates)}")
    dump = {
        "kaynak": "K-46 deneme4 NFV ham @2.0 seed=42 (replay)",
        "h_mm": hv,
        "pitch_mm": px,
        "plate": PLATE,
        "no_go_bounds": NOGO,
        "n_parca": len(pls),
        "b_kilit": int(r5.n_locked),
        "bc_kilit": int(rot.n_locked),
        "placements": [
            {"part_id": p.part_id, "oi": int(p.orientation_idx),
             "x": int(p.x), "y": int(p.y), "z": int(p.z),
             "grid_shape": list(parts[p.part_id]
                                .orientations[p.orientation_idx].grid.shape)}
            for p in pls],
        "removable_order": list(rot.removable_order),
        "certificates": {k: asdict(v) for k, v in rot.certificates.items()},
        "locked_groups": [list(g) for g in rot.locked_groups],
        "skipped_large": list(rot.skipped_large),
    }
    OUT.write_text(json.dumps(dump, indent=1), encoding="utf-8")
    log(f"JSON: {OUT}  ({OUT.stat().st_size / 1e6:.1f} MB)")
    log("BITTI")


if __name__ == "__main__":
    main()
