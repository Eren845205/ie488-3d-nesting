"""c3_height_driver_numune.py — NUMUNE 180mm tavanini HANGI parcalar belirliyor? (teshis).

Plan2'de tavan=buyuk levhalar (rotasyona kapali). Numune (8 tip, hedef 170mm) icin SA-surekli
rotasyona girmeden ONCE meta-ders #11: darbogazi OLC. Tavan dondurulebilir tipte mi yoksa
zorunlu-istif buyuk parca mi?

Baz n=8 NFV-greedy decode + her parca tepe-z (mm). ASCII. URETIME DOKUNMAZ.
Kullanim: python scripts/c3_height_driver_numune.py
"""
from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.models import model_set
from src.nesting3d.voxelize import expand_quantities
from scripts.c3_height_driver import decode_record

PITCH, PLATE, MARGIN = 2.0, 335.0, 1


def main():
    nx = int(PLATE // PITCH)
    ms = model_set("numune")
    parts = expand_quantities(ms, PITCH, n_orientations=8, margin=MARGIN, method="slice")
    # bbox bilgisi (name -> sorted extents)
    ext = {}
    for entry in ms:
        name, mesh = entry[0], entry[1]
        ext[name] = sorted(round(float(x), 0) for x in mesh.extents)

    h, rec = decode_record(parts, nx, nx)
    print("=" * 72)
    print(f"HEIGHT-DRIVER TESHISI — NUMUNE n=8 — tavan={h:.1f}mm (hedef 170)")
    print("=" * 72)
    rec.sort(key=lambda r: -r[1])
    print(f"  {'tepe-z(mm)':>10}  {'oi':>3}  {'bbox(mm)':>18}  parca")
    print("-" * 72)
    for name, topz, oi in rec[:15]:
        print(f"  {topz:>10.1f}  {oi:>3}  {str(ext.get(name,'?')):>18}  {name[:30]}")
    print("-" * 72)
    thr = h * 0.95
    top = [r for r in rec if r[1] >= thr]
    tipler = sorted(set(r[0] for r in top))
    print(f"  tavanin %95'i ({thr:.0f}mm) ustunde {len(top)} parca, {len(tipler)} tip:")
    for t in tipler:
        cnt = sum(1 for r in top if r[0] == t)
        e = ext.get(t)
        oran = (e[2] / max(e[0], 1e-9)) if e else 0
        print(f"     x{cnt:>3}  {t[:34]:<34} bbox={e} oran={oran:.1f}")
    print("=" * 72)


if __name__ == "__main__":
    main()
