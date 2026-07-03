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


# --- K-19: Cidar-duyarli (wall-aware) OPT-IN pitch turetmesi -------------------
# YONTEM_HARITASI §3.1 K-19 / §5 K-19p (F3). Kabuk ailesinde (thin_shell/tube)
# ORTAK pitch, bbox-min yerine CIDAR kalinligindan turer. Cidar tahmini = 2V/A;
# bu deger F1 loader tarafindan watertight+fill<0.5 kabuklarda PartSpec.wall_mm'e
# YAZILIR (burada YENIDEN trimesh.load YOK — hazir alan okunur). Kabuk parcanin
# gercek "en ince ozelligi" cidardir (bbox-min degil) -> pitch cok daha ince
# olur ve ince cavity duvarlari cozunur (Deneme4: 377.3->282.0mm, -%25).
#
# Tetik AND-kapisi (suggest_pitch / suggest_nfv_pitch icinde):
#   (a) cagiran wall_aware=True   (DEFAULT False = mevcut davranis BIT-OZDES),
#   (b) classify_prelim family in {thin_shell, tube},
#   (c) family guveni >= WALL_AWARE_CONF_THRESHOLD (parametreyle ezilebilir).
# H-06 (per-part pitch NO-GO) ihlali DEGIL: pitch yine herkes icin TEK; yalniz
# turetim kurali cidar-duyarli.
#
# WALL_AWARE_CONF_THRESHOLD turetimi (gercek-veri family guvenleri, K-19 olcum):
#   Iki tablo ile olculdu (qty-agirlik family oylamasini kaydirir, ikisi de raporlanir).
#   ASIL KAPI = URETIM qty-agirlikli guvenler (siparis adetleri dahil):
#     deneme4=0.87 -> TETIKLER; plan2=0.58; plan3=0.56; plan1=0.53 (mixed_scale);
#     numune=0.59 (mixed_scale); boxy=0.69 (solid_bulk) -> esige headroom ~0.17.
#   Dry-run qty=1 (bilgi amacli, f3_dryrun; adetsiz family oylamasi):
#     deneme4=0.89; plan2=0.66; plan1=0.64; numune=0.65; plan3=0.52; boxy=0.67
#     -> esige headroom ~0.09 (deneme4 haric en yakin non-tetik = plan2 0.66).
#   Esik (max non-tetik, deneme4] araliginda olmali. 0.75 secildi. Guvenlik payi
#   MUHAFAZAKAR okunmali: qty=1 tablosunda en yakin non-tetik guven 0.66 -> min
#   headroom yalniz ~0.09 (deneme4 tarafinda pay 0.89-0.75=0.14). boxy her iki
#   tabloda da family=solid_bulk (family kapisi zaten reddeder; guven kapisi ikinci
#   savunma). SABIT-SIHIRLI-SAYI DEGIL — wall_conf_threshold parametresiyle ezilir;
#   default degeri veri-ayriminden turetildi (dar qty=1 payi = ilerideki setlerde
#   yeniden olcum gerektirebilir).
WALL_AWARE_CONF_THRESHOLD: float = 0.75
_WALL_AWARE_FAMILIES: tuple = ("thin_shell", "tube")


def wall_feature_mm(instance: "NestingInstance") -> float:
    """Cidar-duyarli en kucuk ozellik (mm): parca basina wall_mm (varsa) yoksa bbox-min.

    F1 loader watertight kabuklarda PartSpec.wall_mm = 2V/A doldurur. wall_mm None
    olan parcalar (loader dolduramadi / kabuk degil) bbox-min ile katilir. Sonuc
    TEK ORTAK deger (min); solve pitch buradan tek skaler turetir (H-06).
    """
    vals = []
    for p in instance.parts:
        if p.wall_mm is not None and p.wall_mm > 0:
            vals.append(float(p.wall_mm))
        else:
            vals.append(min(p.width_mm, p.depth_mm, p.height_mm))
    return min(vals)


def _wall_aware_triggers(
    instance: "NestingInstance", conf_threshold: float,
) -> tuple:
    """(tetiklendi_mi, family, confidence) — cidar dali AND-kapisi (b)+(c).

    classify_prelim (bbox + loader verisi) ile family+guven turer; family kabuk
    ailesinde VE guven esik ustundeyse tetikler. Import lazy (dongusel bagimlilik
    yok + cagirmadan maliyet yok).
    """
    from src.nesting3d.instances.family import classify_prelim
    fam, conf = classify_prelim(instance)
    triggered = fam in _WALL_AWARE_FAMILIES and conf >= conf_threshold
    return triggered, fam, conf


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
    margin: int = 1,
    wall_aware: bool = False,
    wall_conf_threshold: float = WALL_AWARE_CONF_THRESHOLD,
) -> tuple[float, bool, str]:
    """NFV cavity çözücüsü için pitch öner: parça-GÜVENLİ pitch + plaka-oranı + bellek kabalaştırma.

    Mantık (ÖLÇ-ÖNCE, c3_xdataset_speed + probe_safe 2026-06-23): pitch hem veriden (min_feature,
    en büyük parça) hem donanımdan (RAM) türer — SABİT DEĞİL.
      1. GÜVENLİ taban: pitch = min_feature/safe_ratio (oran 1.0 → parça en az 1 voxel GARANTİ,
         voxelize çökmez). En ince güvenli = en iyi cavity; bu tercih edilir.
      2. PLAKA-ORANI tavanı: en büyük parça + 2·margin voxel plakaya SIĞMALI. Kaba pitch'te margin
         (=pitch·margin mm) parçayı plaka dışına itebilir (boxy stres-testi). pitch'i bu tavanın altına
         çek; parça tek boyutta bile plakadan büyükse feasible=False.
      3. Bellek aşarsa: bütçeye sığana kadar KABALAŞTIR — voxelize sınırı (min_ratio) VE plaka tavanı
         içinde. Plan2 gibi ince-parça+büyük-plaka durumu burada.
      4. Hiçbir geçerli pitch yoksa feasible=False → çağıran heightmap'e düşmeli.

    Args:
        plate_w_mm, plate_d_mm: plaka ölçüleri (bellek + plaka-oranı için).
        ram_bytes:   kullanılabilir RAM (probe_capabilities().ram_bytes).
        safe_ratio:  parça-garanti voxelize oranı (min_dim/pitch >= bu); tercih edilen taban.
        min_ratio:   voxelize mutlak alt sınır oranı; bellek için buraya kadar kabalaşılır.
        cells_per_gb: bellek bütçesi (RAM GB başına izinli grid hücresi).
        floor:       pitch alt sınırı (mm) — patolojik koruma.
        margin:      decode'da kullanılan voxel margin (plaka-oranı tavanı için; solve_nfv ile aynı).

    Returns:
        (pitch, feasible, reason). feasible=False → riskli, heightmap önerilir.
    """
    if not instance.parts:
        raise ValueError("Boş instance: NFV pitch türetilemez (parça yok).")

    mf = min_feature_mm(instance)
    max_dim = max(max(p.width_mm, p.depth_mm, p.height_mm) for p in instance.parts)
    min_plate = min(plate_w_mm, plate_d_mm)
    budget = (ram_bytes / 1e9) * cells_per_gb

    # K-19 OPT-IN cidar dali (PLAKA-BOYUT KOSULLU, H-11 FFT bellek duvari korunur):
    # kabuk-ailesi + yeterli guven olunca en kucuk ozellik = CIDAR (mf'yi wall ile
    # degistir). ANCAK NFV'de ince pitch FFT grid'ini kubik buyutur -> buyuk plakada
    # OOM. Bu yuzden cidar pitch'i YALNIZ grid butceye SIGIYORSA uygulanir; sigmazsa
    # min_feature davranisi korunur (heightmap yolu asil hedef; NFV OOM'a girmez).
    wall_prefix = ""
    if wall_aware:
        _triggered, _fam, _conf = _wall_aware_triggers(instance, wall_conf_threshold)
        if _triggered:
            wf = wall_feature_mm(instance)
            if wf < mf - 1e-12:  # cidar gercekten bbox-min'den ince
                _cand = max(floor, wf / safe_ratio)
                if _nfv_grid_cells(_cand, plate_w_mm, plate_d_mm) <= budget:
                    mf = wf
                    wall_prefix = f"cidar-duyarli ({_fam} conf={_conf:.2f}, wall={wf:.2f}mm); "
                else:
                    wall_prefix = (f"cidar-atlandi (plaka buyuk/FFT-bellek H-11, "
                                   f"wall={wf:.2f}mm); ")

    # Plaka-oranı tavanı: en büyük parça(voxel) + 2·margin <= plaka(voxel)
    #   → max_dim + 2·margin·pitch <= min_plate → pitch <= (min_plate - max_dim)/(2·margin).
    m = max(1, int(margin))
    if max_dim >= min_plate:
        return (max(floor, mf / safe_ratio), False,
                wall_prefix + f"en buyuk parca {max_dim:.0f}mm >= plaka {min_plate:.0f}mm -> sigmaz, heightmap onerilir")
    plate_ceil = (min_plate - max_dim) / (2 * m)
    if plate_ceil < floor:
        return (floor, False,
                wall_prefix + f"plaka-orani tavani {plate_ceil:.2f}mm < floor {floor}mm (parca plakaya cok yakin) "
                f"-> NFV riskli, heightmap onerilir")

    pitch_safe = min(max(floor, mf / safe_ratio), plate_ceil)   # parça-garanti, plakaya sığar
    pitch_max = min(max(pitch_safe, mf / min_ratio), plate_ceil)  # voxelize + plaka üst sınırı

    pitch = pitch_safe
    cells = _nfv_grid_cells(pitch, plate_w_mm, plate_d_mm)
    if cells <= budget:
        limiter = ("plaka-orani" if plate_ceil < mf / safe_ratio - 1e-9
                   else f"guvenli min_feature={mf:.2f}/{safe_ratio}")
        return pitch, True, (wall_prefix + f"nfv-pitch={pitch:.2f}mm ({limiter}); "
                             f"grid~{cells / 1e6:.1f}M <= butce {budget / 1e6:.0f}M")

    # Bellek asiyor -> bellek sigana kadar kabalastir (deterministik, voxelize sinirina kadar).
    while cells > budget and pitch < pitch_max - 1e-9:
        pitch = min(pitch_max, pitch * 1.1)
        cells = _nfv_grid_cells(pitch, plate_w_mm, plate_d_mm)

    if cells <= budget:
        return pitch, True, (wall_prefix + f"nfv-pitch={pitch:.2f}mm (bellek icin kabalastirildi, "
                             f"oran={mf / pitch:.2f}); grid~{cells / 1e6:.1f}M <= butce {budget / 1e6:.0f}M")
    # Voxelize sinirina kadar kabalastik ama bellek hala yetmiyor -> NFV bu instance+donanimda riskli.
    return pitch, False, (wall_prefix + f"nfv-pitch={pitch:.2f}mm ama grid~{cells / 1e6:.1f}M > butce "
                          f"{budget / 1e6:.0f}M (RAM {ram_bytes / 1e9:.0f}GB) -> bellek-riskli, "
                          f"heightmap onerilir")


def suggest_pitch(
    instance: "NestingInstance",
    *,
    factor: float = DEFAULT_FACTOR,
    floor: float = DEFAULT_FLOOR,
    ceil: float = DEFAULT_CEIL,
    wall_aware: bool = False,
    wall_conf_threshold: float = WALL_AWARE_CONF_THRESHOLD,
) -> float:
    """Instance için voxel pitch öner: min_dim / factor, [floor, ceil]'e kelepçeli.

    Args:
        instance: NestingInstance (parça boyutları okunur).
        factor:   En küçük özellik kaç voxel'e bölünsün (varsayılan 2.5).
        floor:    Pitch alt sınırı, mm (varsayılan 2.0).
        ceil:     Pitch üst sınırı, mm (varsayılan 15.0).
        wall_aware: OPT-IN cidar-duyarli dal (K-19). DEFAULT False -> mevcut
                    davranis BIT-OZDES. True + kabuk-ailesi + yeterli guven
                    olunca en kucuk ozellik = CIDAR (wall_mm) alinir -> daha
                    ince pitch (ince cavity duvarlari cozunur). Tetik tek ORTAK
                    pitch uretir (H-06 korunur).
        wall_conf_threshold: cidar dali guven esigi (default WALL_AWARE_CONF_THRESHOLD;
                    veri-ayriminden turetildi, override edilebilir).

    Returns:
        Önerilen pitch (mm). Determinist: aynı instance → aynı pitch.

    Raises:
        ValueError: instance'ta parça yoksa veya floor > ceil ise.
    """
    if floor > ceil:
        raise ValueError(f"floor ({floor}) > ceil ({ceil}) — geçersiz aralık.")
    if not instance.parts:
        raise ValueError("Boş instance: pitch türetilemez (parça yok).")

    feature = min_feature_mm(instance)
    if wall_aware:
        triggered, _fam, _conf = _wall_aware_triggers(instance, wall_conf_threshold)
        if triggered:
            feature = min(feature, wall_feature_mm(instance))
    raw = feature / factor
    return max(floor, min(ceil, raw))
