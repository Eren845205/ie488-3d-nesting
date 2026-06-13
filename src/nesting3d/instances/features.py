"""features.py — Instance özellik vektörü (Faz 2.8, PLAN_DEMO1.md).

Her NestingInstance için ~15-25 sayısal özellik çıkarır.  Özellik adları
FEATURE_NAMES listesinde sabit sıralıdır (CSV kolonu olarak kullanılacak).

Tüm özellikler deterministiktir (seed bağımsız, yalnızca instance geometrisine
bağlıdır).  Aynı instance -> aynı vektör.

Özellik Kategorileri
--------------------
1. Parça Sayısı / Adet
   - n_distinct_parts   : benzersiz model sayısı
   - n_total_parts      : toplam parça adedi (qty toplamı)
   - repeat_part_ratio  : 1 - n_distinct_parts / n_total_parts (0 = hepsi farklı)

2. Boyut Dağılımı (normalize — ölçek bağımsız)
   - mean_volume_norm   : ortalama parça hacmi / konteyner_hacmi
   - std_volume_norm    : hacim std sapması / konteyner_hacmi
   - cv_volume          : hacim varyasyon katsayısı (std/mean; 0 = homojen)
   - max_volume_norm    : en büyük parça hacmi / konteyner_hacmi
   - min_volume_norm    : en küçük parça hacmi / konteyner_hacmi
   - volume_ratio       : max_volume / (min_volume + 1e-9)

3. En-Boy-Yükseklik Oranları
   - mean_aspect_xy     : ortalama max(w,d)/min(w,d) oranı (1 = kare taban)
   - mean_aspect_z      : ortalama max(w,d,h)/min(w,d,h) oranı (1 = küp)
   - std_aspect_z       : aspect_z std sapması

4. Parça Tipi Oranları
   - thin_plate_ratio   : min_dim / max_dim < 0.15 olan parça oranı
   - long_rod_ratio     : max_dim / mid_dim > 5 VE min_dim/max_dim < 0.25 oranı
   - cube_like_ratio    : tüm oranlar 0.5..2.0 arasında olan parça oranı

5. Hacimsel Doluluk Alt Sınırı
   - fill_lb            : sum(part_volumes) / container_volume (0..1+)
                          (konteyner yüksekliği None ise min bbox yüksekliği kullanılır)

6. Konteyner Geometrisi
   - container_xy_ratio : container_width / container_depth
   - n_parts_per_m3     : n_total_parts / (container_volume / 1e9)  [1/m^3]

7. Boyut Sapması
   - max_part_fill_xy   : max(w*d) / (container_w * container_d) — en büyük parça
                          taban alanı / konteyner taban alanı

8. Büyük Parça Oranı
   - large_part_ratio   : hacmi ortalama hacmin 3 katından büyük olan parça oranı
                          (eşik: vol > 3.0 * mean_vol; qty-ağırlıklı sayım).
                          0 = tüm parçalar benzer boyutta; 1 = hepsi "büyük".

Toplam: 20 özellik.
"""

from __future__ import annotations

import math
from typing import Dict, List, NamedTuple

from src.nesting3d.instances.format import NestingInstance, PartSpec


# ---------------------------------------------------------------------------
# Sabit özellik adları listesi (CSV kolonu sırası)
# ---------------------------------------------------------------------------

FEATURE_NAMES: List[str] = [
    # 1. Parça sayısı / adet
    "n_distinct_parts",
    "n_total_parts",
    "repeat_part_ratio",
    # 2. Hacim dağılımı (konteyner hacmine normalize)
    "mean_volume_norm",
    "std_volume_norm",
    "cv_volume",
    "max_volume_norm",
    "min_volume_norm",
    "volume_ratio",
    # 3. En-boy oranları
    "mean_aspect_xy",
    "mean_aspect_z",
    "std_aspect_z",
    # 4. Parça tipi oranları
    "thin_plate_ratio",
    "long_rod_ratio",
    "cube_like_ratio",
    # 5. Doluluk alt sınırı
    "fill_lb",
    # 6. Konteyner geometrisi
    "container_xy_ratio",
    "n_parts_per_m3",
    # 7. Boyut sapması
    "max_part_fill_xy",
    # 8. En büyük parça sayısı
    "large_part_ratio",
]

assert len(FEATURE_NAMES) == 20, "FEATURE_NAMES uzunluğu 20 olmalı"


class FeatureVector(NamedTuple):
    """Sıralı özellik vektörü.

    values: float listesi, FEATURE_NAMES ile birebir eşleşir.
    names:  FEATURE_NAMES (sabit referans).
    """

    values: List[float]
    names: List[str]

    def to_dict(self) -> Dict[str, float]:
        return dict(zip(self.names, self.values))


# ---------------------------------------------------------------------------
# Yardımcı fonksiyonlar
# ---------------------------------------------------------------------------

def _dims(part: PartSpec) -> tuple:
    """(w, d, h) döndür.

    source="box" parçada herhangi bir boyut None ise ValueError fırlatılır.
    source="stl" parçada boyutlar bilinmeyebilir; bu durumda 0.0 kullanılır
    (STL ağırlıklı instance'larda özellik vektörü anlamlı olmayabilir).
    """
    if part.source == "box":
        if part.width_mm is None or part.depth_mm is None or part.height_mm is None:
            raise ValueError(
                f"Parça '{part.id}' (source='box'): width_mm, depth_mm ve "
                f"height_mm alanları zorunludur; None olamaz."
            )
        return (part.width_mm, part.depth_mm, part.height_mm)
    # source="stl": boyutlar dosya okunmadan bilinmez, 0.0 kabul edilir
    w = part.width_mm or 0.0
    d = part.depth_mm or 0.0
    h = part.height_mm or 0.0
    return (w, d, h)


def _sorted_dims(part: PartSpec) -> tuple:
    """(min_dim, mid_dim, max_dim) küçükten büyüğe."""
    w, d, h = _dims(part)
    dims = sorted([w, d, h])
    return tuple(dims)  # (min, mid, max)


def _vol(part: PartSpec) -> float:
    w, d, h = _dims(part)
    return w * d * h


def _mean(xs: List[float]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _std(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


# ---------------------------------------------------------------------------
# Ana fonksiyon
# ---------------------------------------------------------------------------

def extract_features(instance: NestingInstance) -> FeatureVector:
    """NestingInstance -> FeatureVector (deterministik, birim testli).

    Yalnızca box-source parçalar işlenir.  STL-source parçaların boyutları
    bilinmediğinden (dosya okunmadan) boyut sıfır kabul edilir — bu, STL
    source ağırlıklı instance'larda vektörün anlamlı olmayacağını gösterir.

    Args:
        instance: NestingInstance

    Returns:
        FeatureVector — values listesi FEATURE_NAMES ile aynı sırada.
    """
    parts = instance.parts
    container = instance.container

    # --- Parça listesini qty'ye göre genişlet (her birim parça ayrı) -------
    # Özellik hesabı için qty-ağırlıklı istatistik kullanılır.
    # Örn. 5 adet 10mm küp -> 5 kez aynı hacim eklenir.

    n_distinct = len(parts)
    n_total = sum(p.qty for p in parts)

    # Hacimler (qty-ağırlıklı düz liste)
    all_vols: List[float] = []
    for p in parts:
        v = _vol(p)
        for _ in range(p.qty):
            all_vols.append(v)

    # repeat_part_ratio: en az 1 parça her zaman var
    if n_total > 0:
        repeat_ratio = 1.0 - (n_distinct / n_total)
    else:
        repeat_ratio = 0.0

    # Hacim istatistikleri
    # Not: mean_vol, std_vol, max_vol, min_vol hesaplama için mm^3 cinsinden
    # saklanır; FEATURE_NAMES'e yazılmadan önce konteyner hacmine bölünür
    # (ölçek-bağımsızlık — veri sızıntısı riski giderildi).
    mean_vol = _mean(all_vols)
    std_vol = _std(all_vols)
    cv_vol = std_vol / mean_vol if mean_vol > 1e-12 else 0.0
    max_vol = max(all_vols) if all_vols else 0.0
    min_vol = min(all_vols) if all_vols else 0.0
    vol_ratio = max_vol / (min_vol + 1e-9)

    # Aspect oranları (qty-ağırlıklı)
    aspect_xy_list: List[float] = []
    aspect_z_list: List[float] = []
    for p in parts:
        w, d, h = _dims(p)
        mn_d, mid_d, mx_d = sorted([w, d, h])
        aspect_xy = (max(w, d) / (min(w, d) + 1e-9))
        aspect_z = mx_d / (mn_d + 1e-9)
        for _ in range(p.qty):
            aspect_xy_list.append(aspect_xy)
            aspect_z_list.append(aspect_z)

    mean_asp_xy = _mean(aspect_xy_list)
    mean_asp_z = _mean(aspect_z_list)
    std_asp_z = _std(aspect_z_list)

    # Parça tipi oranları (qty-ağırlıklı sayım)
    thin_count = 0
    rod_count = 0
    cube_count = 0
    large_count = 0

    total_vol = sum(all_vols)
    mean_vol_dist = mean_vol  # büyük parça eşiği: ortalama hacmin 3 katı üzeri

    for p in parts:
        mn_d, mid_d, mx_d = _sorted_dims(p)
        thin = (mn_d / (mx_d + 1e-9)) < 0.15
        rod = (mx_d / (mid_d + 1e-9)) > 5.0 and (mn_d / (mx_d + 1e-9)) < 0.25
        cube = all(
            0.5 <= dim_a / (dim_b + 1e-9) <= 2.0
            for dim_a, dim_b in [
                (p.width_mm or 0.0, p.depth_mm or 0.0),
                (p.width_mm or 0.0, p.height_mm or 0.0),
                (p.depth_mm or 0.0, p.height_mm or 0.0),
            ]
        )
        large = _vol(p) > 3.0 * mean_vol_dist if mean_vol_dist > 1e-12 else False
        for _ in range(p.qty):
            if thin:
                thin_count += 1
            if rod:
                rod_count += 1
            if cube:
                cube_count += 1
            if large:
                large_count += 1

    thin_ratio = thin_count / n_total if n_total > 0 else 0.0
    rod_ratio = rod_count / n_total if n_total > 0 else 0.0
    cube_ratio = cube_count / n_total if n_total > 0 else 0.0
    large_ratio = large_count / n_total if n_total > 0 else 0.0

    # Doluluk alt sınırı
    cont_w = container.width_mm
    cont_d = container.depth_mm
    cont_h = container.height_mm

    if cont_h is None:
        # open-dimension: teorik minimum yükseklik = toplam parça hacmi / taban alanı
        base_area = cont_w * cont_d
        min_height = total_vol / (base_area + 1e-12)
        cont_vol = cont_w * cont_d * max(min_height, 1.0)
    else:
        cont_vol = cont_w * cont_d * cont_h

    fill_lb = total_vol / (cont_vol + 1e-12)

    # Hacim özelliklerini konteyner hacmine normalize et (ölçek-bağımsız)
    mean_vol_norm = mean_vol / (cont_vol + 1e-12)
    std_vol_norm = std_vol / (cont_vol + 1e-12)
    max_vol_norm = max_vol / (cont_vol + 1e-12)
    min_vol_norm = min_vol / (cont_vol + 1e-12)

    # Konteyner geometrisi
    cont_xy_ratio = cont_w / (cont_d + 1e-9)
    n_per_m3 = n_total / (cont_vol / 1e9 + 1e-12)

    # max part fill xy
    max_part_wh = max(
        (p.width_mm or 0.0) * (p.depth_mm or 0.0) for p in parts
    ) if parts else 0.0
    max_part_fill_xy = max_part_wh / (cont_w * cont_d + 1e-12)

    values = [
        float(n_distinct),
        float(n_total),
        float(repeat_ratio),
        float(mean_vol_norm),
        float(std_vol_norm),
        float(cv_vol),
        float(max_vol_norm),
        float(min_vol_norm),
        float(vol_ratio),
        float(mean_asp_xy),
        float(mean_asp_z),
        float(std_asp_z),
        float(thin_ratio),
        float(rod_ratio),
        float(cube_ratio),
        float(fill_lb),
        float(cont_xy_ratio),
        float(n_per_m3),
        float(max_part_fill_xy),
        float(large_ratio),
    ]

    assert len(values) == len(FEATURE_NAMES), (
        f"Özellik sayısı uyuşmazlığı: {len(values)} != {len(FEATURE_NAMES)}"
    )

    return FeatureVector(values=values, names=list(FEATURE_NAMES))
