"""checks.py — Pipeline asamasi deterministik kontroller.

Her fonksiyon salt-okunur; pipeline verisine dokunmaz.
LLM bagimliligi YOK.

Fonksiyonlar:
    check_parse(data)    -> List[Finding]
    check_nest(data)     -> List[Finding]
    check_price(data)    -> List[Finding]
    check_priority(data) -> List[Finding]

Finding dataclass:
    asama    : pipeline asamasi ("parse"|"nest"|"fiyat"|"oncelik")
    kod      : makine-okunabilir bulgu kodu (ornek: "PARSE_NEG_BOYUT")
    severity : "low" | "med" | "high"
    baslik   : kisa Turkce baslik
    ham_detay: sayilar iceren detay dizesi
    metrik   : metrik dict (sayi referanslari icin)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.watcher.thresholds import WatcherThresholds

logger = logging.getLogger(__name__)

# Paylasilan esik ornegi (import maliyeti bir kez)
_DEFAULT_THRESHOLDS = WatcherThresholds()


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """Tek bir deterministik denetci bulgusunu temsil eder.

    Alanlar
    -------
    asama    : bulgunun ilgili oldugu pipeline asamasi
    kod      : makine-okunabilir kod ("PARSE_NEG_BOYUT" gibi)
    severity : "low" | "med" | "high"
    baslik   : kisa Turkce baslik (operatore gosterilecek)
    ham_detay: sayi ve esik bilgilerini iceren ham detay dizesi
    metrik   : ek sayisal metrikler (topraklama icin kaynak)
    """

    asama: str
    kod: str
    severity: str          # "low" | "med" | "high"
    baslik: str
    ham_detay: str
    metrik: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PARSE sonrasi kontroller
# ---------------------------------------------------------------------------


def check_parse(
    data: Dict[str, Any],
    thresholds: Optional[WatcherThresholds] = None,
) -> List[Finding]:
    """Parse ciktisini denetler.

    Beklenen data anahtarlari:
        parts              : list of part dicts (width_mm, depth_mm, height_mm)
        missing_field_ratio: eksik alan orani (0-1)
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    findings: List[Finding] = []
    parts: List[Dict[str, Any]] = data.get("parts", [])
    missing_ratio: float = float(data.get("missing_field_ratio", 0.0))

    # 1. Negatif / sifir boyut kontrolu
    for p in parts:
        for dim in ("width_mm", "depth_mm", "height_mm"):
            val = p.get(dim)
            if val is None:
                continue
            val = float(val)
            if val <= 0.0:
                findings.append(Finding(
                    asama="parse",
                    kod="PARSE_NEG_BOYUT",
                    severity="high",
                    baslik="Negatif veya sifir boyut tespit edildi",
                    ham_detay=f"{dim}={val}",
                    metrik={dim: val},
                ))
                break  # ayni parca icin bir kez yeterli

    # 2. Eksik alan orani esigi
    if missing_ratio > t.parse_missing_field_ratio_max:
        findings.append(Finding(
            asama="parse",
            kod="PARSE_EKSIK_ALAN",
            severity="med",
            baslik="Yuksek eksik alan orani",
            ham_detay=(
                f"missing_ratio={missing_ratio:.2%}, "
                f"esik={t.parse_missing_field_ratio_max:.2%}"
            ),
            metrik={"missing_ratio": missing_ratio, "esik": t.parse_missing_field_ratio_max},
        ))

    # 3. Boyut sigma-sapma (en az 3 parca gerekir)
    # MAD (Medyan Mutlak Sapma) tabanli: outlier etkisine karsi saglamdir.
    if len(parts) >= t.parse_sigma_min_parts:
        vols = []
        for p in parts:
            w = float(p.get("width_mm", 0.0) or 0.0)
            d = float(p.get("depth_mm", 0.0) or 0.0)
            h = float(p.get("height_mm", 0.0) or 0.0)
            if w > 0 and d > 0 and h > 0:
                vols.append(w * d * h)

        if len(vols) >= t.parse_sigma_min_parts:
            sorted_vols = sorted(vols)
            n = len(sorted_vols)
            # Standart median: cift-n'de iki orta elemanin ortalamasi (ust-orta
            # yanliligi yok); tek-n'de (n-1)//2 == n//2 -> orta eleman.
            median_v = (sorted_vols[(n - 1) // 2] + sorted_vols[n // 2]) / 2.0
            abs_dev = sorted(abs(v - median_v) for v in sorted_vols)
            mad = (abs_dev[(n - 1) // 2] + abs_dev[n // 2]) / 2.0
            # MAD == 0: tum hacimler ozdes (tekduze kume) -> anomali degil,
            # sigma kontrolunu atla. Yapay 1.0 fallback saci-dar esik uretip
            # tekduze siparislerde sahte alarm dogurur, kaldirildi.
            if mad > 0:
                mad_std = mad * 1.4826  # MAD * 1.4826 ~ normal std tahmini
                esik = median_v + t.parse_sigma_multiplier * mad_std
                aykirilar = [v for v in vols if v > esik]
            else:
                aykirilar = []
            if aykirilar:
                findings.append(Finding(
                    asama="parse",
                    kod="PARSE_SIGMA_SAPMA",
                    severity="med",
                    baslik="Parca boyutunda aykiri sapma",
                    ham_detay=(
                        f"aykiri_parca_sayisi={len(aykirilar)}, "
                        f"medyan_hacim={median_v:.1f}, mad={mad:.1f}"
                    ),
                    metrik={
                        "aykiri_sayisi": len(aykirilar),
                        "medyan_hacim": median_v,
                        "mad": mad,
                    },
                ))

    return findings


# ---------------------------------------------------------------------------
# NEST sonrasi kontroller
# ---------------------------------------------------------------------------


def check_nest(
    data: Dict[str, Any],
    thresholds: Optional[WatcherThresholds] = None,
) -> List[Finding]:
    """Nesting ciktisini denetler.

    Beklenen data anahtarlari:
        density               : doluluk orani (0-1)
        height_mm             : yerlesim yuksekligi
        container_height_mm   : konteyner toplam yuksekligi (opsiyonel)
        n_parts               : toplam parca sayisi
        n_placed              : yerlestirilen parca sayisi
        baseline_median_density: opsiyonel medyan referans
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    findings: List[Finding] = []

    density = float(data.get("density", 0.0))
    height_mm = float(data.get("height_mm", 0.0))
    container_h = data.get("container_height_mm")
    n_parts = int(data.get("n_parts", 0))
    n_placed = int(data.get("n_placed", n_parts))  # yoksa hepsinin yerlestigini varsay

    # Baseline medyan: data'dan geliyorsa kullan; yoksa thresholds'a sor
    bm = data.get("baseline_median_density")
    if bm is not None:
        # Override: gecici thresholds nesnesi yerine dogrudan hesapla
        effective_min = float(bm) * (1.0 - t.nest_density_tolerance)
    else:
        effective_min = t.effective_nest_density_min()

    # 1. Doluluk esigi
    if density < effective_min:
        findings.append(Finding(
            asama="nest",
            kod="NEST_DOLULUK_DUSUK",
            severity="med",
            baslik="Doluluk beklenenin altinda",
            ham_detay=(
                f"density={density:.3f}, "
                f"beklenen_min={effective_min:.3f}"
            ),
            metrik={"density": density, "beklenen_min": effective_min},
        ))

    # 2. Yukseklik/konteyner orani
    if container_h is not None and container_h > 0:
        oran = height_mm / float(container_h)
        if oran > t.nest_height_ratio_max:
            findings.append(Finding(
                asama="nest",
                kod="NEST_YUKSEKLIK_ASIM",
                severity="med",
                baslik="Yerlesim yuksekligi konteyner sinirina cok yakin",
                ham_detay=(
                    f"height_mm={height_mm:.1f}, "
                    f"container_height_mm={container_h:.1f}, "
                    f"oran={oran:.3f}, esik={t.nest_height_ratio_max}"
                ),
                metrik={
                    "height_mm": height_mm,
                    "container_height_mm": float(container_h),
                    "oran": oran,
                },
            ))

    # 3. Yerlesmeyen parca
    if n_parts > 0 and n_placed < n_parts:
        unplaced = n_parts - n_placed
        findings.append(Finding(
            asama="nest",
            kod="NEST_YERLESMEYEN_PARCA",
            severity="high",
            baslik="Bir veya daha fazla parca konteyner dis inda kaldi",
            ham_detay=(
                f"n_parts={n_parts}, n_placed={n_placed}, "
                f"unplaced={unplaced}"
            ),
            metrik={"n_parts": n_parts, "n_placed": n_placed, "unplaced": unplaced},
        ))

    return findings


# ---------------------------------------------------------------------------
# FIYAT sonrasi kontroller
# ---------------------------------------------------------------------------


def check_price(
    data: Dict[str, Any],
    thresholds: Optional[WatcherThresholds] = None,
) -> List[Finding]:
    """Fiyatlama ciktisini denetler.

    Beklenen data anahtarlari:
        total_price : nihai fiyat
        median_price: gecmis benzer is medyani (opsiyonel; yoksa oran atlanir)
        min_clamp   : minimum fiyat sabiti
        breakdown   : [{"rule_id": ..., "subtotal_after": float}, ...]
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    findings: List[Finding] = []

    total = float(data.get("total_price", 0.0))
    median = data.get("median_price")
    min_clamp = data.get("min_clamp")
    breakdown = data.get("breakdown", [])

    # 1. Total/medyan oran kontrolu
    if median is not None:
        median_f = float(median)
        if median_f > 0:
            oran = total / median_f
            if oran < t.price_ratio_min:
                findings.append(Finding(
                    asama="fiyat",
                    kod="FIYAT_ORAN_DUSUK",
                    severity="med",
                    baslik="Fiyat gecmis benzerlerinden anormal dusuk",
                    ham_detay=(
                        f"total={total:.2f}, medyan={median_f:.2f}, "
                        f"oran={oran:.2f}, esik_min={t.price_ratio_min}"
                    ),
                    metrik={"total": total, "medyan": median_f, "oran": oran},
                ))
            elif oran > t.price_ratio_max:
                findings.append(Finding(
                    asama="fiyat",
                    kod="FIYAT_ORAN_YUKSEK",
                    severity="high",
                    baslik="Fiyat gecmis benzerlerinden anormal yuksek",
                    ham_detay=(
                        f"total={total:.2f}, medyan={median_f:.2f}, "
                        f"oran={oran:.2f}, esik_max={t.price_ratio_max}"
                    ),
                    metrik={"total": total, "medyan": median_f, "oran": oran},
                ))

    # 2. Min-clamp takili
    if min_clamp is not None:
        min_f = float(min_clamp)
        if abs(total - min_f) < 0.01:  # float karsilastirma toleransi
            findings.append(Finding(
                asama="fiyat",
                kod="FIYAT_MIN_CLAMP",
                severity="low",
                baslik="Fiyat minimum sinira takili",
                ham_detay=(
                    f"total={total:.2f}, min_clamp={min_f:.2f}"
                ),
                metrik={"total": total, "min_clamp": min_f},
            ))

    # 3. Negatif kalem
    for item in breakdown:
        sub = item.get("subtotal_after")
        if sub is not None and float(sub) < 0.0:
            rule_id = item.get("rule_id", "?")
            findings.append(Finding(
                asama="fiyat",
                kod="FIYAT_NEGATIF_KALEM",
                severity="high",
                baslik="Fiyat kaleminde negatif ara toplam",
                ham_detay=(
                    f"rule_id={rule_id}, subtotal_after={sub:.2f}"
                ),
                metrik={"rule_id": rule_id, "subtotal_after": float(sub)},
            ))
            break  # bir kez raporla

    return findings


# ---------------------------------------------------------------------------
# ONCELIK sonrasi kontroller
# ---------------------------------------------------------------------------


def check_priority(
    data: Dict[str, Any],
    thresholds: Optional[WatcherThresholds] = None,
) -> List[Finding]:
    """Onceliklendirme ciktisini denetler.

    Beklenen data anahtarlari:
        warnings        : termin uyari listesi
        priority_classes: siparis oncelik sinifi listesi
    """
    t = thresholds or _DEFAULT_THRESHOLDS
    findings: List[Finding] = []

    warnings = data.get("warnings", [])
    priority_classes = data.get("priority_classes", [])
    n_warn = len(warnings)

    # 1. Cok fazla termin uyarisi
    if n_warn > t.priority_warning_count_max:
        findings.append(Finding(
            asama="oncelik",
            kod="ONCELIK_COK_UYARI",
            severity="med",
            baslik="Cok sayida termin gecikme uyarisi",
            ham_detay=(
                f"uyari_sayisi={n_warn}, "
                f"esik={t.priority_warning_count_max}"
            ),
            metrik={"uyari_sayisi": n_warn, "esik": t.priority_warning_count_max},
        ))

    # 2. Tum siparisler tek sinifta
    if len(priority_classes) >= 2:
        unique_classes = set(priority_classes)
        if len(unique_classes) == 1:
            tek_sinif = next(iter(unique_classes))
            findings.append(Finding(
                asama="oncelik",
                kod="ONCELIK_TEK_SINIF",
                severity="low",
                baslik="Tum siparisler ayni oncelik sinifinda",
                ham_detay=(
                    f"sinif={tek_sinif}, "
                    f"siparis_sayisi={len(priority_classes)}"
                ),
                metrik={"sinif": tek_sinif, "siparis_sayisi": len(priority_classes)},
            ))

    return findings
