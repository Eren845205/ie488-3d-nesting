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

import logging
from dataclasses import dataclass
from typing import List

_LOG = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Akıllı nesting MOD seçimi: NFV cavity vs heightmap (2026-06-27, ÖLÇ-ÖNCE kanıtlı)
# ---------------------------------------------------------------------------
# Felsefe: VARSAYILAN NFV (kalite-güvenli — K-12: NFV >= heightmap HER ZAMAN; cavity yoksa
# birebir eşit, varsa daha iyi). heightmap'e SADECE NFV'nin %0-kazanç + boşuna-yavaş olduğu
# 2 BARİZ durumda düşülür → kazan-kazan (hem hızlı hem kalite-eşit):
#   (A) NET KUTU:          mean_aspect_z < BOX_ASPECT_THR → cavity yok (boxy: 2.8; plan'lar 6.4+).
#   (B) İNCE-PLAKA dom.:   thin_plate_ratio > THIN_PLATE_THR → düz zaten optimal, NFV eğmek
#                          yüksekliği ARTIRIR (K-15; numune: 0.92; plan2 max 0.26).
# Kalite-riski asimetrisi: NFV yanlış-pozitif = SADECE hız (kalite-güvenli); heightmap
# yanlış-negatif (cavity-zengin → heightmap) = %14-29 KALİTE KAYBI. Bu yüzden ŞÜPHEDE NFV
# (konservatif) → false-negative riskini sıfırlar.
# Eşikler "sabit-değil-ama-sabit": kutu/ince-plaka GEOMETRİK sınırlarından + K-14/K-15
# mekanizmasından türer (veri-uydurma DEĞİL). ÖLÇ-ÖNCE 5-veri kanıtı (false-negative=0,
# cavity-zengin plan1/2/3 eşiklerden GENİŞ marjla uzak): scripts/automode_proof.py.
BOX_ASPECT_THR: float = 4.0
THIN_PLATE_THR: float = 0.6


@dataclass
class ModeDecision:
    """Akıllı mod kararı + ŞEFFAFLIK için açıklanabilir gerekçe.

    wall_aware: makine-okur ÖNERİ (reason-dışı yapısal alan) — karar cidar-duyarlı
    pitch (K-19 / F3 `wall_aware`) yolunu öneriyor mu. DEFAULT False = geriye uyum;
    yalnız `predict_nfv_benefit(..., family_routing=True)` iken F5 aile-katmanı (kabuk
    ailesi) tetiklendiğinde True olur (opt-in). Mevcut tüketiciler
    (.mode/.reason okuyanlar) etkilenmez; yeni tüketici `getattr(dec, "wall_aware", False)`
    deseniyle okur.
    """

    mode: str       # "nfv" | "heightmap"
    reason: str
    wall_aware: bool = False


def predict_nfv_benefit(
    instance,
    *,
    family_routing: bool = False,
    box_aspect_thr: float = BOX_ASPECT_THR,
    thin_plate_thr: float = THIN_PLATE_THR,
    wall_aware_conf_thr: float | None = None,
) -> ModeDecision:
    """Instance'a NFV cavity mi heightmap mi uygun — veri-odaklı, açıklanabilir, kalite-güvenli.

    Kural sırası:
      0) AİLE KATMANI (F5, OPT-IN — yalnız `family_routing=True` iken): classify_prelim ailesi
         kabuk (thin_shell/tube) VE güven >= WALL_AWARE_CONF_THRESHOLD (F3 sabiti, pitch.py'den —
         tek kaynak) → heightmap + `wall_aware=True` önerisi. Gerekçe: kabukta K-12
         (NFV>=heightmap) KIRILIR (K-19: NFV-max@kaba 386.4 > heightmap@cidar-pitch 282.0);
         doğru yol cidar-duyarlı pitch. `family_routing=True` iken Deneme4 ince-kabuk "net-kutu"
         DEĞİL "kabuk" gerekçesiyle heightmap'e gider.
      1) NET-KUTU: mean_aspect_z < box_aspect_thr → heightmap (cavity yok).
      2) İNCE-PLAKA: thin_plate_ratio > thin_plate_thr → heightmap (düz zaten optimal).
      3) Aksi → nfv (kalite-güvenli).

    `family_routing` DEFAULT False = v1 BİT-ÖZDEŞ: aile katmanı hiç çalışmaz, mod/gerekçe/
    wall_aware her şey v1 kurallarıyla (net-kutu / ince-plaka / nfv) döner. `family_routing=True`
    iken aile katmanı adım 0'da devreye girer; tetiklemezse (unknown / düşük-güven / kabuk-olmayan)
    yine mevcut kural AYNEN çalışır (konservatif). Aile katmanı türetilemezse (import/veri hatası)
    logla + mevcut kurala düşülür.

    NOT (asimetri düzeltmesi, F5 aşama 1): mod-flip (kabuk→heightmap) ile downstream aksiyon
    (cidar-pitch) ARTIK AYNI bayrağa bağlı — `family_routing=False` iken ikisi de kapalı,
    `True` iken ikisi de birlikte gelir. Böylece "davranış değişmez" iddiası tek bayrakla tutar.

    VARSAYILAN NFV; heightmap SADECE net-kutu VEYA ince-plaka-dominant (VEYA family_routing=True
    iken kabuk-ailesi). NFV >= heightmap (K-12, kabuk-DIŞI) olduğundan NFV seçimi kaliteden
    kaybettirmez; şüphede NFV → false-negative (cavity-zengin→heightmap) riskini sıfırlar.
    ÖLÇ-ÖNCE kanıtlı (family_routing=True): Plan1/2/3 → nfv, numune/boxy → heightmap,
    deneme4 → heightmap+wall_aware, false-negative=0.

    Özellikler `extract_features` ile parça bbox'larından türetilir (box + STL; STL'de
    build_instance_from_order bbox'ları doldurur). İleride telemetri birikince selection/
    altyapısıyla öğrenen sürüme yükseltilebilir (adaptive_params felsefesi).
    """
    # --- F5 aile katmanı (OPT-IN — yalnız family_routing=True) ----------------
    # Kabuk ailesi (thin_shell/tube) + yeterli güven → heightmap + wall_aware önerisi.
    # Eşik + aile listesi F3'ten (pitch.py) import edilir → çift kaynak yok; F5 aile
    # kapısı F3 wall_aware kapısıyla BİREBİR aynı yerde tetiklenir. Import lazy
    # (döngüsel import yok); türetilemezse loglanır + mevcut kurala düşülür (konservatif).
    if family_routing:
        try:
            from src.nesting3d.instances.family import classify_prelim
            from src.nesting3d.instances.pitch import (
                WALL_AWARE_CONF_THRESHOLD as _WA_THR,
                _WALL_AWARE_FAMILIES as _WA_FAMS,
            )
            _thr = _WA_THR if wall_aware_conf_thr is None else float(wall_aware_conf_thr)
            _fam, _conf = classify_prelim(instance)
            if _fam in _WA_FAMS and _conf >= _thr:
                return ModeDecision(
                    "heightmap",
                    f"kabuk ailesi ({_fam}, guven={_conf:.2f} >= {_thr:.2f}): cidar-pitch "
                    f"yolu; K-12 kabukta gecersiz (K-19)",
                    wall_aware=True,
                )
        except Exception as _exc:
            _LOG.warning(
                "aile katmani turetilemedi, v1 kurallara dusuldu: %s",
                type(_exc).__name__,
            )

    from src.nesting3d.instances.features import extract_features
    fv = extract_features(instance)
    feats = dict(zip(fv.names, fv.values))
    maz = float(feats.get("mean_aspect_z", 0.0))
    tpr = float(feats.get("thin_plate_ratio", 0.0))
    if maz < box_aspect_thr:
        return ModeDecision(
            "heightmap",
            f"net-kutu (mean_aspect_z={maz:.1f} < {box_aspect_thr}): cavity yok, "
            f"NFV kazanmaz -> hizli heightmap",
        )
    if tpr > thin_plate_thr:
        return ModeDecision(
            "heightmap",
            f"ince-plaka dominant (thin_plate={tpr:.2f} > {thin_plate_thr}): duz zaten "
            f"optimal, NFV uzatir -> heightmap",
        )
    return ModeDecision(
        "nfv",
        f"cavity-aday (mean_aspect_z={maz:.1f}, thin_plate={tpr:.2f}): NFV kalite-guvenli "
        f"(>=heightmap)",
    )
