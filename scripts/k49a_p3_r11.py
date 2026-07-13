# -*- coding: utf-8 -*-
"""k49a_p3_r11.py — K-49a: plan3 + R11 surekli z-kompaksiyon (MANUEL-GECME probu).

Gerekce (2026-07-13, Eren: "plan3'te de gecebilir miyiz?"): p3 598.5 vs manuel
593 = +5.5mm — en dar acik. d5'te R11 mekanizmasi 7.76mm buldu (K-48 v1;
clearance fix'i K-48b'de). p3'un kuleli yapisinda voxel-sarma payi birikimli
-> R11 tek basina 593-alti verebilir. Parametreler K-48b ile ayni (pay 0.4,
samples 8000). GO esigi: mesh-gercek h < 593.0 VE clear(6000)>=2.0 VE
kilit(post) <= pre (ayni-metrik).
Zincir: k48b_r11_v2.log BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run k49a_p3_r11    SAF ASCII.
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
from scripts.eval_gate import _load_instance
from scripts.k48_r11_probe import _kilit_5dir_meshes
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k49a_p3_r11.log"
BEKLE = Path(__file__).parent / "k48b_r11_v2.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
MANUEL = 593.0
BEKLENEN_H = 598.5   # K-36 sampiyonu (replay dogrulamasi)


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-49a PLAN3 + R11 — manuel-gecme probu (ref 598.5 / manuel 593)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k48b bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k48b bitti — K-49a basliyor")

    inst = _load_instance("plan3")
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
        f" ({(time.perf_counter() - t) / 60:.1f} dk)"
        + ("" if abs(hv - BEKLENEN_H) < 1e-6 else f"  UYARI: != {BEKLENEN_H}"))

    meshes = placed_meshes(pls, parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    log(f"mesh-gercek h (oncesi): {h0:.2f}")
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=0.4,
                              samples_per_mesh=8000, no_go_bounds=NOGO)
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

    h_final = res.height_mm
    legal = (rep.min_mm >= 2.0 and kilit_post <= kilit_pre)
    log(f"HUKUM-VERISI: h={h_final:.2f} | clear={rep.min_mm:.3f} | "
        f"kilit {kilit_pre}->{kilit_post} | manuel {MANUEL} -> "
        + ("MANUEL GECILDI (p3)" if (legal and h_final < MANUEL)
           else ("legal-iyilesme" if (legal and h_final < h0) else "NO-GO/NOTR")))
    if legal and h_final < h0:
        out = _ROOT / "results" / f"plan3_r11_{h_final:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"STL: {out}")
        kaydet("plan3", "nfv", "derin@2.0+r11", h_final, len(pls), n_total,
               float(rep.min_mm), int(kilit_post), None,
               kosu_id="K-49a/r11", log_yolu="scripts/k49a_p3_r11.log",
               pitch=2.0, seed=42, instance=inst)
        log("telemetri v2 satiri yazildi")
    log("BITTI")


if __name__ == "__main__":
    main()
