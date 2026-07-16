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


def _tilt_zorunlu_parca(instance, no_go_bounds):
    """Hicbir duz eksen-hizali pozu no-go'lu plakaya sigmayan ilk parca.

    Kesin dikdortgen testi (uretim formati: tek no-go dikdortgeni
    ((x1,y1),(x2,y2))). (W,D) pozu sigar <=> plakaya sigar VE parca no-go'dan
    kacabilir: sol (x1>=W) / sag (x2<=PW-W) / alt (y1>=D) / ust (y2<=PD-D)
    seritlerinden biri parcayi aliyor. Iki taban pozu da (WxD, DxW) sigmayan
    parca doner; None = boyle parca yok. Format cozulemezse None (kapi
    tetiklemez — konservatif: mevcut davranis).
    """
    try:
        (x1, y1), (x2, y2) = no_go_bounds
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
        pw = float(instance.container.width_mm)
        pd = float(instance.container.depth_mm)
    except Exception:
        return None
    for p in instance.parts:
        w, d = p.width_mm, p.depth_mm
        if not w or not d:
            continue
        sigar = False
        for W, D in ((float(w), float(d)), (float(d), float(w))):
            if W > pw or D > pd:
                continue
            if x1 >= W or x2 <= pw - W or y1 >= D or y2 <= pd - D:
                sigar = True
                break
        if not sigar:
            return p
    return None


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
    # NFV dali icin poz-seti ONERISI (K-53c, 2026-07-16): "fast" (n=8) |
    # "max" (AX24). Yalniz rot-sokum thin_shell dalinda "max" uretilir
    # (d4@AX24 231.5 = -%16.3 vs n=8 276.5, max-parite, sure LEHTE).
    # DEFAULT "fast" = geriye uyum; tuketici acik nfv_quality/n_orientations
    # verdiyse o KAZANIR (oneri yalniz default'u doldurur).
    nfv_quality: str = "fast"


def predict_nfv_benefit(
    instance,
    *,
    family_routing: bool = False,
    box_aspect_thr: float = BOX_ASPECT_THR,
    thin_plate_thr: float = THIN_PLATE_THR,
    wall_aware_conf_thr: float | None = None,
    mode_model=None,
    rot_sokum: bool = False,
    no_go_bounds=None,
) -> ModeDecision:
    """Instance'a NFV cavity mi heightmap mi uygun — veri-odaklı, açıklanabilir, kalite-güvenli.

    Kural sırası:
      0) AİLE KATMANI (F5, OPT-IN — yalnız `family_routing=True` iken): classify_prelim ailesi
         kabuk (thin_shell/tube) VE güven >= WALL_AWARE_CONF_THRESHOLD (F3 sabiti, pitch.py'den —
         tek kaynak) → heightmap + `wall_aware=True` önerisi. Gerekçe: kabukta K-12
         (NFV>=heightmap) KIRILIR (K-19: NFV-max@kaba 386.4 > heightmap@cidar-pitch 282.0);
         doğru yol cidar-duyarlı pitch. `family_routing=True` iken Deneme4 ince-kabuk "net-kutu"
         DEĞİL "kabuk" gerekçesiyle heightmap'e gider.
         `rot_sokum=True` (Eren kararı 2026-07-15; K-46/K-52): rot-söküm dünyasında
         thin_shell hükmü TERSİNE — NFV+rot yoluna gider (kilit rot-kabul zinciriyle
         aklanır; d4 220.69 < 287.0). tube kanıtsız → eski yol. Default False = bit-özdeş.
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
    # --- ADIM -1: TILT-ZORUNLU fizibilite kapisi (Eren istegi 2026-07-15,
    # "plan1'i hallet"; kanit K-40 plan1-NFV 333.0 SERT NO-GO + k51c 111/112
    # eksik yerlesim). Bir parcanin HICBIR duz eksen-hizali pozu no-go'lu
    # plakaya sigmiyorsa NFV o parcayi yerlestiremez (tilt yok) — heightmap
    # yolu (tilt havuzlu) ZORUNLU. Geometrik KESIN dikdortgen testi
    # (veri-uydurma degil); fizibilite kaniti her karar katmanini (model
    # dahil) ezer. no_go_bounds=None (default) -> hic calismaz, BIT-OZDES.
    if no_go_bounds is not None:
        _tp = _tilt_zorunlu_parca(instance, no_go_bounds)
        if _tp is not None:
            return ModeDecision(
                "heightmap",
                f"tilt-zorunlu parca ({_tp.name}: {float(_tp.width_mm):.0f}x"
                f"{float(_tp.depth_mm):.0f}mm hicbir duz pozda no-go'lu "
                f"plakaya sigmiyor): NFV eksen-hizali yerlestiremez -> "
                f"heightmap tilt yolu (K-40)",
            )

    # --- C4 CHALLENGER (OPT-IN — yalniz mode_model verilirse; Sprint-3) -------
    # YARISMA-2 kaniti (2026-07-14, Eren onayi): regret_logistic 9.66mm < kural
    # 17.0mm. CIFT KILIT modelde: aile allowlist'te VE conformal-tekil ise
    # kurali ezer; aksi TUM durumlarda (None donus / hata / model yok) asagidaki
    # kurallar BIT-OZDES calisir. default mode_model=None = eski davranis.
    if mode_model is not None:
        try:
            from src.nesting3d.instances.family import classify_prelim as _clf
            from src.nesting3d.instances.features import (
                extract_features_extended as _fx)
            _fam_m, _ = _clf(instance)
            _sonuc = mode_model.karar(list(_fx(instance).values), _fam_m)
            if _sonuc is not None:
                _arm, _gerekce = _sonuc
                if _arm == "heightmap+wall_aware":
                    return ModeDecision("heightmap", _gerekce, wall_aware=True)
                if _arm.startswith("nfv"):
                    return ModeDecision("nfv", _gerekce)
                return ModeDecision("heightmap", _gerekce)
        except Exception as _exc:
            _LOG.warning("mode_model karari turetilemedi, kurala dusuldu: %s",
                         type(_exc).__name__)

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
                # rot-sokum dunyasi (Eren karari 2026-07-15; kanit K-46/K-52):
                # thin_shell'de kabuk hukmu TERSINE — d4 NFV ham 231.5
                # (b+c)-legal + rot-kabul 220.69 < heightmap+wall_aware 287.0.
                # Kilit korkusu rot-kabul zinciriyle (solve_nfv_kalite
                # rot_kabul) cozulur. tube icin rot-dunyasi kaniti YOK ->
                # eski yol. rot_sokum default False = BIT-OZDES eski davranis.
                if rot_sokum and _fam == "thin_shell":
                    # K-53c (2026-07-16): bu ailede poz seti AX24 (quality=max)
                    # onerilir — d4 eval 231.5 vs n=8 276.5 (-%16.3), K-46
                    # max-parite, sure ilk-24'ten de kisa. Oneri yalniz
                    # default'u doldurur (acik quality/n_orientations ezer).
                    return ModeDecision(
                        "nfv",
                        f"kabuk ailesi ({_fam}, guven={_conf:.2f}) + rot-sokum "
                        f"dunyasi: NFV+rot yolu (K-46/K-52; kilit rot-kabul "
                        f"zinciriyle aklanir; poz seti AX24, K-53c)",
                        nfv_quality="max",
                    )
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
