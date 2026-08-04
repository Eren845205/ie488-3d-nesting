# -*- coding: utf-8 -*-
"""tests/test_k62_v9_pin3d.py — K-62 v9: NFV 3D pin / occupancy on-yukleme.

v8 (2D kolon muhru) yapisal siniri: pinin alti-ustu de yasakti -> kanopi
pin edilemiyordu. v9: pin GERCEK voxelleriyle occupancy'ye ON-YUKLENIR
(occ_onyuk) -> kanopi altina istif + delikten kule = insan cozumunun
mekanigi (plan1 110.41 makas anatomisi, PLAN_KOK_SEBEP_VE_KISIT_V2 v9).

Degismezler:
  - occ_onyuk=None / pin_3d=False -> BIT-OZDES (v8 semantigi korunur).
  - onyukle: carpisma kontrolu YOK (no-go/soft ortusmesi mesru), sinir
    kirpmali, column_top + yukseklik gercek dolu voxellerden.
  - pin_3d=True: pin cozucu-modelde havuzla AYNI clearance dilation'ini
    tasir; kanopi ALTINA yerlesim ve delikten kule MUMKUN.
  - fine_settle/repair pin-farkinda degil -> pin_3d'de atlanir (iz birakir).
"""
from __future__ import annotations

import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")

from src.nesting3d.extreme_point import OccupancyBin3D
from src.nesting3d.parallel_decode import decode
from src.nesting3d.voxelize import voxelize_part
from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)
from src.nesting3d.nfv_solve import solve_nfv

PITCH = 5.0


def _box_part(w=20.0, d=20.0, h=10.0, name="kutu"):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return voxelize_part(name, b, PITCH, n_orientations=1, method="slice")


# ---------------------------------------------------------------------------
# OccupancyBin3D.onyukle (birim)
# ---------------------------------------------------------------------------

def test_onyukle_temel():
    ob = OccupancyBin3D(20, 20, nz_limit=8, pitch=PITCH)
    g = np.ones((4, 4, 2), dtype=bool)
    ob.onyukle(g, 3, 5, 6)
    assert ob.occupancy[3:7, 5:9, 6:8].all()
    assert not ob.occupancy[0:3, :, :].any()
    assert ob.max_height_voxels() == 8          # yukseklik pin tepesini icerir
    assert ob.column_top[3, 5] == 8
    assert ob.column_top[0, 0] == 0
    # altindaki bosluk SERBEST kalir (2D muhurden fark)
    o = _box_part().orientations[0]             # 4x4x2
    assert ob.is_feasible(o, 3, 5, 0)           # pin ALTINA sigar
    assert not ob.is_feasible(o, 3, 5, 5)       # pinle cakisan yer yasak


def test_onyukle_sinir_kirpma():
    ob = OccupancyBin3D(10, 10, nz_limit=8, pitch=PITCH)
    g = np.ones((4, 4, 2), dtype=bool)
    ob.onyukle(g, -2, -2, 0)                    # dilation halesi tasmasi
    assert ob.occupancy[0:2, 0:2, 0:2].all()
    ob.onyukle(g, 8, 8, 0)                      # sag-ust tasma
    assert ob.occupancy[8:10, 8:10, 0:2].all()
    ob.onyukle(g, 50, 50, 0)                    # tamamen disari -> no-op
    assert ob.max_height_voxels() == 2


def test_onyukle_nogo_ustune_hata_yok():
    mask = np.zeros((10, 10), dtype=bool)
    mask[5:, :] = True
    ob = OccupancyBin3D(10, 10, nz_limit=8, pitch=PITCH, no_go_mask=mask)
    g = np.ones((4, 4, 2), dtype=bool)
    ob.onyukle(g, 3, 3, 0)                      # muhurle ortusuyor -> hata YOK
    assert ob.occupancy[3:7, 3:7, 0:2].all()


# ---------------------------------------------------------------------------
# decode + occ_onyuk (mekanizma)
# ---------------------------------------------------------------------------

def test_decode_onyuk_none_bit_ozdes():
    parts = [_box_part(name=f"k{i}") for i in range(3)]
    a = decode(parts, 20, 20, pitch=PITCH, return_placements=True)
    b = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
               occ_onyuk=None)
    assert a == b


def test_decode_kanopi_altina_istif():
    """Havada duran kanopi plakasi on-yuklu: kutular ALTINA (z=0) yerlesir.
    (v8 kolon muhruyle ayni sahnede hicbir kutu yerlesemezdi.)"""
    kanopi = np.ones((20, 20, 1), dtype=bool)   # tum tabani ortuyor, z=6'da
    parts = [_box_part(name=f"k{i}") for i in range(3)]     # 4x4x2 voxel
    h, pls = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
                    occ_onyuk=[(kanopi, 0, 0, 6)])
    assert len(pls) == 3
    for (_pid, _oi, _x, _y, z) in pls:
        assert z == 0, "kutu kanopinin ALTINA inmedi"
    assert h == 7 * PITCH                       # yukseklik kanopi tepesi


def test_decode_delikten_kule():
    """Delikli kanopi: kanopiden YUKSEK kule yalniz delik kolonlarina sigar."""
    kanopi = np.ones((20, 20, 1), dtype=bool)
    kanopi[8:12, 8:12, :] = False               # 4x4 delik
    kule = _box_part(w=15.0, d=15.0, h=50.0, name="kule")   # 3x3x10 voxel
    h, pls = decode([kule], 20, 20, pitch=PITCH, return_placements=True,
                    occ_onyuk=[(kanopi, 0, 0, 5)])
    assert len(pls) == 1
    (_pid, _oi, x, y, z) = pls[0]
    assert z == 0
    assert 8 <= x and x + 3 <= 12 and 8 <= y and y + 3 <= 12, \
        f"kule delikten gecmedi: ({x},{y})"


def test_decode_gpu_parite_onyuk():
    cp = pytest.importorskip("cupy")
    from src.nesting3d.parallel_decode import decode_gpu, probe_cupy
    if probe_cupy() is None:
        pytest.skip("GPU yok")
    kanopi = np.ones((20, 20, 1), dtype=bool)
    kanopi[8:12, 8:12, :] = False
    parts = [_box_part(name=f"k{i}") for i in range(3)]
    onyuk = [(kanopi, 0, 0, 6)]
    from src.nesting3d.fft_backend import get_backend
    fm, _ = get_backend("scipy")
    a = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
               feasible_mask=fm, occ_onyuk=onyuk)
    b = decode_gpu(parts, 20, 20, pitch=PITCH, return_placements=True,
                   occ_onyuk=onyuk)
    assert a == b


# ---------------------------------------------------------------------------
# solve_nfv pin_3d (entegrasyon)
# ---------------------------------------------------------------------------

P2 = 2.0
PLAKA = 80.0


def _inst_kanopili():
    return NestingInstance(
        container=ContainerSpec(width_mm=PLAKA, depth_mm=PLAKA),
        parts=[
            PartSpec(id="kutu", name="kutu", qty=3, source="box",
                     width_mm=16.0, depth_mm=16.0, height_mm=10.0),
            PartSpec(id="kanopi", name="kanopi", qty=1, source="box",
                     width_mm=60.0, depth_mm=60.0, height_mm=4.0),
        ],
    )


def _solve(inst, **kw):
    return solve_nfv(inst, plate_w_mm=PLAKA, plate_d_mm=PLAKA,
                     fine_pitch=P2, seed=42, fine_settle=False, **kw)


def test_solve_pin3d_pinsiz_bit_ozdes():
    a = _solve(_inst_kanopili())
    b = _solve(_inst_kanopili(), pin_3d=True)   # pin yok -> bayrak etkisiz
    assert a.height_mm == b.height_mm
    assert [(p.part_id, p.orientation_idx, p.x, p.y, p.z)
            for p in a.placements] == \
           [(p.part_id, p.orientation_idx, p.x, p.y, p.z)
            for p in b.placements]


def test_solve_pin3d_kanopi_altina_istif():
    """Kanopi z=30mm'e 3D-pinli: kutular ALTINA yerlesir; v8 muhurde ayni
    sahne cozumsuz kalirdi (kanopi disi serit 10mm < kutu 16mm)."""
    pins = [{"ad": "kanopi", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 30.0,
             "rot": None}]
    r = _solve(_inst_kanopili(), pinned_placements=pins, pin_3d=True)
    assert r.n_placed == 4                      # 3 kutu + 1 pin
    kanopi_pl = [p for p in r.placements if p.part_id.startswith("kanopi")]
    assert len(kanopi_pl) == 1
    assert (kanopi_pl[0].x, kanopi_pl[0].y, kanopi_pl[0].z) == (
        int(10 / P2), int(10 / P2), int(30 / P2))
    for p in r.placements:
        if p.part_id.startswith("kanopi"):
            continue
        assert p.z == 0, f"{p.part_id} kanopi altina inmedi (z={p.z})"
    assert r.height_mm == pytest.approx(34.0)   # kanopi tepesi 30+4


def test_solve_pin3d_v8_muhurden_farki():
    """AYNI pinle v8 (pin_3d=False): kutular kanopi kolonlarina giremez —
    tam-yukseklik muhur tabanin ise yarar kismini kapatir. Bu sahnede v8
    ya eksik yerlestirir ya _drop_fallback'te patlar (bilinen v8 siniri);
    v9'un ayni sahneyi tam cozdugu (ustteki test) farkin kaniti."""
    pins = [{"ad": "kanopi", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 30.0,
             "rot": None}]
    try:
        r = _solve(_inst_kanopili(), pinned_placements=pins, pin_3d=False)
    except ValueError:
        return  # muhurlu tabanda drop-fallback carpismasi = v8 siniri
    yerlesen_kutu = [p for p in r.placements
                     if not p.part_id.startswith("kanopi")]
    assert len(yerlesen_kutu) < 3, \
        "v8 muhurle bu sahnede 3 kutunun yerlesmemesi beklenir"


def test_solve_pin3d_dikey_clearance():
    """clearance_mm=2 + kanopi z=10mm (kutu boyu 10mm -> altinda bosluk yok):
    kutular kanopinin USTUNE, >=2mm dikey boslukla cikar."""
    pins = [{"ad": "kanopi", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 10.0,
             "rot": None}]
    r = _solve(_inst_kanopili(), pinned_placements=pins, pin_3d=True,
               clearance_mm=2.0)
    for p in r.placements:
        if p.part_id.startswith("kanopi"):
            continue
        # kanopi tepesi 14mm; dikey clearance -> kutu tabani >= 16mm
        assert p.z * P2 >= 16.0, \
            f"{p.part_id} kanopiye dikey-bosluksuz oturdu (z={p.z * P2}mm)"


def test_solve_pin3d_settle_ve_repair_korumasi():
    pins = [{"ad": "kanopi", "x_mm": 10.0, "y_mm": 10.0, "z_mm": 30.0,
             "rot": None}]
    r = solve_nfv(_inst_kanopili(), plate_w_mm=PLAKA, plate_d_mm=PLAKA,
                  fine_pitch=P2, seed=42, fine_settle=True,
                  repair_separability=True,
                  pinned_placements=pins, pin_3d=True)
    assert "settle skipped (pin_3d" in r.adaptive_reason
    assert "repair skipped (pin_3d" in r.adaptive_reason
