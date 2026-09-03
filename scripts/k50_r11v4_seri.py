# -*- coding: utf-8 -*-
"""k50_r11v4_seri.py — K-50: R11 v4'un COK-SET olcumu (d5 -> d4 -> p2, seri).

Gerekce (A5 dagilim ilkesi + uretim terfisi on-sarti): R11 v4 p3'te kanitlandi
(K-49d: 577.62, manuel −%2.6). Uretime girmesi icin TUM dev-set dagilimi
olculmeli. Tek proses SIRAYLA kosar (GPU/RAM cakismasi yok, zincir kapisi
gereksiz). Her set: sampiyon-recete replay + v4 (pay 0.15 + dogrula-ve-rafine)
+ kapilar (clear>=2.0 rafineden; kilit post<=pre) + STL + telemetri v2.

Setler/replay parametreleri (sampiyon kosularin birebir tekrari):
  d5: ham@2.0 (K-44, 223.5) — kilit taban 0
  d4: ham@2.0 (K-46, 231.5) — 5-yon kilit taban ~363 (post<=pre yeter; (b+c)
      legalitesi K-46'daki gibi rot-sokum sertifikasina dayanir, serh dusulur)
  p2: guard@2.0 (K-41, 544.5) — kilit taban 0
Kosum: python -m scripts.detach_run k50_r11v4_seri    SAF ASCII.
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
from scripts.ax24_kuyruk_335 import _load
from scripts.k48_r11_probe import _kilit_5dir_meshes
from scripts.kxx_telemetri import kaydet

LOG = Path(__file__).parent / "k50_r11v4_seri.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))

SETLER = [
    # (ad, yukleyici, exit_guard, beklenen_voxel_h, manuel, recete_adi)
    ("deneme5", lambda: _load("deneme5", PLATE), False, 223.5, 209.0, "ham@2.0+r11v4"),
    ("deneme4", lambda: _load_instance("deneme4"), False, 231.5, 250.24, "ham@2.0+r11v4"),
    ("plan2",   lambda: _load_instance("plan2"),   True,  544.5, 492.39, "guard@2.0+r11v4"),
]


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def bir_set(ad, yukle, guard, beklenen, manuel, recete):
    log(f"== {ad} (guard={guard}, beklenen replay {beklenen}, manuel {manuel}) ==")
    inst = yukle()
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                  quality="max", seed=42, clearance_mm=2.0,
                  no_go_bounds=NOGO, fine_pitch=2.0, exit_guard=guard)
    px = float(r.fine_pitch)
    parts = r.fine_voxel_parts
    pls = list(r.placements)
    hv = max((p.z + parts[p.part_id].orientations[p.orientation_idx]
              .grid.shape[2]) for p in pls) * px
    log(f"[{ad}] replay: h_voxel={hv:.1f} yerlesen={len(pls)}/{n_total}"
        f" ({(time.perf_counter() - t) / 60:.1f} dk)"
        + ("" if abs(hv - beklenen) < 1e-6 else f"  UYARI: beklenen {beklenen}"))

    meshes = placed_meshes(pls, parts, px)
    h0 = max(float(m.bounds[1][2]) for m in meshes)
    t = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, pay_mm=0.15,
                              samples_per_mesh=12000, no_go_bounds=NOGO)
    log(f"[{ad}] R11 agresif: tasinan={res.n_moved}/{len(meshes)}  h {h0:.2f} -> "
        f"{res.height_mm:.2f}  ({(time.perf_counter() - t) / 60:.1f} dk)")

    t = time.perf_counter()
    dz4, rapor4, tur4, ok4 = dogrula_ve_rafine(meshes, res.dz,
                                               samples_per_mesh=6000)
    if not ok4:
        log(f"[{ad}] rafine YAKINSAMADI ({tur4} tur) — set NO-GO, sampiyon korunur")
        return
    shifted = apply_dz(meshes, dz4)
    h4 = max(float(m.bounds[1][2]) for m in shifted)
    log(f"[{ad}] rafine: {tur4} tur  clear={rapor4.min_mm:.3f}  h={h4:.2f}"
        f"  ({(time.perf_counter() - t) / 60:.1f} dk)")

    t = time.perf_counter()
    try:
        kilit_pre = _kilit_5dir_meshes(meshes)
        kilit_post = _kilit_5dir_meshes(shifted)
        log(f"[{ad}] kilit re-check: pre={kilit_pre} post={kilit_post}"
            f"  ({(time.perf_counter() - t) / 60:.1f} dk)")
    except MemoryError as e:
        kilit_pre = kilit_post = None
        log(f"[{ad}] kilit re-check MemoryError ({e}) — olculemedi (serh)")

    legal = (rapor4.min_mm >= 2.0 and kilit_pre is not None
             and kilit_post <= kilit_pre)
    kazanc = h0 - h4
    log(f"[{ad}] HUKUM-VERISI: h={h4:.2f} (kazanc {kazanc:.2f}) | "
        f"clear={rapor4.min_mm:.3f} | kilit {kilit_pre}->{kilit_post} | "
        f"manuel {manuel} -> "
        + ("MANUEL GECILDI" if (legal and h4 < manuel)
           else ("legal-iyilesme" if (legal and kazanc > 0.01) else "NO-GO/NOTR")))
    if legal and kazanc > 0.01:
        out = _ROOT / "results" / f"{ad}_r11v4_{h4:.1f}mm.stl"
        trimesh.util.concatenate(shifted).export(out)
        log(f"[{ad}] STL: {out}")
        kaydet(ad, "nfv", recete, h4, len(pls), n_total,
               float(rapor4.min_mm), int(kilit_post), None,
               kosu_id=f"K-50/{ad}", log_yolu="scripts/k50_r11v4_seri.log",
               pitch=2.0, seed=42, instance=inst)
        log(f"[{ad}] telemetri v2 satiri yazildi")


def main():
    LOG.write_text("", encoding="utf-8")
    log("K-50 R11 v4 COK-SET SERISI — d5 -> d4 -> p2 (A5 dagilim; terfi on-sarti)")
    for ad, yukle, guard, beklenen, manuel, recete in SETLER:
        try:
            bir_set(ad, yukle, guard, beklenen, manuel, recete)
        except Exception as e:
            log(f"[{ad}] EXCEPTION: {type(e).__name__}: {e} — sonraki sete gecilir")
    log("BITTI")


if __name__ == "__main__":
    main()
