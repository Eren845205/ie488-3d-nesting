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
