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

holey_frames:
    DELİKLİ DÜZ ÇERÇEVE (kanopi sınıfı; K-62 dağılımsal ailesi) + kule/dolgu
    kutuları.  Çerçeve GERÇEK STL yazılır (source="stl") — box-source kabuk
    tuzağının aksine delik geometrisi nesting akışında korunur.  Ayrık kutu
    partisyonu (boolean'sız, her hücre watertight).  Tasarım parametreleri
    (analitik doluluk/alan-oran/delik listesi) meta["tasarim"]'a yazılır —
    tetik-doğruluğu ölçümleri bağımsız beklentiyi oradan türetir.
    Parametreler: stl_dir (zorunlu), mod ("kucuk"|"buyuk"|None=rastgele),
    n_towers, n_fillers, container, seed.

mass_plate_rod_mix:
    Yüksek-adet homojen ince-plaka kitlesi + az sayıda plaka-aşan dik-çubuk
    karışımı (K-65 dağılımsal smoke prototipinin kalıcı jeneratörü —
    `scripts/k65_dagilim_smoke.py` Aile B ile aynı geometrik tetik; tetik
    aile-adına değil geometriye bağlıdır).  Az sayıda plaka MODELİ yüksek
    adetle tekrarlanır (kitle homojen); az sayıda çubuk modeli, uzunluğu
    konteynerin width/depth boyutundan TÜRETİLEREK (+pay), garanti şekilde
    plakayı aşacak biçimde üretilir — NFV/heightmap mod-seçim tetiğinin
    (K-65 "düz-yatışta sığmayan parça") sentetik karşılığı.
    Parametreler: n_plate_models, qty_per_plate, plate_xy_min, plate_xy_max,
    plate_thickness_min, plate_thickness_max, n_rod_models, qty_per_rod,
    rod_cross_min, rod_cross_max, rod_overhang_min, rod_overhang_max,
    container, seed.
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


def hollow_tubes_stl(
    *,
    stl_dir,
    n_parts: int = 8,
    qty_max: int = 1,
    r_min: float = 8.0,
    r_max: float = 18.0,
    wall_min: float = 1.0,
    wall_max: float = 2.0,
    length_min: float = 90.0,
    length_max: float = 180.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """İnce cidarlı borular — GERÇEK geometriyle (source="stl"), M4 portföyü
    için (2026-09-02, deneme5/tube açık yönü: box-köprü içi-boş geometriyi
    kaybettiği için `hollow_tubes` portföye giremiyordu).

    Her boru stl_dir/hollow_tube_s<seed>_<i>.stl olarak yazılır (C'ye büyük
    dosya yazmama kuralı: çağıran D/scratch dizini vermeli). Parça bbox
    boyutları dolu (holey_frames / stl_order_loader deseni). qty_max>1 ise
    adet 1..qty_max (deneme5 tipi tekrar-adetli sipariş dokusu).
    """
    from pathlib import Path

    rng = random.Random(seed)
    cnt = container or _default_container()
    stl_dir = Path(stl_dir)
    stl_dir.mkdir(parents=True, exist_ok=True)
    parts: List[PartSpec] = []
    for i in range(n_parts):
        r = _uniform(rng, r_min, r_max)
        wall = _uniform(rng, wall_min, wall_max)
        length = _uniform(rng, length_min, length_max)
        qty = rng.randint(1, max(1, int(qty_max)))
        r_inner = max(r - wall, r * 0.1)
        mesh = trimesh.creation.annulus(r_min=r_inner, r_max=r, height=length)
        mesh.apply_translation(-mesh.bounds[0])
        yol = stl_dir / f"hollow_tube_s{seed}_{i+1:02d}.stl"
        mesh.export(yol)
        e = mesh.extents
        parts.append(PartSpec(
            id=f"tube_{i+1:02d}", name=f"tube_{i+1:02d}", qty=qty,
            source="stl", stl_path=str(yol),
            width_mm=round(float(e[0]), 3), depth_mm=round(float(e[1]), 3),
            height_mm=round(float(e[2]), 3)))
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "hollow_tubes", "seed": seed, "n_parts": n_parts,
              "qty_max": qty_max, "source": "stl"},
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


def mass_plate_rod_mix(
    n_plate_models: int = 2,
    qty_per_plate: int = 300,
    plate_xy_min: float = 30.0,
    plate_xy_max: float = 110.0,
    plate_thickness_min: float = 3.0,
    plate_thickness_max: float = 10.0,
    n_rod_models: int = 3,
    qty_per_rod: int = 3,
    rod_cross_min: float = 8.0,
    rod_cross_max: float = 20.0,
    rod_overhang_min: float = 5.0,
    rod_overhang_max: float = 125.0,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Yuksek-adet ince-plaka kitlesi + plaka-asan cubuk karisimi (K-65 aile).

    Az sayida plaka MODELI (n_plate_models) yuksek adetle (qty_per_plate)
    tekrarlanir -> kitle homojen ve sayica baskin. Az sayida cubuk MODELI
    (n_rod_models), uzunlugu konteynerin max(width_mm, depth_mm) degerinden
    turetilerek (+rod_overhang payi) garanti sekilde duz-yatista plakaya
    SIGMAYACAK olacak sekilde uretilir (sabit sayi gomulmez; tetik
    `scripts/k65_dagilim_smoke.py` Aile B ile ayni geometrik tanimdadir).

    Args:
        n_plate_models:       Benzersiz ince-plaka modeli sayisi (az; 1-3).
        qty_per_plate:        Her plaka modelinden adet (yuksek; 200-800
                               bandi tipik).
        plate_xy_min:         Plaka X/Y boyutu alt siniri (mm).
        plate_xy_max:         Plaka X/Y boyutu ust siniri (mm).
        plate_thickness_min:  Plaka kalinligi alt siniri (mm).
        plate_thickness_max:  Plaka kalinligi ust siniri (mm).
        n_rod_models:         Benzersiz cubuk modeli sayisi (az).
        qty_per_rod:          Her cubuk modelinden adet.
        rod_cross_min:        Cubuk kesit boyutu alt siniri (mm).
        rod_cross_max:        Cubuk kesit boyutu ust siniri (mm).
        rod_overhang_min:     Cubuk uzunlugunun konteyner max(w,d)'yi asma
                               payi alt siniri (mm).
        rod_overhang_max:     Ayni payin ust siniri (mm).
        container:            Konteyner tanimi; None ise 300x300xNone.
        seed:                 Deterministik uretim icin seed.

    Returns:
        NestingInstance
    """
    rng = random.Random(seed)
    cnt = container or _default_container()
    taban = max(float(cnt.width_mm), float(cnt.depth_mm))
    parts: List[PartSpec] = []
    for i in range(n_plate_models):
        w = _uniform(rng, plate_xy_min, plate_xy_max)
        d = _uniform(rng, plate_xy_min, plate_xy_max)
        h = _uniform(rng, plate_thickness_min, plate_thickness_max)
        parts.append(
            _box_part(f"mprm_plate_{i+1:02d}", f"mprm_plate_{i+1:02d}",
                      qty_per_plate, w, d, h)
        )
    for i in range(n_rod_models):
        cx = _uniform(rng, rod_cross_min, rod_cross_max)
        cy = _uniform(rng, rod_cross_min, rod_cross_max)
        length = taban + _uniform(rng, rod_overhang_min, rod_overhang_max)
        parts.append(
            _box_part(f"mprm_rod_{i+1:02d}", f"mprm_rod_{i+1:02d}",
                      qty_per_rod, cx, cy, length)
        )
    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={
            "family": "mass_plate_rod_mix",
            "seed": seed,
            "n_plate_models": n_plate_models,
            "qty_per_plate": qty_per_plate,
            "n_rod_models": n_rod_models,
            "qty_per_rod": qty_per_rod,
        },
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

# ---------------------------------------------------------------------------
# holey_frames — delikli düz çerçeve (kanopi sınıfı; K-62 dağılımsal ailesi)
# ---------------------------------------------------------------------------

def _cerceve_mesh(fw: float, fd: float, t: float,
                  delikler: List[Tuple[float, float, float, float]]
                  ) -> "trimesh.Trimesh":
    """fw x fd x t plakadan delikler çıkarılmış çerçeve — ızgara-ekstrüzyon
    (delik kenarlarından x/y kesitleri; dolu hücrelerin üst/alt yüzleri +
    dolu/boş sınırlarında duvarlar; ORTAK vertex'li TEK watertight mesh).

    Kutu-birleştirme denemesi NO-GO: çakışık yüzeyler slice-voxelize
    paritesinde delikleri dolduruyordu; extrude_polygon ise triangulation
    engine bağımlılığı istiyor. Bu yol bağımlılıksız ve deterministik."""
    xs = sorted({0.0, fw, *[d[0] for d in delikler], *[d[2] for d in delikler]})
    ys = sorted({0.0, fd, *[d[1] for d in delikler], *[d[3] for d in delikler]})
    nx, ny = len(xs) - 1, len(ys) - 1

    def dolu(i: int, j: int) -> bool:
        if i < 0 or j < 0 or i >= nx or j >= ny:
            return False
        x1, x2, y1, y2 = xs[i], xs[i + 1], ys[j], ys[j + 1]
        if x2 - x1 < 1e-9 or y2 - y1 < 1e-9:
            return False
        return not any(d[0] - 1e-9 <= x1 and x2 <= d[2] + 1e-9
                       and d[1] - 1e-9 <= y1 and y2 <= d[3] + 1e-9
                       for d in delikler)

    verts: List[Tuple[float, float, float]] = []
    vix = {}

    def v(x: float, y: float, z: float) -> int:
        k = (round(x, 6), round(y, 6), round(z, 6))
        if k not in vix:
            vix[k] = len(verts)
            verts.append(k)
        return vix[k]

    faces: List[Tuple[int, int, int]] = []

    def quad(a, b, c, d):  # a-b-c-d çevrimi (dışa bakan CCW)
        faces.append((a, b, c))
        faces.append((a, c, d))

    for i in range(nx):
        for j in range(ny):
            if not dolu(i, j):
                continue
            x1, x2, y1, y2 = xs[i], xs[i + 1], ys[j], ys[j + 1]
            # üst yüz (+Z) CCW yukarıdan
            quad(v(x1, y1, t), v(x2, y1, t), v(x2, y2, t), v(x1, y2, t))
            # alt yüz (-Z)
            quad(v(x1, y1, 0), v(x1, y2, 0), v(x2, y2, 0), v(x2, y1, 0))
            # duvarlar: komşu boşsa
            if not dolu(i - 1, j):  # -X duvarı
                quad(v(x1, y1, 0), v(x1, y1, t), v(x1, y2, t), v(x1, y2, 0))
            if not dolu(i + 1, j):  # +X duvarı
                quad(v(x2, y1, 0), v(x2, y2, 0), v(x2, y2, t), v(x2, y1, t))
            if not dolu(i, j - 1):  # -Y duvarı
                quad(v(x1, y1, 0), v(x2, y1, 0), v(x2, y1, t), v(x1, y1, t))
            if not dolu(i, j + 1):  # +Y duvarı
                quad(v(x1, y2, 0), v(x1, y2, t), v(x2, y2, t), v(x2, y2, 0))

    mesh = trimesh.Trimesh(vertices=np.asarray(verts, dtype=float),
                           faces=np.asarray(faces, dtype=np.int64),
                           process=False)
    mesh.fix_normals()
    return mesh


def holey_frames(
    *,
    stl_dir,
    mod: Optional[str] = None,
    n_towers: int = 4,
    n_fillers: int = 5,
    container: Optional[ContainerSpec] = None,
    seed: int = 0,
) -> NestingInstance:
    """Delikli düz çerçeve + kule/dolgu kutuları (K-62 kanopi ailesi).

    mod="kucuk": küçük çerçeve — alan-oran tetik sınırının iki yanında
        (0.20..0.55 bandı), delikler bol (doluluk ateş tarafı), fd <= 302
        (no-go'dan dy ile kaçabilir -> fizibilite trivial).
    mod="buyuk": plaka-boyu çerçeve — alan-oran hep yüksek; doluluk VE
        kenar-çentiği (y=0 kenarında delik satırı) sınırın iki yanında
        örneklenir; fd >= 305 (no-go üstünden geçmek zorunda).
    mod=None: seed'e göre iki moddan biri.

    Çerçeve STL'i stl_dir/holey_frame_s<seed>.stl olarak yazılır (C'ye
    büyük dosya yazmama kuralı: çağıran D/scratch dizini vermeli).
    meta["tasarim"]: fw/fd/t/delikler/doluluk_analitik/alan_oran_analitik/
    centik_w/centik_d — bağımsız tetik-beklentisi türetimi için.
    """
    from pathlib import Path

    rng = random.Random(seed)
    cnt = container or ContainerSpec(width_mm=335.0, depth_mm=335.0,
                                     height_mm=None)
    W, D = float(cnt.width_mm), float(cnt.depth_mm)
    if mod is None:
        mod = "kucuk" if rng.random() < 0.5 else "buyuk"

    t = _uniform(rng, 3.0, 8.0)
    if mod == "kucuk":
        fw = _uniform(rng, 150.0, 250.0)
        fd = _uniform(rng, 150.0, min(250.0, D - 33.0 - 1.0))
        nx = ny = 2
        hedef_doluluk = rng.choice([_uniform(rng, 0.42, 0.56),
                                    _uniform(rng, 0.64, 0.80)])
        centik = False
    else:
        fw = _uniform(rng, 300.0, min(330.0, W - 2.0))
        fd = _uniform(rng, 305.0, min(330.0, D - 2.0))
        nx, ny = rng.choice([(2, 2), (3, 2), (3, 3)])
        hedef_doluluk = rng.choice([_uniform(rng, 0.42, 0.56),
                                    _uniform(rng, 0.64, 0.80)])
        centik = rng.random() < 0.7  # %70 fizibil taraf

    # Delik boyutu hedef doluluktan: n delik, toplam alan = (1-doluluk)*fw*fd
    delik_alan = (1.0 - hedef_doluluk) * fw * fd / (nx * ny)
    oran = _uniform(rng, 0.7, 1.4)  # hw/hd en-boy
    hd = min((delik_alan / oran) ** 0.5, fd / (ny + 0.5))
    hw = min(delik_alan / hd, fw / (nx + 0.5))
    if centik:
        hw = max(hw, 36.0)  # no-go (33.0mm) geçişine yeter — fizibil taraf
        hd = max(hd, 36.0)
    else:
        hw = min(hw, 30.0) if mod == "buyuk" else hw  # çentiksiz büyükte
        # delikler no-go'dan dar -> fizibilite analitik NEGATİF taraf

    gx = (fw - nx * hw) / (nx + 1)
    delikler: List[Tuple[float, float, float, float]] = []
    for i in range(nx):
        x1 = gx + i * (hw + gx)
        for j in range(ny):
            if centik and j == 0:
                y1 = 0.0  # kenar çentiği: y=0 kenarına açık satır
            else:
                gy = (fd - ny * hd) / (ny + 1)
                y1 = gy + j * (hd + gy)
            delikler.append((round(x1, 3), round(y1, 3),
                             round(x1 + hw, 3), round(y1 + hd, 3)))

    mesh = _cerceve_mesh(fw, fd, t, delikler)
    stl_dir = Path(stl_dir)
    stl_dir.mkdir(parents=True, exist_ok=True)
    yol = stl_dir / f"holey_frame_s{seed}.stl"
    mesh.export(yol)

    delik_alan_top = sum((d[2] - d[0]) * (d[3] - d[1]) for d in delikler)
    doluluk_analitik = 1.0 - delik_alan_top / (fw * fd)
    e = mesh.extents  # uretim stl_order_loader deseni: bbox boyutlari dolu
    parts: List[PartSpec] = [PartSpec(
        id="frame", name="frame", qty=1, source="stl", stl_path=str(yol),
        width_mm=round(float(e[0]), 3), depth_mm=round(float(e[1]), 3),
        height_mm=round(float(e[2]), 3))]

    kule_kesit_max = max(10.0, min(hw, hd) - 6.0)
    for i in range(n_towers):
        c = _uniform(rng, 8.0, kule_kesit_max)
        parts.append(_box_part(f"tw{i}", f"tw{i}", rng.randint(1, 2),
                               c, _uniform(rng, 8.0, kule_kesit_max),
                               _uniform(rng, 40.0, 90.0)))
    for i in range(n_fillers):
        parts.append(_box_part(f"fl{i}", f"fl{i}", 1,
                               _uniform(rng, 15.0, 55.0),
                               _uniform(rng, 15.0, 55.0),
                               _uniform(rng, 8.0, 30.0)))

    return NestingInstance(
        container=cnt,
        parts=parts,
        meta={"family": "holey_frames", "seed": seed, "mod": mod,
              "tasarim": {
                  "fw": round(fw, 3), "fd": round(fd, 3), "t": round(t, 3),
                  "delikler": [list(d) for d in delikler],
                  "doluluk_analitik": round(doluluk_analitik, 4),
                  "alan_oran_analitik": round(fw * fd / (W * D), 4),
                  "centik": centik,
                  "centik_w": round(hw, 3) if centik else None,
                  "centik_d": round(hd, 3) if centik else None,
              }},
    )
