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

shell_bells:
    İnce cidarlı yarım-küre/çan KABUKLARI (trimesh ile içi boş; cidar ~1mm).
    Düşük true_fill + yüksek shell_score; F1 taksonomisinde 'thin_shell' ailesi.
    Parçalar box-source olarak temsil edilir ama wall_mm/true_fill ölçülür
    (gerçek trimesh kabuk hacim/yüzeyinden 2V/A).
    Parametreler: n_parts, r_min, r_max, wall_min, wall_max, container, seed.

hollow_tubes:
    İnce cidarlı BORULAR (trimesh annulus; uzun + içi boş).  Düşük true_fill +
    yüksek uzama; F1 taksonomisinde 'tube' ailesi.
    Parametreler: n_parts, r_min, r_max, wall_min, wall_max, length_min,
    length_max, container, seed.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

import numpy as np
import trimesh

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


def _shell_partspec(
    pid: str, name: str, qty: int, mesh: "trimesh.Trimesh"
) -> PartSpec:
    """İçi boş bir trimesh KABUK'tan box-source PartSpec üret (wall/true_fill ölçülü).

    Parça voxelize köprüsünde box olarak temsil edilir; ancak wall_mm ve
    true_fill gerçek kabuk geometrisinden (2V/A, V/bbox_vol) ölçülür — böylece
    F1 taksonomisi parçayı thin_shell/tube olarak tanır.  Kati parçalarda
    (true_fill >= 0.5) wall_mm None kalır (shell değildir).

    UYARI: source="box" + stl_path=None oldugundan bu parçalar gerçek
    nesting/voxelize akışına girerse içi-boş geometri KAYBOLUR — bbox'ları
    kadar KATI BLOK olarak istiflenirler. shell_bells/hollow_tubes YALNIZ
    F1 taksonomi / özellik-vektörü / sınıflandırma testleri içindir;
    doluluk-yükseklik benchmark'ında kullanılırsa sonuç yanıltıcı olur.
    """
    mesh.apply_translation(-mesh.bounds[0])
    e = mesh.extents
    w, d, h = float(e[0]), float(e[1]), float(e[2])
    bbox_vol = w * d * h

    volume = abs(float(mesh.volume)) if mesh.is_watertight else None
    area = float(mesh.area)

    true_fill = None
    wall_mm = None
    if volume is not None and volume > 0.0 and bbox_vol > 0.0:
        true_fill = volume / bbox_vol
        if area > 0.0 and true_fill < 0.5:
            wall_mm = 2.0 * volume / area

    return PartSpec(
        id=pid,
        name=name,
        qty=qty,
        source="box",
        width_mm=round(w, 3),
        depth_mm=round(d, 3),
        height_mm=round(h, 3),
        wall_mm=round(wall_mm, 4) if wall_mm is not None else None,
        true_fill=round(true_fill, 6) if true_fill is not None else None,
    )


def _bell_shell_mesh(radius: float, wall: float, sections: int = 48) -> "trimesh.Trimesh":
    """İnce cidarlı yarım-küre/çan kabuğu (revolve ile watertight).

    Dış ve iç yarım-küre profillerini birleştirip 360° döndürür; boolean
    backend GEREKMEZ (deterministik + sağlam).
    """
    ri = max(radius - wall, radius * 0.05)
    n = 40
    th = np.linspace(0.0, np.pi / 2.0, n)
    outer = np.column_stack([radius * np.sin(th), radius * np.cos(th)])
    inner = np.column_stack([ri * np.sin(th[::-1]), ri * np.cos(th[::-1])])
    profile = np.vstack([outer, inner])
    return trimesh.creation.revolve(profile, sections=sections)


# ---------------------------------------------------------------------------
# Üreticiler — F1 shell aileleri
# ---------------------------------------------------------------------------

def shell_bells(
    n_parts: int = 8,
    r_min: float = 20.0,
    r_max: float = 60.0,
    wall_min: float = 0.8,
    wall_max: float = 1.6,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """İnce cidarlı yarım-küre/çan kabukları (thin_shell ailesi).

    Args:
        n_parts:   Kabuk sayısı (her biri adet=1).
        r_min:     Yarıçap alt sınırı (mm).
        r_max:     Yarıçap üst sınırı (mm).
        wall_min:  Cidar kalınlığı alt sınırı (mm).
        wall_max:  Cidar kalınlığı üst sınırı (mm).
        container: Konteyner tanımı; None ise 300x300xNone.
        seed:      Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_parts):
        r = _uniform(rng, r_min, r_max)
        wall = _uniform(rng, wall_min, wall_max)
        mesh = _bell_shell_mesh(r, wall)
        parts.append(
            _shell_partspec(f"bell_{i+1:02d}", f"bell_{i+1:02d}", 1, mesh)
        )
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "shell_bells", "seed": seed, "n_parts": n_parts},
    )


def hollow_tubes(
    n_parts: int = 8,
    r_min: float = 8.0,
    r_max: float = 18.0,
    wall_min: float = 1.0,
    wall_max: float = 2.0,
    length_min: float = 90.0,
    length_max: float = 180.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """İnce cidarlı borular (tube ailesi; uzun + içi boş).

    Args:
        n_parts:    Boru sayısı (her biri adet=1).
        r_min:      Dış yarıçap alt sınırı (mm).
        r_max:      Dış yarıçap üst sınırı (mm).
        wall_min:   Cidar kalınlığı alt sınırı (mm).
        wall_max:   Cidar kalınlığı üst sınırı (mm).
        length_min: Boru boyu alt sınırı (mm).
        length_max: Boru boyu üst sınırı (mm).
        container:  Konteyner tanımı; None ise 300x300xNone.
        seed:       Deterministik üretim için seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_parts):
        r = _uniform(rng, r_min, r_max)
        wall = _uniform(rng, wall_min, wall_max)
        length = _uniform(rng, length_min, length_max)
        r_inner = max(r - wall, r * 0.1)
        mesh = trimesh.creation.annulus(r_min=r_inner, r_max=r, height=length)
        parts.append(
            _shell_partspec(f"tube_{i+1:02d}", f"tube_{i+1:02d}", 1, mesh)
        )
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "hollow_tubes", "seed": seed, "n_parts": n_parts},
    )


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


# ---------------------------------------------------------------------------
# 2026-07-14 eklemeleri (ML plani / 01_VERI §6 sentetik cogaltma)
# ---------------------------------------------------------------------------

def repeat_rod_mix(
    n_rod_models: int = 2,
    qty_per_rod: int = 40,
    n_boxes: int = 8,
    cross_min: float = 6.0,
    cross_max: float = 14.0,
    length_min: float = 80.0,
    length_max: float = 160.0,
    box_min: float = 15.0,
    box_max: float = 55.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """deneme5-sinifi 'tekrarli-orgu' ailesi: az rod-modeli x YUKSEK adet ince
    cubuk + az sayida kutu karisimi (K-44 dersi: bu anatomi NFV'nin ideal
    sahasi — 216x ozdes cubuk). Egitim tablosunda bu ailenin sentetik temsili
    yoktu; mod-secici d5-tipi siparisi hic goremiyordu."""
    rng = random.Random(seed)
    cnt = container or _default_container()
    parts: List[PartSpec] = []
    for i in range(n_rod_models):
        cx = _uniform(rng, cross_min, cross_max)
        cy = _uniform(rng, cross_min, cross_max)
        length = _uniform(rng, length_min, length_max)
        parts.append(_box_part(f"rrm_rod_{i+1:02d}", f"rrm_rod_{i+1:02d}",
                               qty_per_rod, cx, cy, length))
    for i in range(n_boxes):
        w = _uniform(rng, box_min, box_max)
        d = _uniform(rng, box_min, box_max)
        h = _uniform(rng, box_min, box_max)
        parts.append(_box_part(f"rrm_box_{i+1:02d}", f"rrm_box_{i+1:02d}",
                               1, w, d, h))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "repeat_rod_mix", "seed": seed,
              "n_rod_models": n_rod_models, "qty_per_rod": qty_per_rod},
    )


def perturb_instance(
    instance: NestingInstance,
    *,
    seed: int,
    qty_jitter: float = 0.30,
    scale_jitter: float = 0.10,
) -> NestingInstance:
    """Domain randomization (01_VERI §6): qty +-%30, olcek +-%10 jitter.

    Deterministik: ayni (instance, seed) -> ayni varyant. Kaynak izi meta'da
    (source=perturb(<orijinal aile>), perturb_seed). Parca id'lerine _p<seed>
    eki (orijinalle karismasin)."""
    rng = random.Random(seed)
    parts: List[PartSpec] = []
    for p in instance.parts:
        qty = max(1, int(round(p.qty * _uniform(rng, 1.0 - qty_jitter,
                                                1.0 + qty_jitter))))
        s = _uniform(rng, 1.0 - scale_jitter, 1.0 + scale_jitter)
        parts.append(_box_part(f"{p.id}_p{seed}", f"{p.name}_p{seed}", qty,
                               p.width_mm * s, p.depth_mm * s, p.height_mm * s))
    orijinal_aile = (instance.meta or {}).get("family", "unknown")
    return NestingInstance(
        container=instance.container,
        parts=parts,
        meta={"family": orijinal_aile, "source": f"perturb({orijinal_aile})",
              "perturb_seed": seed},
    )
