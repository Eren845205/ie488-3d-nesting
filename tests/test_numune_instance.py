"""test_numune_instance.py — NestingInstance kurma testleri (hizli, voxelizasyon yok).

@pytest.mark.slow ile isaretlenen testler agir kosma icin ayrilir (SA/voxel).
Varsayilan kosu sadece instance kurma + metadat dogrulamayi kapsar.

Kabul kriteri:
    python -m pytest tests/test_numune_instance.py -q   -> yesil (hizli kisimlar)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.nesting3d.instances.numune_loader import build_numune_instance, _stl_path
from src.nesting3d.instances.format import NestingInstance
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_QUANTITIES


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def _stl_files_exist() -> bool:
    """Numuneler/*.stl dosyalari mevcut mu?"""
    for key in NUMUNE_QUANTITIES:
        idx = int(key[1:])
        if not (NUMUNE_DIR / f"{idx}.stl").exists():
            return False
    return True


_SKIP_IF_NO_STL = pytest.mark.skipif(
    not _stl_files_exist(),
    reason="Numuneler/*.stl dosyalari mevcut degil — CI'da beklenen atlama",
)


# ---------------------------------------------------------------------------
# Hizli testler (STL mevcutsa coser)
# ---------------------------------------------------------------------------

@_SKIP_IF_NO_STL
def test_build_numune_instance_returns_nesting_instance():
    """build_numune_instance() NestingInstance dondurmeli."""
    inst = build_numune_instance()
    assert isinstance(inst, NestingInstance)


@_SKIP_IF_NO_STL
def test_container_is_335():
    """Konteyner 335x335 mm, acik yukseklik (None)."""
    inst = build_numune_instance()
    assert inst.container.width_mm == 335.0
    assert inst.container.depth_mm == 335.0
    assert inst.container.height_mm is None


@_SKIP_IF_NO_STL
def test_part_count_matches_numune_quantities():
    """Parca sayisi NUMUNE_QUANTITIES ile eslesmeli."""
    inst = build_numune_instance()
    assert len(inst.parts) == len(NUMUNE_QUANTITIES)


@_SKIP_IF_NO_STL
def test_total_qty_matches():
    """Toplam adet NUMUNE_QUANTITIES toplamina esit olmali."""
    inst = build_numune_instance()
    expected_total = sum(NUMUNE_QUANTITIES.values())
    actual_total = sum(p.qty for p in inst.parts)
    assert actual_total == expected_total


@_SKIP_IF_NO_STL
def test_all_parts_source_stl():
    """Tum parcalar source='stl' olmali (generic motor; kutu degil)."""
    inst = build_numune_instance()
    for part in inst.parts:
        assert part.source == "stl", f"Parca {part.id} source={part.source!r} beklenen 'stl'"


@_SKIP_IF_NO_STL
def test_stl_paths_exist():
    """Her parcaya ait STL dosyasi disk uzerinde mevcut olmali."""
    inst = build_numune_instance()
    for part in inst.parts:
        assert part.stl_path is not None, f"Parca {part.id}: stl_path None"
        assert Path(part.stl_path).exists(), f"STL yok: {part.stl_path}"


@_SKIP_IF_NO_STL
def test_bbox_dims_populated():
    """STL bounding-box boyutlari (pitch meta) doldurulmali: tumu > 0."""
    inst = build_numune_instance()
    for part in inst.parts:
        assert part.width_mm is not None and part.width_mm > 0, (
            f"Parca {part.id}: width_mm={part.width_mm}"
        )
        assert part.depth_mm is not None and part.depth_mm > 0, (
            f"Parca {part.id}: depth_mm={part.depth_mm}"
        )
        assert part.height_mm is not None and part.height_mm > 0, (
            f"Parca {part.id}: height_mm={part.height_mm}"
        )


@_SKIP_IF_NO_STL
def test_distinct_part_ids():
    """Her parcayi tanimlayan id benzersiz olmali."""
    inst = build_numune_instance()
    ids = [p.id for p in inst.parts]
    assert len(ids) == len(set(ids)), f"Tekrar eden ID'ler: {ids}"


@_SKIP_IF_NO_STL
def test_no_hybrid_orientation_import():
    """numune_loader NUMUNE_ORIENTATIONS_HYBRID'i import etmemeli (generic motor).

    Belgeleme yorumlarinda gecmesi kabul edilir; import/kullanimda gececmez.
    """
    import src.nesting3d.instances.numune_loader as mod

    # NUMUNE_ORIENTATIONS_HYBRID modullerin ad alaninda olmamali
    assert not hasattr(mod, "NUMUNE_ORIENTATIONS_HYBRID"), (
        "numune_loader.py NUMUNE_ORIENTATIONS_HYBRID'i import ediyor — generic olmali!"
    )

    # Kaynak kodun import satirlarinda gecmemeli
    import inspect
    src_lines = inspect.getsource(mod).splitlines()
    import_lines = [ln for ln in src_lines if ln.strip().startswith(("import ", "from "))]
    for ln in import_lines:
        assert "NUMUNE_ORIENTATIONS_HYBRID" not in ln, (
            f"numune_loader.py import satirinda hibrit poz seti: {ln!r}"
        )


@_SKIP_IF_NO_STL
def test_suggest_pitch_works_on_instance():
    """suggest_pitch() STL bounding-box boyutlariyla pitch uretebilmeli."""
    from src.nesting3d.instances.pitch import suggest_pitch
    inst = build_numune_instance()
    pitch = suggest_pitch(inst)
    assert pitch > 0, f"Pitch pozitif olmali, elde edilen: {pitch}"
    # Pitch tavan 15 mm; gercek parcalara gore daha kucuk beklenir
    assert pitch <= 15.0, f"Pitch {pitch} tavan 15 mm'yi asmali degil"


@_SKIP_IF_NO_STL
def test_meta_has_expected_keys():
    """Instance meta sozlugu beklenen alanlari icermeli."""
    inst = build_numune_instance()
    for key in ("family", "description", "n_distinct_parts", "total_qty"):
        assert key in inst.meta, f"Meta'da eksik anahtar: {key}"
    assert inst.meta["family"] == "numune"


# ---------------------------------------------------------------------------
# Agir testler (SA/voxel) — varsayilan kosuda atlanir
# ---------------------------------------------------------------------------

@pytest.mark.slow
@_SKIP_IF_NO_STL
def test_voxelize_numune_instance():
    """to_voxel_parts() gercek STL parcalari voxelize edebilmeli.

    AGIR: her STL trimesh.load + dilimleme -> yavas.
    """
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.instances.pitch import suggest_pitch

    inst = build_numune_instance()
    pitch = suggest_pitch(inst)
    vparts = to_voxel_parts(inst, pitch, n_orientations=8)
    assert len(vparts) > 0, "Voxelizasyon bos liste dondurmemeli"
