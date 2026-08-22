# -*- coding: utf-8 -*-
"""test_pin3d_kose_clearance.py — HAM-PIN kosegen-bosluk sizintisi fix'i.

KOK-SEBEP (seed2 teshisi, 2026-08-20, results/k66_seed2_teshis.json):
_dilate cekirdegi L1/arti-sekilli (kose hucreleri dolmaz). Parca-parca
temasta iki taraf da sisik oldugundan eksen boslugu korunur; ama HAM-pin
(v17, dilation'siz damga) x serbest parcanin L1-dilation'i birlesince
KOSEGEN cebi acik kalir: parca pin kosesine sqrt(ex^2+ey^2) < clearance
mesafeye oturabilir (seed2'de 1,256mm; en kotu ~0).

FIX: kose kapama PARCA cekirdeginde (kose_doldur) — pin-tarafi damga
denemesi eksen sozlesmesini bozdu (kose hucresi, koseyi crossing eksen
komsusunun L1-halkasiyla ayni hucre; occupancy ikisini ayiramaz). Parca
dilation'i pinli+pin_3d cozumlerde L1 | S_diag olur:
  S_diag = {(+-u,+-v): u,v>=1, u+v>m, (u-1)^2+(v-1)^2 < m^2}
Eksen yuzleri L1 ile BIT-OZDES (HAM-pin 1x-margin sozlesmesi korunur);
kosegen cep, parcanin kendi kose-hucresi pin raw kosesine degdigi icin
kapanir. Pinsiz yollarda kose_doldur=False -> bit-ozdes (A11.3).
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
from src.nesting3d.voxelize import _dilate, _dilate_kose

P2 = 2.0


# ---------------------------------------------------------------------------
# _dilate_kose (birim)
# ---------------------------------------------------------------------------

def test_kose_m1_tek_hucre():
    """Tek hucre, m=1: 4 kosegen dolar; eksen komsulari (L1 halka) HAM kalir."""
    g = np.zeros((1, 1, 1), dtype=bool)
    g[0, 0, 0] = True
    out = _dilate_kose(g, 1)
    assert out.shape == (3, 3, 1)          # pad 1 her yana
    assert out[1, 1, 0]                    # merkez (raw)
    for cx, cy in ((0, 0), (0, 2), (2, 0), (2, 2)):
        assert out[cx, cy, 0], f"kose ({cx},{cy}) dolmadi"
    for ax, ay in ((0, 1), (1, 0), (1, 2), (2, 1)):
        assert not out[ax, ay, 0], f"eksen komsusu ({ax},{ay}) HAM kalmali"


def test_kose_m0_noop():
    g = np.ones((2, 2, 1), dtype=bool)
    out = _dilate_kose(g, 0)
    assert out is g                        # times<=0 -> dokunma


def test_kose_kutu_union_yalniz_koseler():
    """4x4 kutu, m=1: L1 | kose birlesimi L1'e yalniz 4 kose hucresi ekler;
    eksen yuzleri (kenar seritler) L1 ile BIT-OZDES kalir."""
    g = np.zeros((4, 4, 2), dtype=bool)
    g[:, :, :] = True
    l1 = _dilate(g, 1)
    out = l1 | _dilate_kose(g, 1)
    assert out.shape == (6, 6, 2)
    eklenen = out & ~l1
    for cx, cy in ((0, 0), (0, 5), (5, 0), (5, 5)):
        assert eklenen[cx, cy, :].all(), f"kose ({cx},{cy}) dolmadi"
    assert int(eklenen.sum()) == 4 * 2     # z-katman basina tam 4 kose
    # eksen yuzleri degismedi (1x-margin HAM-pin sozlesmesi)
    assert (out[0, 1:5, :] == l1[0, 1:5, :]).all()
    assert (out[1:5, 0, :] == l1[1:5, 0, :]).all()


def test_kose_eklenen_eksen_bandina_sizmiyor():
    """m=2: L1'in otesine eklenen hucrelerin TAMAMI kose bolgesinde —
    raw ile ayni satiri VEYA ayni sutunu paylasan hucre eklenmez
    (eksen 1x-margin sozlesmesi yapisal korunur)."""
    g = np.zeros((3, 3, 1), dtype=bool)
    g[:, :, 0] = True
    l1 = _dilate(g, 2)                     # pad 2 -> 7x7; raw 2..4
    out = l1 | _dilate_kose(g, 2)
    eklenen = out & ~l1
    assert eklenen.any()                   # kose bolgesi gercekten dolu
    xs, ys, _zs = np.nonzero(eklenen)
    for x, y in zip(xs, ys):
        assert not (2 <= x <= 4) and not (2 <= y <= 4), \
            f"eksen bandina sizinti: ({x},{y})"


# ---------------------------------------------------------------------------
# solve_nfv pin_3d kosegen cebi (entegrasyon)
#
# Sahne (deterministik): plaka 34x34, pitch 2, clearance 2 (margin 1 voxel).
# Pin kutusu 15.3x15.3x10 @ (0,0,0): raw hucreler 0..7 (mesh 15.3'te biter,
# hucre sinirina 0.7 kala). Serbest kutu 16x16x10: dilated grid 10 hucre;
# nx=17 -> yalniz (7,7) kosegen cebi z=0'da sigar (eksen-bitisik yerler
# pin raw'iyla cakisir, sag serit plakaya sigmaz). Fix oncesi: kutu cebe
# oturur, mesh mesafesi sqrt(0.7^2+0.7^2)=0.99mm < 2. Fix sonrasi: cep
# damgali -> kutu pin USTUNE cikar, clearance >= 2.
# ---------------------------------------------------------------------------

def _inst_kose_cebi():
    return NestingInstance(
        container=ContainerSpec(width_mm=34.0, depth_mm=34.0),
        parts=[
            PartSpec(id="pin_kutu", name="pin_kutu", qty=1, source="box",
                     width_mm=15.3, depth_mm=15.3, height_mm=10.0),
            PartSpec(id="kutu", name="kutu", qty=1, source="box",
                     width_mm=16.0, depth_mm=16.0, height_mm=10.0),
        ],
    )


def _min_mesh_clearance(r):
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.export_stl import placed_meshes
    meshes = list(placed_meshes(list(r.placements), r.fine_voxel_parts,
                                float(r.fine_pitch)))
    return float(min_clearance(meshes).min_mm)


_PINS = [{"ad": "pin_kutu", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0,
          "rot": None}]


def test_pin3d_kosegen_cebi_clearance_korunur():
    r = solve_nfv(_inst_kose_cebi(), plate_w_mm=34.0, plate_d_mm=34.0,
                  fine_pitch=P2, seed=42, fine_settle=False,
                  pinned_placements=_PINS, pin_3d=True, clearance_mm=2.0)
    assert r.n_placed == 2
    gap = _min_mesh_clearance(r)
    assert gap >= 2.0 - 1e-6, \
        f"kosegen cebi sizintisi: clearance {gap:.3f}mm < 2.0"


def test_pin3d_kosegen_cebi_settle_clearance_korunur():
    """Settle katmani (fine 0.5, margin 4 voxel) ayni cebi ACAMAZ —
    seed2 mekanizmasi settle'in parcayi cebe indirmesiydi (z=73.5 izi)."""
    r = solve_nfv(_inst_kose_cebi(), plate_w_mm=34.0, plate_d_mm=34.0,
                  fine_pitch=P2, seed=42, fine_settle=True,
                  pinned_placements=_PINS, pin_3d=True, clearance_mm=2.0)
    assert r.n_placed == 2
    gap = _min_mesh_clearance(r)
    assert gap >= 2.0 - 1e-6, \
        f"settle kosegen cebine indirdi: clearance {gap:.3f}mm < 2.0"


def test_pin3d_eksen_bosluk_sozlesmesi_degismez():
    """Fix eksen-bitisik semantige dokunmaz: v17 HAM 1x-margin senaryosu
    (test_k62_v9_pin3d.test_pin3d_ham_pin_xy_boslugu_tek_dilation ikizi)
    ayni kalir — bosluk ~2mm, cift-dilation vergisi YOK."""
    inst = NestingInstance(
        container=ContainerSpec(width_mm=40.0, depth_mm=20.0),
        parts=[
            PartSpec(id="pin_kutu", name="pin_kutu", qty=1, source="box",
                     width_mm=16.0, depth_mm=16.0, height_mm=10.0),
            PartSpec(id="kutu", name="kutu", qty=1, source="box",
                     width_mm=16.0, depth_mm=16.0, height_mm=10.0),
        ],
    )
    r = solve_nfv(inst, plate_w_mm=40.0, plate_d_mm=20.0,
                  fine_pitch=P2, seed=42, fine_settle=False,
                  pinned_placements=_PINS, pin_3d=True, clearance_mm=2.0)
    assert r.n_placed == 2
    assert all(p.z == 0 for p in r.placements), "kutular yan-yana kalmali"
    gap = _min_mesh_clearance(r)
    assert 2.0 - 1e-6 <= gap <= 2.0 + P2 / 2, \
        f"eksen boslugu degisti: {gap:.3f}mm (beklenen ~2mm, 1x margin)"
