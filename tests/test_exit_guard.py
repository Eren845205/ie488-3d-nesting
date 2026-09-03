# -*- coding: utf-8 -*-
"""R2 exit_guard testleri — kilit-KACINAN NFV yerlestirme.

DEGISMEZ (K-29 kaniti): her parca yerlestigi anda mevcut sahneye karsi >=1
duz cikisa sahipse, ters yerlestirme sirasi gecerli sirali sokumdur ->
nihai 5-yon kilit = 0 GARANTI.
"""
import numpy as np
import trimesh

from src.nesting3d.parallel_decode import _has_exit, decode
from src.nesting3d.accessibility import check_separability_5dir
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.voxelize import voxelize_part
from src.nesting3d.instances.format import (NestingInstance, ContainerSpec,
                                            PartSpec)

PITCH = 5.0


def _box_part(name="k", w=10.0, d=10.0, h=10.0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return voxelize_part(name, b, PITCH, n_orientations=1, method="slice")


def test_has_exit_dogruluk_tablosu():
    o = _box_part().orientations[0]           # 2x2x2 voxel kutu
    occ = np.zeros((10, 10, 10), dtype=bool)
    # bos sahne: her yer cikisli
    assert _has_exit(occ, o, 4, 4, 0)
    # ustu kapali ama yanlar acik -> cikisli (+X/-X/+Y/-Y)
    occ[:, :, 3] = True                       # tavan katmani (z=3)
    occ[4:6, 4:6, 3] = True
    assert _has_exit(occ, o, 4, 4, 0)
    # dort yan duvar + tavan (tam kafes) -> cikissiz
    occ[:] = False
    occ[3, 3:7, 0:3] = True                   # -X duvari
    occ[6, 3:7, 0:3] = True                   # +X duvari
    occ[3:7, 3, 0:3] = True                   # -Y duvari
    occ[3:7, 6, 0:3] = True                   # +Y duvari
    occ[3:7, 3:7, 2] = True                   # tavan (z=2; parca z0-1'de)
    kucuk = np.zeros((10, 10, 10), dtype=bool)
    # 2x2x2 kutu (4,4,0)'da: +Z tavan occ[4:6,4:6,2]... parca fh=2 -> z2=2,
    # ustu occ[...,2:] tavani gorur; yanlar duvarlari gorur -> False
    assert not _has_exit(occ, o, 4, 4, 0)
    # tavanda delik yok ama +X duvari kaldirilirsa -> cikisli
    occ[6, 3:7, 0:3] = False
    assert _has_exit(occ, o, 4, 4, 0)
    # plaka kenari = cikis (kose parcasi)
    occ[:] = True
    occ[0:2, 0:2, 0:2] = False
    assert _has_exit(occ, o, 0, 0, 0)


def test_decode_exit_guard_bit_identity_kapali():
    parts = [_box_part(f"k{i}") for i in range(4)]
    h0, p0 = decode(parts, 20, 20, pitch=PITCH, return_placements=True)
    h1, p1 = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
                    exit_guard=False)
    assert h0 == h1 and p0 == p1


def test_decode_exit_guard_kutularda_zararsiz():
    parts = [_box_part(f"k{i}") for i in range(4)]
    h0, p0 = decode(parts, 20, 20, pitch=PITCH, return_placements=True)
    h1, p1 = decode(parts, 20, 20, pitch=PITCH, return_placements=True,
                    exit_guard=True)
    assert h1 == h0                            # kutular kenetlenmez -> ayni
    assert p1 == p0


def test_solve_nfv_exit_guard_garantisi():
    # ic-ice girmeye MUSAIT karisim (kucuk + buyuk kutular, cavity mod NFV'de)
    inst = NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="buyuk", name="buyuk", qty=2, source="box",
                     width_mm=40.0, depth_mm=40.0, height_mm=20.0),
            PartSpec(id="kucuk", name="kucuk", qty=6, source="box",
                     width_mm=10.0, depth_mm=10.0, height_mm=10.0),
        ])
    r = solve_nfv(inst, plate_w_mm=100.0, plate_d_mm=100.0,
                  fine_pitch=PITCH, n_orientations=2, fine_settle=True,
                  exit_guard=True)
    assert r.n_placed == 8
    # DEGISMEZ: exit_guard acikken nihai sahne 5-yon kilitsiz
    assert check_separability_5dir(r.placements, r.fine_voxel_parts).n_locked == 0


def test_guard_scene_ic_ice_parmagi_yakalar():
    """K-32 dersi: bbox-slab yaklasik testi (_has_exit v1) ic-ice gecmis
    parmaklari GOREMEZ (engel bbox icinde) -> yanlis-GECER. Exact _GuardScene
    (_blocks tabanli) yakalamali. Fixture: tam-kenet cifti (5 yonde de
    karsilikli blokeli)."""
    from src.nesting3d.parallel_decode import _GuardScene, _has_exit
    from tests.test_separability_repair import _fake_tam

    A = _fake_tam("A", True)
    B = _fake_tam("B", False)
    scene = _GuardScene()
    scene.ekle("A", A.orientations[0], 0, 0, 0)
    # exact guard: B (0,0,0)'da CIKISSIZ (dogru)
    assert not scene.cikisli_mi(B.orientations[0], 0, 0, 0)
    # v1 yaklasik test ayni vakada yanlis-GECER veriyordu (bilinen acik —
    # bu assert acigi belgeler; v1 artik uretim yolunda KULLANILMIYOR)
    occ = np.zeros((4, 4, 4), dtype=bool)
    g = A.orientations[0].grid
    occ[0:2, 0:2, 0:2] |= g
    assert _has_exit(occ, B.orientations[0], 0, 0, 0)  # v1: yanlis-GECER
    # bos sahnede exact guard serbest birakir
    bos = _GuardScene()
    assert bos.cikisli_mi(B.orientations[0], 0, 0, 0)
