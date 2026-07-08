"""coarse_to_fine.py — Coarse-to-fine nesting hızlandırma katmani.

Algoritma ozeti
---------------
1. COARSE: instance'i kaba pitch ile voxelize et, tune() ile tum algoritma
   portfoyunu kos.  Kazanan coarse cozumden SIRA + ORYANTASYON cikart.
2. FINE: instance'i ince pitch ile yeniden voxelize et, coarse sirayi ve
   coarse oryantasyon indekslerini koruyarak place_in_order ile tek geciste
   yerlesim yap.

Hiz kazanimi: arama (tune) kaba voxel uzayinda yapilir (ucuz), final
kalitesi ince cozunurlukle belirlenir.

Deterministik: ayni (instance, pitchler, budget, seed) -> ayni sonuc.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from src.nesting3d.bin3d import Bin3D, Placement3D
from src.nesting3d.dblf import place_in_order
from src.nesting3d.instances.format import NestingInstance, to_voxel_parts
from src.nesting3d.tuner import tune

# İnce-açı refinement (Faz 2b) — dünya ekseni vektörleri
_REFINE_AXIS_VEC = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}

# Voxelizasyon güvenlik oranı: bir parçanın en küçük boyutu / pitch bu değerin
# ALTINA düşerse parça voxel grid'de KAYBOLUR (boş grid → hata). 0.5 teorik
# sınır; 0.6 güvenlik payı bırakır.
_VOXEL_SAFE_RATIO = 0.6


def clearance_to_voxels(clearance_mm: float, pitch: float):
    """Parça-arası min boşluk (mm) -> (margin, z_clearance) voxel sayıları.

    Hoca şartı (2026-06-11): parçalar arasında her yönde min 1 mm boşluk. Bu
    voxel katmanında iki bağımsız mekanizmayla verilir:
      - margin      = YATAY dilation (voxelize._dilate, yalnız x/y).
      - z_clearance = DİKEY boşluk (Bin3D, istif arayüzü başına tek taraflı).

    clearance_mm == 0.0 (varsayılan): (0, 1) = MEVCUT davranış BİT-ÖZDEŞ
      (yatay dilation YOK; dikey z_clearance tarihsel tek-hücre değeri).
    clearance_mm > 0:
      margin = z_clearance = max(1, ceil(clearance_mm / pitch))

    ÖLÇÜM-KALİBRELİ FORMÜL (2026-07-06): Naif "2*margin*pitch alt-sınır" YANLIŞ
    çıktı. Deneme4 @0.5mm bağımsız ölçüm (plain DBLF + wall_aware üretim yolu):
      margin=1, zc=2  -> min_boşluk 0.79-0.90 mm  (HÂLÂ < 1mm İHLAL)
      margin=2, zc=2  -> min_boşluk 1.05 mm       (OK >= 1mm)
    Konservatif slice-voxelizasyon (merkez-içi + yüzey hücreleri) ve DBLF'in
    dilated-grid bitişikliği, gerçek boşluğu voxel başına ~pitch DEĞİL ~pitch/2
    kadar açıyor; bu yüzden garanti için margin da z_clearance kadar (ceil(
    clearance/pitch)) olmalı. pitch 0.5 -> 2 (ölçümle OK), pitch 2.0 -> 1
    (NFV/benchmark margin=1 konvansiyonuyla tutarlı), pitch 5.0 -> 1.

    NOT: NFV yolu (nfv_solve) zaten margin=1 kullanır; bu yardımcı yalnız
    NFV-DIŞI (coarse_to_fine / heightmap / tuner / dblf-fallback) yolları içindir.
    Ölçüm HAKEM: gerçek min boşluk clearance.min_clearance ile doğrulanır.
    """
    if clearance_mm <= 0.0:
        return 0, 1
    n = max(1, math.ceil(clearance_mm / pitch))
    return n, n


def _min_feature_mm(instance: NestingInstance) -> float:
    """Instance'taki EN İNCE parçanın en küçük boyutu (mm).

    Coarse pitch'in üst sınırını belirler: pitch bundan fazla kabalaşırsa
    en ince parça voxelize'da kaybolur. Boyut metası yoksa 0.0 döner.
    """
    best = float("inf")
    for p in instance.parts:
        dims = [d for d in (p.width_mm, p.depth_mm, p.height_mm)
                if d is not None and d > 0]
        if dims:
            best = min(best, min(dims))
    return best if best != float("inf") else 0.0


def _voxelize_with_fallback(
    instance: NestingInstance, pitch: float, floor_pitch: float,
    *, n_orientations: int = 4, clearance_mm: float = 0.0
):
    """Voxelize; boş-grid hatasında pitch'i otomatik KIS (ince-duvar güvenliği).

    bbox boyutu güvenli görünse bile bir parça ince-duvarlı (içi boş) olabilir
    ve kaba pitch'te kaybolur (ValueError). Bu durumda pitch ×1/1.5 ile küçülür,
    floor_pitch'e (fine) kadar denenir. Döner: (voxel_parts, kullanılan_pitch).

    clearance_mm > 0 ise yatay margin GERÇEKTEN kullanılan pitch'ten türetilir
    (pitch küçülürse margin voxel sayısı artar -> mm-boşluk sabit kalır).
    clearance_mm == 0.0 -> margin=0 (mevcut davranış bit-özdeş).
    """
    cur = pitch
    while True:
        try:
            margin, _zc = clearance_to_voxels(clearance_mm, cur)
            return to_voxel_parts(instance, cur, n_orientations=n_orientations,
                                  margin=margin), cur
        except ValueError:
            nxt = cur / 1.5
            if nxt <= floor_pitch:
                # floor'a indik: son çare floor ile dene (patlarsa propagate)
                margin, _zc = clearance_to_voxels(clearance_mm, floor_pitch)
                return to_voxel_parts(instance, floor_pitch,
                                      n_orientations=n_orientations,
                                      margin=margin), floor_pitch
            cur = nxt


def suggest_coarse_pitch(
    instance: NestingInstance,
    fine_pitch: float,
    *,
    factor: float = 3.0,
) -> float:
    """Her veriye özel, EN KABA-GÜVENLİ coarse pitch (mm).

    - Hedef: fine_pitch × factor (hız-kalite dengesi).
    - Güvenlik tavanı: en ince parça voxelize'da kaybolmasın
      (min_feature / _VOXEL_SAFE_RATIO). Hedef bunu aşarsa tavana kelepçelenir.
    - fine_pitch'ten küçük olamaz.

    Böylece ince parçalı siparişlerde (örn. 1 mm parça) sabit kaba pitch'in
    voxelizasyonu patlatması engellenir — coarse pitch otomatik daralır.
    """
    target = fine_pitch * factor
    min_feat = _min_feature_mm(instance)
    if min_feat > 0:
        safe_cap = min_feat / _VOXEL_SAFE_RATIO
        target = min(target, safe_cap)
    return max(fine_pitch, target)


# ---------------------------------------------------------------------------
# İnce-açı refinement (Faz 2b) — hocanın "0.5-1° hassas döndürme" isteği
# ---------------------------------------------------------------------------


def _refined_rot_matrices(
    base_rot: np.ndarray, window_deg: float, step_deg: float, axes
) -> List[np.ndarray]:
    """Kazanan ayrık poz (base_rot) çevresinde ince-açı rotasyon matrisleri.

    İlk eleman DAİMA base_rot (0° = tam ayrık poz). _best_position eşitlikte en
    küçük orientation_idx'i seçtiğinden perturbasyonsuz poz önceliklidir →
    REGRESYON KORUMASI: refinement bir parçaya, mevcut yığın durumunda baz
    pozdan daha kötü bir yerleşim ASLA seçtirmez (en kötü baz poza eşit).

    Perturbasyon: her eksen için ±step, ±2·step, ... ±window (dünya ekseninde
    R_pert @ base_rot ile pozu küçük açı döndür — örn. Z = plaka düzleminde
    in-plane dönüş). Sürekli açı (master sette yok), 1° gibi ince adımlar.
    """
    base = np.asarray(base_rot, dtype=float)
    mats = [base]
    if window_deg <= 0 or step_deg <= 0:
        return mats
    import trimesh
    n = int(round(window_deg / step_deg))
    offsets: List[float] = []
    for k in range(1, n + 1):
        offsets.append(k * step_deg)
        offsets.append(-k * step_deg)
    for ax in axes:
        v = _REFINE_AXIS_VEC[ax]
        for a in offsets:
            R = trimesh.transformations.rotation_matrix(math.radians(a), v)
            mats.append(R @ base)
    return mats


def _build_refined_fine_parts(
    instance: NestingInstance,
    fine_pitch: float,
    orient_map: Dict[str, int],
    *,
    window_deg: float,
    step_deg: float,
    axes,
    margin: int = 0,
    orient_rot: Optional[Dict[str, np.ndarray]] = None,
):
    """Fine voxel parçalarını, her parçanın KAZANAN ayrık pozu çevresinde
    ince-açı aday oryantasyonlarıyla kur.

    Önce ucuz tek-poz `to_voxel_parts` ile doğru id/mesh şeması alınır (expand
    edilmiş id'ler coarse order_ids ile eşleşmeli), sonra her parçanın
    `.orientations` alanı refinement adaylarıyla DEĞİŞTİRİLİR. Voxelizasyon
    (model_adı, ayrık_poz_indeksi) ile ÖNBELLEKLENİR — aynı modelin aynı pozu
    olan onlarca parça tek voxelizasyonu paylaşır (gerçek STL'lerde maliyet
    böyle kontrol altında kalır).
    """
    from src.nesting3d.voxelize import (
        rotation_matrices, N_MASTER_POSES, voxelize_part)

    master = rotation_matrices(N_MASTER_POSES)
    # Doğru id/mesh için ucuz tek-poz voxelizasyon; orientations sonra değişir.
    base_parts = to_voxel_parts(instance, fine_pitch, n_orientations=1,
                                margin=margin)
    cache: Dict[tuple, List[Any]] = {}
    for part in base_parts:
        didx = orient_map.get(part.id, 0)
        if didx < 0 or didx >= len(master):
            didx = 0
        # Baz poz: kazananin GERCEK rot matrisi (poz-atlamaya dayanikli,
        # 2026-07-08); yoksa eski master-indeks varsayimi (birebir eski yol).
        rot0 = orient_rot.get(part.id) if orient_rot else None
        base_rot = rot0 if rot0 is not None else master[didx]
        key = (part.name, rot0.tobytes() if rot0 is not None else didx)
        if key not in cache:
            rmats = _refined_rot_matrices(base_rot, window_deg, step_deg, axes)
            try:
                vp = voxelize_part(part.name, part.mesh, fine_pitch,
                                   rot_matrices=rmats, method="slice",
                                   margin=margin)
                cache[key] = vp.orientations
            except Exception:
                # Dejenere aci dayanikliligi (2026-07-07, plan3 probu):
                # bazi acilarla slice-voxelize poligon kurtaramiyor (shapely
                # None.exterior — K-22 yan bulgusunun aci karsiligi). TEK bozuk
                # aci TUM cozumu OLDURMESIN: acilar TEK TEK denenir, bozulanlar
                # ATLANIR; hicbiri tutmazsa baz poza dusulur (fine_angle_safe
                # zaten yalniz iyilestirirse kullanir -> dusus kayipsiz).
                orients: List[Any] = []
                for rm in rmats:
                    try:
                        vp1 = voxelize_part(part.name, part.mesh, fine_pitch,
                                            rot_matrices=[rm], method="slice",
                                            margin=margin)
                        orients.extend(vp1.orientations)
                    except Exception:
                        continue
                if not orients:
                    vp0 = voxelize_part(part.name, part.mesh, fine_pitch,
                                        rot_matrices=[base_rot],
                                        method="slice", margin=margin)
                    orients = list(vp0.orientations)
                cache[key] = orients
        part.orientations = cache[key]
    return base_parts


# ---------------------------------------------------------------------------
# Otomatik poz-sayısı seçimi (VERİ-ODAKLI — sabit n yok)
# ---------------------------------------------------------------------------

# Poz katmanları: geometrinin doğal kademeleri (tuned sayı DEĞİL).
# TABAN = 8: "parçayı her düz yüze yatırma + 90° dönüşler" TAM menüsü (6 yüz ×
# dönüş, deduped = 8). Bu sihirli sayı değil, EKSİKSİZ düz-yerleştirme kümesi;
# arama her parçaya bu menüden en iyisini ZATEN kendi seçer (veri-odaklı, per-part).
# Üst kademeler SITUASYONEL ekstralar (maliyet/kazanç sorusu gerçek):
#   12 = +eğik pozlar (20-35°, düz olmayan yerleşim)
#   28 = küpün tam 24 simetrisi
# Algoritma tabandan başlar, ekstraları ancak kazanç varsa açar (early-stopping).
_ORIENTATION_LADDER = (8, 12, 28)
# Bir üst kademeye geçmek için gereken ASGARİ göreli kazanç. Altındaysa dur —
# ekstra pozun maliyeti kaliteyi haklı çıkarmıyor (early-stopping eşiği).
_ESCALATION_MIN_GAIN = 0.01  # %1


def _auto_select_n_orientations(
    instance: NestingInstance, plate_w_mm: float, plate_d_mm: float,
    coarse_pitch: float, fine_pitch: float,
    ladder=_ORIENTATION_LADDER, min_gain: float = _ESCALATION_MIN_GAIN,
    *, clearance_mm: float = 0.0,
):
    """Poz sayısını VERİ-ODAKLI seç — sabit n YOK, her instance kendi n'ini bulur.

    Kademeli artır (4→8→12→28); her kademede UCUZ bir constructive prob (DBLF,
    tüm pozları dener) ile coarse yüksekliği ölç. Üst kademe en az min_gain (%1)
    iyileştirmiyorsa DUR (early-stopping) — ekstra pozun maliyeti kaliteyi haklı
    çıkarmadığında boşuna ödenmez. Kazanan kademenin coarse voxel parçaları
    yeniden kullanılmak üzere döner (çift voxelizasyon yok).

    Döner: (best_n, coarse_parts, used_pitch, trail)  — trail=[(n, yükseklik),...]
    """
    from src.nesting3d.dblf import dblf

    prev_h = None
    best_n = ladder[0]
    best_parts = None
    best_used = coarse_pitch
    trail = []
    for n in ladder:
        parts, used = _voxelize_with_fallback(
            instance, coarse_pitch, fine_pitch, n_orientations=n,
            clearance_mm=clearance_mm)
        _margin, _zc = clearance_to_voxels(clearance_mm, used)

        def factory(_p=used, _z=_zc):
            return Bin3D(plate_w_mm, plate_d_mm, _p, z_clearance=_z)

        _, b = dblf(parts, factory)
        h = b.max_height_voxels()
        trail.append((n, int(h)))
        if prev_h is None or h < prev_h * (1.0 - min_gain):
            best_n, prev_h, best_parts, best_used = n, h, parts, used
        else:
            break  # kazanç durdu → bu instance için yeterli poz bulundu
    return best_n, best_parts, best_used, trail


# ---------------------------------------------------------------------------
# Sonuc dataclass
# ---------------------------------------------------------------------------


@dataclass
class CoarseToFineResult:
    """solve_coarse_to_fine cikti dataclass'i.

    Fields
    ------
    placements      : Fine (ince) cozunurluklu Placement3D listesi.
    bin3d           : Fine Bin3D durumu (yerlesim sonrasi).
    height_mm       : Fine max_height_mm (minimize edilen hedef).
    density         : Fine doluluk orani (0..1).
    winning_config  : Coarse tuner'in kazanan konfig adi.
    coarse_height_mm: Coarse kazananin height_mm degeri (karsilastirma icin).
    coarse_pitch    : Coarse voxelizasyon adimi (mm).
    fine_pitch      : Fine voxelizasyon adimi (mm).
    coarse_time_s   : Coarse arama suresi (saniye).
    fine_time_s     : Fine yerlesim suresi (saniye).
    n_placed        : Yerlestirilmis parca sayisi.
    tune_result     : Coarse TuneResult (tuner kiyas tablosu/baseline icin).
    fine_voxel_parts: Fine voxel parcalari {id: VoxelPart} (3D onizleme icin).
    fine_angle_used : İnce-açı refinement bu çözümde GERÇEKTEN kullanıldı mı
                      (güvenli mod: yalnız global yüksekliği iyileştirdiyse True;
                      aksi halde açısız baz çözüm seçilir → False).
    fine_angle_time_s: İnce-açı rafine aşamasında geçen süre (saniye). Rafine
                      hiç koşmadıysa (KAPALI/atlandı/window=0) 0.0. Telemetri
                      (rapor-only): H-15 "asla zarar vermez ama hep ödetir"
                      maliyetini görünür kılar.
    drop_cache_stats: Fine yerlesim Bin3D'sinin drop_map onbellek istatistikleri
                      (H-16). drop_cache=False iken (uretim default) None;
                      acikken {hit_ratio, keys, peak_mb, fallbacks, ...}
                      (Bin3D.drop_cache_stats). Rapor-only telemetri.
    """

    placements: List[Placement3D]
    bin3d: Bin3D
    height_mm: float
    density: float
    winning_config: str
    coarse_height_mm: float
    coarse_pitch: float
    fine_pitch: float
    coarse_time_s: float
    fine_time_s: float
    n_placed: int
    tune_result: Any = None
    fine_voxel_parts: Dict[str, Any] = field(default_factory=dict)
    fine_angle_used: bool = False
    fine_angle_time_s: float = 0.0
    adaptive_reason: Optional[str] = None
    drop_cache_stats: Optional[Dict[str, object]] = None


# ---------------------------------------------------------------------------
# Ana arayuz
# ---------------------------------------------------------------------------


def solve_coarse_to_fine(
    instance: NestingInstance,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    coarse_pitch: Optional[float] = None,
    fine_pitch: float,
    budget: int = 70,
    seed: int = 42,
    menu: Optional[Dict[str, Any]] = None,
    n_orientations: int = 4,
    fine_angle_window: float = 0.0,
    fine_angle_step: float = 1.0,
    fine_angle_axes: str = "z",
    fine_angle_safe: bool = True,
    adaptive: bool = False,
    skip_fine_angle: bool = False,
    drop_cache: bool = False,
    drop_cache_cap_mb: float = 300.0,
    clearance_mm: float = 0.0,
    no_go_bounds=None,
) -> CoarseToFineResult:
    """Coarse-to-fine iki asamali nesting coz.

    Asama 1 — COARSE
    ~~~~~~~~~~~~~~~~
    Instance'i coarse_pitch ile voxelize et.  tune() ile tum algoritma
    portfoyunu (veya menu varsa o menudeki konfigleri) kos.  Kazanan
    SolveResult'tan parca sirasini (order_ids) ve oryantasyon indekslerini
    (orient_map) cikart.

    Asama 2 — FINE
    ~~~~~~~~~~~~~~
    Instance'i fine_pitch ile yeniden voxelize et.  Coarse'dan gelen siray
    ve oryantasyonlari kullanarak place_in_order ile tek geciste yerlesim
    yap.  Density hesabi bin3d.packing_density() ile yapilir.

    Parametreler
    ------------
    instance        : Cozulecek NestingInstance.
    plate_w_mm      : Tabla genisligi (mm).
    plate_d_mm      : Tabla derinligi (mm).
    coarse_pitch    : Kaba voxel adimi (mm) — arama icin.
    fine_pitch      : Ince voxel adimi (mm) — final kalitesi icin.
    budget          : Her konfig icin iterasyon sayisi.
    seed            : Deterministik tohum.
    menu            : Opsiyonel ozel tune menüsü; None ise build_menu() kullanilir.
    n_orientations  : Voxelizasyon poz sayisi (master sete indeks ust siniri).
                      4 = ilk 4 eksen-hizali (varsayilan); 8 = 8 eksen-hizali;
                      12 = +4 egik poz (20-35°); 28 = tum 24 simetri+egik.
                      Hem coarse arama hem fine yerlesim AYNI poz setini kullanir
                      (tutarlilik: coarse'un sectigi oryantasyon indeksi fine'da
                      ayni poza isaret etmeli).
    fine_angle_window: İnce-açı refinement penceresi (derece). 0 = KAPALI
                      (mevcut davranis, ayrik poz aynen). >0 ise fine asamada
                      her parca kazanan ayrik pozun ±window° cevresinde
                      fine_angle_step° adimli aday acilarda yeniden voxelize
                      edilir; _best_position en dusuk z_top'u secer. Hocanin
                      0.5-1° hassas dondurme istegi (Faz 2b).
    fine_angle_step : Refinement aci adimi (derece, varsayilan 1.0).
    fine_angle_axes : Perturbasyon eksenleri ("z" = plaka duzleminde in-plane
                      donus; "xyz" = uc eksen). Varsayilan "z".
    fine_angle_safe : True (varsayilan) ise algoritma HEM acisiz baz cozumu HEM
                      ince-acili cozumu uretir, GLOBAL yuksekligi daha iyi olani
                      secer → ince aci ASLA zarar veremez (yalniz iyilestirirse
                      kullanilir). False ise refined kosulsuz secilir (ham etkiyi
                      olcmek/deney icin). fine_angle_window=0 iken etkisiz.
    adaptive        : True ise SABIT ince-aci ayari yerine, coarse voxellerden
                      cikan "kutuluk" ozelligine gore ince-aci penceresi/eksenleri
                      OTOMATIK secilir (adaptive_params.recommend). Kutu parcalarda
                      ince-aci atlanir, duzensizlerde acilir. Veri-odakli: tek bir
                      veriye tuned sabit sayi yerine her instance'a uyarlanir.
                      Karar gerekcesi sonuc.adaptive_reason'a yazilir. Bu modda
                      fine_angle_window vb. argumanlari override edilir.
    skip_fine_angle : True ise ince-aci rafine asamasi (adaylar/ikinci gecis)
                      HIC kosmaz -> yalniz acisiz baz cozum kullanilir. OPT-IN
                      hiz fix'i (H-15p): kabuk/donel-simetrik ailelerde rafine
                      SONUCA hic girmiyor ama ~11x yerlesim + ek voxelize
                      odetiyor. Varsayilan False = mevcut davranis BIREBIR
                      (adaptive/recommend ciktisi dahil hicbir default degismez).
                      fine_angle_window>0 (veya adaptive rafine acsa) bile bu
                      bayrak True iken rafine atlanir.
    drop_cache      : True ise FINE yerlesim Bin3D'si dirty-region drop_map
                      onbellegini kullanir (H-16). OPT-IN hiz fix'i: kabuk/
                      donel-simetrik ailelerde (wall_aware) fine dblf gecisi
                      ~4x hizlanir, yukseklik ve yerlesim BIREBIR ayni kalir
                      (cache dogruluk-notr, h16_on_analiz: sizinti 0/20 +
                      bit-ozdes 20/20). Varsayilan False = mevcut davranis
                      BIREBIR (onbelleksiz yol). THREAD-GUVENLIGI: bu Bin3D
                      _run_fine icinde LOKAL kurulur, sirali place_in_order
                      dongusunde kullanilir ve BASKA THREAD'e verilmez;
                      paralel decode yolu ayri sinif (OccupancyBin3D) kullanir
                      -> per-decode tek-thread garantisi yapisal, lock gereksiz.
    drop_cache_cap_mb: drop_cache=True iken onbellek bellek tavani (MB, LRU
                      eviction esigi). Varsayilan 300. Kapaliyken etkisiz.
    clearance_mm    : Parca-arasi GARANTI edilen min bosluk (mm; hoca sarti
                      2026-06-11). 0.0 (varsayilan) -> MEVCUT davranis BIT-OZDES
                      (yatay margin=0, dikey z_clearance=1). >0 iken HER
                      voxelize (coarse + fine) ve HER Bin3D (coarse + fine)
                      kendi pitch'inden turetilen (margin, z_clearance) ile
                      kurulur (clearance_to_voxels) -> yatay dilation + dikey
                      bosluk birlikte >= clearance_mm gercek boslugu saglar.
                      NFV yolu ayri (zaten margin=1); bu param yalniz bu
                      NFV-DISI coarse_to_fine yolunu etkiler.

    Returns
    -------
    CoarseToFineResult
    """
    # coarse_pitch=None → her veriye özel en kaba-güvenli pitch otomatik seçilir
    # (en ince parça voxelize'da kaybolmayacak şekilde — sabit kaba pitch'in
    # ince parçalı siparişlerde patlamasını önler).
    if coarse_pitch is None:
        coarse_pitch = suggest_coarse_pitch(instance, fine_pitch)

    # ------------------------------------------------------------------
    # Asama 1: COARSE arama
    # ------------------------------------------------------------------
    t0 = time.perf_counter()

    # Adaptif: poz sayısını VERİ-ODAKLI seç (kademeli artır, kazanç durunca dur).
    # Sabit n yerine her instance kendi n'ini bulur; kazanan voxeller reuse edilir.
    n_orient_trail = None
    if adaptive:
        n_orientations, coarse_parts, coarse_pitch, n_orient_trail = \
            _auto_select_n_orientations(
                instance, plate_w_mm, plate_d_mm, coarse_pitch, fine_pitch,
                clearance_mm=clearance_mm)
    else:
        # İnce-duvarlı parça kaba pitch'te kaybolursa pitch otomatik kısılır.
        coarse_parts, coarse_pitch = _voxelize_with_fallback(
            instance, coarse_pitch, fine_pitch, n_orientations=n_orientations,
            clearance_mm=clearance_mm,
        )

    # Coarse Bin3D dikey boşluğu coarse pitch'ten türetilir (clearance_mm=0 ->
    # z_clearance=1, mevcut davranış bit-özdeş).
    _coarse_margin, _coarse_zc = clearance_to_voxels(clearance_mm, coarse_pitch)

    # NO-GO area (2026-07-07): yasak-bolge mm-bbox'u verildiyse her pitch'te
    # maske kurulup Bin3D'ye gecilir (default None = BIT-OZDES eski davranis).
    def _ng_mask(_pitch):
        if no_go_bounds is None:
            return None
        return Bin3D.no_go_mask_from_bounds(
            no_go_bounds, plate_w_mm, plate_d_mm, _pitch)

    def coarse_factory() -> Bin3D:
        # drop_cache COARSE'ta da (2026-07-08, py-spy kaniti: plan2 tam-portfoy
        # suresi coarse tune'daki kachesiz _drop_map_general'de yasiyor; H-15
        # dersi "coarse-tune %90" + H-16 cache BIT-OZDES kanitli). Ayni bayrak
        # iki asamayi da acar — default False = eski davranis birebir.
        return Bin3D(plate_w_mm, plate_d_mm, coarse_pitch, z_clearance=_coarse_zc,
                     no_go_mask=_ng_mask(coarse_pitch),
                     drop_cache=drop_cache, drop_cache_cap_mb=drop_cache_cap_mb)

    tune_result = tune(
        coarse_parts,
        coarse_factory,
        budget=budget,
        seed=seed,
        menu=menu,
    )

    coarse_time_s = time.perf_counter() - t0
    winner = tune_result.result

    # Coarse kazananindan sira ve oryantasyon cikar
    order_ids: List[str] = [p.part_id for p in winner.placements]
    orient_map: Dict[str, int] = {
        p.part_id: p.orientation_idx for p in winner.placements
    }
    # Poz-atlamaya dayanikli esleme (2026-07-08, None.exterior fix'inin
    # tamamlayicisi): voxelize_part artik dejenere pozu ATLAYABILIR ->
    # orientations listesi kisalir ve coarse indeksi fine listesinde BASKA
    # (hatta tasan) poza denk gelebilir. Kazananin GERCEK rot matrisi tasinir;
    # fine tarafinda indeks matris eslesmesiyle yeniden bulunur.
    _coarse_by_id = {p.id: p for p in coarse_parts}
    orient_rot: Dict[str, np.ndarray] = {}
    for _pl in winner.placements:
        _cp = _coarse_by_id.get(_pl.part_id)
        if _cp is not None and 0 <= _pl.orientation_idx < len(_cp.orientations):
            orient_rot[_pl.part_id] = np.asarray(
                _cp.orientations[_pl.orientation_idx].rot_matrix, dtype=float)

    # ------------------------------------------------------------------
    # Adaptif: sabit ince-açı yerine coarse voxellerden "kutuluk" özelliğiyle
    # veri-odaklı seç (kutu→atla, düzensiz→aç). Şeffaf gerekçe kaydedilir.
    # ------------------------------------------------------------------
    adaptive_reason: Optional[str] = None
    if adaptive:
        from src.nesting3d.adaptive_params import recommend
        rec = recommend(coarse_parts)
        fine_angle_window = rec.fine_angle_window
        fine_angle_step = rec.fine_angle_step
        fine_angle_axes = rec.fine_angle_axes
        adaptive_reason = (f"poz: {n_orient_trail} → n={n_orientations} "
                           f"(kazanç durunca durdu); {rec.reason}")

    # ------------------------------------------------------------------
    # Asama 2: FINE yerlesim
    # ------------------------------------------------------------------
    t1 = time.perf_counter()

    # Fine (margin, z_clearance) fine pitch'ten türetilir. clearance_mm=0 ->
    # (0, 1) = mevcut davranış bit-özdeş (margin yok, tarihsel z_clearance=1).
    _fine_margin, _fine_zc = clearance_to_voxels(clearance_mm, fine_pitch)

    # H-15p OPT-IN atlama: skip_fine_angle True iken rafine yolu HIC kosmaz
    # (window>0 / adaptive rafine acsa bile). Baz cozum kullanilir -> kalite
    # riski sifir olan ailelerde (kabuk/donel-simetrik) 11x yerlesim + ek
    # voxelize odenmez. Default False -> mevcut davranis birebir.
    refine_on = bool(fine_angle_window and fine_angle_window > 0) \
        and not skip_fine_angle

    def _run_fine(parts_by_id, orient_fn):
        """order_ids sırasında verilen parçaları yerleştir → (placements, bin).

        H-16: drop_cache True ise fine Bin3D dirty-region drop_map onbellegini
        acar. Bu Bin3D burada LOKAL kurulur ve yalniz asagidaki sirali
        place_in_order dongusunde okunur/yazilir -> baska thread'e sizmaz
        (per-decode tek-thread; lock gereksiz — bkz. docstring THREAD-GUVENLIGI).
        """
        ordered = [parts_by_id[pid] for pid in order_ids if pid in parts_by_id]
        b = Bin3D(plate_w_mm, plate_d_mm, fine_pitch, z_clearance=_fine_zc,
                  drop_cache=drop_cache, drop_cache_cap_mb=drop_cache_cap_mb,
                  no_go_mask=_ng_mask(fine_pitch))
        pls = place_in_order(ordered, b, orient_fn)
        return pls, b

    # --- Baz çözüm (ince açı YOK) — daima üretilir (güvenli karşılaştırma tabanı)
    base_parts = to_voxel_parts(instance, fine_pitch,
                                n_orientations=n_orientations,
                                margin=_fine_margin)
    base_by_id: Dict[str, Any] = {p.id: p for p in base_parts}

    # orient_map'i FINE listesine yeniden hizala: once rot-matris eslesmesi,
    # bulunamazsa eski indeks LEN-KELEPCELI (poz atlandiysa liste kisalmis
    # olabilir — tasan indeks IndexError'la cozumu oldurmesin).
    for _pid, _fp in base_by_id.items():
        _rot = orient_rot.get(_pid)
        _idx = None
        if _rot is not None:
            for _i, _o in enumerate(_fp.orientations):
                if np.allclose(_o.rot_matrix, _rot, atol=1e-9):
                    _idx = _i
                    break
        if _idx is None:
            _idx = min(orient_map.get(_pid, 0), len(_fp.orientations) - 1)
        orient_map[_pid] = _idx

    def _base_orient(idx: int, part: Any) -> tuple:
        return (orient_map.get(part.id, 0),)

    base_pls, base_bin = _run_fine(base_by_id, _base_orient)

    fine_angle_used = False
    fine_angle_time_s = 0.0
    if refine_on:
        # Telemetri (H-15): rafine asamasinin GERCEK maliyetini olc (rapor-only).
        _t_ref = time.perf_counter()
        # --- İnce-açılı çözüm: kazanan pozun ±window° çevresinde 1° adımlı
        # adaylar; _best_position en iyiyi (baz=indeks 0 öncelikli) seçer.
        axes = tuple(a for a in fine_angle_axes.lower()
                     if a in _REFINE_AXIS_VEC) or ("z",)
        ref_parts = _build_refined_fine_parts(
            instance, fine_pitch, orient_map,
            window_deg=fine_angle_window, step_deg=fine_angle_step, axes=axes,
            margin=_fine_margin, orient_rot=orient_rot,
        )
        ref_by_id: Dict[str, Any] = {p.id: p for p in ref_parts}

        def _ref_orient(idx: int, part: Any):
            return range(len(part.orientations))

        ref_pls, ref_bin = _run_fine(ref_by_id, _ref_orient)

        # ALGORİTMA KENDİSİ SEÇER: global yüksekliği daha iyi olanı al.
        # safe=True → ince açı yalnız STRICT iyileştirirse kullanılır (eşitlikte
        # baz; ince açı asla zarar veremez). safe=False → refined koşulsuz (deney).
        ref_better = ref_bin.max_height_voxels() < base_bin.max_height_voxels()
        if (not fine_angle_safe) or ref_better:
            fine_placements, fine_bin, fine_by_id = ref_pls, ref_bin, ref_by_id
            fine_angle_used = True
        else:
            fine_placements, fine_bin, fine_by_id = base_pls, base_bin, base_by_id
        fine_angle_time_s = time.perf_counter() - _t_ref
    else:
        fine_placements, fine_bin, fine_by_id = base_pls, base_bin, base_by_id

    fine_time_s = time.perf_counter() - t1

    # ------------------------------------------------------------------
    # Metrikler
    # ------------------------------------------------------------------
    height_mm = fine_bin.max_height_mm()
    density = fine_bin.packing_density()

    # H-16 telemetri (rapor-only): kazanan fine Bin3D'nin onbellek istatistikleri.
    # drop_cache=False iken enabled=False sozlugu doner; disariya None gecir ki
    # kapali yolda telemetri de eski (alan yok) kalsin -> birebir dokunulmazlik.
    _dc_stats = fine_bin.drop_cache_stats() if drop_cache else None

    return CoarseToFineResult(
        placements=fine_placements,
        bin3d=fine_bin,
        height_mm=height_mm,
        density=density,
        winning_config=tune_result.winning_config_name,
        coarse_height_mm=winner.height_mm,
        coarse_pitch=coarse_pitch,
        fine_pitch=fine_pitch,
        coarse_time_s=coarse_time_s,
        fine_time_s=fine_time_s,
        n_placed=len(fine_placements),
        tune_result=tune_result,
        fine_voxel_parts=fine_by_id,
        fine_angle_used=fine_angle_used,
        fine_angle_time_s=fine_angle_time_s,
        adaptive_reason=adaptive_reason,
        drop_cache_stats=_dc_stats,
    )
