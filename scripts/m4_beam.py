"""m4_beam.py — Adım C1: BEAM SEARCH GO/NO-GO (cavity miyopisini kır).

Teşhis (M1+M2+M3): tek-geçiş greedy constructive cavity ÇIKMAZ — sıra (M2),
seçim kuralı (M3), greedy (M1) hiçbiri 300'ü kımıldatmadı. Kök neden MİYOPİ:
erken parça boşluğa gevşek asılıyor, geç parçalar yükseğe çıkıyor; lokal hiçbir
düzeltme işe yaramıyor çünkü hata zaten yapılmış oluyor.

Beam search = greedy'nin genelleştirmesi (B=1 greedy). Her adımda B kısmi-çözüm
taşır; her durumu sıradaki parçanın TOP-M alternatif yerleşimiyle dallandırır,
B×M aday arasından en iyi B'yi tutar. Erken kararı tek dala hapsetmediği için
"gevşek asma" tuzağından çıkış şansı verir.

KONTROL: B=1, M=1 → mevcut greedy (300 vermeli, sağlaması bu).
GO: B>=3 testbed'de 300'ü heightmap'in (216) ALTINA indirirse → cavity mekanizması
    kurtarılabilir, C2/C3'e (LNS/VNS) yatırım anlamlı. NO-GO: greedy-constructive
    ailesi tümden ölü; kalan tek yol C3 (Magics'i sıfırdan = ay-mertebesi).

Beam aday skoru (hangi M dal): cavity (max(z_top,cur_max), z_top, z, y, x) — greedy-1,
greedy-2,... = en iyi M alternatif. Beam tutma skoru: (max_z_used, column_top std)
— düşük zarf + DÜZ yüzey (gelecek parçalar için iyi taban).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19

QTY = {
    "PO-TR154979-17747_P282335": 3,
    "part284676_06B23B8_model_r_0": 4,
    "part282114_07D4114_model_r_0": 3,
    "PO-TR154989-17667_P282407": 4,
    "PO-TR156122-17810_P284641": 4,
    "part282115_07D4113": 3,
    "PO-TR154979-17747_P282334": 3,
}

PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
N_OR = 4
MARGIN = 1
CAP = 4000


def clone(ob: OccupancyBin3D) -> OccupancyBin3D:
    nb = OccupancyBin3D(ob.nx, ob.ny, nz_limit=ob.occupancy.shape[2],
                        pitch=ob.pitch, cavity=ob.cavity, cavity_cap=ob.cavity_cap)
    nb.occupancy = ob.occupancy.copy()
    nb.column_top = ob.column_top.copy()
    nb.extreme_points = set(ob.extreme_points)
    nb.placed_voxels = ob.placed_voxels
    nb._max_z_used = ob._max_z_used
    return nb


def part_candidates(ob: OccupancyBin3D, part, top_m: int):
    """Bu parça için en iyi top_m (score, ep, oi) yerleşim adayı (cavity skoru)."""
    eps = sorted(ob.extreme_points, key=lambda e: (e[2], e[1], e[0]))
    cur_max = ob.max_height_voxels() if ob.cavity else 0
    out = []
    for oi, orient in enumerate(part.orientations):
        fw, fd, fh = orient.grid.shape
        # ilk-feasible bu orient için min (monoton skor) → orient başına 1 aday;
        # M çeşitliliği orientation'lardan + (gerekirse) sonraki feasible'lardan gelir.
        found = 0
        for ep in eps:
            ex, ey, ez = ep
            if ob.is_feasible(orient, ex, ey, ez):
                zt = ez + fh
                score = (max(zt, cur_max), zt, ez, ey, ex)
                out.append((score, ep, oi))
                found += 1
                if found >= top_m:  # bu orient için birkaç alternatif al
                    break
    out.sort(key=lambda t: t[0])
    return out[:top_m]


def beam_decode(parts, order, nx, ny, B, M):
    pos = {id(p): i for i, p in enumerate(order)}
    ordered = sorted(parts, key=lambda vp: pos[id(vp)])
    start = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH, cavity=True, cavity_cap=CAP)
    beams = [start]  # liste of OccupancyBin3D
    for part in ordered:
        expanded = []  # (beam_score, bin)
        for ob in beams:
            cands = part_candidates(ob, part, M)
            if not cands:
                fb = _drop_fallback(ob, part)
                (ex, ey, ez), oi = fb
                cands = [((0,), (ex, ey, ez), oi)]
            for _score, ep, oi in cands:
                nb = clone(ob)
                nb.place(part.orientations[oi], ep[0], ep[1], ep[2])
                bscore = (nb._max_z_used, float(nb.column_top.std()))
                expanded.append((bscore, nb))
        expanded.sort(key=lambda t: t[0])
        beams = [nb for _, nb in expanded[:B]]
    return min(ob.height_mm() for ob in beams)


def main():
    print("=" * 70)
    print(f"M4 BEAM SEARCH GO/NO-GO  (pitch={PITCH}, cap={CAP})")
    print("=" * 70, flush=True)
    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"testbed: {len(parts)} parca, taban {nx}x{ny}", flush=True)

    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[heightmap]      {hm:.1f} mm  ({time.perf_counter()-t:.1f}s)  <- yenilmesi gereken", flush=True)

    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    configs = [(1, 1), (3, 3), (5, 4), (8, 5)]
    for B, M in configs:
        t = time.perf_counter()
        h = beam_decode(parts, largest, nx, ny, B, M)
        flag = ""
        if B == 1 and M == 1:
            flag = "  (KONTROL: greedy ~300 olmali)"
        elif h < hm - 0.5:
            flag = "  *** heightmap'i GECTI -> GO ***"
        print(f"[beam B={B} M={M}]  {h:.1f} mm  ({time.perf_counter()-t:.1f}s){flag}", flush=True)

    print("-" * 70)
    print("GO: B>=3 heightmap'in altina inerse -> miyopi kirildi, C2/C3'e yatir.")
    print("NO-GO: greedy-constructive ailesi olu; kalan tek yol C3 (Magics sifirdan).")
    print("=" * 70)


if __name__ == "__main__":
    main()
