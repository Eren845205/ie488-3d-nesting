"""instances/pitch.py — Parça ölçeğinden adaptif voxel pitch önerisi (R6).

APP_YOL_HARITASI §2 R6 ("pitch/margin/taban default'ları senaryo-eksenli") ve
§3 madde 6 ("parça ölçeğinden otomatik pitch önerisi") bu modülde somutlaşır.

Sorun (2026-06-14 tanısı): donmuş benchmark tek bir global pitch (15 mm)
dayatıyordu; ama tek pitch hem 300 mm'lik kutuları hem 3-12 mm'lik ince levhaları
aynı anda çözemiyor. Dilim-voxelizer en küçük parça boyutu ~pitch/2 altına
düşünce boş grid üretip çöküyordu (tune setinin 10 instance'ından 3'ü: her iki
thin_plates + bir long_rods).

Çözüm: pitch'i her instance'ın EN KÜÇÜK parça boyutundan TÜRET. Tek-konfig
kuralı (PLAN_DEMO1 Değişmez #4 / §5) artık pitch SAYISINA değil bu TÜRETME
KURALINA uygulanır — kural tüm instance'lara aynı uygulandığı için determinizm
ve karşılaştırma adilliği korunur; benchmark uçtan uca koşar.

Determinizm: girdi instance sabitken çıktı pitch sabit (saf fonksiyon, rastgelelik
yok).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - sadece tip ipucu
    from src.nesting3d.instances.format import NestingInstance


# Varsayılan türetme parametreleri.
# factor: en küçük özellik kaç voxel'e bölünsün (min_dim / factor = pitch).
#   2.5 → en ince parça ~2.5 voxel kalınlık alır; dilim merkezleri güvenle
#   parçaya düşer (ampirik eşik min_dim/pitch ~0.5; 2.5 bunun çok üstünde).
# floor: pitch alt sınırı (mm) — patolojik pitch→0 koruması (yalnız güvenlik
#   tabanı). 2026-06-14: 2.0 → 0.5 indirildi. Sebep: BR instance'ları birim
#   ölçekli (parça 1-20 mm, konteyner 100 mm); 1 mm'lik BR kutusu pitch <=0.67
#   gerektiriyor ama floor=2.0 onu 2.0'a kelepçeleyip boş grid → guard hatası
#   veriyordu. floor=0.5 → 1 mm parça pitch 0.5 (min_dim/pitch=2.0, güvenle
#   voxelize). Sentetik aileler etkilenmez (pitch'leri zaten floor'un üstünde).
#   İlke (kullanıcı kararı): parça KAYBOLMAMALI; ince pitch'in runtime maliyeti
#   kabul edilir — clamp ile geometriyi bozmaktansa hassas çöz.
# ceil: pitch üst sınırı (mm) — büyük parçalı instance'larda bile bu kadar
#   kaba git; eski global 15 mm tavanı korunur (büyük-kutu runtime sınırı).
DEFAULT_FACTOR: float = 2.5
DEFAULT_FLOOR: float = 0.5
DEFAULT_CEIL: float = 15.0


def min_feature_mm(instance: "NestingInstance") -> float:
    """Instance'taki tüm parçaların en küçük (w/d/h) boyutu (mm)."""
    return min(
        min(p.width_mm, p.depth_mm, p.height_mm)
        for p in instance.parts
    )


# --- NFV "kalite modu" pitch türetmesi (backlog #1, ölçüm 2026-06-23) ---------
# NFV (FFT-cavity) çözücüsü suggest_pitch'in TERSİ bir pitch ister:
#   * suggest_pitch: min_dim/2.5 → İNCE pitch (heightmap'te ince ucuz, kalite için iyi).
#   * NFV: FFT maliyeti ve bellek pitch ile KÜBİK büyür; kalite ise pitch'e AZ duyarlı
#     (Plan2 ölçümü: 2.0mm=556 vs 1.5mm hedeflenen ~%1 — ama 1.5mm bu donanımda OOM).
#   → NFV için DOĞRU pitch = parçayı kaybetmeyen EN KABA pitch (hız+bellek minimum, kalite ~korunur).
#
# İKİ türetme oranı (voxelize.py geometrik eşiğinden; ikisi de SABİT-SAYI değil, türetme kuralı):
#   SAFE_FILL_RATIO=1.0: min_dim/pitch>=1.0 → parça en az 1 voxel kalınlık GARANTİ (dilim merkezi
#     her zaman içeride → voxelize ASLA çökmez). Tercih edilen taban; en ince=en iyi cavity.
#   MIN_FILL_RATIO=0.5: voxelize.py ampirik MUTLAK alt sınır (~0.5 altı kesin kaybolur). Bellek
#     mecbur bırakırsa pitch SADECE buraya kadar kabalaştırılır (oran 0.5'te voxelize hizaya bağlı,
#     risk var → fallback + heightmap düşüşü devrede).
# 2026-06-23 cross-dataset ölçümü (c3_xdataset_speed + probe_safe): oran 1.0 plan1/plan3/boxy'de hem
#   güvenli hem bellek-OK (çökme YOK); SADECE plan2 (1mm ince parça+büyük plaka, 172M>bütçe) bellek
#   için 2.0mm'ye kabalaşır. Eski tek-oran 0.5 plan1'de çöküyordu (Plan2-overfit) → bu düzeltme.
# NFV_CELLS_PER_GB: bellek pre-flight bütçesi. proxy=nx*ny*nz_limit. Ölçüm (16GB): 21.5M (2.0mm)
#   çalıştı, 50.9M (1.5mm) OOM → ~2.0e6 hücre/GB. Donanım RAM'inden ölçekler (sabit değil).
SAFE_FILL_RATIO: float = 1.0
MIN_FILL_RATIO: float = 0.5
NFV_CELLS_PER_GB: float = 2.0e6
_NFV_NZ_BUDGET_MM: float = 1600.0  # parallel_decode._nz_limit ile aynı (800 dilim @2mm)


def _nfv_grid_cells(pitch: float, plate_w_mm: float, plate_d_mm: float) -> float:
    """NFV occupancy grid'inin üst-sınır hücre sayısı (bellek proxy'si). nz_limit dahil."""
    nx = int(plate_w_mm // pitch)
    ny = int(plate_d_mm // pitch)
    nz = int(_NFV_NZ_BUDGET_MM / max(pitch, 1e-6))
    return float(nx) * float(ny) * float(nz)


def suggest_nfv_pitch(
    instance: "NestingInstance",
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    ram_bytes: int,
    safe_ratio: float = SAFE_FILL_RATIO,
    min_ratio: float = MIN_FILL_RATIO,
    cells_per_gb: float = NFV_CELLS_PER_GB,
    floor: float = DEFAULT_FLOOR,
) -> tuple[float, bool, str]:
    """NFV cavity çözücüsü için pitch öner: parça-GÜVENLİ pitch + bellek pre-flight kabalaştırma.

    Mantık (ÖLÇ-ÖNCE, c3_xdataset_speed + probe_safe 2026-06-23): pitch hem veriden (min_feature)
    hem donanımdan (RAM) türer — SABİT DEĞİL.
      1. GÜVENLİ taban: pitch = min_feature/safe_ratio (oran 1.0 → parça en az 1 voxel GARANTİ,
         voxelize çökmez). En ince güvenli = en iyi cavity; bu tercih edilir.
      2. Bellek aşarsa: pitch'i bellek bütçesine sığana kadar KABALAŞTIR — ama yalnızca voxelize
         mutlak sınırına (min_ratio=0.5) kadar. Plan2 gibi ince-parça+büyük-plaka durumu burada.
      3. O sınıra kadar bellek sığmazsa feasible=False → çağıran heightmap'e düşmeli.

    Args:
        plate_w_mm, plate_d_mm: plaka ölçüleri (bellek proxy'si grid boyutu).
        ram_bytes:   kullanılabilir RAM (probe_capabilities().ram_bytes).
        safe_ratio:  parça-garanti voxelize oranı (min_dim/pitch >= bu); tercih edilen taban.
        min_ratio:   voxelize mutlak alt sınır oranı; bellek için buraya kadar kabalaşılır.
        cells_per_gb: bellek bütçesi (RAM GB başına izinli grid hücresi).
        floor:       pitch alt sınırı (mm) — patolojik koruma.

    Returns:
        (pitch, feasible, reason). feasible=False → bellek-riskli, heightmap önerilir.
    """
    if not instance.parts:
        raise ValueError("Boş instance: NFV pitch türetilemez (parça yok).")

    mf = min_feature_mm(instance)
    budget = (ram_bytes / 1e9) * cells_per_gb
    pitch_safe = max(floor, mf / safe_ratio)      # parça-garanti (en ince güvenli)
    pitch_max = max(pitch_safe, mf / min_ratio)   # voxelize mutlak üst sınır (bunun üstü kesin kayıp)

    pitch = pitch_safe
    cells = _nfv_grid_cells(pitch, plate_w_mm, plate_d_mm)
    if cells <= budget:
        return pitch, True, (f"nfv-pitch={pitch:.2f}mm (guvenli: min_feature={mf:.2f}/{safe_ratio}); "
                             f"grid~{cells / 1e6:.1f}M <= butce {budget / 1e6:.0f}M")

    # Bellek asiyor -> bellek sigana kadar kabalastir (deterministik, voxelize sinirina kadar).
    while cells > budget and pitch < pitch_max - 1e-9:
        pitch = min(pitch_max, pitch * 1.1)
        cells = _nfv_grid_cells(pitch, plate_w_mm, plate_d_mm)

    if cells <= budget:
        return pitch, True, (f"nfv-pitch={pitch:.2f}mm (bellek icin kabalastirildi, "
                             f"oran={mf / pitch:.2f}); grid~{cells / 1e6:.1f}M <= butce {budget / 1e6:.0f}M")
    # Voxelize sinirina kadar kabalastik ama bellek hala yetmiyor -> NFV bu instance+donanimda riskli.
    return pitch, False, (f"nfv-pitch={pitch:.2f}mm ama grid~{cells / 1e6:.1f}M > butce "
                          f"{budget / 1e6:.0f}M (RAM {ram_bytes / 1e9:.0f}GB) -> bellek-riskli, "
                          f"heightmap onerilir")


def suggest_pitch(
    instance: "NestingInstance",
    *,
    factor: float = DEFAULT_FACTOR,
    floor: float = DEFAULT_FLOOR,
    ceil: float = DEFAULT_CEIL,
) -> float:
    """Instance için voxel pitch öner: min_dim / factor, [floor, ceil]'e kelepçeli.

    Args:
        instance: NestingInstance (parça boyutları okunur).
        factor:   En küçük özellik kaç voxel'e bölünsün (varsayılan 2.5).
        floor:    Pitch alt sınırı, mm (varsayılan 2.0).
        ceil:     Pitch üst sınırı, mm (varsayılan 15.0).

    Returns:
        Önerilen pitch (mm). Determinist: aynı instance → aynı pitch.

    Raises:
        ValueError: instance'ta parça yoksa veya floor > ceil ise.
    """
    if floor > ceil:
        raise ValueError(f"floor ({floor}) > ceil ({ceil}) — geçersiz aralık.")
    if not instance.parts:
        raise ValueError("Boş instance: pitch türetilemez (parça yok).")

    raw = min_feature_mm(instance) / factor
    return max(floor, min(ceil, raw))
