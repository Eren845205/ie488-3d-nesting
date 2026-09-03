# -*- coding: utf-8 -*-
"""k57_rot_profil.py — rot_kabul kaleminin ICI (plan2 315s): cProfile.

Anatomi: rot_kabul solve-ici 569s (p2 315 / p3 121 / d4 133) — cift-rot fix
sonrasi kapida rot BIR kez kosuyor ama plan2'nin 315s'i hala buyuk. Bu teshis
plan2 sahnesini BIR kez uretir (solve_nfv_kalite, rot/r11 KAPALI — yalniz
layout), meshes'i D'ye pickle'lar (tekrar-profil bedava olsun), sonra
kilit_rot_meshes'i cProfile ile kosar: sure re-voxelize'da mi, 5-yon blocks
kurulumunda mi (n^2), rot aci-denemelerinde mi, erode'da mi?

Kosum: python -m scripts.detach_run k57_rot_profil    SAF ASCII.
Cikti: scripts/k57_rot_profil.log + results/k57_rot_profil_top.txt
       + D cache: results/k57_plan2_meshes.pkl
"""
from __future__ import annotations

import cProfile
import io
import pickle
import pstats
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_rot_profil.log"
PKL = _ROOT / "results" / "k57_plan2_meshes.pkl"
TOP = _ROOT / "results" / "k57_rot_profil_top.txt"


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _sahne():
    """plan2 uretim layout'unun meshes listesi (pickle-cache'li).

    GUVENLIK NOTU: pickle YALNIZ bu scriptin kendi urettigi lokal teshis
    cache'i icin (ayni makine, ayni kullanici; dis/untrusted kaynak YOK,
    uretim yolu degil). trimesh nesneleri icin JSON pratik degil."""
    if PKL.exists():
        log(f"sahne cache'ten: {PKL}")
        return pickle.loads(PKL.read_bytes())
    from scripts.eval_gate import NOGO_STD, PLATE_STD, _load_instance
    from src.nesting3d.export_stl import placed_meshes
    from src.nesting3d.nfv_solve import solve_nfv_kalite
    inst = _load_instance("plan2")
    t = time.perf_counter()
    # rot_kabul KAPALI -> ham kilitli kalir ama layout AYNI (guard'a gecmesin
    # diye rot_kabul=True'da sahne degismezdi; kapali+guard'li secim farkli
    # OLABILIR -> uretim paritesi icin ACIK kosuyoruz, sure oderiz)
    res, tel = solve_nfv_kalite(
        inst, plate_w_mm=PLATE_STD[0], plate_d_mm=PLATE_STD[1],
        clearance_mm=2.0, no_go_bounds=NOGO_STD, quality="fast", seed=42,
        r11=False, rot_kabul="auto")
    log(f"solve: {time.perf_counter() - t:.0f}s  h={res.height_mm}"
        f"  secilen={tel.get('secilen')}"
        f"  rot_kabul_tel_sure={((tel.get('rot_kabul') or {}).get('sure_s'))}")
    meshes = placed_meshes(list(res.placements), res.fine_voxel_parts,
                           float(res.fine_pitch))
    PKL.write_bytes(pickle.dumps(meshes, protocol=pickle.HIGHEST_PROTOCOL))
    log(f"sahne pickle'landi: {PKL} ({PKL.stat().st_size // 2**20}MB,"
        f" {len(meshes)} mesh)")
    return meshes


def main():
    LOG.write_text("", encoding="utf-8")
    from src.nesting3d.continuous_settle import kilit_rot_meshes
    log("K-57 ROT PROFIL (plan2; kilit_rot_meshes cProfile)")
    meshes = _sahne()

    t = time.perf_counter()
    pr = cProfile.Profile()
    pr.enable()
    rep = kilit_rot_meshes(meshes)
    pr.disable()
    dt = time.perf_counter() - t
    certs = getattr(rep, "certificates", None) or {}
    log(f"kilit_rot_meshes: {dt:.1f}s  n_locked={rep.n_locked}"
        f"  cert={len(certs)}")
    # bit-ozdeslik kaniti icin denetim detayi (memo oncesi/sonrasi kiyas)
    log(f"  removable_order_n={len(rep.removable_order)}"
        f"  order_ilk10={rep.removable_order[:10]}")
    for pid, c in sorted(certs.items()):
        log(f"  cert {pid}: eksen={c.eksen} aci={c.aci_deg:.2f}"
            f" yon={c.yon} lift={c.lift_vox}")

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(25)
    TOP.write_text(s.getvalue(), encoding="utf-8")
    # log'a ozet (ilk 15 anlamli satir)
    for line in s.getvalue().splitlines():
        ln = line.rstrip()
        if ln and ("cumtime" in ln or "/" in ln or ".py" in ln):
            log("  " + ln[:150])
    log(f"TOP: {TOP}")
    log("BITTI")


if __name__ == "__main__":
    main()
