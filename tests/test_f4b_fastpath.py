"""test_f4b_fastpath.py — F4-B ozdes-grup hizli yol prototipi (RAM-siz birim testleri).

scripts/f4b_fastpath.py bir OLC-ONCE prototipidir (uretime dokunmaz). Bu testler
saf geometri fonksiyonlarini sentetik gridlerle dogrular; STL/voxelize maliyeti
YOK. Kabuk telescoping mekanigi, solid-parca istif-yok davranisi, kule formulu ve
+Z erisilebilirlik sanity'si guard altina alinir.
"""
from __future__ import annotations

import math

import numpy as np

from scripts.f4b_fastpath import (
    _funnel_grid,
    _orient_from_grid,
    _solid_box_grid,
    best_group_tower,
    nest_advance_vox,
    part_top_vox,
    per_layer_area_ub,
    per_layer_count,
    shared_plate_vox,
    tower_accessible,
)


def test_solid_box_no_nesting():
    """Solid parca: her kolon tam yukseklik dolu -> advance = tam yukseklik."""
    box = _orient_from_grid(_solid_box_grid(side=10, height=12))
    assert part_top_vox(box) == 12
    assert nest_advance_vox(box) == 12  # istif YOK


def test_shell_telescopes():
    """Ince-kabuk huni: kolonlar z'de ince -> advance << tam yukseklik."""
    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    h = part_top_vox(funnel)
    adv = nest_advance_vox(funnel)
    assert 0 < adv < h  # telescoping var


def test_per_layer_grid_packing():
    assert per_layer_count(10, 10, 30, 20) == 3 * 2  # floor(30/10)*floor(20/10)
    assert per_layer_count(31, 5, 30, 20) == 0        # sigmaz (fw>nx)


def test_group_tower_formula_and_orientation_choice():
    """Kule = h_part + (n_dik-1)*(advance+tampon); en dusuk kuleyi secmeli."""
    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    buf = 1
    tw = best_group_tower([funnel], qty=40, nx=60, ny=60, buffer_vox=buf)
    assert tw is not None
    per = per_layer_count(tw["fw"], tw["fh"], 60, 60)
    assert tw["per_layer"] == per
    assert tw["n_vertical"] == math.ceil(40 / per)
    exp = tw["h_part_vox"] + (tw["n_vertical"] - 1) * tw["advance_vox"]
    assert tw["tower_vox"] == exp
    # telescoping kulesi istif-yok kulesinden KISA
    naive = tw["h_part_vox"] * tw["n_vertical"]
    assert tw["tower_vox"] < naive


def test_shared_plate_consistent_and_lower_bound():
    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    tw = best_group_tower([funnel], qty=40, nx=60, ny=60, buffer_vox=1)
    rows = [(40, tw["fw"] * tw["fh"], tw["h_part_vox"], tw["advance_vox"])]
    sp = shared_plate_vox(rows, plate_cells=60 * 60, hi_vox=tw["tower_vox"])
    assert sp is not None
    assert part_top_vox(funnel) <= sp <= tw["tower_vox"]


def test_shared_plate_infeasible_returns_none():
    """Tek kolon plaka alanindan buyukse (buyuk duz parca) -> None."""
    big = _orient_from_grid(_solid_box_grid(side=50, height=4))
    rows = [(2, 50 * 50, 4, 4)]  # 2 kopya, her biri 2500 hucre; plaka 40x40=1600
    assert shared_plate_vox(rows, plate_cells=40 * 40, hi_vox=999) is None


def test_nested_tower_plus_z_removable():
    """Istiflenmis huni kulesi +Z yonunde sokulebilmeli (kilitli grup YOK)."""
    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    adv = nest_advance_vox(funnel) + 1
    ok, summary = tower_accessible(funnel, adv, k=5)
    assert ok, summary


def test_per_layer_area_ub_is_valid_upper_bound_over_grid():
    """HIGH regresyon: grid per_layer gercek maks-yerlesimi ALT-sayar; alan-tabani
    ust sinir onu her zaman >= kapsar. Karsi-ornek: 11x6 footprint, 20x20 plaka —
    grid yalniz 3 der (floor(20/11)*floor(20/6)=1*3), alan siniri 6 (400//66).
    grid n_dik = ceil(qty/3) SISER; gecerli n_vert_lb = ceil(qty/6) KUCUK."""
    grid_n = per_layer_count(11, 6, 20, 20)
    area_ub = per_layer_area_ub(11 * 6, 20 * 20)
    assert grid_n == 3
    assert area_ub == 6
    assert grid_n <= area_ub               # grid ASLA alan-siniri asamaz
    # 4 kopya: grid n_dik=2 (kule sisik/gecersiz LB), n_vert_lb=1 (gecerli)
    assert math.ceil(4 / grid_n) == 2
    assert math.ceil(4 / area_ub) == 1


def test_per_layer_area_ub_degenerate():
    assert per_layer_area_ub(0, 400) == 0
    assert per_layer_area_ub(66, 0) == 0
    assert per_layer_area_ub(-5, 400) == 0


def test_bin3d_aligned_drop_equals_nest_advance():
    """MEDIUM-2 kilit: nest_advance_vox(o) == Bin3D dizilim ile birebir olcum.

    place(kopya0 @z=0) yaptiktan sonra AYNI hizali kopyanin drop_z'si tam olarak
    nest_advance_vox(o)'dur (kabuk-telescoping gercek Bin3D drop kuraliyla
    ozdes). Ayrica z_clearance == buffer iliskisi: tampon = ust-kopyaya eklenen
    dikey bosluk, drop_z'yi tam o kadar buyutur."""
    from src.nesting3d.bin3d import Bin3D
    from src.nesting3d.voxelize import VoxelPart

    funnel = _orient_from_grid(_funnel_grid(side=20, height=16, wall=2))
    part = VoxelPart("f", "f", None, [funnel], int(funnel.grid.sum()))
    adv = nest_advance_vox(funnel)
    assert adv > 0  # kabuk telescope eder (test anlamli)

    # z_clearance = 0: hizali kopya drop-z'si == nest_advance_vox (birebir)
    b0 = Bin3D(plate_w_mm=40, plate_d_mm=40, pitch=1.0, z_clearance=0)
    b0.place(part, 0, 0, 0, 0)
    assert b0.drop_z(funnel, 0, 0) == adv

    # z_clearance = buffer: drop-z == nest_advance + buffer (f4b'nin adv+tampon'u)
    buffer = 3
    bb = Bin3D(plate_w_mm=40, plate_d_mm=40, pitch=1.0, z_clearance=buffer)
    bb.place(part, 0, 0, 0, 0)
    assert bb.drop_z(funnel, 0, 0) == adv + buffer


def test_orient_from_grid_profiles():
    """filled/bottom/top profilleri ham gridle tutarli."""
    g = np.zeros((3, 3, 5), dtype=bool)
    g[1, 1, 2] = True  # tek voxel z=2
    o = _orient_from_grid(g)
    assert o.filled[1, 1] and not o.filled[0, 0]
    assert o.bottom[1, 1] == 2
    assert o.top[1, 1] == 3          # highest+1
    assert nest_advance_vox(o) == 1  # top-bottom = 1
