# -*- coding: utf-8 -*-
"""k49d_p3_r11_rafine.py — K-49d: plan3 R11 v4 (dogrula-ve-rafine, KESIN oturma).

Eren'in itirazi (2026-07-13): "3.2 cok ama — optimum sonucu vermez." Hakli:
pay tamponu saf kalite kaybi. v4: kucuk payla (0.15) agresif kompakt +
dogrula_ve_rafine dongusuyle ihlalci ciftler milimetrik geri kaldirilir ->
tam 2.00x'e oturur, pay kaybi sifira iner.
Zincir: k49c_p3_r11_pay.log BITTI olana kadar bekler (K-49c payli surumun
kiyas cizgisi; v4 ondan alcak veya esit olmali).
Kosum: python -m scripts.detach_run k49d_p3_r11_rafine    SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.clearance import min_clearance
from src.nesting3d.continuous_settle import (
    apply_dz, continuous_z_settle, dogrula_ve_rafine)
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.nfv_solve import solve_nfv
from scripts.eval_gate import _load_instance
from scripts.k48_r11_probe import _kilit_5dir_meshes
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k49d_p3_r11_rafine.log"
BEKLE = Path(__file__).parent / "k49c_p3_r11_pay.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))
MANUEL = 593.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-49d PLAN3 R11 v4 — dogrula-ve-rafine (pay 0.15 + kesin oturma; manuel 593)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1].endswith("BITTI"):
            break
        if tur % 10 == 0:
            log(f"k49c bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("k49c bitti — K-49d basliyor")

    inst = _load_instance("plan3")
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=False)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    log(f"replay: yerlesen={len(pls)}/{n_total} ({(time.perf_counter() - t) / 60:.1f} dk)")

    meshes = placed_meshes(pls, parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=0.15,
                              samples_per_mesh=12000, no_go_bounds=NOGO)
    log(f"R11 agresif: tasinan={res.n_moved}/{len(meshes)}  h {h0:.2f} -> "
        f"{res.height_mm:.2f}  ({(time.perf_counter() - t) / 60:.1f} dk)")

    t = time.perf_counter()
    dz4, rapor4, tur4, ok4 = dogrula_ve_rafine(meshes, res.dz,
                                               samples_per_mesh=6000)
    if not ok4:
        log(f"rafine YAKINSAMADI ({tur4} tur, son clear="
            f"{rapor4.min_mm if rapor4 else '?'}) — v4 NO-GO, v3 sonucu gecerli")
        log("BITTI")
        return
    shifted = apply_dz(meshes, dz4)
    h4 = max(float(m.bounds[1][2]) for m in shifted)
    log(f"rafine: {tur4} tur  clear={rapor4.min_mm:.3f}  h={h4:.2f}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    t = time.perf_counter()
    try:
        kilit_pre = _kilit_5dir_meshes(meshes)
        kilit_post = _kilit_5dir_meshes(shifted)
        log(f"kilit re-check: pre={kilit_pre} post={kilit_post}"
            f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    except MemoryError as e:
        kilit_pre = kilit_post = None
        log(f"kilit re-check MemoryError ({e}) — olculemedi (serh)")

    legal = (rapor4.min_mm >= 2.0 and kilit_pre is not None
             and kilit_post <= kilit_pre)
    log(f"HUKUM-VERISI: h={h4:.2f} | clear={rapor4.min_mm:.3f} | "
        f"kilit {kilit_pre}->{kilit_post} | manuel {MANUEL} -> "
        + ("MANUEL GECILDI (p3)" if (legal and h4 < MANUEL)
           else ("legal-iyilesme" if (legal and h4 < h0) else "NO-GO/NOTR")))
    if legal and h4 < h0:
        out = _ROOT / "results" / f"plan3_r11d_{h4:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"STL: {out}")
        kaydet("plan3", "nfv", "derin@2.0+r11v4", h4, len(pls), n_total,
               float(rapor4.min_mm), int(kilit_post), None,
               kosu_id="K-49d/r11v4", log_yolu="scripts/k49d_p3_r11_rafine.log",
               pitch=2.0, seed=42, instance=inst)
        log("telemetri v2 satiri yazildi")
    log("BITTI")


if __name__ == "__main__":
    main()
