"""c3_height_driver_deneme4.py — 264mm tavanini HANGI parcalar belirliyor? (teshis)

GERCEK plaka (325 = hoca 335-5mm kenar) + URETIM wall_aware heightmap yolu
(K-19, clearance margin=2/z2 = DURUST 264mm). Mevcut c3_height_driver.py NFV
decode'u (386 yolu) olcer; BU script uretimde KAZANAN heightmap sonucunu (264)
olcer -> dogru tavan teshisi (§6 meta-ders #11: stratejiden ONCE darbogazi olc).

Karar: tavani 2 dev ROBT plakasi mi, ASY canlar mi, dugme istifi mi belirliyor?
-> hangi kaldirac (odakli-rotasyon / K-24 zincir / A1) dogru hedef.

URETIME DOKUNMAZ — scripts/ only. ASCII.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

import src.nesting3d.coarse_to_fine as c2f
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.tuner import build_menu
from src.nesting3d.instances.format import _make_mesh
from scripts.clearance_decompose import make_deneme4

PLATE = 325.0
FINE = 0.5
SEED = 42
BUDGET = 25

_orig = c2f.clearance_to_voxels


def _patched(clearance_mm, pitch):
    # 264-config: fine margin=2/z2 (gercek plakada olculen dURUST clearance-1mm),
    # coarse uretim (1,1).
    if pitch <= 0.75:
        return 2, 2
    return 1, 1


def main():
    inst = make_deneme4()
    menu = {"dblf_only": build_menu()["dblf_only"]}
    c2f.clearance_to_voxels = _patched
    try:
        r = solve_coarse_to_fine(
            inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
            coarse_pitch=None, fine_pitch=FINE, budget=BUDGET, seed=SEED,
            menu=menu, skip_fine_angle=True, drop_cache=True, clearance_mm=1.0,
        )
    finally:
        c2f.clearance_to_voxels = _orig

    vp = r.fine_voxel_parts
    pitch = r.fine_pitch
    h = r.height_mm

    # bbox extents (tip basina bir kez)
    ext = {}
    for pp in inst.parts:
        if pp.name not in ext:
            e = sorted(round(float(x), 1) for x in _make_mesh(pp).extents)
            ext[pp.name] = e

    rec = []
    for p in r.placements:
        grid = vp[p.part_id].orientations[p.orientation_idx].grid
        fh = grid.shape[2]
        topz = (p.z + fh) * pitch
        rec.append((p.name, (p.z) * pitch, topz, p.orientation_idx, fh * pitch))

    print("=" * 84, flush=True)
    print(f"HEIGHT-DRIVER TESHISI — Deneme4 GERCEK plaka {PLATE:.0f} "
          f"(URETIM wall_aware 264-config) tavan={h:.1f}mm  yerlesen={r.n_placed}/588",
          flush=True)
    print("=" * 84, flush=True)

    rec.sort(key=lambda x: -x[2])
    print(f"  {'tepe-z':>7} {'taban-z':>7} {'yuk':>6} {'oi':>3}  {'bbox(mm)':>22}  parca", flush=True)
    print("-" * 84, flush=True)
    for name, botz, topz, oi, ph in rec[:20]:
        print(f"  {topz:>7.1f} {botz:>7.1f} {ph:>6.1f} {oi:>3}  "
              f"{str(ext.get(name, '?')):>22}  {name[:32]}", flush=True)
    print("-" * 84, flush=True)

    # tavan %90 ustu: hangi tipler, kac parca
    thr = h * 0.90
    top = [x for x in rec if x[2] >= thr]
    tc = Counter(x[0] for x in top)
    print(f"\n  TAVANIN %90'i ({thr:.1f}mm) USTUNDE {len(top)} parca, {len(tc)} tip:", flush=True)
    for t, c in tc.most_common():
        tmax = max(x[2] for x in top if x[0] == t)
        print(f"     x{c:>3}  tepe-max={tmax:>7.1f}  bbox={ext.get(t)}  {t[:40]}", flush=True)

    # TUM tipler global max tepe-z (hangi tip en yukari cikiyor)
    allc = {}
    for name, botz, topz, oi, ph in rec:
        if name not in allc or topz > allc[name]:
            allc[name] = topz
    print(f"\n  TUM 13 TIP — global max tepe-z (sirali):", flush=True)
    for t, mz in sorted(allc.items(), key=lambda kv: -kv[1]):
        cnt = sum(1 for x in rec if x[0] == t)
        print(f"     tepe-max={mz:>7.1f}  x{cnt:<4} bbox={str(ext.get(t)):>22}  {t[:36]}", flush=True)
    print("=" * 84, flush=True)
    print("BITTI", flush=True)


if __name__ == "__main__":
    main()
