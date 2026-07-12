# -*- coding: utf-8 -*-
"""k48b_r11_v2.py — K-48b: R11 v2 probu (orneklem-payi fix'i; d5).

K-48 v1 hukmu: kazanc 7.76mm + kilit 0->0 AMA clearance(6000)=1.591<2.0 —
orneklem-tabanli mesafe en yakin cifti kacirdi (continuous_settle risk notu).
v2 fix: pay_mm 0.1->0.4 + samples_per_mesh 4000->8000. Beklenti: kazancin
onemli kismi korunur, clearance >=2.0'a doner.
Zincir: k47c_d4_cert_dump.log BITTI olana kadar bekler (GPU/RAM sirasi).
Kosum: python -m scripts.detach_run k48b_r11_v2    SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import apply_settle, continuous_z_settle
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.ax24_kuyruk_335 import _load
from scripts.k48_r11_probe import _kilit_5dir_meshes
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k48b_r11_v2.log"
BEKLE = Path(__file__).parent / "k47c_d4_cert_dump.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
PAY_MM = 0.4
SAMPLES = 8000


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-48b R11 v2 — pay 0.4 + samples 8000 (v1: 7.76mm kazanc ama clear 1.591)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k47c bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k47c bitti — K-48b basliyor")

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
    log(f"replay: h_voxel={hv:.1f} yerlesen={len(pls)}/{n_total}"
        f" ({(time.perf_counter() - t) / 60:.1f} dk)")

    meshes = placed_meshes(pls, parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=PAY_MM,
                              samples_per_mesh=SAMPLES, no_go_bounds=NOGO)
    log(f"R11v2: tasinan={res.n_moved}/{len(meshes)} sweep={res.sweeps_used}"
        f"  h {h0:.2f} -> {res.height_mm:.2f}  KAZANC={res.gain_mm:.2f}mm"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    shifted = apply_settle(meshes, res)
    rep = min_clearance(shifted, samples_per_mesh=6000)
    log(f"clearance(6000): {rep.min_mm:.3f}")
    t = time.perf_counter()
    kilit_pre = _kilit_5dir_meshes(meshes)
    kilit_post = _kilit_5dir_meshes(shifted)
    log(f"kilit re-check: pre={kilit_pre} post={kilit_post}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    go = (res.gain_mm > 0.5 and rep.min_mm >= 2.0 and kilit_post <= kilit_pre)
    log(f"HUKUM-VERISI: kazanc={res.gain_mm:.2f}mm | clear={rep.min_mm:.3f} | "
        f"kilit {kilit_pre}->{kilit_post} -> {'GO' if go else 'NO-GO / NOTR'}")
    if go:
        h_final = res.height_mm
        out = _ROOT / "results" / f"deneme5_r11v2_{h_final:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"STL: {out}")
        kaydet("deneme5", "nfv", "ham@2.0+r11", h_final,
               len(pls), n_total, float(rep.min_mm), int(kilit_post),
               time.perf_counter() - t, kosu_id="K-48b/r11v2",
               log_yolu="scripts/k48b_r11_v2.log", pitch=2.0, seed=42,
               instance=inst)
        log("telemetri v2 satiri yazildi (kxx_telemetri)")
    log("BITTI")


if __name__ == "__main__":
    main()
