"""synthetic.py — Seed'li sentetik instance üreticiler.

Tüm üreticiler:
- Aynı seed + aynı parametreler -> aynı instance (deterministik).
- Varsayılan konteyner 300 x 300 x None (open-dimension).
- Birim: mm.

Aile Açıklamaları
-----------------
random_boxes:
    Uniform dağılımdan rastgele kutu boyutları.  Genel amaçlı kıyaslama temeli.
    Parametreler: n_parts, min_dim, max_dim, container, seed.

few_large_many_small:
    Küçük sayıda büyük parça + çok sayıda küçük parça.  Büyük parçalar hacme
    hâkimdir; sıralama/poz kararı kritik.
    Parametreler: n_large, n_small, large_min, large_max, small_min, small_max,
    container, seed.

high_qty_repeat:
    Az sayıda farklı model ama her modelden yüksek adet.  Voxelization
    paylaşımının performansa etkisini test eder; tekrar-parça oranı yüksek.
    Parametreler: n_models, qty_per_model, dim_min, dim_max, container, seed.

thin_plates:
    Kalınlık << diğer boyutlar olan ince levhalar.  Yükseklik optimizasyonunda
    plaka yönelimi kritik; 'thin_plate_ratio' özelliği yüksek çıkar.
    Parametreler: n_parts, xy_min, xy_max, thickness_min, thickness_max,
    container, seed.

long_rods:
    Uzunluk >> diğer boyutlar olan çubuk/profil parçalar.  Uzun-çubuk oranı
    yüksek; Ry rotasyonu varsa yatırarak istiflemek kritik.
    Parametreler: n_parts, cross_min, cross_max, length_min, length_max,
    container, seed.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)


# ---------------------------------------------------------------------------
# Yardımcı
# ---------------------------------------------------------------------------

def _default_container() -> ContainerSpec:
    return ContainerSpec(width_mm=300.0, depth_mm=300.0, height_mm=None)


def _box_part(pid: str, name: str, qty: int, w: float, d: float, h: float) -> PartSpec:
    return PartSpec(
        id=pid,
        name=name,
        qty=qty,
        source="box",
        width_mm=round(w, 3),
        depth_mm=round(d, 3),
        height_mm=round(h, 3),
    )


def _uniform(rng: random.Random, lo: float, hi: float) -> float:
    return rng.uniform(lo, hi)


# ---------------------------------------------------------------------------
# Üreticiler
# ---------------------------------------------------------------------------

def random_boxes(
    n_parts: int = 10,
    min_dim: float = 10.0,
    max_dim: float = 80.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Uniform dağılımdan rastgele kutu boyutları üretir.

    Args:
        n_parts:   Parça sayısı (her parça adet=1).
        min_dim:   Her boyut için alt sınır (mm).
        max_dim:   Her boyut için üst sınır (mm).
        container: Konteyner tanımı; None ise 300x300xNone.
        seed:      Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_parts):
        w = _uniform(rng, min_dim, max_dim)
        d = _uniform(rng, min_dim, max_dim)
        h = _uniform(rng, min_dim, max_dim)
        parts.append(_box_part(f"box_{i+1:03d}", f"box_{i+1:03d}", 1, w, d, h))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "random_boxes", "seed": seed, "n_parts": n_parts},
    )


def few_large_many_small(
    n_large: int = 3,
    n_small: int = 12,
    large_min: float = 60.0,
    large_max: float = 120.0,
    small_min: float = 8.0,
    small_max: float = 25.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Az sayıda büyük + çok sayıda küçük parça.

    Args:
        n_large:   Büyük parça sayısı.
        n_small:   Küçük parça sayısı.
        large_min: Büyük parça boyut alt sınırı (mm).
        large_max: Büyük parça boyut üst sınırı (mm).
        small_min: Küçük parça boyut alt sınırı (mm).
        small_max: Küçük parça boyut üst sınırı (mm).
        container: Konteyner tanımı; None ise 300x300xNone.
        seed:      Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_large):
        w = _uniform(rng, large_min, large_max)
        d = _uniform(rng, large_min, large_max)
        h = _uniform(rng, large_min, large_max)
        parts.append(_box_part(f"large_{i+1:02d}", f"large_{i+1:02d}", 1, w, d, h))
    for i in range(n_small):
        w = _uniform(rng, small_min, small_max)
        d = _uniform(rng, small_min, small_max)
        h = _uniform(rng, small_min, small_max)
        parts.append(_box_part(f"small_{i+1:02d}", f"small_{i+1:02d}", 1, w, d, h))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={
            "family": "few_large_many_small",
            "seed": seed,
            "n_large": n_large,
            "n_small": n_small,
        },
    )


def high_qty_repeat(
    n_models: int = 4,
    qty_per_model: int = 8,
    dim_min: float = 15.0,
    dim_max: float = 60.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Az sayıda farklı model, her modelden yüksek adet.

    Tekrar-parça oranı = 1 - n_models / toplam_parça yüksek olacak şekilde
    tasarlanmıştır.

    Args:
        n_models:      Benzersiz model sayısı.
        qty_per_model: Her modelden kaç adet.
        dim_min:       Model boyut alt sınırı (mm).
        dim_max:       Model boyut üst sınırı (mm).
        container:     Konteyner tanımı; None ise 300x300xNone.
        seed:          Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_models):
        w = _uniform(rng, dim_min, dim_max)
        d = _uniform(rng, dim_min, dim_max)
        h = _uniform(rng, dim_min, dim_max)
        parts.append(
            _box_part(f"model_{i+1:02d}", f"model_{i+1:02d}", qty_per_model, w, d, h)
        )
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={
            "family": "high_qty_repeat",
            "seed": seed,
            "n_models": n_models,
            "qty_per_model": qty_per_model,
        },
    )


def thin_plates(
    n_parts: int = 8,
    xy_min: float = 40.0,
    xy_max: float = 150.0,
    thickness_min: float = 3.0,
    thickness_max: float = 12.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """İnce levha parçalar (kalınlık << xy boyutları).

    Poz tercihi kritik: yatay levha yüksekliği thickness_mm, dik levha
    xy_max mm olur.

    Args:
        n_parts:       Parça sayısı.
        xy_min:        Levha X/Y boyutu alt sınırı (mm).
        xy_max:        Levha X/Y boyutu üst sınırı (mm).
        thickness_min: Kalınlık alt sınırı (mm).
        thickness_max: Kalınlık üst sınırı (mm).
        container:     Konteyner tanımı; None ise 300x300xNone.
        seed:          Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_parts):
        w = _uniform(rng, xy_min, xy_max)
        d = _uniform(rng, xy_min, xy_max)
        h = _uniform(rng, thickness_min, thickness_max)
        parts.append(_box_part(f"plate_{i+1:02d}", f"plate_{i+1:02d}", 1, w, d, h))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={
            "family": "thin_plates",
            "seed": seed,
            "n_parts": n_parts,
        },
    )


def long_rods(
    n_parts: int = 8,
    cross_min: float = 5.0,
    cross_max: float = 20.0,
    length_min: float = 100.0,
    length_max: float = 250.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Uzun çubuk/profil parçalar (uzunluk >> kesit boyutları).

    Uzun-çubuk oranı yüksek.  Ry rotasyonu mevcut ise yatırarak daha iyi
    yükseklik elde edilebilir.

    Args:
        n_parts:    Parça sayısı.
        cross_min:  Kesit boyutu alt sınırı (mm).
        cross_max:  Kesit boyutu üst sınırı (mm).
        length_min: Uzunluk alt sınırı (mm).
        length_max: Uzunluk üst sınırı (mm).
        container:  Konteyner tanımı; None ise 300x300xNone.
        seed:       Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_parts):
        cx = _uniform(rng, cross_min, cross_max)
        cy = _uniform(rng, cross_min, cross_max)
        length = _uniform(rng, length_min, length_max)
        # uzunluk her zaman Z (ilk poz) olarak atanır
        parts.append(_box_part(f"rod_{i+1:02d}", f"rod_{i+1:02d}", 1, cx, cy, length))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={
            "family": "long_rods",
            "seed": seed,
            "n_parts": n_parts,
        },
    )
