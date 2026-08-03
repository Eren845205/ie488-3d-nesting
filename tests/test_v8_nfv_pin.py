# -*- coding: utf-8 -*-
"""tests/test_v8_nfv_pin.py — K-62 v8: NFV dalinda pinned_placements.

Degismezler:
  - pinned_placements=None -> solve_nfv BIT-OZDES (yukseklik + placements).
  - Pin TAM verilen (mm) konumda, verilen rot'la sahnede; cozum havuzundan
    donor kopyasi DUSER (toplam yerlesim sayisi korunur).
  - Pin footprint kolonlari cozucuye MUHURLU: hicbir cozulen parca pin
    kolonlariyla cakismaz (v8-MVP konservatif semantigi).
  - Coklu-kopya: ayni ada iki pin, iki FARKLI kopyayi tuketir.
"""
from __future__ import annotations

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)
from src.nesting3d.nfv_solve import solve_nfv

PITCH = 2.0
PLAKA = 80.0


def _instance():
    return NestingInstance(
        container=ContainerSpec(width_mm=PLAKA, depth_mm=PLAKA),
        parts=[
            PartSpec(id="kutu", name="kutu", qty=3, source="box",
                     width_mm=16.0, depth_mm=16.0, height_mm=10.0),
            PartSpec(id="kule", name="kule", qty=2, source="box",
                     width_mm=10.0, depth_mm=10.0, height_mm=40.0),
        ],
    )


def _solve(**kw):
    return solve_nfv(_instance(), plate_w_mm=PLAKA, plate_d_mm=PLAKA,
                     fine_pitch=PITCH, seed=42, fine_settle=False, **kw)


def test_pin_none_bit_ozdes():
    a = _solve()
    b = _solve(pinned_placements=None)
    assert a.height_mm == b.height_mm
    assert [(p.part_id, p.orientation_idx, p.x, p.y, p.z)
            for p in a.placements] == \
           [(p.part_id, p.orientation_idx, p.x, p.y, p.z)
            for p in b.placements]


def test_pin_tam_konumda_ve_havuzdan_duser():
    pins = [{"ad": "kule", "x_mm": 60.0, "y_mm": 60.0, "z_mm": 0.0,
             "rot": None}]
    r = _solve(pinned_placements=pins)
    assert r.n_placed == 5  # 4 cozulen + 1 pin (toplam korunur)
    pinli = [p for p in r.placements
             if (p.x, p.y, p.z) == (int(60 / PITCH), int(60 / PITCH), 0)]
    assert len(pinli) == 1, "pin TAM verilen mm konumunda olmali"
    assert pinli[0].part_id.startswith("kule")


def test_pin_kolonlari_cozucuye_muhurlu():
    pins = [{"ad": "kule", "x_mm": 60.0, "y_mm": 60.0, "z_mm": 0.0,
             "rot": None}]
    r = _solve(pinned_placements=pins)
    # pin footprint'i (60..70mm kare) — margin'siz pin 5x5 voxel
    px0, px1 = int(60 / PITCH), int(70 / PITCH)
    pin_id = [p for p in r.placements
              if (p.x, p.y, p.z) == (px0, px0, 0)][0].part_id
    for p in r.placements:
        if p.part_id == pin_id:
            continue
        o = r.fine_voxel_parts[p.part_id].orientations[p.orientation_idx]
        f = o.filled
        # cozulen parcanin dolu kolonlari pin karesiyle kesisMEMELI
        for dx in range(f.shape[0]):
            for dy in range(f.shape[1]):
                if not f[dx, dy]:
                    continue
                cx, cy = p.x + dx, p.y + dy
                assert not (px0 <= cx < px1 and px0 <= cy < px1), \
                    f"{p.part_id} pin kolonuna girdi ({cx},{cy})"


def test_coklu_kopya_pin_nfvde():
    pins = [
        {"ad": "kule", "x_mm": 60.0, "y_mm": 60.0, "z_mm": 0.0, "rot": None},
        {"ad": "kule", "x_mm": 60.0, "y_mm": 40.0, "z_mm": 0.0, "rot": None},
    ]
    r = _solve(pinned_placements=pins)
    assert r.n_placed == 5
    pinliler = [p for p in r.placements
                if p.x == int(60 / PITCH) and p.z == 0
                and p.y in (int(60 / PITCH), int(40 / PITCH))]
    assert len(pinliler) == 2
    assert pinliler[0].part_id != pinliler[1].part_id
