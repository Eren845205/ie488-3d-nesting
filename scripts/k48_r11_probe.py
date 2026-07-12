# -*- coding: utf-8 -*-
"""k48_r11_probe.py — K-48: R11 surekli z-kompaksiyon GERCEK-SET probu (deneme5).

Gerekce (2026-07-12, onayli program #3): fine_settle pitch/4 kafesinde durur;
R11 kafesi birakir (mesh-gercek mesafe, surekli z). Beklenen kazanc kaynagi:
kalan kafes yuvarlamasi + voxel yuzey-sarmasi sismesi (katman basina ~0.1-0.5mm,
kule boyunca birikir). PROB: K-44 sampiyonu (d5 ham @2.0 = 223.5) replay →
R11 → kapilar. GO esigi: kazanc > 0.5mm (B2 gurultu bandi) + clear(6000)>=2.0
+ kilit(post) <= kilit(pre) (ayni margin-0 @1.0 re-voxelize metrigiyle).
Zincir: k47b_p2_pitch1.log BITTI olana kadar bekler (GPU/RAM sirasi).
Kosum: python -m scripts.detach_run k48_r11_probe    SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
from types import SimpleNamespace
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import apply_settle, continuous_z_settle
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.voxelize import voxelize_part
from scripts.ax24_kuyruk_335 import _load

LOG = Path(__file__).parent / "k48_r11_probe.log"
BEKLE = Path(__file__).parent / "k47b_p2_pitch1.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
REF_VOXEL = 223.5   # K-44 sampiyon (voxel-raporlu)
CHECK_PITCH = 1.0   # kilit re-check voxelize pitch'i (konservatif kapsayici)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _kilit_5dir_meshes(meshes):
    """Mesh listesinde 5-yon kilit sayisi (margin-0, @CHECK_PITCH re-voxelize).
    Pozisyon kafese yuvarlanir (<=0.5 voxel) — pre/post AYNI metrik, delta durust."""
    parts = {}
    pls = []
    for i, m in enumerate(meshes):
        pid = f"m{i}"
        vp = voxelize_part(pid, m, CHECK_PITCH, n_orientations=1, margin=0,
                           z_dilate=0, rot_matrices=[np.eye(4)])
        parts[pid] = vp
        org = m.bounds[0]
        pls.append(SimpleNamespace(
            part_id=pid, orientation_idx=0,
            x=int(round(org[0] / CHECK_PITCH)),
            y=int(round(org[1] / CHECK_PITCH)),
            z=int(round(org[2] / CHECK_PITCH))))
    return int(check_separability_5dir(pls, parts).n_locked)


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-48 R11 SUREKLI Z-KOMPAKSIYON PROBU — deneme5 (K-44 223.5 replay)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k47b bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k47b bitti — K-48 basliyor")

    inst = _load("deneme5", PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=False)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"replay: h_voxel={hv:.1f} pitch={px} yerlesen={len(pls)}/{n_total}"
        f" ({(time.perf_counter() - t) / 60:.1f} dk)"
        + ("" if abs(hv - REF_VOXEL) < 1e-6 else f"  UYARI: ref {REF_VOXEL} degil!"))

    meshes = placed_meshes(pls, parts, px)
    h_mesh0 = max(float(m.bounds[1][2]) for m in meshes)
    log(f"mesh-gercek h (oncesi): {h_mesh0:.2f}  (voxel raporu {hv:.1f})")

    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, no_go_bounds=NOGO)
    log(f"R11: dusme toplam={res.telemetri['toplam_dusme_mm']:.1f}mm  "
        f"tasinan={res.n_moved}/{len(meshes)}  sweep={res.sweeps_used}  "
        f"h {res.height_before_mm:.2f} -> {res.height_mm:.2f}  "
        f"KAZANC={res.gain_mm:.2f}mm  ({(time.perf_counter() - t) / 60:.1f} dk)")

    shifted = apply_settle(meshes, res)
    rep = min_clearance(shifted, samples_per_mesh=6000)
    log(f"clearance(6000): {rep.min_mm:.3f}")

    t = time.perf_counter()
    kilit_pre = _kilit_5dir_meshes(meshes)
    kilit_post = _kilit_5dir_meshes(shifted)
    log(f"kilit re-check (margin-0 @{CHECK_PITCH}): pre={kilit_pre} post={kilit_post}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    go = (res.gain_mm > 0.5 and rep.min_mm >= 2.0 and kilit_post <= kilit_pre)
    log(f"HUKUM-VERISI: kazanc={res.gain_mm:.2f}mm | clear={rep.min_mm:.3f} | "
        f"kilit {kilit_pre}->{kilit_post} | esikler(>0.5 / >=2.0 / <=pre) -> "
        f"{'GO (uretim kablolamaya aday, eval-gate ile)' if go else 'NO-GO / NOTR'}")
    if go:
        out = _ROOT / "results" / f"deneme5_r11_{res.height_mm:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
