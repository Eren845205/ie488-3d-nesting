"""c3_height_driver.py — Plan2 522mm tavanini HANGI parcalar belirliyor? (teshis).

Koordineli rack (Yol A) Plan2'de kazanmadi: rack-uygun parcalar tavanin altinda.
Peki tavani (522) NE belirliyor? Tepedeki parcalari olc -> "donmesi gereken parca" net.

Baz n=8 NFV-greedy decode (c3_generality.decode_nfv ile AYNI mantik) ama her parcanin
yerlestigi TEPE-z'sini (mm) kaydet. Tepeye en yakin parcalari raporla.

URETIME DOKUNMAZ — scripts/ only. ASCII.
Kullanim: python scripts/c3_height_driver.py [plan2|plan3|plan1]
"""
from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts, _make_mesh
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback
from scripts.c3_generality import _blb_nfv_fast, DATASETS, PITCH, MARGIN


def decode_record(parts, nx, ny):
    """NFV-greedy (c3_generality.decode_nfv ile birebir) + her parca tepe-z (mm) kaydi."""
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    rec = []
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            o = _blb_nfv_fast(ob, orient)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            (x, y, z), oi = _drop_fallback(ob, part)
            best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
        fh = part.orientations[oi].grid.shape[2]
        rec.append((part.name, (z + fh) * PITCH, oi))
    return ob.height_mm(), rec


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    cfg = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"crot_{ds}"}
    if cfg["plate"] is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    res = build_instance_from_order(stl_map, cfg["qty"], **kwargs)
    inst = res.instance
    cont = inst.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)
    parts = to_voxel_parts(inst, PITCH, n_orientations=8, margin=MARGIN, method="slice")

    h, rec = decode_record(parts, nx, ny)
    print("=" * 72)
    print(f"HEIGHT-DRIVER TESHISI — {ds} n=8 — tavan={h:.1f}mm")
    print("=" * 72)

    # parca bbox (en-boy) bilgisi
    ext = {}
    for p in inst.parts:
        if p.name not in ext:
            e = sorted(round(float(x), 0) for x in _make_mesh(p).extents)
            ext[p.name] = e

    rec.sort(key=lambda r: -r[1])
    print(f"  {'tepe-z(mm)':>10}  {'oi':>3}  {'bbox(mm)':>20}  parca")
    print("-" * 72)
    for name, topz, oi in rec[:15]:
        print(f"  {topz:>10.1f}  {oi:>3}  {str(ext.get(name,'?')):>20}  {name[:30]}")
    print("-" * 72)
    # tavana yakin (>= %95) kac parca, hangi tipler?
    thr = h * 0.95
    top = [r for r in rec if r[1] >= thr]
    tipler = sorted(set(r[0] for r in top))
    print(f"  tavanin %95'i ({thr:.0f}mm) ustunde {len(top)} parca, {len(tipler)} tip:")
    for t in tipler:
        cnt = sum(1 for r in top if r[0] == t)
        print(f"     x{cnt:>3}  {t[:40]}  bbox={ext.get(t)}")
    print("=" * 72)


if __name__ == "__main__":
    main()
