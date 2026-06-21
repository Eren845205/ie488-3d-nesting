"""adaptive_params.py — instance özelliklerinden çözüm parametrelerini ÖNERİR.

Sabit sihirli sayılar (n_orientations=8, ince-açı penceresi=5° vb.) yerine,
parçaların UCUZ geometrik özelliklerinden VERİ-ODAKLI karar. Amaç: körlemesine
sweep yapmadan (maliyetli) hangi ayarların işe yarayacağını önceden tahmin edip
denenecekleri sınırlamak.

Şeffaf kural (eğitimsiz, açıklanabilir — kara kutu değil):
- "kutuluk" (doluluk/solidity) = voxel_count / bbox_voxel_sayısı  (0..1).
  ~1 → parça katı bir kutu; eksen-hizalı en iyi oturur, rotasyon/ince-açı pek
  yardım etmez. Düşük → düzensiz/oyuklu parça; ince açı interlock'a yardım edebilir.

Karar mantığı:
- Kutu parçalar → ince-açı refinement'i ATLA (boşuna ~4× maliyet ödeme).
- Düzensiz parçalar → ince-açıyı AÇ. (Güvenli mod zaten global yüksekliği
  iyileştirmezse kullanmaz → YANLIŞ öneri bile sessizce zarar veremez.)

n_orientations: 8 = tüm eksen-hizalı pozlar (24-simetrinin pratik alt kümesi);
sihirli sayı değil, "tüm 90° yüzleri dene" ilkesi → güvenli taban. Eğik pozlar
(n>8) ve ince-açı situasyona bağlı; bunları özellik belirler.

Bu modül sistemdeki tuner/seçim-modeli felsefesinin (özellikten-config tahmini)
poz/açı knob'larına uygulanmış halidir; ileride öğrenen tahminciye yükseltilebilir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


# Bu değerin ÜSTÜ "kutu" sayılır → ince-açı atlanır. Plan1/Plan2 gerçek verisiyle
# kalibre edilecek (kutu-ağırlıklı setlerde ince-açı kazanç vermedi).
BOXINESS_SKIP_ANGLE: float = 0.85


@dataclass
class SolveParams:
    """Önerilen çözüm parametreleri + ŞEFFAFLIK için gerekçe."""

    n_orientations: int
    fine_angle_window: float
    fine_angle_step: float
    fine_angle_axes: str
    boxiness: float
    reason: str


def _fill_ratio(orient) -> float:
    """Tek oryantasyonun doluluk oranı = dolu voxel / bbox voxel (0..1)."""
    g = orient.grid
    total = int(g.shape[0]) * int(g.shape[1]) * int(g.shape[2])
    if total <= 0:
        return 1.0
    return float(orient.voxel_count) / float(total)


def instance_boxiness(voxel_parts: List) -> float:
    """Hacim-ağırlıklı ortalama doluluk (oryantasyon 0 üzerinden).

    Büyük parçalar yüksekliği belirlediğinden hacimle ağırlıklanır — küçük bir
    aykırı parça kararı saptırmasın.
    """
    num = 0.0
    den = 0.0
    for p in voxel_parts:
        if not p.orientations:
            continue
        o = p.orientations[0]
        w = float(o.voxel_count)
        num += _fill_ratio(o) * w
        den += w
    return num / den if den > 0 else 1.0


def recommend(voxel_parts: List,
              boxiness_skip_angle: float = BOXINESS_SKIP_ANGLE) -> SolveParams:
    """Voxelize edilmiş parçalardan çözüm parametrelerini öner (şeffaf kural)."""
    b = instance_boxiness(voxel_parts)
    if b >= boxiness_skip_angle:
        return SolveParams(
            n_orientations=8, fine_angle_window=0.0, fine_angle_step=1.0,
            fine_angle_axes="z", boxiness=b,
            reason=(f"kutuluk={b:.2f} >= {boxiness_skip_angle:.2f} → ince-açı "
                    f"ATLANDI (parçalar kutuya yakın, açı kazanç vermez)"),
        )
    return SolveParams(
        n_orientations=8, fine_angle_window=5.0, fine_angle_step=1.0,
        fine_angle_axes="z", boxiness=b,
        reason=(f"kutuluk={b:.2f} < {boxiness_skip_angle:.2f} → ince-açı AÇIK "
                f"(düzensiz parçalar; güvenli mod iyileştirmezse yine kullanmaz)"),
    )
