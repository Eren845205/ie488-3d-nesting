# -*- coding: utf-8 -*-
"""R1 kilit-tahliye post-pass testleri (separability_repair + solve_nfv kablosu).

Fixture'lar test_separability_5dir'in kenet desenlerini kullanir: SIRALI
sokumde kilit ancak KARSILIKLI kenette olusur; tam-kenet cifti 5-yonde de
kilitlidir -> onarim tahliye edip ustte yeniden yerlestirmeli.
"""
import numpy as np

from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.bin3d import Placement3D
from src.nesting3d.separability_repair import repair_separability
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.instances.format import (NestingInstance, ContainerSpec,
                                            PartSpec)
from src.nesting3d.voxelize import _column_profiles
from tests.test_separability_5dir import _FakePart, _tam_kenet

PITCH = 5.0


def _pl(pid, x, y, z):
    return Placement3D(pid, pid, x, y, z, 0)


def _fake_tam(pid, desen_a):
    p = _FakePart(_tam_kenet(desen_a))
    # dblf/Bin3D.place icin gereken alanlar — fake'e ekle
    p.id = p.name = pid
    o = p.orientations[0]
    o.filled, o.bottom, o.top = _column_profiles(o.grid)
    o.voxel_count = int(o.grid.sum())
    return p


def test_repair_tam_kenedi_cozer():
    parts = {"A": _fake_tam("A", True), "B": _fake_tam("B", False)}
    pls = [_pl("A", 0, 0, 0), _pl("B", 0, 0, 0)]
    assert check_separability_5dir(pls, parts).n_locked == 2
    rr = repair_separability(pls, parts, plate_w_mm=100.0, plate_d_mm=100.0,
                             pitch=PITCH)
    assert rr.repaired
    assert rr.n_locked_before == 2
    assert rr.n_locked_after == 0
    assert len(rr.placements) == 2
    assert check_separability_5dir(rr.placements, parts).n_locked == 0


def test_repair_temiz_sahnede_dokunmaz():
    parts = {"A": _fake_tam("A", True)}
    pls = [_pl("A", 0, 0, 0)]
    rr = repair_separability(pls, parts, plate_w_mm=100.0, plate_d_mm=100.0,
                             pitch=PITCH)
    assert not rr.repaired
    assert rr.n_locked_after == 0
    assert [(p.part_id, p.x, p.y, p.z) for p in rr.placements] == \
           [("A", 0, 0, 0)]


def _inst():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[PartSpec(id="box_a", name="box_a", qty=4, source="box",
                        width_mm=30.0, depth_mm=20.0, height_mm=10.0)])


def test_solve_nfv_repair_default_bit_identical():
    r0 = solve_nfv(_inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False)
    r1 = solve_nfv(_inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False,
                   repair_separability=False)
    assert r0.height_mm == r1.height_mm
    assert [(p.part_id, p.x, p.y, p.z, p.orientation_idx) for p in r0.placements] == \
           [(p.part_id, p.x, p.y, p.z, p.orientation_idx) for p in r1.placements]


def test_solve_nfv_repair_acik_kutularda_zararsiz():
    # kutular kenetlenmez -> repair acik olsa da sonuc legal ve yukseklik ayni
    r0 = solve_nfv(_inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False)
    r1 = solve_nfv(_inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                   fine_pitch=PITCH, n_orientations=2, fine_settle=False,
                   repair_separability=True)
    assert r1.height_mm == r0.height_mm
    assert check_separability_5dir(r1.placements, r1.fine_voxel_parts).n_locked == 0
