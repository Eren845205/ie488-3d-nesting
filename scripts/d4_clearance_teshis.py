# -*- coding: utf-8 -*-
"""d4_clearance_teshis.py — deneme4_n24 (yeni kural 2mm) clearance 1.555 teshisi.

STL'i bagli bilesenlere ayir -> min_clearance ile worst_pair'i bul ->
cift AABB'lerinden bosluk ekseni (yatay margin mi / dikey z_clearance mi) cikar.
SAF ASCII cikti (cp1254 dersi).
"""
import sys
from pathlib import Path
_ROOT = Path(r"C:\dev\ie488")
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.clearance import min_clearance

STL = _ROOT / "results" / "deneme4_n24_nogo335_288.0mm.stl"


def main():
    print(f"yukleniyor: {STL.name}", flush=True)
    m = trimesh.load(STL, process=False)
    # STL'de vertexler ucgen-basina kopyali -> merge etmeden split her ucgen
    # adasini ayri bilesen sanir (5.8M bilesen kazasi). Once kaynakla.
    m.merge_vertices()
    comps = m.split(only_watertight=False)
    print(f"bilesen sayisi: {len(comps)} (beklenen ~588)", flush=True)
    if len(comps) > 2000:
        print("UYARI: bilesen sayisi anormal — split hala kirik, cikiliyor")
        return
    rep = min_clearance(list(comps), samples_per_mesh=3000, seed=0)
    print(f"min_mm={rep.min_mm:.3f}  pair={rep.worst_pair}  "
          f"checked={rep.n_pairs_checked}", flush=True)
    if rep.worst_pair is None:
        return
    i, j = rep.worst_pair
    bi, bj = comps[i].bounds, comps[j].bounds
    print(f"parca i={i}: min={np.round(bi[0],2)} max={np.round(bi[1],2)}")
    print(f"parca j={j}: min={np.round(bj[0],2)} max={np.round(bj[1],2)}")
    # eksen bazinda AABB bosluklari (negatif = o eksende ortusuyor)
    for ax, ad in enumerate("xyz"):
        gap = max(bi[0][ax] - bj[1][ax], bj[0][ax] - bi[1][ax])
        print(f"  AABB bosluk {ad}: {gap:+.3f} mm")
    # en yakin nokta cifti hangi dogrultuda? (orneklem ile)
    from scipy.spatial import cKDTree
    pi, _ = trimesh.sample.sample_surface(comps[i], 6000, seed=1)
    pj, _ = trimesh.sample.sample_surface(comps[j], 6000, seed=2)
    tree = cKDTree(pj)
    d, idx = tree.query(pi, k=1)
    k = int(np.argmin(d))
    a, b = pi[k], pj[idx[k]]
    v = b - a
    print(f"yakin cift: dist={d[k]:.3f}  vektor={np.round(v,3)}  "
          f"|dx|={abs(v[0]):.3f} |dy|={abs(v[1]):.3f} |dz|={abs(v[2]):.3f}")
    # ayni cift icin ek 10 en-yakin ornek yonu (tek ornek yaniltmasin)
    order = np.argsort(d)[:10]
    dirs = pj[idx[order]] - pi[order]
    print("ilk10 en-yakin vektor ortalama |bilesen|: "
          f"dx={np.mean(np.abs(dirs[:,0])):.3f} "
          f"dy={np.mean(np.abs(dirs[:,1])):.3f} "
          f"dz={np.mean(np.abs(dirs[:,2])):.3f}")


if __name__ == "__main__":
    main()
