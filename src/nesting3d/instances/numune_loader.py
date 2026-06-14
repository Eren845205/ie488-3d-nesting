"""numune_loader.py — Hocanin gercek STL numunelerinden NestingInstance kurucusu.

Amac (overfit kanitlama):
    Elayarli hibrit poz setini (NUMUNE_ORIENTATIONS_HYBRID) KULLANMADAN genel
    motoru gercek geometri uzerinde kosturmak.  Bu modul sadece instance
    yapisini kurar; poz secimi ve pitch hesabi benchmark / runner tarafindan
    generik kurallara gore yapilir.

Kullanim:
    from src.nesting3d.instances.numune_loader import build_numune_instance

    inst = build_numune_instance()
    # -> NestingInstance: 8 parca, 335x335xNone konteyner

Tasarim kararlari:
    - source="stl": voxelize.py gercek geometriyi okur (kutulastirma yok).
    - width_mm/depth_mm/height_mm: STL'in bounding-box extentleri (mm).
      pitch.py min_feature_mm() ve features.py _dims() bu degerleri kullanir.
      Gercek voxelizasyon to_voxel_parts -> _make_mesh -> trimesh.load'dan
      gelir; boyut alanlari sadece istatistik/pitch icin yardimci metadir.
    - NUMUNE_ORIENTATIONS_HYBRID'e referans VERILMEZ (generic motor).
    - Konteyner: 335 x 335 mm, acik yukseklik (None).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import trimesh

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.models import NUMUNE_DIR, NUMUNE_QUANTITIES

# Konteyner tabani: hocanin verdigi 335 mm plaka
_CONTAINER = ContainerSpec(width_mm=335.0, depth_mm=335.0, height_mm=None)


def _stl_path(part_key: str, models_dir: Path) -> Path:
    """Parca anahtari (orn. 'n3') -> mutlak STL dosya yolu."""
    idx = int(part_key[1:])  # 'n3' -> 3
    return models_dir / f"{idx}.stl"


def _bbox_extents(stl_path: Path) -> tuple:
    """STL dosyasinin bounding-box boyutlarini (w, d, h) mm cinsinden dondur.

    trimesh min-cikma noktasina tasinmis mesh kullanilir (ayni sekilde
    _make_mesh de uygular).  Boyutlar pitch ve istatistik icin kullanilir;
    gercek voxelizasyon asil dosyadan yapilir.
    """
    mesh = trimesh.load(str(stl_path), force="mesh")
    if mesh.is_empty or len(mesh.faces) == 0:
        raise ValueError(f"Bos veya okunamayan mesh: {stl_path}")
    mesh.apply_translation(-mesh.bounds[0])
    extents = mesh.extents  # (w, d, h) mm
    return float(extents[0]), float(extents[1]), float(extents[2])


def build_numune_instance(
    models_dir: Path | str | None = None,
) -> NestingInstance:
    """Hocanin gercek STL numunelerinden NestingInstance kur.

    Args:
        models_dir: STL dosyalarinin bulundugu dizin.  None ise proje koku /
                    Numuneler/ kullanilir (NUMUNE_DIR).

    Returns:
        NestingInstance — 8 parca, 335x335xNone konteyner.
        Her PartSpec source='stl' + bounding-box boyutlari (pitch meta).

    Raises:
        FileNotFoundError: STL dosyasi bulunamadiysa.
        ValueError:        Bos/okunamayan mesh.
    """
    if models_dir is None:
        models_dir = NUMUNE_DIR
    models_dir = Path(models_dir)

    parts: List[PartSpec] = []
    for key, qty in NUMUNE_QUANTITIES.items():
        path = _stl_path(key, models_dir)
        if not path.exists():
            raise FileNotFoundError(
                f"STL dosyasi bulunamadi: {path}. "
                f"Numuneler/ klasorunu kontrol edin."
            )
        w, d, h = _bbox_extents(path)
        parts.append(
            PartSpec(
                id=key,
                name=key,
                qty=qty,
                source="stl",
                stl_path=str(path),
                # Bounding-box boyutlari: pitch.suggest_pitch + features icin meta
                width_mm=w,
                depth_mm=d,
                height_mm=h,
            )
        )

    return NestingInstance(
        container=_CONTAINER,
        parts=parts,
        meta={
            "family": "numune",
            "description": "Hocanin gercek STL numuneleri — generic motor (el-ayarsiz)",
            "container_mm": "335x335xNone",
            "n_distinct_parts": len(parts),
            "total_qty": sum(p.qty for p in parts),
            "stl_dir": str(models_dir),
            "orientation_policy": "generic (NUMUNE_ORIENTATIONS_HYBRID kullanilmadi)",
        },
    )
