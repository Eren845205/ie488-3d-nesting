"""test_accessibility.py â€” F2 erisilebilirlik denetimi v1 (post-check).

Sentetik, elle kurulmus kucuk 3D bool maskeler (STL YOK). Her fixture bir
yerlesim sahnesi (part_id, grid, x, y, z) listesidir; check_accessibility
+Z yonunde tek-tek sokulebilirligi denetler ve AccessibilityReport dondurur.

Tum senaryolar hizli/deterministik. SAF ASCII.
"""

import numpy as np

from src.nesting3d.accessibility import (
    AccessibilityReport,
    PlacedVoxels,
    check_accessibility,
    placed_voxels_from_scene,
    check_placements,
)


def _box(nx, ny, nz):
    """Dolu dikdortgen voxel blogu."""
    return np.ones((nx, ny, nz), dtype=bool)


# ---------------------------------------------------------------------------
# (1) Yan yana iki kutu -> ikisi de cikarilabilir, kilit yok
# ---------------------------------------------------------------------------

def test_two_side_by_side_boxes_no_lock():
    scene = [
        ("A", _box(3, 3, 3), 0, 0, 0),
        ("B", _box(3, 3, 3), 5, 0, 0),  # x=5: sutun paylasmiyor
    ]
    report = check_accessibility(placed_voxels_from_scene(scene))

    assert isinstance(report, AccessibilityReport)
    assert report.n_locked == 0
    assert report.locked_groups == []
    assert report.all_accessible is True
    assert set(report.removable_order) == {"A", "B"}


# ---------------------------------------------------------------------------
# (2) Klasik kilit: alt parcanin C/L oyuguna ustten giren kanca
# ---------------------------------------------------------------------------

def _c_hook_lock_scene():
    """Iki parca kilitli cift.

    A (taban, kesit x-z): sol duvar, taban, sag duvar + sag ustte SOLA
    uzanan bir cikinti (lip). B (kanca): dikey cubuk yukari cikar + tabanda
    A'nin cikintisinin ALTINA uzanan bir ayak.

    +Z: B ayagi A cikintisina carpar (B, A tarafindan yukarida bloke).
    Ayni zamanda B cubugu A tabaninin uzerinden gecer (A, B tarafindan
    yukarida bloke). Iki yonlu blok -> kilitli cift.
    """
    # Ortak lattice: nx=5, ny=1, nz=6
    A = np.zeros((5, 1, 6), dtype=bool)
    A[0:5, 0, 0] = True     # taban z=0, x=0..4
    A[0, 0, 0:5] = True     # sol duvar
    A[4, 0, 0:5] = True     # sag duvar
    A[3:5, 0, 4] = True     # sag ust lip (cikinti) x=3..4, z=4

    B = np.zeros((5, 1, 6), dtype=bool)
    B[2, 0, 1:6] = True     # dikey cubuk x=2, z=1..5 (tepeden disari)
    B[3, 0, 1] = True       # ayak x=3, z=1 (A lip'inin x=3,z=4 ALTINDA)
    return [("A", A, 0, 0, 0), ("B", B, 0, 0, 0)]


def test_c_hook_interlock_pair_detected():
    report = check_accessibility(placed_voxels_from_scene(_c_hook_lock_scene()))

    assert report.n_locked == 2
    assert len(report.locked_groups) == 1
    assert set(report.locked_groups[0]) == {"A", "B"}
    assert report.all_accessible is False
    assert report.removable_order == []


# ---------------------------------------------------------------------------
# (3) Ic ice ama acik bardak-istifi -> kilit YOK (yanlis-pozitif kontrolu)
# ---------------------------------------------------------------------------

def _open_cup_stack_scene():
    """Ic bardak dis bardagin ICINDE, +Z serbest.

    Dis bardak: taban + dort yandan yuksek duvar (kap). Ic bardak: daha
    kucuk, dis bardagin tabaninin UZERINDE oturur, ic sutunlarda; ic
    bardagin duvarlari dis duvarla sutun PAYLASMAZ. Paylasilan sutunlar
    yalniz taban bolgesi: orada dis (alt) <= ic (ust) -> kilit yok.
    """
    outer = np.zeros((6, 6, 8), dtype=bool)
    outer[:, :, 0] = True         # taban z=0
    outer[0, :, 0:8] = True       # duvarlar (cevre)
    outer[5, :, 0:8] = True
    outer[:, 0, 0:8] = True
    outer[:, 5, 0:8] = True

    inner = np.zeros((6, 6, 8), dtype=bool)
    inner[2:4, 2:4, 1] = True     # ic taban z=1 (dis tabanin uzerinde)
    inner[2:4, 2:4, 1:5] = True   # ic bardak govdesi, ic sutunlar 2..3
    return [("outer", outer, 0, 0, 0), ("inner", inner, 0, 0, 0)]


def test_open_cup_stack_no_false_positive():
    report = check_accessibility(placed_voxels_from_scene(_open_cup_stack_scene()))

    assert report.n_locked == 0
    assert report.locked_groups == []
    # ic bardak once cikar (serbest), sonra dis
    assert report.removable_order[0] == "inner"
    assert set(report.removable_order) == {"inner", "outer"}


# ---------------------------------------------------------------------------
# (4) 3+ parcali zincir: sira-bagimli cikarma (ust cikinca alt serbest)
# ---------------------------------------------------------------------------

def _stacked_chain_scene():
    """Uc kutu ust uste (ofsetli). Sadece en ust bastan serbest; ust
    cikinca orta serbest kalir, sonra alt. +Z dogru sirayi bulmali."""
    return [
        ("bottom", _box(3, 3, 2), 0, 0, 0),
        ("middle", _box(3, 3, 2), 0, 0, 2),
        ("top", _box(3, 3, 2), 0, 0, 4),
    ]


def test_stacked_chain_order_dependent_removal():
    report = check_accessibility(placed_voxels_from_scene(_stacked_chain_scene()))

    assert report.n_locked == 0
    assert report.removable_order == ["top", "middle", "bottom"]


# ---------------------------------------------------------------------------
# (5) Bos yerlesim / tek parca kenar durumlari
# ---------------------------------------------------------------------------

def test_empty_scene():
    report = check_accessibility([])
    assert report.n_parts == 0
    assert report.n_locked == 0
    assert report.removable_order == []
    assert report.locked_groups == []
    assert report.all_accessible is True


def test_single_part_always_accessible():
    scene = [("solo", _box(4, 4, 4), 1, 1, 0)]
    report = check_accessibility(placed_voxels_from_scene(scene))
    assert report.n_parts == 1
    assert report.n_locked == 0
    assert report.removable_order == ["solo"]


# ---------------------------------------------------------------------------
# Adapter: Placement3D + VoxelPart kaynagi (cozuculerin cikti formati)
# ---------------------------------------------------------------------------

class _FakeOrient:
    def __init__(self, grid):
        self.grid = grid


class _FakePart:
    def __init__(self, pid, grid):
        self.id = pid
        self.orientations = [_FakeOrient(grid)]


class _FakePlacement:
    def __init__(self, pid, x, y, z):
        self.part_id = pid
        self.x = x
        self.y = y
        self.z = z
        self.orientation_idx = 0


def test_check_placements_adapter_dict_and_list():
    parts = [_FakePart("A", _box(3, 3, 3)), _FakePart("B", _box(3, 3, 3))]
    placements = [_FakePlacement("A", 0, 0, 0), _FakePlacement("B", 5, 0, 0)]

    # parts as list
    r1 = check_placements(placements, parts)
    assert r1.n_locked == 0 and set(r1.removable_order) == {"A", "B"}

    # parts as dict {id: part}
    r2 = check_placements(placements, {p.id: p for p in parts})
    assert r2.n_locked == 0 and set(r2.removable_order) == {"A", "B"}


def test_summary_is_ascii():
    report = check_accessibility(placed_voxels_from_scene(_c_hook_lock_scene()))
    s = report.summary()
    # SAF ASCII (cp1254 guvenli â€” sembol/Turkce harf yok)
    s.encode("ascii")
    assert "locked" in s.lower()


def test_placedvoxels_column_profiles():
    """colmin/colmax global sutun profillerini dogru veriyor mu."""
    grid = np.zeros((2, 1, 5), dtype=bool)
    grid[0, 0, 2:4] = True   # sutun (0,0): z=2,3
    pv = placed_voxels_from_scene([("p", grid, 10, 20, 100)])[0]
    assert isinstance(pv, PlacedVoxels)
    assert pv.filled[0, 0] and not pv.filled[1, 0]
    assert pv.colmin[0, 0] == 2 and pv.colmax[0, 0] == 3


# ---------------------------------------------------------------------------
# (LOW-2) Mover dikey-delik durumu: kolon min/max ozeti delik varken de dogru
# ---------------------------------------------------------------------------

def test_mover_vertical_hole_blocker_inside_gap_is_locked():
    """Mover ayni kolonda z=0 ve z=2'de dolu (z=1 delik); blocker z=1'de.

    +Z kaldirmada mover'in alt disi (z=0) blocker'a (z=1) carpar -> kilitli.
    Ayrica mover'in z=2 hucresi blocker'in ustunde -> karsilikli kilit.
    """
    mover_grid = np.zeros((1, 1, 3), dtype=bool)
    mover_grid[0, 0, 0] = True
    mover_grid[0, 0, 2] = True
    scene = [
        ("mover", mover_grid, 0, 0, 0),
        ("blocker", _box(1, 1, 1), 0, 0, 1),  # mover deliginin icinde
    ]
    report = check_accessibility(placed_voxels_from_scene(scene))
    assert report.n_locked == 2
    assert len(report.locked_groups) == 1
    assert set(report.locked_groups[0]) == {"mover", "blocker"}


def test_blocker_fully_below_mover_not_locked():
    """Ayni kolonda blocker tamamen mover'in ALTINDA -> yanlis-pozitif yok."""
    scene = [
        ("upper", _box(1, 1, 1), 0, 0, 2),
        ("lower", _box(1, 1, 1), 0, 0, 0),
    ]
    report = check_accessibility(placed_voxels_from_scene(scene))
    assert report.n_locked == 0
    assert report.removable_order[0] == "upper"
