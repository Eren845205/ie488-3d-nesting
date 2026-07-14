"""demo_pipeline.py — Uçtan uca demo pipeline (§6.4 işleyiş zinciri).

Zincir:
    1. Sipariş havuzu → rank_orders (EDD ağırlıklı önceliklendirme)
    2. build_batches (allow_mixing=False) → parti planı
    3. check_feasibility → termin uyarıları
    4. Her parti için: NestingInstance kur → suggest_pitch (adaptif) →
       to_voxel_parts → Instance-Tuner (portföy + menü konfigleri) yerleşimi
       → yükseklik + doluluk metrikleri + tuner konfig kıyası
       + Algoritma-seçim tahmini (artefakt varsa; yoksa gizlenir)
    5. Her parti için: PricingEngine → fiyat dökümü
    6. results/demo_pipeline_report.md → bölümlü markdown raporu
    7. Konsola özet bas

Deterministik: sabit ref_date + seed; iki koşu aynı raporu üretir.

Tuner: build_menu() konfigleri (baseline portföy + 6 ek konfig) her parti
için aynı TUNER_BUDGET/seed ile koşar; en iyi monoton kabul garantisi ile
seçilir; kazanan konfig + DBLF'ye kazanç% rapora eklenir.

Selection: data/selection_model.json artefaktı varsa yüklenir; her parti için
is_easy + predicted_winner + explain bilgisi nesting_results'a eklenir
(BİLGİLENDİRME — çözüm her zaman tuner'dan gelir).

Kullanım:
    python scripts/demo_pipeline.py
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Proje kökü
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

RESULTS_DIR = _ROOT / "results"
REPORT_FILENAME = "demo_pipeline_report.md"

# Instance-Tuner demo bütçesi: demo süresi < ~15 s kalsın
TUNER_BUDGET = 70

# Coarse-to-fine otomatik tetik: bu kadar parçadan ÇOK olan siparişlerde
# (gerçek-dünya ölçeği) kaba-optimize → ince-final kullanılır. Küçük demo
# senaryoları doğrudan tek-çözünürlük tune ile koşar (zaten hızlı).
C2F_THRESHOLD = 40            # voxel-parça (kopya açılmış) eşiği


class _SkipTelemetryV2(Exception):
    """Telemetri v2 yazimini bilerek atla (test/disable) — kontrol-akisi istisnasi."""
COARSE_BUDGET = 25           # kaba aşama iterasyon (final ince + tam menü)

# Web nesting yollarında GARANTİ edilen parça-arası min boşluk (mm). Hoca şartı
# GÜNCELLENDİ (2026-07-09 cevap 5, ANAYASA A2): her yönde >= 2 mm ("2mm daha
# güvenli; TÜM boşluklar için geçerli"). Eski 1mm değeri 2026-06-11 kuralıydı.
# Bu değer clearance_to_voxels ile pitch'e göre (margin, z_clearance) voxel
# sayısına çevrilir. NFV kalite yolu ayrıca pitch'ini de bundan türetir
# (K-38 clearance-kuantizasyonu: pitch == clearance = tek-voxel TAM pencere).
# Fix 2026-07-06: eski web yolu margin=0 + z_clearance=1 -> ince pitch'te (Deneme4
# @0.5mm) gerçek boşluk 0.083mm'ye iniyordu (ihlal); artık pitch'ten türetilir.
WEB_MIN_CLEARANCE_MM = 2.0

# HIGH-2 runtime clearance kapisi (2026-07-06): her web nest'ten SONRA uretilen
# yerlesimin gercek min boslugu ORNEKLEM ile dogrulanir. min_clearance UST-sinir
# oldugundan olculen deger < esik ise KESIN ihlal. Bu ornek/mesh sayisi hiz-
# duyarlilik dengesidir (588 parca ~10s). Voxel-katmani margin ASIL garanti;
# bu bagimsiz post-nest dogrulama/uyari (reviewer HIGH-2).
CLEARANCE_GATE_SAMPLES = 3000

# Parti-seviyesi PARALEL nesting: birden çok bağımsız parti (örn. 5 farklı
# müşteriden 5 ayrı sipariş) ayrı SÜREÇLERDE aynı anda koşar → toplam süre =
# en yavaş tek partininki, partilerin TOPLAMI değil. Partiler tam bağımsız
# (sonuç batch_id'ye yazılır), paylaşılan değişken durum yok. Sıralı CPU-bound
# (GIL) olduğundan thread değil SÜREÇ gerekir. Otomatik tetik: >=2 parti VE
# toplam parça > PARALLEL_MIN_PARTS. Sonuç paralel/sıralıda AYNI (seed aynı).
PARALLEL_MIN_PARTS = 40      # bu kadar parçanın altında paralel ek-maliyeti değmez

# Paralel işçi (süreç) ÜST SINIRI. Sınırsız DEĞİL — işlemciyi/ RAM'i boğmamak,
# makineyi (sunucu + operatör UI + tarayıcı aynı cihazda) yanıt-verir tutmak için.
# Politika (donanım-farkında, _resolve_max_workers):
#   1. Açık override: env NESTING_MAX_WORKERS (kesin işçi sayısı).
#   2. Otomatik: tespit_edilen_çekirdek - NESTING_RESERVE_CORES (OS/UI'ye pay),
#      en az 1; ayrıca PARALLEL_HARD_CAP ve parti sayısı ile kısıtlanır.
# Her işçi tam bir süreç (kendi RAM'i) olduğundan işçi sayısı = RAM yükü de demek.
PARALLEL_RESERVE_CORES = 2   # OS/UI/tarayıcıya bırakılan çekirdek (env ile değişir)
PARALLEL_HARD_CAP = 8        # VARSAYILAN mutlak tavan (bilinmeyen müşteri makinesi
                             # için güvenli). env NESTING_HARD_CAP ile EZİLİR —
                             # süper bilgisayarda NESTING_HARD_CAP=64 gibi yüksek
                             # ver → tam paralellik. Tavan tamamen kaldırılmaz:
                             # RAM okunamadığında (kapı atlanır) ve çok-sayıda
                             # küçük partide aşırı süreç spawn'ını önler (son emniyet).
# RAM-FARKINDA sınır: işçi sayısı sadece çekirdeğe değil, BOŞ RAM'e de tabi.
# Her işçi ayrı süreç (Python + voxel ızgaraları). Çok çekirdekli ama az-RAM'li
# makinede çekirdek-kadar işçi belleği şişirir (swap/çökme). Bu yüzden:
#   ram_işçi = (boş_RAM × NESTING_RAM_HEADROOM) / NESTING_MEM_PER_WORKER_GB
# ile de kısıtlanır. per-worker bütçe bir KESTİRİM (parça/çözünürlüğe bağlı) —
# env ile ayarlanır; RAM okunamazsa bu sınır atlanır (CPU-only eski davranış).
PARALLEL_MEM_PER_WORKER_GB = 1.5   # işçi-başına tahmini RAM bütçesi (env ile değişir)
PARALLEL_RAM_HEADROOM = 0.8        # boş RAM'in en çok bu oranı paralele ayrılır
# Kaba pitch = fine × faktör. SABİT TABAN YOK: fine_pitch zaten en ince
# parçaya göre güvenli (suggest_pitch = min_feature/2.5); ×3 ile çarpınca
# min_feature/coarse ≈ 0.83 > 0.5 → ince parça KAYBOLMAZ. Sabit 3mm taban,
# 1mm parçalı siparişlerde (Plan2) voxelizasyonu patlatıyordu.
COARSE_PITCH_FACTOR = 3.0

# Algoritma-seçim model artefaktı
SELECTION_MODEL_PATH = _ROOT / "data" / "selection_model.json"

# ---------------------------------------------------------------------------
# Senaryo fixture — Ford/Baykar/ASELSAN havuzu + parça listeleri
# ---------------------------------------------------------------------------

SCENARIO: Dict[str, Any] = {
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    # Kapasite: 1 makine, 8 saatlik parti, 1 vardiya, 25 000 cm3 parti hacim sınırı
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 25_000.0,
    },
    # Konteyner boyutu (335x250 tabanlı kaba demo — pitch büyük tutuldu)
    "container": {
        "width_mm": 335.0,
        "depth_mm": 250.0,
    },
    # pitch artık suggest_pitch ile instance'tan türetilir; bu alan fallback
    "pitch": 15.0,
    "n_orientations": 4,
    # Portföy bütçesi: her çözücü başına iterasyon (demo hızı için 120)
    "portfolio_budget": 120,
    # Sipariş havuzu — her siparişe kutu parça listesi eklendi
    "orders": [
        {
            "order_id": "ORD-FORD-A1",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "ford_a1_p1", "name": "ford_bracket",
                 "qty": 4, "source": "box",
                 "width_mm": 80.0, "depth_mm": 60.0, "height_mm": 30.0},
                {"id": "ford_a1_p2", "name": "ford_cover",
                 "qty": 2, "source": "box",
                 "width_mm": 100.0, "depth_mm": 80.0, "height_mm": 20.0},
            ],
        },
        {
            "order_id": "ORD-FORD-A2",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "ford_a2_p1", "name": "ford_flange",
                 "qty": 3, "source": "box",
                 "width_mm": 70.0, "depth_mm": 70.0, "height_mm": 25.0},
            ],
        },
        {
            "order_id": "ORD-ASEL-A1",
            "customer": "ASELSAN",
            "deadline": "2026-06-20",
            "priority_class": 1,
            "parts": [
                {"id": "asel_a1_p1", "name": "asel_housing",
                 "qty": 2, "source": "box",
                 "width_mm": 120.0, "depth_mm": 90.0, "height_mm": 50.0},
                {"id": "asel_a1_p2", "name": "asel_plate",
                 "qty": 3, "source": "box",
                 "width_mm": 150.0, "depth_mm": 100.0, "height_mm": 15.0},
            ],
        },
        {
            "order_id": "ORD-BAYK-C1",
            "customer": "BAYKAR",
            "deadline": "2026-06-25",
            "priority_class": 2,
            "parts": [
                {"id": "bayk_c1_p1", "name": "bayk_rib",
                 "qty": 5, "source": "box",
                 "width_mm": 90.0, "depth_mm": 45.0, "height_mm": 20.0},
                {"id": "bayk_c1_p2", "name": "bayk_spar",
                 "qty": 2, "source": "box",
                 "width_mm": 200.0, "depth_mm": 30.0, "height_mm": 25.0},
            ],
        },
        {
            "order_id": "ORD-FORD-C1",
            "customer": "FORD",
            "deadline": "2026-06-28",
            "priority_class": 2,
            "parts": [
                {"id": "ford_c1_p1", "name": "ford_seal",
                 "qty": 6, "source": "box",
                 "width_mm": 50.0, "depth_mm": 50.0, "height_mm": 15.0},
            ],
        },
    ],
    # Portföy varsayılan senaryo: "küçük" — eski senaryoya benzer
    # (webapp'te ikon ile ayırt edilir; daha sıkı senaryo RICH_SCENARIO)
    "scenario_label": "standard",
    # Örnek fiyatlama kural seti
    "pricing_rules": {
        "version": "1.0",
        "name": "Demo kural seti v1",
        "rules": [
            {
                "id": "r_volume",
                "type": "unit_price",
                "input_field": "hacim_m3",
                "unit_price": 8000.0,
                "description": "Hacim bazlı birim fiyat (8000 $/m3)",
            },
            {
                "id": "r_konteyner",
                "type": "unit_price",
                "input_field": "konteyner_sayisi",
                "unit_price": 50.0,
                "description": "Konteyner kullanım ücreti (50 $/konteyner)",
            },
            {
                "id": "r_doluluk_bonus",
                "type": "conditional_multiplier",
                "condition_field": "doluluk_oran",
                "operator": ">=",
                "threshold": 0.6,
                "multiplier": 0.95,
                "description": "Yüksek doluluk indirimi (%5)",
            },
            {
                "id": "r_min",
                "type": "min_clamp",
                "min_price": 200.0,
                "description": "Minimum parti fiyatı",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Zengin demo senaryosu — portföyün ayırt edici olduğu yoğun vaka
# ~20 parça, sıkı taban (335×250), karışık boyutlar
# ---------------------------------------------------------------------------

RICH_SCENARIO: Dict[str, Any] = {
    # Ayırt edici "few-large-many-small" senaryosu:
    # Her parti farklı boyut dağılımına sahip; SA/MultiStartSA DBLF'yi
    # tüm 3 partide de yeniyor (gain %3.7-4.8).
    # Kabul kriterleri (ampirik olarak doğrulandı, seed=42):
    #   B001 FORD:    sa_5starts kazanır, gain≈3.7%, 3 farklı yükseklik
    #   B002 ASELSAN: sa_auto kazanır,   gain≈4.3%, 2 farklı yükseklik
    #   B003 BAYKAR:  sa_auto kazanır,   gain≈4.8%, 2 farklı yükseklik
    # Tüm parça min_dim ≥ 16 mm → suggest_pitch ≈ 6.4 mm → arama uzayı uygun.
    # Toplam koşu süresi < 10 s (TUNER_BUDGET=70, budget=350/konfig).
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 200_000.0,
    },
    "container": {
        "width_mm": 250.0,
        "depth_mm": 200.0,
    },
    "pitch": 8.0,
    "n_orientations": 4,
    "portfolio_budget": 350,
    "scenario_label": "rich",
    "orders": [
        {
            "order_id": "RICH-FORD-A1",
            "customer": "FORD",
            "deadline": "2026-06-18",
            "priority_class": 1,
            "parts": [
                {"id": "r_f_p1", "name": "ford_hull_L", "qty": 2, "source": "box",
                 "width_mm": 150.0, "depth_mm": 120.0, "height_mm": 70.0},
                {"id": "r_f_p2", "name": "ford_hull_M", "qty": 2, "source": "box",
                 "width_mm": 130.0, "depth_mm": 110.0, "height_mm": 60.0},
                {"id": "r_f_p3", "name": "ford_mid", "qty": 3, "source": "box",
                 "width_mm": 80.0, "depth_mm": 60.0, "height_mm": 40.0},
                {"id": "r_f_p4", "name": "ford_mid2", "qty": 3, "source": "box",
                 "width_mm": 70.0, "depth_mm": 55.0, "height_mm": 35.0},
                {"id": "r_f_p5", "name": "ford_small", "qty": 6, "source": "box",
                 "width_mm": 35.0, "depth_mm": 30.0, "height_mm": 25.0},
                {"id": "r_f_p6", "name": "ford_tiny1", "qty": 8, "source": "box",
                 "width_mm": 28.0, "depth_mm": 24.0, "height_mm": 20.0},
                {"id": "r_f_p7", "name": "ford_tiny2", "qty": 8, "source": "box",
                 "width_mm": 22.0, "depth_mm": 20.0, "height_mm": 16.0},
            ],
        },
        {
            "order_id": "RICH-ASEL-A1",
            "customer": "ASELSAN",
            "deadline": "2026-06-20",
            "priority_class": 1,
            "parts": [
                {"id": "r_a_p1", "name": "asel_block_L", "qty": 2, "source": "box",
                 "width_mm": 140.0, "depth_mm": 115.0, "height_mm": 65.0},
                {"id": "r_a_p2", "name": "asel_block_M", "qty": 2, "source": "box",
                 "width_mm": 120.0, "depth_mm": 100.0, "height_mm": 55.0},
                {"id": "r_a_p3", "name": "asel_mid", "qty": 3, "source": "box",
                 "width_mm": 75.0, "depth_mm": 65.0, "height_mm": 38.0},
                {"id": "r_a_p4", "name": "asel_mid2", "qty": 3, "source": "box",
                 "width_mm": 65.0, "depth_mm": 55.0, "height_mm": 32.0},
                {"id": "r_a_p5", "name": "asel_small", "qty": 6, "source": "box",
                 "width_mm": 38.0, "depth_mm": 32.0, "height_mm": 22.0},
                {"id": "r_a_p6", "name": "asel_tiny", "qty": 8, "source": "box",
                 "width_mm": 25.0, "depth_mm": 22.0, "height_mm": 18.0},
            ],
        },
        {
            "order_id": "RICH-BAYK-C1",
            "customer": "BAYKAR",
            "deadline": "2026-06-25",
            "priority_class": 2,
            "parts": [
                {"id": "r_b_p1", "name": "bayk_hull_L", "qty": 2, "source": "box",
                 "width_mm": 155.0, "depth_mm": 105.0, "height_mm": 62.0},
                {"id": "r_b_p2", "name": "bayk_hull_M", "qty": 2, "source": "box",
                 "width_mm": 120.0, "depth_mm": 90.0, "height_mm": 52.0},
                {"id": "r_b_p3", "name": "bayk_mid", "qty": 3, "source": "box",
                 "width_mm": 78.0, "depth_mm": 62.0, "height_mm": 38.0},
                {"id": "r_b_p4", "name": "bayk_mid2", "qty": 3, "source": "box",
                 "width_mm": 65.0, "depth_mm": 55.0, "height_mm": 32.0},
                {"id": "r_b_p5", "name": "bayk_small", "qty": 6, "source": "box",
                 "width_mm": 38.0, "depth_mm": 32.0, "height_mm": 22.0},
                {"id": "r_b_p6", "name": "bayk_tiny1", "qty": 8, "source": "box",
                 "width_mm": 28.0, "depth_mm": 24.0, "height_mm": 20.0},
                {"id": "r_b_p7", "name": "bayk_tiny2", "qty": 8, "source": "box",
                 "width_mm": 22.0, "depth_mm": 20.0, "height_mm": 16.0},
            ],
        },
    ],
    "pricing_rules": {
        "version": "1.0",
        "name": "Demo kural seti v1",
        "rules": [
            {
                "id": "r_volume",
                "type": "unit_price",
                "input_field": "hacim_m3",
                "unit_price": 8000.0,
                "description": "Hacim bazlı birim fiyat (8000 $/m3)",
            },
            {
                "id": "r_konteyner",
                "type": "unit_price",
                "input_field": "konteyner_sayisi",
                "unit_price": 50.0,
                "description": "Konteyner kullanım ücreti (50 $/konteyner)",
            },
            {
                "id": "r_doluluk_bonus",
                "type": "conditional_multiplier",
                "condition_field": "doluluk_oran",
                "operator": ">=",
                "threshold": 0.6,
                "multiplier": 0.95,
                "description": "Yüksek doluluk indirimi (%5)",
            },
            {
                "id": "r_min",
                "type": "min_clamp",
                "min_price": 200.0,
                "description": "Minimum parti fiyatı",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Yardımcı: hacim hesabı (cm3 → m3)
# ---------------------------------------------------------------------------

def _part_real_volume_mm3(p: Dict[str, Any]) -> tuple:
    """Tek parca GERCEK hacmi (mm3) + 'hacim-bilinmiyor' bayragi.

    box  -> w*d*h (dolu kutu; gercek hacim = bbox hacmi).
    stl  -> true_fill * w*d*h. true_fill = gercek mesh V / bbox V (watertight
            parcada stl_order_loader doldurur). true_fill None ise parca gercek
            hacmi BILINMIYOR -> (0.0, True); cagiran 'hacim eksik parca' sayar.

    Donus: (hacim_mm3, bilinmiyor_mu). Adet (qty) burada CARPILMAZ — cagiran
    _parts_real_volume_mm3 qty ile olcekler.
    """
    w = p.get("width_mm") or 0.0
    d = p.get("depth_mm") or 0.0
    h = p.get("height_mm") or 0.0
    if p.get("source") == "box":
        return float(w) * float(d) * float(h), False
    # stl (veya bbox'i olan diger kaynak): gercek doluluk true_fill'den gelir.
    tf = p.get("true_fill")
    if tf is None:
        return 0.0, True  # gercek hacim bilinmiyor (watertight degil / olculemedi)
    return float(tf) * float(w) * float(d) * float(h), False


def _parts_real_volume_mm3(parts_list: List[Dict[str, Any]]) -> tuple:
    """Parca listesinin toplam GERCEK hacmi (mm3) + hacim-eksik parca sayisi.

    box tam kutu; stl true_fill*bbox. true_fill'siz stl parcalar toplama
    KATILMAZ ama adetleri 'missing' olarak sayilir (rapor izi #17/#19).
    Donus: (toplam_mm3, hacim_eksik_parca_adedi).

    BILINCLI KARAR 2026-07-03 (DENETIM_RAPORU_2026-07-03.md Dalga-3 #17 kapanisi):
    STL siparislerde gercek mesh hacmi (true_fill*bbox) artik yalniz raporda
    DEGIL, fiyat girdisine (_build_pricing_inputs -> hacim_m3) VE parti
    gruplamaya (Order.total_volume_cm3 -> batch.total_volume_cm3) yansir. Yani
    STL hacmi fiyati ve parti hacmini ETKILER (eskiden STL hacmi 0 yutulurdu).
    true_fill None -> 0 katki (eski davranis korunur) + volume_missing_parts izi.
    """
    total = 0.0
    missing = 0
    for p in parts_list:
        qty = int(p.get("qty", 1))
        vol, unknown = _part_real_volume_mm3(p)
        if unknown:
            missing += qty
        else:
            total += vol * qty
    return total, missing


def _parts_volume_cm3(parts_list: List[Dict[str, Any]]) -> float:
    """Parça listesinden toplam hacmi cm3 cinsinden hesaplar.

    #17/#19: STL parcalar da sayilir (true_fill*bbox). ESKIDEN yalniz box
    parcalar sayilirdi -> STL siparislerin hacmi 0 gorunuyordu. box-only kosu
    (default demo senaryolari) BIREBIR ayni sonucu verir (davranis korunur).

    BILINCLI KARAR 2026-07-03 (Dalga-3 #17 kapanisi): bu deger Order.total_volume_cm3
    olarak akar -> batch.total_volume_cm3 -> _build_pricing_inputs hacim_m3. Boylece
    STL gercek hacmi fiyat + parti girdisine yansir (rapor-only DEGIL). true_fill
    None ise ilgili parca 0 katki verir (eski davranis) + volume_missing_parts izi.
    """
    total_mm3, _ = _parts_real_volume_mm3(parts_list)
    return total_mm3 / 1000.0  # mm3 -> cm3


# ---------------------------------------------------------------------------
# Yardımcı: RAM ön-guard (#23/#24) — RAPOR-ONLY
# ---------------------------------------------------------------------------
#
# Bu guard bellek-riskini yalniz RAPORLAR (pitch'i DEGISTIRMEZ). Karar: "emin
# olamadigin yerde rapor-only kal" (dalga direktifi). Boylece HICBIR kosuda
# (default demo dahil) cozucu davranisi degismez; yalniz 'bellek yetmeyecek'
# asiri durumda gorunur bir iz (reason alani) birakilir.
#
# Esik SABIT-SIHIRLI-SAYI DEGIL: suggest_nfv_pitch'teki fren formulunun ayni
# desenidir — budget = (ram_available_bytes/1e9) * NFV_CELLS_PER_GB. Karsilastirma
# grid hucre TAHMINI (envelope proxy nx*ny*nz) vs bu butce. ram_available_bytes
# None ise (RAM okunamadi) guard DEVRE DISI (CPU-only davranis korunur).

def _ram_guard_reason(
    pitch: float,
    plate_w_mm: float,
    plate_d_mm: float,
    ram_available_bytes: Optional[int],
) -> Optional[str]:
    """Bellek riskini rapor-only degerlendir; riskliyse ASCII reason, degilse None.

    RAPOR-ONLY: pitch/davranis DEGISMEZ. ram_available_bytes None -> None
    (guard kapali). Tahmin envelope proxy (heightmap/coarse occupancy grid'inin
    ust-sinir hucre sayisi); budget suggest_nfv_pitch ile ayni turetilmis oran.
    """
    if ram_available_bytes is None or ram_available_bytes <= 0 or pitch <= 0:
        return None
    try:
        from src.nesting3d.instances.pitch import (
            NFV_CELLS_PER_GB, _nfv_grid_cells,
        )
        cells = _nfv_grid_cells(pitch, plate_w_mm, plate_d_mm)
        budget = (ram_available_bytes / 1e9) * NFV_CELLS_PER_GB
        if cells > budget:
            return (
                "RAM-guard (rapor-only): tahmini grid ~%.0fM hucre @pitch %.2fmm "
                "> bellek butcesi ~%.0fM (bos RAM %.1fGB) -> bellek-riskli; pitch "
                "DEGISTIRILMEDI (davranis korundu), operator daha kaba pitch/plaka "
                "veya daha fazla RAM dusunmeli." % (
                    cells / 1e6, pitch, budget / 1e6, ram_available_bytes / 1e9,
                )
            )
    except Exception:
        return None  # tahmin kurulamazsa sessiz-guvenli (guard yok say)
    return None


# ---------------------------------------------------------------------------
# Yardımcı: NestingInstance + Bin3D kurucusu
# ---------------------------------------------------------------------------

def _build_nesting_instance(
    order_parts: List[Dict[str, Any]],
    container: Dict[str, Any],
) -> "NestingInstance":  # type: ignore[name-defined]  # noqa: F821
    """Sipariş parça listesinden NestingInstance oluşturur."""
    from src.nesting3d.instances.format import (
        ContainerSpec,
        NestingInstance,
        PartSpec,
    )

    container_spec = ContainerSpec(
        width_mm=float(container["width_mm"]),
        depth_mm=float(container["depth_mm"]),
        height_mm=container.get("height_mm"),
    )

    parts = []
    for p in order_parts:
        parts.append(
            PartSpec(
                id=p["id"],
                name=p["name"],
                qty=int(p["qty"]),
                source=p["source"],
                width_mm=p.get("width_mm"),
                depth_mm=p.get("depth_mm"),
                height_mm=p.get("height_mm"),
                stl_path=p.get("stl_path"),
                # F5/F1 aile sinyali: loader (stl_order_loader) doldurdugu cidar/doluluk
                # metasini PartSpec'e tasi ki auto mod-secimi (predict_nfv_benefit aile
                # katmani) kabuk aileyi gorebilsin. Yoksa (box/eski dict) None = davranis
                # DEGISMEZ (classify_prelim kati kabul eder).
                wall_mm=p.get("wall_mm"),
                true_fill=p.get("true_fill"),
                family=p.get("family"),
            )
        )

    return NestingInstance(container=container_spec, parts=parts)


def _bin_factory(container: Dict[str, Any], pitch: float,
                 clearance_mm: float = 0.0, no_go_bounds=None):
    """Bin3D fabrika fonksiyonu döndürür.

    clearance_mm > 0 ise dikey z_clearance pitch'ten türetilir (hoca >= 2mm
    şartı, A2 2026-07-09; tuner + dblf-fallback yolları). clearance_mm == 0.0
    -> z_clearance=1 (mevcut davranış bit-özdeş).
    no_go_bounds ((x1,y1),(x2,y2)) mm verilirse yasak-bolge maskesi kurulur
    (K-45 kablosu); None = maske yok (davranis birebir).
    """
    from src.nesting3d.bin3d import Bin3D
    from src.nesting3d.coarse_to_fine import clearance_to_voxels

    _margin, _zc = clearance_to_voxels(clearance_mm, pitch)
    _mask = (Bin3D.no_go_mask_from_bounds(
        no_go_bounds, float(container["width_mm"]),
        float(container["depth_mm"]), pitch) if no_go_bounds else None)

    def factory() -> Bin3D:
        return Bin3D(
            plate_w_mm=float(container["width_mm"]),
            plate_d_mm=float(container["depth_mm"]),
            pitch=pitch,
            z_clearance=_zc,
            no_go_mask=_mask,
        )
    return factory


def _clearance_gate(placements, voxel_parts_dict, pitch: float,
                    instr: Dict[str, Any]) -> str:
    """Post-nest clearance DOGRULAMA (HIGH-2; hoca >=1mm sarti 2026-06-11,
    2026-07-06 mailde 335 plaka + 1-2mm ile teyit edildi).

    Uretilen yerlesimi BAGIMSIZ olc: placed_meshes ORIJINAL mesh'leri (voxel
    margin-kaydirmasi dahil) yerine koyar; min_clearance ornek-tabanli min
    boslugu raporlar. Ornekleme UST-sinir verir -> olculen deger < esik ise
    KESIN ihlal (uretilemez). Voxel-katmani margin asil garanti; bu ek uyari
    katmani (sessiz <1mm yerlesimi gorunur kilar; NFV fine-pitch HIGH-3 dahil).

    GATE HATASI ASLA nest'i bozmaz (fail-open): istisnada telemetriye hata
    yazar, '' doner. Doner: ihlal uyari notu ('' = OK / atlandi / hata).
    """
    if WEB_MIN_CLEARANCE_MM <= 0 or len(placements) < 2:
        return ""
    import time as _t
    try:
        from src.nesting3d.export_stl import placed_meshes
        from src.nesting3d.clearance import min_clearance
        _t0 = _t.perf_counter()
        meshes = placed_meshes(placements, voxel_parts_dict, pitch)
        rep = min_clearance(meshes, samples_per_mesh=CLEARANCE_GATE_SAMPLES, seed=0)
        instr["min_clearance_mm"] = round(rep.min_mm, 3)
        instr["clearance_check_s"] = round(_t.perf_counter() - _t0, 2)
        if rep.min_mm < WEB_MIN_CLEARANCE_MM:
            return (
                f"UYARI: olculen parca-arasi min bosluk {rep.min_mm:.3f}mm < "
                f"{WEB_MIN_CLEARANCE_MM:.1f}mm (hoca sarti) -> bu yerlesim "
                f"URETILEMEZ olabilir; clearance ayari/pitch gozden gecirilmeli."
            )
    except Exception as _exc:  # noqa: BLE001 — gate dogrulama, nest'i bozamaz
        instr["clearance_check_error"] = str(_exc)
    return ""


# ---------------------------------------------------------------------------
# Fiyat girdisi oluşturucu
# ---------------------------------------------------------------------------

def _build_pricing_inputs(
    batch_volume_cm3: float,
    height_mm: float,
    density: float,
    n_containers: int = 1,
) -> Dict[str, float]:
    """Nesting sonuçlarından fiyatlama girdisi dict'i üretir."""
    return {
        "hacim_m3": batch_volume_cm3 / 1_000_000.0,  # cm3 → m3
        "konteyner_sayisi": float(n_containers),
        "doluluk_oran": density,
        "mesafe_km": 0.0,   # demo: mesafe bilinmiyor
        "agirlik_kg": 0.0,  # demo: ağırlık bilinmiyor
    }


# ---------------------------------------------------------------------------
# Yardımcı: selection model zarif yükleme
# ---------------------------------------------------------------------------

def _load_selection_model_safe():
    """SELECTION_MODEL_PATH varsa (prefilter, model) yukle; yoksa (None, None).

    Zarif düşüş: dosya yoksa veya hata oluşursa sessizce (None, None) döner.
    Demo bu durumda selection tahminini gizler; tuner her zaman çalışır.
    """
    if not SELECTION_MODEL_PATH.exists():
        return None, None
    try:
        from src.nesting3d.selection.persistence import load_selection_model
        return load_selection_model(SELECTION_MODEL_PATH)
    except Exception:
        return None, None


def _predict_selection(
    prefilter,
    model,
    instance,
) -> Optional[Dict[str, Any]]:
    """Instance için selection tahmini üret.

    Zarif düşüş: prefilter/model None ise None döner.
    Dönüş: {"is_easy": bool, "predicted_winner": str, "explain": str} veya None.
    """
    if prefilter is None or model is None:
        return None
    try:
        from src.nesting3d.instances.features import extract_features
        from src.nesting3d.selection.selector import EASY_CONFIDENCE_THRESHOLD

        fv = extract_features(instance)
        features = fv.values

        is_easy, easy_conf = prefilter.predict(features)
        pf_explain = prefilter.explain()

        if is_easy and easy_conf >= EASY_CONFIDENCE_THRESHOLD:
            predicted_winner = "dblf"
            explain = f"KOLAY instance (prefilter guven={easy_conf:.1%}). {pf_explain}"
        else:
            solver_name, model_conf = model.predict(features)
            model_explain = model.explain()
            predicted_winner = solver_name
            explain = (
                f"ZOR instance; model tahmini={solver_name} "
                f"(guven={model_conf:.1%}). {model_explain}"
            )
        return {
            "is_easy": is_easy and easy_conf >= EASY_CONFIDENCE_THRESHOLD,
            "predicted_winner": predicted_winner,
            "explain": explain,
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Parti işçisi (ProcessPool için modül-seviyesi, picklable) + dispatch
# ---------------------------------------------------------------------------

def _process_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Tek partinin nesting + fiyatlama hesabı (parti-paralel SÜREÇ işçisi).

    payload tamamen picklable: batch_id, all_parts (parça dict listesi —
    stl_path/box boyutları), batch_volume_cm3, container_cfg, pitch_fallback,
    n_orient, seed, pricing_rules. Dönüş: {batch_id, nesting, pricing}.

    Tüm ağır CPU işi (voxelize + tuner/coarse-to-fine) burada; süreçler arası
    izole. Mantık run_pipeline'ın eski sıralı parti gövdesiyle BİREBİR aynı —
    yalnızca dış-kapsam değişkenleri payload'dan okunur, sonuç dict döndürülür.
    """
    import time as _time
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.instances.pitch import suggest_pitch
    from src.nesting3d.tuner import tune as tuner_tune
    from src.nesting3d.instances.plate import resolve_container
    from src.pricing.schema import RuleSet
    from src.pricing.engine import PricingEngine

    batch_id = payload["batch_id"]
    all_parts = payload["all_parts"]
    batch_volume_cm3 = payload["batch_volume_cm3"]
    container_cfg = payload["container_cfg"]
    pitch_fallback = payload["pitch_fallback"]
    n_orient = payload["n_orient"]
    seed = payload["seed"]
    nesting_mode = payload.get("nesting_mode", "auto")  # akıllı default: veri-odaklı NFV/heightmap
    nfv_quality = payload.get("nfv_quality", "fast")  # NFV: "fast" (n=8) | "max" (donanım-tavanı)
    time_budget_sec = payload.get("time_budget_sec")  # #22: opsiyonel; None = bugünkü davranış BİREBİR
    wall_aware_pitch = bool(payload.get("wall_aware_pitch", False))  # K-19 OPT-IN; False=davranis birebir
    auto_family_routing = bool(payload.get("auto_family_routing", False))  # F5 OPT-IN; False=davranis birebir
    # NO-GO (yasak bolge) plaka ozelligi: ((x1,y1),(x2,y2)) mm veya None.
    # run_pipeline scenario/plate-config'ten cozer (K-45 kablosu, 2026-07-11);
    # None = mevcut davranis BIREBIR (maske hic kurulmaz).
    _ng = payload.get("no_go_bounds")
    no_go_bounds = (
        ((float(_ng[0][0]), float(_ng[0][1])), (float(_ng[1][0]), float(_ng[1][1])))
        if _ng else None)

    rule_set = RuleSet.from_dict(payload["pricing_rules"])
    pricing_engine = PricingEngine(rule_set)
    _sel_prefilter, _sel_model = _load_selection_model_safe()

    # ENSTRUMANTASYON (rapor-only, #17/#18/#19/#22/#23): tum donus yollarina
    # (basari + fallback + hata) MERGE edilen ortak alanlar. Cozucu sonucu
    # (yukseklik/yerlesim) DEGISMEZ — yalniz gorunurluk. _instr mutable; _ret
    # cagri aninda okur, deger ogrenildikce guncellenir.
    _instr: Dict[str, Any] = {}

    def _ret(nesting, pricing):
        merged = {**nesting, **_instr}
        return {"batch_id": batch_id, "nesting": merged, "pricing": pricing}

    if not all_parts:
        return _ret(
            {"height_mm": 0.0, "density": 0.0, "n_parts": 0,
             "elapsed_sec": 0.0, "note": "Parça yok",
             "portfolio": None, "tuner": None, "selection": None},
            {"total_price": 0.0, "breakdown": []},
        )

    _pdims = [
        (p.get("width_mm"), p.get("depth_mm"), p.get("height_mm"))
        for p in all_parts
    ]
    _cw, _cd, _ch, _plate_auto = resolve_container(container_cfg, _pdims)
    container = {"width_mm": _cw, "depth_mm": _cd, "height_mm": _ch}

    # #18 PLAKA RAPORLAMA: kullanilan plaka W×D + otomatik-turetildi bayragi tum
    # donus yollarina tasinsin (web + gecmis operator gorunurlugu icin).
    # #17/#19 HACIM: gercek parca hacmi (box tam, stl true_fill*bbox) + hacim-eksik
    # parca sayisi (height'tan bagimsiz — burada hesaplanir; volume_fill_pct
    # height ogrenilince eklenir).
    _mesh_vol_mm3, _vol_missing = _parts_real_volume_mm3(all_parts)
    _instr.update({
        "plate_w_mm": round(_cw, 2),
        "plate_d_mm": round(_cd, 2),
        "plate_auto": bool(_plate_auto),
        "mesh_volume_cm3": round(_mesh_vol_mm3 / 1000.0, 2),
        "volume_missing_parts": int(_vol_missing),
        "volume_fill_pct": 0.0,  # height bilinince guncellenir
        "budget_exceeded": False,  # #22: bütçe aşımı; solve sonrası guncellenir
        "time_budget_sec": time_budget_sec,
    })

    def _set_volume_fill(height_mm: float) -> None:
        """Envelope (plaka x yukseklik) bazli gercek-mesh doluluk yuzdesi (#17/#19)."""
        env = _cw * _cd * float(height_mm or 0.0)
        _instr["volume_fill_pct"] = round(
            (_mesh_vol_mm3 / env * 100.0) if env > 0 and _mesh_vol_mm3 > 0 else 0.0, 1
        )

    instance = _build_nesting_instance(all_parts, container)

    # AKILLI MOD ("auto"): instance'tan veri-odaklı NFV/heightmap seçimi (predict_nfv_benefit).
    # VARSAYILAN NFV (kalite-güvenli, K-12 NFV>=heightmap); heightmap SADECE net-kutu VEYA
    # ince-plaka-dominant (NFV'nin %0-kazanç+yavaş olduğu durumlar) → kazan-kazan. Şüphede NFV
    # → false-negative (cavity-zengin→heightmap=kalite kaybı) riski SIFIR. ÖLÇ-ÖNCE kanıtlı.
    auto_reason = None
    if nesting_mode == "auto":
        from src.nesting3d.adaptive_params import predict_nfv_benefit
        try:
            # F5 OPT-IN: family_routing=auto_family_routing -> bayrak kapaliyken aile
            # katmani predict icinde HIC calismaz (mod/gerekce/wall_aware v1 BIT-OZDES);
            # acikken kabuk-ailesi mod-flip + wall_aware onerisi BIRLIKTE gelir (tek kapi,
            # asimetri yok).
            # C4 CHALLENGER (Sprint-3, Eren onayi 2026-07-14): promote edilmis
            # mod-modeli varsa yukle; model YALNIZ allowlist-aile + conformal-
            # tekil durumda kurali ezer (mode_model_io cift-kilit sozlesmesi).
            # Dosya yok/bozuk -> None -> kural BIT-OZDES.
            from src.nesting3d.selection.mode_model_io import (
                MODE_MODEL_PATH, load_mode_model)
            _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
            _dec = predict_nfv_benefit(instance,
                                       family_routing=auto_family_routing,
                                       mode_model=_mm)
            nesting_mode = _dec.mode
            auto_reason = f"auto->{_dec.mode}: {_dec.reason}"
            # Aile-ailesi onerisi (wall_aware) -> cidar-duyarli pitch'i (F3 kablosu) OTOMATIK
            # ac. Bayrak False iken wall_aware zaten hic uretilmez. Guvenli getattr okuma.
            if auto_family_routing and getattr(_dec, "wall_aware", False):
                wall_aware_pitch = True
        except Exception as _auto_exc:
            # Güvenli düşüş: auto türetilemezse hızlı heightmap (regresyon yok).
            nesting_mode = "heightmap"
            auto_reason = f"auto basarisiz ({_auto_exc}) -> heightmap (guvenli dusus)"

    try:
        # K-19 OPT-IN: wall_aware_pitch True + kabuk-ailesi + guven kapisi -> cidar
        # turevli ince pitch; False (default) -> mevcut davranis BIT-OZDES.
        pitch = suggest_pitch(instance, wall_aware=wall_aware_pitch)
    except Exception:
        pitch = pitch_fallback

    # SUGGESTED vs APPLIED pitch izi (rapor-only): suggest_pitch ONERISI
    # (cidar-duyarli ideal ince pitch); applied nfv bellek pre-flight'i / fallback
    # ile kabalasabilir. Ikisini AYRI tut ki sessiz geri-kabalastirma faz'i
    # "etkisiz" gostermesin (K-19 telemetri gerekcesi).
    # M2 (F3): bu alanlar simdilik yalniz _instr raporunda tasinir; kalici telemetri
    # kablosu (telemetry.append_run'a suggested/applied gecisi) F5'te — demo_pipeline
    # append_run cagirmiyor, kapsam buyutmemek icin burada yeni cagri EKLENMEZ.
    _suggested_pitch = pitch
    _instr["suggested_pitch_mm"] = round(_suggested_pitch, 3)
    _instr["applied_pitch_mm"] = round(pitch, 3)
    _instr["wall_aware_pitch"] = wall_aware_pitch

    nfv_pitch_reason = None
    if nesting_mode == "nfv":
        # K-45 KALITE RECETESI (2026-07-11): NFV pitch'i artik suggest_nfv_pitch
        # DEGIL, clearance'tan turer: pitch == WEB_MIN_CLEARANCE_MM (K-38 kaniti:
        # efektif bosluk = ceil(clearance/pitch)*pitch; pitch==clearance tek-voxel
        # TAM pencere; (clearance/2, clearance) araligi ZEHIRLI = sanal sisme;
        # daha ince tam basamak clearance/2 grid butcesini asiyor). Sampiyon
        # kosulari birebir bu pitch'le alindi: plan3 598.5 / plan2 544.5 /
        # deneme5 223.5 (MOTOR/YONTEM_HARITASI §3 K-36/41/44). suggest_nfv_pitch
        # onerisi yalniz TELEMETRI olarak korunur (sessiz sapma izi).
        pitch = float(WEB_MIN_CLEARANCE_MM)
        nfv_pitch_reason = (
            f"kalite-recetesi: pitch=clearance={pitch}mm (K-38 kuantizasyon)")
        try:
            from src.nesting3d.instances.pitch import suggest_nfv_pitch
            from src.nesting3d.capabilities import probe_capabilities
            _sug_pitch, _, _sug_reason = suggest_nfv_pitch(
                instance, plate_w_mm=float(container["width_mm"]),
                plate_d_mm=float(container["depth_mm"]),
                ram_bytes=probe_capabilities().ram_bytes,
                wall_aware=wall_aware_pitch,
            )
            _instr["nfv_suggested_pitch_mm"] = round(float(_sug_pitch), 3)
        except Exception:
            pass  # oneri yalniz rapor — kurulamazsa recete etkilenmez

    # APPLIED pitch nihai (nfv bellek pre-flight sonrasi kabalasmis olabilir);
    # suggested (ideal ince) ile fark = sessiz geri-kabalastirma izi.
    _instr["applied_pitch_mm"] = round(pitch, 3)

    selection_pred = _predict_selection(_sel_prefilter, _sel_model, instance)

    # #23/#24 RAM ON-GUARD (RAPOR-ONLY): pitch nihai; bellek riskini yalniz
    # RAPORLA (pitch DEGISTIRME). Default kosularda (bol RAM + kaba pitch + kucuk
    # plaka) None doner -> hicbir iz, davranis birebir. Yalniz asiri durumda
    # (bellek yetmeyecek) reason alani gorunur olur.
    try:
        from src.nesting3d.capabilities import probe_capabilities as _probe_ram
        _ram_avail = _probe_ram().ram_available_bytes
        _rg = _ram_guard_reason(
            pitch, float(container["width_mm"]), float(container["depth_mm"]),
            _ram_avail,
        )
        if _rg:
            _instr["ram_guard_reason"] = _rg
            logger.warning("nesting[%s]: %s", batch_id, _rg)
    except Exception:
        pass  # guard tahmini kurulamazsa sessiz-guvenli (davranis degismez)

    # ÇİFT-VOXELİZE KALDIRMA: voxel_parts SADECE tuner + DBLF-fallback yolunda gerekli.
    # NFV (solve_nfv) ve coarse_to_fine KENDİ voxelize'larını yapar → buradaki fine voxelize
    # o yollarda BOŞA olurdu (Plan2 büyük parça @0.5mm = 159s/parça çift). Yol kararı için gereken
    # len(voxel_parts)'ı voxelize ETMEDEN tahmin et: to_voxel_parts semantiği = distinct ada göre
    # qty topla (format.py:227-246) → estimated_n_parts BİREBİR == len(to_voxel_parts(...)).
    _name_to_qty = {}
    for _p in all_parts:
        _nm = _p.get("name")
        _name_to_qty[_nm] = _name_to_qty.get(_nm, 0) + int(_p.get("qty", 1))
    estimated_n_parts = sum(_name_to_qty.values())

    t_nest_start = _time.perf_counter()
    # Web NFV-DIŞI yolları (tuner + dblf-fallback) için z_clearance pitch'ten
    # türetilir (hoca >= 1mm). NFV yolu bu factory'yi kullanmaz (kendi margin=1).
    factory = _bin_factory(container, pitch, clearance_mm=WEB_MIN_CLEARANCE_MM,
                           no_go_bounds=no_go_bounds)
    # Tuner + dblf-fallback voxelize'ında yatay margin (parça-arası >= 1mm boşluk)
    # aynı pitch'ten türetilir. coarse_to_fine kendi içinde türetir; NFV margin=1.
    from src.nesting3d.coarse_to_fine import clearance_to_voxels as _clear_vox
    _web_margin, _ = _clear_vox(WEB_MIN_CLEARANCE_MM, pitch)
    # GRACEFUL clearance-cap (2026-07-06): kaba pitch'te margin=1 = pitch mm
    # dilation, fiziksel clearance_mm'nin USTUNDE over-provision eder (M3);
    # auto-plaka bunu hesaba katmadigindan dilated parca plakayi asip nest
    # 0-cikti HATASI verir (kucuk-parca demo: braket 40mm @ pitch 6 -> 52mm >
    # plaka 50). Cozum: en buyuk parca + 2*margin*pitch plakaya sigmazsa margin'i
    # sigacak degere KIS (0'a kadar) + telemetri. SABIT-plaka gercek siparislerde
    # (parca << plaka) TETIKLENMEZ -> tam clearance korunur; yalniz siniraşan
    # kenar-durumu (dolayisiyla eski margin=0 davranisi) geri gelir. Tuner/DBLF
    # yolu (bu _web_margin'i kullanan) icin; c2f fine-pitch kendi kucuk dilation'i.
    if _web_margin > 0 and pitch > 0:
        _plate_min = min(float(container["width_mm"]), float(container["depth_mm"]))
        _max_part = max(
            (float(_v) for _p in all_parts
             for _v in (_p.get("width_mm"), _p.get("depth_mm"), _p.get("height_mm"))
             if _v), default=0.0)
        _fit_margin = int((_plate_min - _max_part) / (2.0 * pitch))
        if _fit_margin < _web_margin:
            _web_margin = max(0, _fit_margin)
            _instr["clearance_capped_margin"] = _web_margin  # <esik: plaka/pitch dar
    _c2f_result = None
    voxel_parts = None  # yalnız tuner/DBLF yolunda üretilir (None = henüz voxelize edilmedi)
    try:
        if nesting_mode == "nfv":
            # K-45: Opt-in NFV "kalite modu" artik SAMPIYON RECETESIYLE kosar
            # (solve_nfv_kalite = pitch==clearance + kosullu exit_guard; kanit
            # K-36/41/44: plan3 598.5 / plan2 544.5 / deneme5 223.5 cift-legal).
            # Ham sonuc kilitsizse guard vergisi ODENMEZ (d5 +20.5 tasarrufu);
            # kilitliyse exit_guard'la yeniden kosulur (p2'de 532-INVALID ->
            # 544.5-legal). solve KENDI voxelize'ini yapar (voxel_parts gereksiz).
            from src.nesting3d.nfv_solve import solve_nfv_kalite
            _c2f_result, _nfv_tel = solve_nfv_kalite(
                instance,
                plate_w_mm=float(container["width_mm"]),
                plate_d_mm=float(container["depth_mm"]),
                clearance_mm=WEB_MIN_CLEARANCE_MM,
                no_go_bounds=no_go_bounds,
                n_orientations=None,  # n=8 (fast) veya donanım-tavanı (max); ÖLÇÜM: 4⊂8 garanti
                quality=nfv_quality,
                seed=seed,
                time_budget_sec=time_budget_sec,  # #22: None -> bugünkü davranış BİREBİR
                r11="auto",  # K-50 kablosu: kucuk/orta sette mesh-duzeyi son
                             # dusme (tek-tarafli; kapilar gecemezse sonuc AYNEN;
                             # parca tavani ustunde atlar + iz birakir)
            )
            _instr["nfv_kalite"] = _nfv_tel  # recete izi (ham/guard kilit + secim + r11)
            tune_result = _c2f_result.tune_result
        elif estimated_n_parts > C2F_THRESHOLD:
            # coarse_to_fine KENDİ voxelize'ını (kaba+ince) yapar → buradaki voxelize gereksiz.
            from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
            # H-15p: F3 cidar-pitch fiilen uygulandiginda (wall_aware_pitch True
            # = kabuk/donel-simetrik aile) ince-aci rafinesi SONUCA girmiyor ama
            # ~11x yerlesim + ek voxelize odetiyor -> atla (kalite riski sifir).
            # wall_aware False iken skip=False -> davranis birebir.
            #
            # H-15p v2 (h15b_coarse_profil.py olcumu): asil maliyet ince-aci
            # DEGIL, COARSE TUNE asamasi (~%90: 7 konfig x budget x ~32s/gecis).
            # K-19 v2 kazanan sirasi MUKEMMEL tip-blok hacim-azalan -> SA/GA/Tabu
            # duz DBLF sirasini gecemiyor bu ailede. wall_aware True iken coarse
            # aramayi KISITLA: build_menu()'den yalniz dblf_only konfigi kullan.
            # wall_aware False iken menu=None -> mevcut davranis birebir.
            _coarse_menu = None
            if wall_aware_pitch:
                from src.nesting3d.tuner import build_menu as _build_menu
                _full_menu = _build_menu()
                _coarse_menu = {"dblf_only": _full_menu["dblf_only"]}
                _instr["coarse_menu_reason"] = (
                    "dblf_only: thin_shell/H-15p (coarse tune %90 pay, "
                    "SA/GA kazandirmiyor)"
                )
            _c2f_result = solve_coarse_to_fine(
                instance,
                plate_w_mm=float(container["width_mm"]),
                plate_d_mm=float(container["depth_mm"]),
                coarse_pitch=None,
                fine_pitch=pitch,
                budget=COARSE_BUDGET,
                seed=seed,
                menu=_coarse_menu,
                skip_fine_angle=wall_aware_pitch,
                # H-16w: kabuk/donel-simetrik aile (wall_aware) FINE dblf gecisi
                # ~4x hizlanir (dirty-region drop_map onbellegi). Cache dogruluk-
                # notr (yukseklik/yerlesim BIREBIR); wall_aware False iken
                # drop_cache=False -> mevcut davranis BIT-OZDES. Bin3D per-decode
                # tek-thread (bkz. solve_coarse_to_fine THREAD-GUVENLIGI).
                drop_cache=wall_aware_pitch,
                # Hoca >= 2mm boşluk şartı (A2 2026-07-09; fix 2026-07-06): coarse+
                # fine voxelize ve Bin3D'ler pitch'ten türetilen (margin,
                # z_clearance) ile kurulur. NFV yolu ayrı (zaten margin=1); bu
                # yalnız NFV-DIŞI coarse_to_fine (web heightmap) yolunu etkiler.
                clearance_mm=WEB_MIN_CLEARANCE_MM,
                # K-45: yasak bolge (plaka ozelligi) heightmap yolunda da maske
                # olarak kurulur; None = maske yok (davranis birebir).
                no_go_bounds=no_go_bounds,
            )
            if wall_aware_pitch:
                _instr["fine_angle_reason"] = "skipped: thin_shell/H-15p"
            tune_result = _c2f_result.tune_result
        else:
            # Tuner yolu: voxel_parts GERÇEKTEN gerekli → SADECE burada voxelize et.
            # Voxelize hatası (OOM/boş-grid) mevcut davranışı korur: "Voxelization hatasi" note + _ret.
            try:
                voxel_parts = to_voxel_parts(
                    instance, pitch, n_orientations=n_orient, margin=_web_margin
                )
            except Exception as _vox_exc:
                return _ret(
                    {"height_mm": 0.0, "density": 0.0, "n_parts": len(all_parts),
                     "elapsed_sec": 0.0, "note": f"Voxelization hatasi: {_vox_exc}",
                     "portfolio": None, "tuner": None, "selection": selection_pred},
                    {"total_price": 0.0, "breakdown": []},
                )
            tune_result = tuner_tune(
                voxel_parts, factory, budget=TUNER_BUDGET, seed=seed,
            )
    except Exception as exc:
        # Zarif düşüş: tuner başarısız → DBLF tek başına
        try:
            from src.nesting3d.dblf import dblf as _dblf
            if voxel_parts is None:
                # NFV/coarse yolunda hata → voxel_parts henüz üretilmedi; fallback için tek kez voxelize et.
                voxel_parts = to_voxel_parts(
                    instance, pitch, n_orientations=n_orient, margin=_web_margin
                )
            _placements, bin3d = _dblf(voxel_parts, factory)
            t_nest_elapsed = _time.perf_counter() - t_nest_start
            _set_volume_fill(bin3d.max_height_mm())  # #17/#19
            # HIGH-2: fallback yolu da clearance dogrular (sessiz <1mm olmasin).
            _fb_cl_note = _clearance_gate(
                _placements, {p.id: p for p in voxel_parts}, pitch, _instr)
            nesting = {
                "height_mm": bin3d.max_height_mm(),
                "density": bin3d.packing_density(),
                "n_parts": len(_placements),
                "elapsed_sec": round(t_nest_elapsed, 3),
                "note": (f"Tuner hatasi (DBLF fallback): {exc}"
                         + (f" | {_fb_cl_note}" if _fb_cl_note else "")),
                "portfolio": None, "tuner": None, "selection": selection_pred,
            }
        except Exception as exc2:
            return _ret(
                {"height_mm": 0.0, "density": 0.0, "n_parts": estimated_n_parts,
                 "elapsed_sec": 0.0,
                 "note": f"Tuner hatasi: {exc}; DBLF fallback hatasi: {exc2}",
                 "portfolio": None, "tuner": None, "selection": selection_pred},
                {"total_price": 0.0, "breakdown": []},
            )
        pricing_inputs = _build_pricing_inputs(
            batch_volume_cm3=batch_volume_cm3,
            height_mm=nesting["height_mm"], density=nesting["density"],
            n_containers=1,
        )
        try:
            p_result = pricing_engine.calculate(pricing_inputs)
            pricing = {
                "total_price": p_result.total_price,
                "breakdown": [str(line) for line in p_result.breakdown],
                "inputs": pricing_inputs,
            }
        except Exception as exc3:
            pricing = {
                "total_price": 0.0,
                "breakdown": [f"Fiyatlama hatasi: {exc3}"],
                "inputs": pricing_inputs,
            }
        return _ret(nesting, pricing)

    t_nest_elapsed = _time.perf_counter() - t_nest_start
    if _c2f_result is not None:
        winner_result = _c2f_result
        voxel_parts_3d = _c2f_result.fine_voxel_parts
        # M1 (F3): solver ICI geri-kabalastirma (nfv_solve used_pitch / coarse_to_fine
        # fine_pitch) sonrasi GERCEK sonuc pitch'i suggest'ten sapabilir -> applied'i
        # solver sonucuyla guncelle ki sessiz kabalasma telemetride gorunur olsun.
        # (heightmap/tuner yolunda solver'a giren pitch = uygulanan pitch; orada line
        # 768'deki applied_pitch_mm oldugu gibi kalir.)
        _instr["applied_pitch_mm"] = round(_c2f_result.fine_pitch, 3)
        # H-15 telemetri (rapor-only, her C2F kosusu): ince-aci rafinesi gercekten
        # kullanildi mi + rafinede gecen sure. solve_nfv sonucunda bu alanlar
        # olmayabilir -> getattr ile guvenli oku (mevcut alan adlarini bozma).
        _instr["fine_angle_used"] = bool(getattr(_c2f_result, "fine_angle_used", False))
        _fa_time = getattr(_c2f_result, "fine_angle_time_s", None)
        if _fa_time is not None:
            _instr["fine_angle_time_s"] = round(float(_fa_time), 3)
        # H-15p v2 telemetri (rapor-only, her C2F kosusu): coarse arama suresi
        # (asil maliyet, h15b_coarse_profil.py olcumu) + fine yerlesim suresi +
        # kazanan konfig adi. getattr ile guvenli oku (mevcut alan adlarini bozma).
        _c_time = getattr(_c2f_result, "coarse_time_s", None)
        if _c_time is not None:
            _instr["coarse_time_s"] = round(float(_c_time), 3)
        _f_time = getattr(_c2f_result, "fine_time_s", None)
        if _f_time is not None:
            _instr["fine_time_s"] = round(float(_f_time), 3)
        _wcfg = getattr(_c2f_result, "winning_config", None)
        if _wcfg is not None:
            _instr["winning_config"] = _wcfg
        # H-16w telemetri (rapor-only): fine drop_map onbellek istatistikleri.
        # drop_cache kapaliyken (wall_aware False / eski yol) None -> alan
        # eklenmez (telemetri de birebir eski kalir). getattr guvenli.
        _dc_stats = getattr(_c2f_result, "drop_cache_stats", None)
        if _dc_stats is not None:
            _instr["drop_cache_hit_ratio"] = round(
                float(_dc_stats.get("hit_ratio", 0.0)), 4)
            _instr["drop_cache_keys"] = int(_dc_stats.get("keys", 0))
            _instr["drop_cache_peak_mb"] = round(
                float(_dc_stats.get("peak_mb", 0.0)), 2)
            _instr["drop_cache_fallbacks"] = int(_dc_stats.get("fallbacks", 0))
            _instr["drop_cache_evictions"] = int(_dc_stats.get("evictions", 0))
    else:
        winner_result = tune_result.result
        voxel_parts_3d = {p.id: p for p in voxel_parts}
    height_mm = winner_result.height_mm
    density = winner_result.density
    n_placed = len(winner_result.placements)
    winner_config = tune_result.winning_config_name
    baseline_height = tune_result.baseline_height_mm

    # #17/#19 gercek-mesh doluluk% (envelope = plaka x bu yukseklik).
    _set_volume_fill(height_mm)
    # #22 ZAMAN BUTCESI izi: solve_nfv budget asiminda strategy'ye "budget_exceeded"
    # yazar; bu iz adaptive_reason'a tasinir. time_budget_sec None ise asla tetiklenmez
    # (bugünkü davranış birebir).
    if _c2f_result is not None:
        _areason = getattr(_c2f_result, "adaptive_reason", None) or ""
        _instr["budget_exceeded"] = "budget_exceeded" in _areason

    dblf_height = baseline_height
    gain_pct = (
        (dblf_height - height_mm) / dblf_height * 100.0
        if dblf_height > 0 else 0.0
    )

    tuner_rows = []
    for cfg_name, cfg_result in tune_result.all_results:
        is_win = cfg_result is winner_result
        cfg_gain = (
            (dblf_height - cfg_result.height_mm) / dblf_height * 100.0
            if dblf_height > 0 else 0.0
        )
        tuner_rows.append({
            "config": cfg_name,
            "height_mm": round(cfg_result.height_mm, 2),
            "density": round(cfg_result.density, 4),
            "time_s": round(cfg_result.time_s, 3),
            "winner": is_win,
            "gain_pct": round(cfg_gain, 2),
        })

    portfolio_data = {
        "winner": winner_config,
        "dblf_height_mm": round(dblf_height, 2),
        "gain_pct": round(gain_pct, 2),
        "table_md": "",
        "rows": tuner_rows,
    }

    # HIGH-2 runtime clearance kapisi: uretilen yerlesim hoca >=1mm sartini
    # gercekten sagliyor mu? _cl_pitch = SONUCUN pitch'i (c2f/nfv fine_pitch veya
    # tuner input pitch). Ihlal -> note'a uyari (nest bozulmaz).
    _cl_pitch = _c2f_result.fine_pitch if _c2f_result is not None else pitch
    _clearance_note = _clearance_gate(
        winner_result.placements, voxel_parts_3d, _cl_pitch, _instr)

    # TELEMETRI v2 (STRATEJI Faz-2, 2026-07-07): MOD-duzeyi karar + DURUST
    # metrik satiri (data/telemetry/runs_v2.jsonl; v1 dosyasina DOKUNMAZ).
    # Kilit sayisi burada olculur (accessibility ~1sn/588 parca — ucuz);
    # min_clearance HIGH-2 gate'ten (_instr) gelir. Telemetri yazimi uretimi
    # ASLA bozamaz: her hata logger.warning ile yutulur (bilerek genis except —
    # M1-maskeleme degil: yan-kanal kayit, ana akis degil).
    try:
        import os as _os
        # Test kosusunda GERCEK telemetri dosyasi kirletilmez (pytest otomatik
        # PYTEST_CURRENT_TEST set eder); TELEMETRY_V2_DISABLE=1 ile de kapatilir.
        if ("PYTEST_CURRENT_TEST" in _os.environ
                or _os.environ.get("TELEMETRY_V2_DISABLE") == "1"):
            raise _SkipTelemetryV2()
        from src.nesting3d.telemetry import append_run_v2, V2_DEFAULT_PATH
        from src.nesting3d.accessibility import check_placements as _acc_check
        from src.nesting3d.instances.family import classify_family as _clf_fam
        _n_locked = int(_acc_check(
            winner_result.placements, voxel_parts_3d).n_locked)
        _instr["n_locked"] = _n_locked  # rapor izinde de gorunur
        try:
            _fam, _fam_conf = _clf_fam(instance)
        except Exception:
            _fam, _fam_conf = None, None
        _v2_mode = (
            "nfv" if nesting_mode == "nfv"
            else ("heightmap+wall_aware" if wall_aware_pitch else "heightmap"))
        append_run_v2(
            _ROOT / V2_DEFAULT_PATH,
            kaynak="pipeline",
            instance_id=str(batch_id),
            mode=_v2_mode,
            height_mm=float(height_mm),
            n_placed=int(n_placed),
            n_total=int(estimated_n_parts),
            min_clearance_mm=_instr.get("min_clearance_mm"),
            n_locked=_n_locked,
            family_f1=_fam, family_conf=_fam_conf,
            source=str(payload.get("kaynak", "pipeline")),
            pitch_fine=float(_cl_pitch),
            seed=int(seed),
            duration_s=round(t_nest_elapsed, 3),
            clearance_req_mm=WEB_MIN_CLEARANCE_MM,
            winning_config=str(winner_config),
            # K-50 kablosu: r11 uygulandiysa mesh-duzeyi ekstra dusme izi
            # (ana height_mm voxel-raporlu kalir; r11 alanlari additive)
            **({"r11_height_mm": _instr["nfv_kalite"]["r11"]["height_mm"],
                "r11_kazanc_mm": _instr["nfv_kalite"]["r11"]["kazanc_mm"],
                "r11_min_clearance_mm":
                    _instr["nfv_kalite"]["r11"]["min_clearance_mm"]}
               if (_instr.get("nfv_kalite", {}).get("r11", {}) or {})
               .get("uygulandi") else {}),
        )
    except _SkipTelemetryV2:
        pass
    except Exception as _tv2_exc:
        logger.warning("telemetri v2 yazilamadi (uretim etkilenmez): %s", _tv2_exc)

    nesting = {
        "height_mm": height_mm,
        "density": density,
        "n_parts": n_placed,
        "elapsed_sec": round(t_nest_elapsed, 3),
        "note": _clearance_note,
        "auto_mode_reason": auto_reason,  # "auto" seçimi gerekçesi (None=auto kullanılmadı)
        "nesting_mode_used": nesting_mode,  # auto çözüldükten sonra fiilen kullanılan mod
        # GLB/STL export placements'ı bu pitch'le mm'e çevirir → SONUCUN pitch'i şart:
        # NFV fine-settle (K-17) kabul edilirse placements used_pitch/4 hücrelerindedir;
        # ince-duvar fallback'te de used_pitch istenen pitch'ten sapabilir.
        "pitch_mm": round(_c2f_result.fine_pitch if _c2f_result is not None else pitch, 2),
        "portfolio": portfolio_data,
        "tuner": {
            "winning_config": winner_config,
            "baseline_height_mm": round(baseline_height, 2),
            "improvement_mm": round(tune_result.improvement_mm, 2),
            "gain_vs_baseline_pct": round(gain_pct, 2),
            "budget": TUNER_BUDGET,
            "configs_tried": len(tune_result.all_results),
            "rows": tuner_rows,
        },
        "selection": selection_pred,
        "placements": winner_result.placements,
        "voxel_parts": voxel_parts_3d,
    }

    pricing_inputs = _build_pricing_inputs(
        batch_volume_cm3=batch_volume_cm3,
        height_mm=height_mm, density=density, n_containers=1,
    )
    try:
        p_result = pricing_engine.calculate(pricing_inputs)
        pricing = {
            "total_price": p_result.total_price,
            "breakdown": [str(line) for line in p_result.breakdown],
            "inputs": pricing_inputs,
        }
    except Exception as exc:
        pricing = {
            "total_price": 0.0,
            "breakdown": [f"Fiyatlama hatasi: {exc}"],
            "inputs": pricing_inputs,
        }
    return _ret(nesting, pricing)


def _should_parallelize(scenario: Dict[str, Any], n_batches: int, total_parts: int) -> bool:
    """Parti-paralel koşulsun mu? scenario['parallel_batches']: True/False/'auto'.

    'auto' (varsayılan): >=2 parti VE toplam parça > PARALLEL_MIN_PARTS.
    Env NESTING_PARALLEL=0 her durumda kapatır (hata ayıklama/Windows kaçışı).
    """
    import os
    if os.environ.get("NESTING_PARALLEL", "").strip() == "0":
        return False
    flag = scenario.get("parallel_batches", "auto")
    if flag is True:
        return n_batches >= 2
    if flag is False:
        return False
    return n_batches >= 2 and total_parts > PARALLEL_MIN_PARTS


def _detect_cores() -> int:
    """Kullanılabilir mantıksal çekirdek sayısını GÜVENİLİR tespit et (çapraz-platform).

    Öncelik: os.process_cpu_count() (Py 3.13+; CPU affinity/cgroup sınırına SAYGI
    duyar — container/VM'de doğru) → os.cpu_count() → 2 (son çare). Bu çağrılar
    Windows/Linux/macOS'ta standarttır; hiçbiri istisna fırlatmaz, en kötü None
    döner (o zaman 2 varsayılır). Yani tespit her donanımda çalışır.
    """
    import os
    n = None
    _proc_count = getattr(os, "process_cpu_count", None)  # Python 3.13+
    if callable(_proc_count):
        try:
            n = _proc_count()
        except Exception:
            n = None
    if not n:
        n = os.cpu_count()
    return int(n) if n and n > 0 else 2


def _available_ram_gb() -> Optional[float]:
    """Boş (kullanılabilir) RAM'i GB cinsinden döndür; okunamazsa None.

    Sıra: psutil (çapraz-platform, en güvenilir) → Windows ctypes
    (GlobalMemoryStatusEx) → Linux /proc/meminfo (MemAvailable) → None.
    None dönerse çağıran RAM sınırını ATLAR (CPU-only davranış) — yani RAM
    okunamayan ortamda da çalışmaya devam eder, sadece RAM kapısı devre dışı.
    """
    # 1) psutil (varsa)
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        pass
    # 2) Windows
    try:
        import sys as _sys
        if _sys.platform.startswith("win"):
            import ctypes
            class _MEMSTAT(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = _MEMSTAT()
            stat.dwLength = ctypes.sizeof(_MEMSTAT)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return stat.ullAvailPhys / (1024 ** 3)
    except Exception:
        pass
    # 3) Linux
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    kb = float(line.split()[1])
                    return kb / (1024 ** 2)
    except Exception:
        pass
    return None


def _resolve_max_workers(n_batches: int) -> int:
    """Kaç paralel SÜREÇ kullanılacağını donanıma (CPU + RAM) göre belirle.

    Sıra:
      1. env NESTING_MAX_WORKERS verilmişse onu kullan (kesin; >=1'e kıstırılır).
      2. Yoksa: tespit_çekirdek - rezerv (env NESTING_RESERVE_CORES, vars. 2).
    Sonra:
      - RAM kapısı: boş_RAM okunabiliyorsa ram_işçi = (boş × headroom) /
        per_worker_gb ile kısıtla (az-RAM'li makinede süreç şişmesini önler).
        RAM okunamazsa bu kapı atlanır.
      - Mutlak tavan (PARALLEL_HARD_CAP) + iş kadarı (n_batches).
    Sınırsız olmaz; makine ne CPU ne RAM tarafından boğulur.
    """
    import os
    cores = _detect_cores()
    raw = os.environ.get("NESTING_MAX_WORKERS", "").strip()
    if raw:
        try:
            want = max(1, int(raw))
        except ValueError:
            want = max(1, cores - PARALLEL_RESERVE_CORES)
    else:
        try:
            reserve = int(os.environ.get("NESTING_RESERVE_CORES", str(PARALLEL_RESERVE_CORES)))
        except ValueError:
            reserve = PARALLEL_RESERVE_CORES
        want = max(1, cores - max(0, reserve))

    # RAM kapısı (boş RAM okunabiliyorsa). NESTING_MAX_WORKERS açık verilse bile
    # RAM yetmiyorsa düşürülür — güvenlik CPU override'ından önce gelir.
    avail = _available_ram_gb()
    if avail is not None:
        try:
            per = float(os.environ.get("NESTING_MEM_PER_WORKER_GB", str(PARALLEL_MEM_PER_WORKER_GB)))
        except ValueError:
            per = PARALLEL_MEM_PER_WORKER_GB
        if per > 0:
            ram_workers = int((avail * PARALLEL_RAM_HEADROOM) / per)
            want = min(want, max(1, ram_workers))

    # Mutlak tavan: varsayılan PARALLEL_HARD_CAP, env NESTING_HARD_CAP ile ezilir
    # (süper bilgisayar: yüksek değer ver → tam paralellik). + iş kadarı.
    try:
        hard_cap = int(os.environ.get("NESTING_HARD_CAP", str(PARALLEL_HARD_CAP)))
    except ValueError:
        hard_cap = PARALLEL_HARD_CAP
    hard_cap = max(1, hard_cap)
    return max(1, min(want, n_batches, hard_cap))


def _run_batches_parallel(payloads: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Partileri ayrı SÜREÇLERDE paralel koş. Hata/desteklenmezse {} (caller sıralıya düşer).

    İşçi sayısı donanım-farkında ve ÜST-SINIRLI (_resolve_max_workers): asla
    sınırsız değil; OS/UI'ye çekirdek payı bırakılır. Sonuçlar batch_id'ye göre
    map'lenir; çağıran parti SIRASINA göre dizer (determinizm — aynı seed).
    """
    import os
    try:
        from concurrent.futures import ProcessPoolExecutor
        max_workers = _resolve_max_workers(len(payloads))
        # Etkili işçi 1 ise (zayıf makine / yüksek rezerv) paralel ANLAMSIZ —
        # 1-süreçlik havuz sıralıdan yavaştır (boşa spawn). Sıralıya bırak.
        if max_workers <= 1:
            logger.info(
                "nesting: tek işçi çözümlendi (çekirdek=%d) → paralel atlandı, SIRALI",
                _detect_cores(),
            )
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            for r in ex.map(_process_batch, payloads):
                out[r["batch_id"]] = r
        _ram = _available_ram_gb()
        _eff_cap = os.environ.get("NESTING_HARD_CAP", str(PARALLEL_HARD_CAP))
        logger.info(
            "nesting: %d parti %d sürecte PARALEL koşuldu (çekirdek=%d, boş RAM=%s, "
            "işçi-başı bütçe=%.1fGB, tavan=%s)",
            len(payloads), max_workers, _detect_cores(),
            ("%.1fGB" % _ram if _ram is not None else "okunamadı"),
            PARALLEL_MEM_PER_WORKER_GB, _eff_cap,
        )
        return out
    except Exception as exc:
        # ProcessPool kurulamadı/pickle/Windows sorunu → caller sıralı koşar.
        # Sessiz değil: kullanıcı loglardan paralelin düştüğünü görür.
        logger.warning(
            "nesting: paralel parti yürütme başarısız (%s) → SIRALI'ya düşülüyor", exc,
        )
        return {}


# ---------------------------------------------------------------------------
# Ana pipeline
# ---------------------------------------------------------------------------

# Fix-1 (CRITICAL): siparis basina toplam parca adedi (total_qty) sinirsizdi.
# parser/attachment katmanlari parca-basi adedi clamp'ler (MAX_QTY=5000) ama
# cok sayida parca satiri toplamda yine asiri buyuyebilir (orn. 30 parca x
# 5000 = 150.000). Kapasite/nesting motoru bu olcekte OOM'a dusebilir; kabul-
# oncesi guard — mevcut "total_qty<=0" atlama desenininin simetrigi.
MAX_ORDER_TOTAL_QTY = 100_000


def run_pipeline(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Sipariş havuzu → çizelgeleme → nesting → fiyatlama → rapor.

    Parametreler
    ------------
    scenario : senaryo dict (SCENARIO fixture formatında)

    Dönüş
    -----
    dict — ranked_orders, batches, warnings, nesting_results,
           pricing_results, elapsed_sec, report_path
    """
    from src.scheduling.models import Capacity, Order
    from src.scheduling.rules import PriorityConfig, rank_orders
    from src.scheduling.batcher import build_batches
    from src.scheduling.feasibility import check_feasibility
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.instances.pitch import suggest_pitch
    from src.nesting3d.tuner import tune as tuner_tune
    from src.pricing.schema import RuleSet
    from src.pricing.engine import PricingEngine

    from src.nesting3d.instances.plate import resolve_container

    t0 = time.perf_counter()
    today = scenario["ref_date"]
    # Plaka politikasi cekirdekte: scenario["container"] verilirse o GERCEK plaka,
    # verilmezse (None/eksik) her parti icin PARCALARDAN otomatik turetilir.
    # Sabit default YOK — mail/numune/dogrudan cagri fark etmez (kullanici karari).
    container_cfg = scenario.get("container")
    pitch_fallback = float(scenario.get("pitch", 15.0))
    n_orient = int(scenario.get("n_orientations", 4))
    seed = int(scenario.get("seed", 42))
    # K-45: yasak bolge (no-go) plaka OZELLIGIDIR — oncelik: scenario acik degeri
    # > plate.local.json "no_go" > env PLATE_NOGO > None (maske yok, davranis
    # birebir). Hoca 2026-07-09 duzeltmesi: x[152.5,185.5] y[0.2,45] tam-yukseklik.
    no_go_bounds = scenario.get("no_go_bounds")
    if no_go_bounds is None:
        try:
            from src.runtime.plate_config import resolve_no_go
            no_go_bounds = resolve_no_go(_ROOT)
        except Exception:
            no_go_bounds = None  # config cozulemezse maskesiz devam (guvenli)

    # Algoritma-seçim model zarif yükleme (model yoksa None, None)
    _sel_prefilter, _sel_model = _load_selection_model_safe()

    # --- 1. Sipariş nesnelerini kur + doğrula ---
    orders: List[Order] = []
    order_parts_map: Dict[str, List[Dict[str, Any]]] = {}
    skipped_orders: List[str] = []  # bos/sifir-adet siparisler (atlandi)

    for od in scenario["orders"]:
        parts_list = od.get("parts", [])
        total_qty = sum(p.get("qty", 1) for p in parts_list)

        # ROBUSTLUK: parcasiz veya sifir-adet siparis tum partiyi COKERTMEZ.
        # (gercek kutuda LLM bazen sinyal tasiyan ama parcasiz "siparis" uretir;
        # Order.validate total_quantity>0 ister.) Boyle siparis atlanir, gecerli
        # siparisler islenir; durum skipped_orders + warnings'e yazilir.
        if not parts_list or total_qty <= 0:
            skipped_orders.append(od.get("order_id", "?"))
            continue

        # Fix-1 (CRITICAL): asiri buyuk toplam adet -> OOM riski. Simetrik
        # atlama: gecerli siparisler islenmeye devam eder, bu siparis
        # skipped_orders'da sessizce degil GORUNUR sekilde atlanir.
        if total_qty > MAX_ORDER_TOTAL_QTY:
            logger.warning(
                "run_pipeline: siparis %s toplam adet asiri buyuk (%d > "
                "MAX_ORDER_TOTAL_QTY=%d) — atlandi.",
                od.get("order_id", "?"), total_qty, MAX_ORDER_TOTAL_QTY,
            )
            skipped_orders.append(od.get("order_id", "?"))
            continue

        vol_cm3 = _parts_volume_cm3(parts_list)

        o = Order(
            order_id=od["order_id"],
            customer=od["customer"],
            parts_ref=od["order_id"],
            total_quantity=total_qty,
            total_volume_cm3=vol_cm3,
            deadline=od["deadline"],
            priority_class=od["priority_class"],
        )
        o.validate(today)
        orders.append(o)
        order_parts_map[od["order_id"]] = parts_list

    if not orders:
        # Hicbir gecerli siparis kalmadi -> caller (otonom/poller) yakalar.
        raise ValueError(
            "Gecerli siparis yok — tum siparisler bos/sifir adet "
            f"(atlanan: {', '.join(skipped_orders) or 'yok'})"
        )

    cap_cfg = scenario["capacity"]
    capacity = Capacity(
        num_machines=int(cap_cfg["num_machines"]),
        batch_duration_hours=float(cap_cfg["batch_duration_hours"]),
        shifts_per_day=int(cap_cfg["shifts_per_day"]),
        max_volume_per_batch_cm3=cap_cfg.get("max_volume_per_batch_cm3"),
    )
    capacity.validate()

    # --- 2. Önceliklendirme + çizelgeleme ---
    config = PriorityConfig.default()
    ranked = rank_orders(orders, config, today)
    batches = build_batches(ranked, capacity, allow_mixing=False)
    warnings = check_feasibility(batches, capacity, today)
    # NOT: atlanan bos/sifir-adet siparisler `warnings` listesine KONULMAZ —
    # bu liste yapisal feasibility uyari nesneleri tutar (rapor ureteci .order_id
    # erisir). Atlananlar donus dict'inde ayri `skipped_orders` anahtarinda
    # yuzeye cikar (sessiz dusurme yok); UI/otonom oradan okur.

    # --- 3. Her parti için nesting + fiyatlama (parti-paralel) ---
    nesting_results: Dict[str, Dict[str, Any]] = {}
    pricing_results: Dict[str, Dict[str, Any]] = {}

    # Parti yükleri (picklable). Her parti BAĞIMSIZ — sonuç batch_id'ye yazılır,
    # paylaşılan değişken durum yok — bu yüzden süreç-paralel güvenli.
    payloads: List[Dict[str, Any]] = []
    for batch in batches:
        all_parts: List[Dict[str, Any]] = []
        for order in batch.orders:
            all_parts.extend(order_parts_map[order.order_id])
        payloads.append({
            "batch_id": batch.batch_id,
            "all_parts": all_parts,
            "batch_volume_cm3": batch.total_volume_cm3,
            "container_cfg": container_cfg,
            "pitch_fallback": pitch_fallback,
            "n_orient": n_orient,
            "seed": seed,
            "pricing_rules": scenario["pricing_rules"],
            "nesting_mode": scenario.get("nesting_mode", "auto"),
            "nfv_quality": scenario.get("nfv_quality", "fast"),
            "no_go_bounds": no_go_bounds,  # K-45: yasak bolge (plaka ozelligi)
            "time_budget_sec": scenario.get("time_budget_sec"),  # #22: None = bugünkü davranış
            # K-19 OPT-IN cidar-duyarli pitch. Yoksa False = gozcu/default davranis
            # DEGISMEZ (BIT-OZDES). True olunca suggest_pitch/suggest_nfv_pitch'e
            # wall_aware=True gecer (kabuk-ailesi + guven kapisi iceride).
            "wall_aware_pitch": bool(scenario.get("wall_aware_pitch", False)),
            # F5 OPT-IN aile-yonlendirme. Yoksa False = davranis DEGISMEZ (BIT-OZDES):
            # predict_nfv_benefit'e family_routing=False geter -> aile katmani HIC calismaz.
            # True VE nesting_mode=="auto" iken: kabuk-ailesi mod-flip + wall_aware_pitch
            # otomatik acilir (yukarida _process_batch icinde).
            # webapp/gozcu kablosu F5 asama-2 rollout 2026-07-05'te baglandi
            # (poller/manuel/otonom/adet-gir hepsi auto_family_routing=True gecer).
            "auto_family_routing": bool(scenario.get("auto_family_routing", False)),
        })

    # Birden çok bağımsız parti varsa AYRI SÜREÇLERDE paralel koş (örn. 5
    # müşteriden 5 sipariş → 5 parti → ~tek parti süresi, toplamı değil). Sonuç
    # sıralı ile AYNI (her parti aynı seed, batch_id'ye yazılır). Paralel
    # kapalı/desteklenmiyor/düşerse otomatik sıralıya iner.
    total_parts = sum(len(pl["all_parts"]) for pl in payloads)
    results_map: Dict[str, Dict[str, Any]] = {}
    if _should_parallelize(scenario, len(payloads), total_parts):
        results_map = _run_batches_parallel(payloads)
    if not results_map:
        for payload in payloads:
            r = _process_batch(payload)
            results_map[r["batch_id"]] = r

    # Parti SIRASINA göre diz (determinizm + rapor/UI sırası korunur)
    for batch in batches:
        r = results_map[batch.batch_id]
        nesting_results[batch.batch_id] = r["nesting"]
        pricing_results[batch.batch_id] = r["pricing"]

    elapsed_total = time.perf_counter() - t0

    # --- 4. Rapor oluştur ---
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = RESULTS_DIR / REPORT_FILENAME

    report_md = _build_report_markdown(
        today=today,
        ranked=ranked,
        batches=batches,
        warnings=warnings,
        nesting_results=nesting_results,
        pricing_results=pricing_results,
        elapsed_total=elapsed_total,
    )
    report_path.write_text(report_md, encoding="utf-8")

    # --- 5. Konsol özeti ---
    _print_console_summary(
        ranked=ranked,
        batches=batches,
        warnings=warnings,
        nesting_results=nesting_results,
        pricing_results=pricing_results,
        elapsed_total=elapsed_total,
    )

    return {
        "ranked_orders": ranked,
        "batches": batches,
        "warnings": warnings,
        "nesting_results": nesting_results,
        "pricing_results": pricing_results,
        "skipped_orders": skipped_orders,
        "elapsed_sec": round(elapsed_total, 3),
        "report_path": str(report_path),
    }


# ---------------------------------------------------------------------------
# Rapor markdown oluşturucu
# ---------------------------------------------------------------------------

def _build_report_markdown(
    today: date,
    ranked: list,
    batches: list,
    warnings: list,
    nesting_results: Dict[str, Any],
    pricing_results: Dict[str, Any],
    elapsed_total: float,
) -> str:
    lines = []
    lines.append(f"# Demo Pipeline Raporu — {today.isoformat()}")
    lines.append("")
    lines.append(
        "> Bu rapor `scripts/demo_pipeline.py` tarafindan otomatik uretilmistir."
    )
    lines.append(
        f"> Toplam kosus suresi: **{elapsed_total:.2f} saniye**"
    )
    lines.append("")

    # --- Bölüm 1: Sipariş öncelik tablosu ---
    lines.append("## 1. Siparis Oncelik Tablosu")
    lines.append("")
    lines.append("| Sira | Siparis | Musteri | Termin | Oncelik | Hacim (cm3) |")
    lines.append("|------|---------|---------|--------|---------|-------------|")
    for i, o in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {o.order_id} | {o.customer} | {o.deadline} "
            f"| {o.priority_class} | {o.total_volume_cm3:.0f} |"
        )
    lines.append("")

    # --- Bölüm 2: Parti planı + termin/kapasite uyarıları ---
    lines.append("## 2. Parti Plani")
    lines.append("")
    lines.append("| Parti | Musteri | Siparisler | Hacim (cm3) | Asiri mi |")
    lines.append("|-------|---------|------------|-------------|----------|")
    for b in batches:
        order_ids = ", ".join(o.order_id for o in b.orders)
        lines.append(
            f"| {b.batch_id} | {b.customer} | {order_ids} "
            f"| {b.total_volume_cm3:.0f} | {'EVET' if b.oversized else 'Hayir'} |"
        )
    lines.append("")

    if warnings:
        lines.append("### Termin Uyarilari")
        lines.append("")
        lines.append("| Siparis | Termin | Tahmini Bitis | Gecikme (gun) | Parti |")
        lines.append("|---------|--------|---------------|---------------|-------|")
        for w in warnings:
            lines.append(
                f"| {w.order_id} | {w.deadline} | {w.estimated_completion} "
                f"| {w.delay_days} | {w.batch_id} |"
            )
        lines.append("")
    else:
        lines.append("_Termin asimi uyarisi yok._")
        lines.append("")

    # --- Bölüm 3: Nesting sonuçları ---
    lines.append("## 3. Nesting Sonuclari")
    lines.append("")
    lines.append(
        "| Parti | Plaka (WxD mm) | Pitch (mm) | Yukseklik (mm) | Doluluk (%) | Hacim-Doluluk (%) | Parca | Sure (s) | Kazanan | DBLF'ye Kazanc% | Not |"
    )
    lines.append(
        "|-------|----------------|------------|----------------|-------------|-------------------|-------|----------|---------|-----------------|-----|"
    )
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        h = nr.get("height_mm", 0.0)
        d = nr.get("density", 0.0)
        n = nr.get("n_parts", 0)
        t = nr.get("elapsed_sec", 0.0)
        note = nr.get("note", "")
        pitch_mm = nr.get("pitch_mm", "-")
        port = nr.get("portfolio") or {}
        winner_name = port.get("winner", "dblf")
        gain_pct = port.get("gain_pct", 0.0)
        # #18 plaka + #17/#19 hacim-doluluk (iki eksen: mm yukseklik YANINDA hacim-%)
        _pw = nr.get("plate_w_mm")
        _pd = nr.get("plate_d_mm")
        _plate_str = (f"{_pw:.0f}x{_pd:.0f}" if _pw and _pd else "-")
        if nr.get("plate_auto"):
            _plate_str += " (oto)"
        _vfp = nr.get("volume_fill_pct", 0.0)
        _vmiss = nr.get("volume_missing_parts", 0)
        _vfp_str = f"{_vfp:.1f}" + (f" (eksik:{_vmiss})" if _vmiss else "")
        lines.append(
            f"| {b.batch_id} | {_plate_str} | {pitch_mm} | {h:.1f} | {d * 100:.1f} "
            f"| {_vfp_str} | {n} | {t:.2f} | {winner_name} | {gain_pct:.1f}% | {note} |"
        )
    lines.append("")
    lines.append(
        "> Plaka `(oto)` = siparisten TURETILDI (gercek platform olcusu girilmedi). "
        "Hacim-Doluluk = gercek parca hacmi / zarf (mm yuksekligin YANINDA ikinci eksen); "
        "`eksik:N` = gercek hacmi bilinmeyen (true_fill'siz) parca adedi."
    )
    lines.append("")

    # --- Bölüm 3b: Instance-Tuner konfig kıyas tabloları ---
    lines.append("## 3b. Instance-Tuner Konfig Kiyasi")
    lines.append("")
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        tuner_data = nr.get("tuner")
        if not tuner_data:
            port = nr.get("portfolio")
            if not port:
                lines.append(f"### Parti {b.batch_id}: tuner verisi yok")
                lines.append("")
                continue
            # Eski format / fallback
            lines.append(f"### Parti {b.batch_id} — {b.customer}")
            lines.append(f"**Kazanan: `{port.get('winner','?')}` (fallback)**")
            lines.append("")
            continue
        winner_cfg = tuner_data.get("winning_config", "?")
        baseline_h = tuner_data.get("baseline_height_mm", 0.0)
        improvement = tuner_data.get("improvement_mm", 0.0)
        gain = tuner_data.get("gain_vs_baseline_pct", 0.0)
        n_configs = tuner_data.get("configs_tried", 0)
        budget = tuner_data.get("budget", 0)
        lines.append(f"### Parti {b.batch_id} — {b.customer}")
        lines.append(
            f"**Kazanan konfig: `{winner_cfg}` | "
            f"Portfoy baseline: {baseline_h:.2f} mm | "
            f"Kazanc: {improvement:.2f} mm ({gain:.1f}%) | "
            f"Denenen konfig: {n_configs} x budget={budget}**"
        )
        lines.append("")
        # Konfig kıyas tablosu
        rows = tuner_data.get("rows", [])
        if rows:
            lines.append("| Konfig | Yukseklik (mm) | Doluluk | Sure (s) | Baseline'a Kazanc% | Sonuc |")
            lines.append("|--------|----------------|---------|----------|---------------------|-------|")
            for row in rows:
                win_mark = "KAZANDI" if row.get("winner") else ""
                cfg_gain = row.get("gain_pct", 0.0)
                gain_str = f"+{cfg_gain:.1f}%" if cfg_gain > 0.01 else "0%"
                lines.append(
                    f"| {row['config']} | {row['height_mm']:.2f} | "
                    f"{row['density'] * 100:.1f}% | {row['time_s']:.3f} | "
                    f"{gain_str} | {win_mark} |"
                )
        lines.append("")

    # --- Bölüm 3c: Algoritma-seçim tahmini ---
    has_selection = any(
        nesting_results.get(b.batch_id, {}).get("selection") is not None
        for b in batches
    )
    if has_selection:
        lines.append("## 3c. Algoritma-Secim Tahmini (Bilgilendirme)")
        lines.append("")
        lines.append(
            "> NOT: Tahmin yalnizca bilgilendirme icin gosterilir. "
            "Cozum her zaman Instance-Tuner'dan gelir."
        )
        lines.append("")
        for b in batches:
            nr = nesting_results.get(b.batch_id, {})
            sel = nr.get("selection")
            if sel is None:
                continue
            is_easy_str = "KOLAY" if sel.get("is_easy") else "ZOR"
            predicted = sel.get("predicted_winner", "?")
            explain = sel.get("explain", "")
            lines.append(f"**{b.batch_id} ({b.customer})**: {is_easy_str} — "
                         f"tahmin={predicted}")
            if explain:
                lines.append(f"  _{explain}_")
            lines.append("")

    # --- Bölüm 4: Fiyat dökümü ---
    lines.append("## 4. Fiyat Dokumu")
    lines.append("")
    for b in batches:
        pr = pricing_results.get(b.batch_id, {})
        total = pr.get("total_price", 0.0)
        lines.append(f"### Parti {b.batch_id} — {b.customer}")
        lines.append("")
        lines.append(f"**Toplam Fiyat: {total:.2f} $**")
        lines.append("")
        for line_str in pr.get("breakdown", []):
            lines.append(f"- {line_str}")
        lines.append("")

    # --- Bölüm 5: Özet ---
    lines.append("## 5. Ozet")
    lines.append("")
    total_revenue = sum(
        pr.get("total_price", 0.0) for pr in pricing_results.values()
    )
    total_nesting_time = sum(
        nr.get("elapsed_sec", 0.0) for nr in nesting_results.values()
    )
    lines.append(f"| Metrik | Deger |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Toplam Ciro Onerisi | {total_revenue:.2f} $ |")
    lines.append(f"| Toplam Pipeline Suresi | {elapsed_total:.2f} s |")
    lines.append(f"| Toplam Nesting Suresi | {total_nesting_time:.2f} s |")
    lines.append(f"| Siparis Sayisi | {len(ranked)} |")
    lines.append(f"| Parti Sayisi | {len(batches)} |")
    lines.append(f"| Uyari Sayisi | {len(warnings)} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Konsol özeti
# ---------------------------------------------------------------------------

def _print_console_summary(
    ranked: list,
    batches: list,
    warnings: list,
    nesting_results: Dict[str, Any],
    pricing_results: Dict[str, Any],
    elapsed_total: float,
) -> None:
    sep = "=" * 72
    print(sep)
    print("DEMO PIPELINE OZETI")
    print(sep)
    print(f"Siparis sayisi   : {len(ranked)}")
    print(f"Parti sayisi     : {len(batches)}")
    print(f"Uyari sayisi     : {len(warnings)}")
    print()

    print("--- Oncelik Sirasi (ilk 5) ---")
    for i, o in enumerate(ranked[:5], 1):
        print(f"  {i}. {o.order_id:20s} termin={o.deadline}  oncelik={o.priority_class}")
    if len(ranked) > 5:
        print(f"  ... ve {len(ranked) - 5} siparis daha")
    print()

    total_rev = 0.0
    print("--- Parti Ozeti (Instance-Tuner) ---")
    for b in batches:
        nr = nesting_results.get(b.batch_id, {})
        pr = pricing_results.get(b.batch_id, {})
        h = nr.get("height_mm", 0.0)
        d = nr.get("density", 0.0)
        price = pr.get("total_price", 0.0)
        total_rev += price
        tuner_data = nr.get("tuner") or {}
        winner_cfg = tuner_data.get("winning_config", nr.get("portfolio", {}) and nr["portfolio"].get("winner", "?") or "?")
        gain_pct = tuner_data.get("gain_vs_baseline_pct", 0.0)
        improvement_mm = tuner_data.get("improvement_mm", 0.0)
        gain_str = f" | kazanc={improvement_mm:.2f}mm ({gain_pct:.1f}%)" if gain_pct > 0.01 else ""
        sel = nr.get("selection")
        sel_str = ""
        if sel is not None:
            easy_tag = "kolay" if sel.get("is_easy") else "zor"
            sel_str = f" | secim-tahmin={sel.get('predicted_winner','?')}({easy_tag})"
        print(
            f"  {b.batch_id}: {b.customer:12s} | "
            f"yukseklik={h:.1f}mm | doluluk={d * 100:.1f}% | "
            f"kazanan-konfig={winner_cfg}{gain_str}{sel_str} | fiyat={price:.2f}$"
        )
    print()
    print(f"Toplam ciro onerisi : {total_rev:.2f} $")
    print(f"Pipeline suresi     : {elapsed_total:.2f} s")
    print(f"Tuner budget        : {TUNER_BUDGET} iter/konfig")
    print(sep)


# ---------------------------------------------------------------------------
# Doğrudan çalıştırma
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse as _argparse
    _ap = _argparse.ArgumentParser(description="Demo pipeline")
    _ap.add_argument(
        "--scenario", choices=["standard", "rich"], default="rich",
        help="Senaryo secimi: 'standard' (5 siparis) veya 'rich' (yogun, 3 siparis ~20 parca)",
    )
    _args = _ap.parse_args()
    _scenario = RICH_SCENARIO if _args.scenario == "rich" else SCENARIO
    result = run_pipeline(_scenario)
    print(f"\nRapor: {result['report_path']}")
