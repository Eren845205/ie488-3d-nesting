# -*- coding: utf-8 -*-
"""plan3_fine_arama_smoke.py — plan3_fine_arama cekirdek makinesini HIZLI dogrula.

Amac: 50 dk'lik fine-angle champion cozumune GEREK KALMADAN, prototipin yerel
arama + legal-dogrulama + STL-yazma yolunu kucuk bir instance uzerinde saniyeler
icinde kosarak DOGRU calistigini kanitla (cevre-baginsiz). SAF ASCII.

Kosum: python -m scripts.plan3_fine_arama_smoke
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

import trimesh

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.coarse_to_fine import solve_coarse_to_fine, clearance_to_voxels
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
import scripts.plan3_fine_arama as P


def _boxes():
    specs = {"a": (30, 20, 15), "b": (25, 25, 25), "c": (40, 15, 10),
             "d": (18, 18, 30)}
    stl_map = {k: trimesh.creation.box(extents=v).export(file_type="stl")
               for k, v in specs.items()}
    qty = {"a": 3, "b": 3, "c": 3, "d": 3}
    return stl_map, qty


def main():
    print("=" * 70)
    print("SMOKE: plan3_fine_arama cekirdek makinesi (kucuk instance)")
    print("=" * 70, flush=True)
    stl_map, qty = _boxes()
    plate = (120.0, 120.0)
    res = build_instance_from_order(
        stl_map, qty, container_w_mm=plate[0], container_d_mm=plate[1],
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_smoke_fine")
    inst = res.instance
    n_total = sum(int(p.qty) for p in inst.parts)
    pitch = suggest_pitch(inst, wall_aware=False)
    print(f"instance: {len(inst.parts)} tip, n={n_total}, pitch={pitch:.3f}, "
          f"plaka={plate}", flush=True)

    # UCUZ champion (fine_angle KAPALI -> saniyeler)
    t = time.perf_counter()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=plate[0], plate_d_mm=plate[1],
        coarse_pitch=None, fine_pitch=pitch, budget=20, seed=13,
        n_orientations=8, clearance_mm=1.0, fine_angle_window=0.0)
    _fm, fine_zc = clearance_to_voxels(1.0, pitch)
    print(f"champion(ucuz): h={r.height_mm:.2f}mm  n_placed={r.n_placed}  "
          f"fine_zc={fine_zc}  ({time.perf_counter() - t:.1f}s)", flush=True)

    # cekirdek fonksiyonlari plan3_fine_arama'dan kullan (PLATE'i gecici ayarla)
    P.PLATE = plate
    P.CLEARANCE_MM = 1.0

    # anchor: yeniden-yerlesim kazanani birebir uretmeli
    order0 = [pl.part_id for pl in r.placements]
    orient0 = {pl.part_id: int(pl.orientation_idx) for pl in r.placements}
    b0, pls0 = P._place(order0, orient0, r.fine_voxel_parts,
                        plate[0], plate[1], pitch, fine_zc)
    anchor_ok = abs(b0.max_height_mm() - r.height_mm) < 1e-6
    print(f"[anchor] yeniden-yerlesim h={b0.max_height_mm():.2f}mm  "
          f"birebir={'EVET' if anchor_ok else 'HAYIR'}", flush=True)
    assert anchor_ok, "anchor birebir uretilemedi — makine hatasi"

    # kisa yerel arama (10 sn)
    (best_order, best_orient, best_bin, best_pls,
     checkpoints, parts_by_id) = P.local_search(
        r, n_total, pitch, fine_zc, seed=13, budget_s=10.0)
    print(f"[arama] baslangic {r.height_mm:.2f}mm -> en_iyi "
          f"{best_bin.max_height_mm():.2f}mm  kontrol-noktasi={len(checkpoints)}",
          flush=True)

    # legal dogrulama + STL
    from src.nesting3d.export_stl import placed_meshes
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.accessibility import check_placements
    from scripts.eval_gate import legal_of
    meshes = placed_meshes(best_pls, parts_by_id, pitch)
    rep = min_clearance(meshes)
    acc = check_placements(best_pls, parts_by_id)
    legal, reason = legal_of(best_bin.max_height_mm(), len(best_pls), n_total,
                             float(rep.min_mm), int(acc.n_locked), clearance_req=1.0)
    print(f"[legal] {legal if legal is not None else 'INVALID(' + reason + ')'}  "
          f"clear={rep.min_mm:.3f}  kilit={acc.n_locked}  "
          f"yerlesim={len(best_pls)}/{n_total}", flush=True)
    out = _ROOT / "results" / "plan3_fine_arama" / "smoke_best.stl"
    out.parent.mkdir(parents=True, exist_ok=True)
    trimesh.util.concatenate(meshes).export(str(out))
    print(f"[STL] yazildi: {out} ({out.stat().st_size / 1e3:.0f}KB)", flush=True)
    print("SMOKE OK — cekirdek makine (anchor+arama+legal+STL) calisiyor.")


if __name__ == "__main__":
    main()
