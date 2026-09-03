# -*- coding: utf-8 -*-
"""k55_bench_settle.py — K-55 mikro-benchmark: continuous_z_settle duvar saati.

Sentetik ama R11-temsili sahne: cok-katmanli kutu istifi (yatayda sikisik,
z'de araliklarla asili) — settle'in kaba+ince taramasi ve komsu sorgulari
gercekci sayida calisir. AYNI fixture degisiklik oncesi/sonrasi kosulur;
dz vektoru MD5'i bit-ozdeslik kanitidir.
Kosum: python -m scripts.k55_bench_settle [n_parca]    SAF ASCII.
"""
from __future__ import annotations
import hashlib
import sys
import time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh


def sahne(n=48, seed=7):
    """n kutu: 4 sutun x katmanlar; z'de 3-9mm rastgele bosluk (dusecek yer var)."""
    rng = np.random.default_rng(seed)
    meshes = []
    kolon_xy = [(0.0, 0.0), (40.0, 0.0), (0.0, 40.0), (40.0, 40.0),
                (80.0, 0.0), (80.0, 40.0), (0.0, 80.0), (40.0, 80.0)]
    z_top = {k: 0.0 for k in range(len(kolon_xy))}
    for i in range(n):
        k = i % len(kolon_xy)
        w = float(rng.uniform(18, 30))
        d = float(rng.uniform(18, 30))
        h = float(rng.uniform(8, 22))
        gap = float(rng.uniform(3.0, 9.0))
        x0, y0 = kolon_xy[k]
        z0 = z_top[k] + gap
        m = trimesh.creation.box(extents=[w, d, h])
        m.apply_translation([x0 + w / 2, y0 + d / 2, z0 + h / 2])
        z_top[k] = z0 + h
        meshes.append(m)
    return meshes


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    meshes = sahne(n)
    from src.nesting3d.continuous_settle import continuous_z_settle
    t0 = time.perf_counter()
    res = continuous_z_settle(meshes, clearance_mm=2.0, samples_per_mesh=4000)
    sure = time.perf_counter() - t0
    dz_md5 = hashlib.md5(np.round(res.dz, 9).tobytes()).hexdigest()
    print(f"n={n}  sure={sure:.1f}s  h {res.height_before_mm:.2f}->"
          f"{res.height_mm:.2f} (kazanc {res.gain_mm:.2f})  "
          f"n_moved={res.n_moved} sweeps={res.sweeps_used}")
    print(f"dz_md5={dz_md5}")


if __name__ == "__main__":
    main()
