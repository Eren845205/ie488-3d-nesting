"""m3_selection_rule.py — Adım A: seçim kuralı GO/NO-GO.

Teşhis (M1+M2): cavity'nin duvarı SIRALAMA değil, SEÇİM kuralı. Mevcut kural
"en-derine at" (score=max(z_top,cur_max), z_top, z, y, x) → parça boşlukta GEVŞEK
durur, etrafı kullanılamaz, yüzey parçalanır. Magics'in farkı = best-fit /
maximal-contact: parçayı EN ÇOK TEMAS edecek (en az boşluk bırakacak) yere oturt.

Bu script aynı testbed'i (m2_prototype) sabit largest-first sırayla, FARKLI seçim
kurallarıyla decode eder. Order'ı sabitler (M2 order'ın önemsiz olduğunu kanıtladı)
→ izole olarak seçim kuralının etkisini ölçer.

KURALLAR:
  deepest   : mevcut cavity kuralı (kontrol)
  blb       : saf bottom-left-back (z_top, z, y, x) — guard'sız
  contact   : maximal-contact (parça yüzeyinin occupancy+zemin+duvara temas voxel
              sayısını MAKSIMİZE et; tie → düşük z_top)

GO: contact (veya blb) cavity-decode'u heightmap'in ALTINA indirirse → seçim kuralı
    ASIL lever, Adım B'ye (gerçek NFV + Plan2) yatır. NO-GO: sorun daha derin.
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
CAP = int(sys.argv[2]) if len(sys.argv) > 2 else 4000


def _contact_count(ob: OccupancyBin3D, orient, x, y, z) -> int:
    """Parça (x,y,z)'ye konunca occupancy + bin-sınırı ile temas eden yüzey voxel
    sayısı. Yüksek = sıkı oturma (az boşluk). Zemin (z==0) ve duvarlar da temas sayılır.
    """
    fw, fd, fh = orient.grid.shape
    g = orient.grid
    occ = ob.occupancy
    contact = 0
    # 6 yön; her yönde parça voxeli ile o yöndeki komşu voxel occupancy/sınır mı?
    # -z (alt): zemin (z==0) veya altta occupancy
    if z == 0:
        contact += int(g[:, :, 0].sum())
    else:
        contact += int((g[:, :, 0] & occ[x:x+fw, y:y+fd, z-1]).sum())
    # iç -z temaslar: parçanın kendi voxelleri arası değil, occupancy ile; parça katı
    # değilse iç boşluk komşuluğu occupancy olamaz → atla (ucuz proxy, dış yüzey yeter)
    # +z üst: üstte occupancy (nadir)
    ztop = z + fh
    if ztop < occ.shape[2]:
        contact += int((g[:, :, -1] & occ[x:x+fw, y:y+fd, ztop]).sum())
    # -x duvar / occupancy
    if x == 0:
        contact += int(g[0, :, :].sum())
    else:
        contact += int((g[0, :, :] & occ[x-1, y:y+fd, z:ztop]).sum())
    # +x
    if x + fw == ob.nx:
        contact += int(g[-1, :, :].sum())
    else:
        contact += int((g[-1, :, :] & occ[x+fw, y:y+fd, z:ztop]).sum())
    # -y
    if y == 0:
        contact += int(g[:, 0, :].sum())
    else:
        contact += int((g[:, 0, :] & occ[x:x+fw, y-1, z:ztop]).sum())
    # +y
    if y + fd == ob.ny:
        contact += int(g[:, -1, :].sum())
    else:
        contact += int((g[:, -1, :] & occ[x:x+fw, y+fd, z:ztop]).sum())
    return contact


def decode(parts, order, nx, ny, rule):
    pos = {id(p): i for i, p in enumerate(order)}
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH, cavity=True, cavity_cap=CAP)
    ordered = sorted(parts, key=lambda vp: pos[id(vp)])
    for part in ordered:
        eps = sorted(ob.extreme_points, key=lambda e: (e[2], e[1], e[0]))
        cur_max = ob.max_height_voxels()
        best_key = None
        best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if rule in ("deepest", "blb"):
                # monoton skor → ilk feasible (z,y,x sırasında) per-orient minimum
                for ep in eps:
                    ex, ey, ez = ep
                    if ob.is_feasible(orient, ex, ey, ez):
                        zt = ez + fh
                        if rule == "deepest":
                            key = (max(zt, cur_max), zt, ez, ey, ex, oi)
                        else:  # blb
                            key = (zt, ez, ey, ex, oi)
                        if best_key is None or key < best_key:
                            best_key, best = key, (ex, ey, ez, oi)
                        break
            else:  # contact — monoton değil, TÜM feasible EP taranır
                for ep in eps:
                    ex, ey, ez = ep
                    if ob.is_feasible(orient, ex, ey, ez):
                        zt = ez + fh
                        # envelope içinde kal (protrude cezası), sonra max temas, sonra alçak
                        c = _contact_count(ob, orient, ex, ey, ez)
                        key = (max(zt, cur_max), -c, zt, ez, ey, ex, oi)
                        if best_key is None or key < best_key:
                            best_key, best = key, (ex, ey, ez, oi)
        if best is None:
            fb = _drop_fallback(ob, part)
            (ex, ey, ez), oi = fb
            best = (ex, ey, ez, oi)
        ex, ey, ez, oi = best
        ob.place(part.orientations[oi], ex, ey, ez)
    return ob.height_mm()


def main():
    print("=" * 70)
    print(f"M3 SECIM KURALI GO/NO-GO  (pitch={PITCH}, cap={CAP})")
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
    print(f"[heightmap]  {hm:.1f} mm  ({time.perf_counter()-t:.1f}s)  <- yenilmesi gereken", flush=True)

    largest = sorted(parts, key=lambda vp: -vp.volume_voxels)
    for rule in ("deepest", "blb", "contact"):
        t = time.perf_counter()
        h = decode(parts, largest, nx, ny, rule)
        flag = "  *** heightmap'i GECTI ***" if h < hm - 0.5 else ""
        print(f"[{rule:8s}]  {h:.1f} mm  ({time.perf_counter()-t:.1f}s){flag}", flush=True)

    print("-" * 70)
    print("GO kosulu: 'contact' (veya 'blb') heightmap'in altina inerse seçim kuralı")
    print("ASIL lever -> Adim B (gercek NFV + Plan2). Aksi halde sorun daha derin.")
    print("=" * 70)


if __name__ == "__main__":
    main()
