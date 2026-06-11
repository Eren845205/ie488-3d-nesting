"""probe_nesting.py — plaka-plaka geçişme tanısı + optimal kule alt sınırı.

Soru 1: iki plaka (n3/n6/n7/n8, aynı VEYA çapraz tip) üst üste konduğunda
voxel modelde ne kadar İÇ İÇE geçebiliyor?
Soru 2: 12 plakanın (4 tip x 3) istif sırası optimize edilirse kule en az
kaç mm olur?  335 tabana iki plaka yan yana sığmadığından (Helly: tüm
çiftler x'te ve y'de kesişir -> ortak kolon var) bu kule, TÜM yerleşimin
alt sınırıdır — ≤170 hedefinin fizibilite testi.

Kullanım: python -m scripts.probe_nesting [pitch] [margin]
"""

import sys
from functools import lru_cache

import trimesh

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_PLATES
from src.nesting3d.voxelize import voxelize_part

PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
MARGIN = int(sys.argv[2]) if len(sys.argv) > 2 else 1
ALLOWED = (0, 1, 4, 5)  # NUMUNE_ORIENTATIONS plaka pozları
ZC = 1 if MARGIN else 0
PLATES = sorted(NUMUNE_PLATES)


def load_part(name: str):
    mesh = trimesh.load(str(NUMUNE_DIR / f"{name[1:]}.stl"), force="mesh")
    mesh.apply_translation(-mesh.bounds[0])
    return voxelize_part(name, mesh, PITCH, n_orientations=8, margin=MARGIN,
                         method="slice", allowed_orientations=ALLOWED)


import numpy as np

FULL_OVERLAP = "--free" not in sys.argv  # default: tam-bindirme şartı


def best_drop(b: Bin3D, vp, base_fp=None) -> tuple:
    """En düşük z veren (poz, z).

    FULL_OVERLAP modunda üst plakanın footprint'inin >= %85'i alttaki
    plakanın footprint'iyle (base_fp = (fw0, fh0), (0,0)'da) bindirmek
    zorunda — köşe-kaçışı artefaktını (plaka kenara ilişip 'derin geçişme'
    gibi görünmesi) eler; gerçek çıkıntı->delik eşleşmesini ölçer.
    """
    best = None
    for oi, o in enumerate(vp.orientations):
        Z = b.drop_map(o)
        if Z is None:
            continue
        if FULL_OVERLAP and base_fp is not None:
            fw0, fh0 = base_fp
            fw, fh = o.filled.shape
            xs = np.arange(Z.shape[0])[:, None]
            ys = np.arange(Z.shape[1])[None, :]
            ox = np.minimum(xs + fw, fw0) - np.maximum(xs, 0)
            oy = np.minimum(ys + fh, fh0) - np.maximum(ys, 0)
            mask = (np.clip(ox, 0, None) * np.clip(oy, 0, None)
                    >= 0.85 * fw * fh)
            if not mask.any():
                continue
            z = int(Z[mask].min())
        else:
            z = int(Z.min())
        if best is None or z < best[1]:
            best = (oi, z)
    return best


def main() -> None:
    print(f"pitch {PITCH} mm, margin {MARGIN} — plaka geçişme matrisi (mm)")
    parts = {n: load_part(n) for n in PLATES}
    thick = {}   # tek plaka tepe yüksekliği (voxel)
    nest = {}    # nest[(alt, üst)] = geçişme (voxel)

    for a in PLATES:
        b = Bin3D(335.0, 335.0, PITCH, z_clearance=ZC)
        b.place(parts[a], 0, 0, 0, 0)
        thick[a] = b.max_height_voxels()
        fp0 = parts[a].orientations[0].filled.shape
        for u in PLATES:
            res = best_drop(b, parts[u], base_fp=fp0)
            nest[(a, u)] = thick[a] + ZC - res[1] if res else 0

    hdr = "        " + "".join(f"{u:>8}" for u in PLATES)
    print(hdr + "   (satır=alt, sütun=üst plaka)")
    for a in PLATES:
        row = "".join(f"{nest[(a, u)] * PITCH:8.1f}" for u in PLATES)
        print(f"  {a:>4}  {row}   kalınlık {thick[a] * PITCH:.1f}")

    # 12'li kule DP: durum = (kalan adetler, son tip) -> max toplam geçişme.
    # Heightmap istifinde üst yüzeyi son plaka domine eder -> Markov yaklaşımı.
    @lru_cache(maxsize=None)
    def dp(counts: tuple, last: int) -> int:
        if sum(counts) == 0:
            return 0
        best_n = -1
        for t, c in enumerate(counts):
            if c == 0:
                continue
            nxt = tuple(c - 1 if i == t else v for i, v in enumerate(counts))
            gain = nest[(PLATES[last], PLATES[t])] if last >= 0 else 0
            best_n = max(best_n, gain + dp(nxt, t))
        return best_n

    total_thick = sum(3 * thick[n] for n in PLATES)
    best_nest = dp((3, 3, 3, 3), -1)
    tower_vox = total_thick + 11 * ZC - best_nest

    # optimal sırayı geri-izle (implementasyona girecek)
    seq, counts, last = [], (3, 3, 3, 3), -1
    while sum(counts):
        for t, c in enumerate(counts):
            if c == 0:
                continue
            nxt = tuple(c - 1 if i == t else v for i, v in enumerate(counts))
            gain = nest[(PLATES[last], PLATES[t])] if last >= 0 else 0
            if gain + dp(nxt, t) == dp(counts, last):
                seq.append(PLATES[t])
                counts, last = nxt, t
                break
    print(f"  optimal istif sırası  : {' -> '.join(seq)}")
    print(f"\n  12 plaka ham kalınlık : {total_thick * PITCH:6.1f} mm")
    print(f"  z_clearance (11 ara)  : {11 * ZC * PITCH:6.1f} mm")
    print(f"  optimal geçişme (DP)  : {best_nest * PITCH:6.1f} mm")
    print(f"  EN İYİ KULE (alt sınır): {tower_vox * PITCH:6.1f} mm "
          f"{'<= 170 MÜMKÜN' if tower_vox * PITCH <= 170 else '> 170 -> hedef bu modelde İMKÂNSIZ'}")


if __name__ == "__main__":
    main()
