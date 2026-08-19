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

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec


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

    box-source parçalarda boyutlar PartSpec'te dolu gelir.  STL-source
    parçalarda boyutlar da genellikle dolu gelir: stl_order_loader parçayı
    kurarken bounding-box extents'i width_mm/depth_mm/height_mm alanlarına
    yazar.  Boyut yine de eksikse (None) 0.0 kabul edilir.

    NOT (F1 taksonomisi): Bu fonksiyonun döndürdüğü 20-uzunluklu vektör
    DONMUŞ bir sözleşmedir (seçim modeli onu tüketir) — adı/sırası/değeri
    değişmez.  Yeni aile-farkında özellikler (wall_est/true_fill_mean/
    shell_score) için extract_features_extended / extract_family_features
    kullanılır (bu vektörü SONA ekler, mevcut 20'yi bozmaz).

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


# ---------------------------------------------------------------------------
# F1 aile-farkında özellikler (ADDITIVE — mevcut 20-vektör DONMUŞ kalır)
# ---------------------------------------------------------------------------
#
# Tasarım kararı: extract_features() ve FEATURE_NAMES (20) hiç değiştirilmedi;
# yeni özellikler ayrı bir uzatılmış API üzerinden verilir.  Böylece 20-uzunluklu
# vektörü tüketen seçim modeli ve mevcut testler BOZULMAZ; yeni tüketiciler
# uzatılmış vektörün SONUNA eklenmiş 3 aile özelliğini alır.

FAMILY_FEATURE_NAMES: List[str] = [
    "wall_est",         # parçaların en ince tahmini cidarı (mm); shell yoksa 0.0
    "true_fill_mean",   # qty-ağırlıklı ortalama gerçek doluluk (0..1)
    "shell_score",      # qty-ağırlıklı 0..1 kabuklaşma skoru (birimsiz)
]

# Uzatılmış vektör: mevcut 20 + 3 (SONA eklenmiş).
EXTENDED_FEATURE_NAMES: List[str] = list(FEATURE_NAMES) + list(FAMILY_FEATURE_NAMES)


def _wall_est(parts: List[PartSpec]) -> float:
    """Parçaların wall_mm'lerinden en ince cidar (None'lar dışlanır).

    Hiç shell/wall yoksa güvenli varsayılan 0.0 (shell bilgisi yok).
    """
    walls = [p.wall_mm for p in parts if p.wall_mm is not None and p.wall_mm > 0.0]
    if not walls:
        return 0.0
    return float(min(walls))


def _effective_true_fill(part: PartSpec) -> float:
    """Parça için etkin doluluk (qty-ağırlıklı ortalamada kullanılır).

    box-source: true_fill yoksa 1.0 (tanım gereği dolu kutu).
    stl-source: true_fill dolu ise o değer; None ise ölçülememiş -> atlanır
                (çağıran skip eder).
    """
    if part.true_fill is not None:
        return float(part.true_fill)
    if part.source == "box":
        return 1.0
    return -1.0  # sentinel: ölçülememiş stl (çağıran atlar)


def _true_fill_mean(parts: List[PartSpec]) -> float:
    """qty-ağırlıklı ortalama gerçek doluluk (ölçülememiş stl'ler dışlanır)."""
    total = 0.0
    n = 0
    for p in parts:
        tf = _effective_true_fill(p)
        if tf < 0.0:
            continue
        q = max(int(p.qty), 0)
        total += tf * q
        n += q
    if n == 0:
        return 1.0  # bilgi yoksa kati varsay (nötr)
    return total / n


def _part_shell_score(part: PartSpec) -> float:
    """Tek parça kabuklaşma skoru (0..1); wall_mm/min_bbox_kenar oranından türer.

    r = wall_mm / min_bbox_kenar.  İnce cidar (küçük r) -> yüksek skor.
    r <= 0.05 -> 1.0 (belirgin kabuk);  r >= 0.20 -> 0.0 (kabuk değil).
    wall_mm yoksa (kati) -> 0.0.
    """
    if part.wall_mm is None or part.wall_mm <= 0.0:
        return 0.0
    edges = [e for e in (part.width_mm, part.depth_mm, part.height_mm)
             if e is not None and e > 0.0]
    if not edges:
        return 0.0
    min_edge = min(edges)
    r = part.wall_mm / min_edge
    lo, hi = 0.05, 0.20
    if r <= lo:
        return 1.0
    if r >= hi:
        return 0.0
    return (hi - r) / (hi - lo)


def _shell_score(parts: List[PartSpec]) -> float:
    """qty-ağırlıklı ortalama kabuklaşma skoru (0..1)."""
    total = 0.0
    n = 0
    for p in parts:
        s = _part_shell_score(p)
        q = max(int(p.qty), 0)
        total += s * q
        n += q
    if n == 0:
        return 0.0
    return total / n


def extract_family_features(instance: NestingInstance) -> Dict[str, float]:
    """Yalnızca F1 aile-farkında 3 özelliği döndür (isim->değer)."""
    parts = instance.parts
    return {
        "wall_est": float(_wall_est(parts)),
        "true_fill_mean": float(_true_fill_mean(parts)),
        "shell_score": float(_shell_score(parts)),
    }


def extract_features_extended(instance: NestingInstance) -> FeatureVector:
    """20 temel özellik + 3 aile özelliği (SONA eklenmiş) -> FeatureVector.

    values[0:20] extract_features() ile BİREBİR aynıdır; [20:23] aile
    özellikleridir.  names = EXTENDED_FEATURE_NAMES.
    """
    base = extract_features(instance)
    fam = extract_family_features(instance)
    values = list(base.values) + [
        fam["wall_est"], fam["true_fill_mean"], fam["shell_score"],
    ]
    return FeatureVector(values=values, names=list(EXTENDED_FEATURE_NAMES))


# ---------------------------------------------------------------------------
# M5 özellik ekleri (ADDITIVE — STRATEJI/ML_YENIDEN_YAPILANMA_PLANI_2026-08-18
# §3.2 / §6 M5): 20 temel + 3 aile (F1) vektörü DONMUŞ kalır; bu grup EXTENDED
# desenini izleyerek SONA eklenir.  Mevcut extract_features /
# extract_features_extended tüketicileri (seçim modeli, persistence) ETKİLENMEZ.
#
# solidity_proxy kararı: PartSpec.true_fill zaten "gerçek hacim / bbox hacmi"
# (watertight ölçüm; bkz. format.py PartSpec.true_fill docstring'i) taşıyor —
# ayrı bir ham hacim alanı (volume_mm3) YOK ve gerek de yok; solidity_proxy bu
# alanın qty-ağırlıklı ortalamasıdır (_true_fill_mean ile birebir aynı hesap,
# kod tekrarını önlemek için o fonksiyon yeniden kullanılır).

M5_FEATURE_NAMES: List[str] = [
    "plaka_asan_ratio",  # düz yatışta (büyük x orta taban) konteynere eksen-hizalı
                         # sığmayan parçaların adet-ağırlıklı oranı (K-65 sinyalinin
                         # sürekli hâli; bkz. adaptive_params._duz_yatista_sigmayan_parca)
    "log_n_total",       # log10(1 + toplam parça adedi) — ölçek bandı
    "solidity_proxy",    # true_fill'in adet-ağırlıklı ortalaması (K-62: ML delikli
                         # parçayı GÖREMİYOR bulgusunun sürekli sinyali)
]

# Tam vektör: mevcut 20 + 3 (aile) + 3 (M5) = 26 (SONA eklenmiş).
FULL_FEATURE_NAMES: List[str] = list(EXTENDED_FEATURE_NAMES) + list(M5_FEATURE_NAMES)


def _plaka_asan_ratio(parts: List[PartSpec], container: ContainerSpec) -> float:
    """Düz yatışta konteynere eksen-hizalı sığmayan parçaların adet-ağırlıklı oranı.

    Mantık adaptive_params._duz_yatista_sigmayan_parca ile birebir aynıdır
    (kopyalanmıştır — instances katmanı adaptive_params'a bağımlı olmamalı,
    alt katman üst katmana bağımlılık kurmaz); farkı: ilk-bulunanı değil,
    TÜM parçalar üzerinde adet-ağırlıklı ORANI döndürür.

    Konteyner boyutu yoksa/geçersizse 0.0 (konservatif, tetik yok — eski
    davranışla tutarlı).
    """
    pw = float(container.width_mm or 0.0)
    pd = float(container.depth_mm or 0.0)
    if pw <= 0.0 or pd <= 0.0:
        return 0.0
    total_qty = 0
    asan_qty = 0
    for p in parts:
        w, d, h = _dims(p)
        _mn, orta, buyuk = sorted((w, d, h))
        fits = (buyuk <= pw and orta <= pd) or (buyuk <= pd and orta <= pw)
        q = max(int(p.qty), 0)
        total_qty += q
        if not fits:
            asan_qty += q
    if total_qty == 0:
        return 0.0
    return asan_qty / total_qty


def extract_m5_features(instance: NestingInstance) -> Dict[str, float]:
    """Yalnızca M5 özellik grubunu döndür (isim->değer)."""
    parts = instance.parts
    n_total = sum(max(int(p.qty), 0) for p in parts)
    return {
        "plaka_asan_ratio": float(_plaka_asan_ratio(parts, instance.container)),
        "log_n_total": float(math.log10(1.0 + n_total)),
        "solidity_proxy": float(_true_fill_mean(parts)),
    }


def extract_features_full(instance: NestingInstance) -> FeatureVector:
    """20 temel + 3 aile (F1) + 3 M5 özelliği (SONA eklenmiş) -> FeatureVector.

    values[0:20] extract_features() ile BİREBİR aynıdır; [20:23] aile
    (wall_est/true_fill_mean/shell_score); [23:26] M5
    (plaka_asan_ratio/log_n_total/solidity_proxy).  names = FULL_FEATURE_NAMES.
    """
    ext = extract_features_extended(instance)
    m5 = extract_m5_features(instance)
    values = list(ext.values) + [
        m5["plaka_asan_ratio"], m5["log_n_total"], m5["solidity_proxy"],
    ]
    return FeatureVector(values=values, names=list(FULL_FEATURE_NAMES))
