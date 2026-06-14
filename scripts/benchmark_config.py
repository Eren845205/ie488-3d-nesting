"""benchmark_config.py — Dondurulmus benchmark parametresi seti (PLAN_DEMO1 §2.6).

Tek-konfig kurali (§5 / PLAN_DEMO1 Koru. Degismez #4):
    Bu dosyadaki parametreler sabittir.  Motor degisikligi ancak benchmark
    ortalamasini bozmuyorsa merge edilir.  Parametre ayari yalnizca TUNE
    yarisinda yapilir; HOLDOUT yarisi final dogrulama icin rezervedir.

Bolunme kurali:
    TUNE_INSTANCES : parametre ayari ve algoritma secim deneylerinde kullanilir.
    HOLDOUT_INSTANCES: sadece final degerlendirmede kullanilir; tune sirasinda
                        KESINLIKLE bakma.

Konfigurasyonu degistirmek icin bu dosyayi guncelleyin ve eski sonuclari
gecersiz sayip benchmark'i yeniden kosun.  Her parametre satiri hangi karar
icin var oldugunun kisa gerekcesinni comments'ta tasir.
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.nesting3d.instances.format import ContainerSpec


def _sq(side: float) -> ContainerSpec:
    """Kare-taban, açık-yükseklik konteyner (side x side x None)."""
    return ContainerSpec(width_mm=side, depth_mm=side, height_mm=None)

# ---------------------------------------------------------------------------
# Cozucu parametreleri
# ---------------------------------------------------------------------------

# Voxelizasyon adimi politikasi (2026-06-14 — adaptif pitch, R6).
#
# ESKI (kirik): tek global PITCH=15 mm.  Tek pitch hem 300 mm kutulari hem
# 3-12 mm ince levhalari cozemiyordu; tune setinin 10 instance'indan 3'u
# (her iki thin_plates + bir long_rods) bos voxel grid uretip cokuyordu
# (slice voxelizer min_dim ~pitch/2 altinda kayboluyor).  Tam benchmark HIC
# uctan uca kosmamisti — birim testler kucuk fixture'larda gecip gercek
# config'i akliyordu (sahte yesil).
#
# YENI: pitch her instance'in EN KUCUK parca boyutundan TURETILIR
# (instances/pitch.suggest_pitch: min_dim / PITCH_FACTOR, [PITCH_FLOOR, PITCH]
# araligina kelepcelenir).  Tek-konfig kurali artik pitch SAYISINA degil bu
# TURETME KURALINA uygulanir — kural tum instance'lara ayni uygulandigi icin
# determinizm + adillik korunur.
#
# PITCH burada artik TAVAN (en kaba pitch) rolundedir; buyuk-kutu runtime'ini
# sinirlar ve eski 15 mm degeriyle geriye uyumludur.
ADAPTIVE_PITCH: bool = True   # tam-set kosusunda her instance'a kendi pitch'i
PITCH_FACTOR: float = 2.5     # min_dim / factor → en ince parca ~2.5 voxel
PITCH_FLOOR: float = 0.5      # pitch alt siniri (mm); BR birim-olcek (1mm parca)
                              # icin 2.0 -> 0.5 (2026-06-14, bkz pitch.py notu)
PITCH: float = 15.0           # pitch TAVANI (mm) — suggest_pitch'in ceil'i

# Runtime butcesi: adaptif pitch konteyner-eksen voxel sayisini bu degerin
# uzerine cikarirsa instance ATLANIR + LOGLANIR (sessiz kabalastirma yok,
# cokme yok). 170: tum tune aileleri gecer (en yogun thin_plates ~152
# voxel/eksen); BR birim-olcek 1mm parcalari (~200 voxel/eksen) atlanir —
# BR verisi yeniden-olceklenince veya HPC gelince (A14) butce yukseltilir.
MAX_VOXELS_PER_AXIS: int = 170

# SA iterasyon butcesi.  Tuning set icin kalibre edildi:
# DBLF icin 0 (deterministik greedy, iterasyon yok).
# SA icin 200: gecmis SA kosusu 181.5 mm rekoru 200 iterasyonla elde edildi.
BUDGET: int = 200

# Ana seed.  Tum kosular bu seed'den turetilir.  Degistirmek sonuclari
# degistirir ve karsilastirmayi bozar.
SEED: int = 42

# Karsilastirilacak cozucu isimleri.  benchmark._SOLVER_REGISTRY'de kayitli
# olmali.  Tam portfoy (PLAN_DEMO1 Faz 5.3): dblf + sa3d + ga + tabu.
# "dblf": deterministik baseline (her zaman dahil — referans noktasi / cikar
#         tabani; hicbir metaheuristik bunun altina dusemez).
# "sa3d": simulated annealing wrapper (SASolver).
# "ga"  : genetik algoritma (GASolver; A12 kismi sinyal: hocanin onerisi).
# "tabu": tabu search (TabuSolver).
SOLVER_NAMES: List[str] = ["dblf", "sa3d", "ga", "tabu"]

# ---------------------------------------------------------------------------
# Instance listesi — tune / holdout bolunmesi
#
# Her eleman bir dict:
#   id:     str    — benzersiz tanimlayici (CSV/MD satirinda gorunur)
#   family: str    — synthetic aile adi veya "bischoff_ratcliff"
#   split:  str    — "tune" | "holdout"
#   params: dict   — ilgili uretici fonksiyonuna gecilecek keyword argumanlari
#                    (seed, n_parts, vb.)
#
# Synthetic 5 aile × 2 seed = 10 tune instance
# BR seckileri (BR1, BR3, BR5, BR9, BR12) × 1 seed = 5 holdout instance
# Toplam: 15 instance (10 tune + 5 holdout)
# ---------------------------------------------------------------------------

# NOT (2026-06-14): parametreler "AYIRT EDİCİ REJİM"e göre seçildi. Eski seyrek
# kurulum (8 parça, 300x300 taban) çözücüleri ayırt edemiyordu — DBLF zaten
# optimal, metaheuristikler 0 kazanç (sahte portföy; APP_YOL_HARITASI §2.2
# bulgu #2). Çözüm: SIKI TABAN (parçalar tabanın küçük kısmı → katman başına
# çok parça → 2D yerleşim + oryantasyon kararı önemli → DBLF suboptimal). Her
# preset DBLF üzerine SA/GA/tabu kazancı gösterecek şekilde ampirik seçildi
# (kazanç parantezde); voxel bütçesi içinde (vpa<=32) ve hızlı (<=2s).
TUNE_INSTANCES: List[Dict[str, Any]] = [
    # --- random_boxes (sıkı taban, ~+14%) ---
    {
        "id": "syn_rb_s0", "family": "random_boxes", "split": "tune",
        "params": {"n_parts": 15, "min_dim": 20, "max_dim": 60,
                   "container": _sq(120), "seed": 0},
    },
    {
        "id": "syn_rb_s1", "family": "random_boxes", "split": "tune",
        "params": {"n_parts": 15, "min_dim": 20, "max_dim": 60,
                   "container": _sq(120), "seed": 1},
    },
    # --- few_large_many_small (büyük+küçük interlocking, ~+21%; GA güçlü) ---
    {
        "id": "syn_flms_s0", "family": "few_large_many_small", "split": "tune",
        "params": {"n_large": 4, "n_small": 20, "large_min": 50, "large_max": 90,
                   "small_min": 12, "small_max": 30, "container": _sq(130), "seed": 0},
    },
    {
        "id": "syn_flms_s2", "family": "few_large_many_small", "split": "tune",
        "params": {"n_large": 4, "n_small": 20, "large_min": 50, "large_max": 90,
                   "small_min": 12, "small_max": 30, "container": _sq(130), "seed": 2},
    },
    # --- high_qty_repeat (tekrar parça, sıkı, ~+5%) ---
    {
        "id": "syn_hqr_s0", "family": "high_qty_repeat", "split": "tune",
        "params": {"n_models": 5, "qty_per_model": 10, "dim_min": 20, "dim_max": 45,
                   "container": _sq(110), "seed": 0},
    },
    {
        "id": "syn_hqr_s3", "family": "high_qty_repeat", "split": "tune",
        "params": {"n_models": 5, "qty_per_model": 10, "dim_min": 20, "dim_max": 45,
                   "container": _sq(110), "seed": 3},
    },
    # --- thin_plates (ince levha, oryantasyon, ~+9%) ---
    {
        "id": "syn_tp_s0", "family": "thin_plates", "split": "tune",
        "params": {"n_parts": 20, "xy_min": 25, "xy_max": 45, "thickness_min": 6,
                   "thickness_max": 11, "container": _sq(75), "seed": 0},
    },
    {
        "id": "syn_tp_s4", "family": "thin_plates", "split": "tune",
        "params": {"n_parts": 20, "xy_min": 25, "xy_max": 45, "thickness_min": 6,
                   "thickness_max": 11, "container": _sq(75), "seed": 4},
    },
    # --- long_rods (çubuk, yatır/dik oryantasyon, ~+11%; konteyner>=uzunluk) ---
    {
        "id": "syn_lr_s0", "family": "long_rods", "split": "tune",
        "params": {"n_parts": 12, "cross_min": 12, "cross_max": 22, "length_min": 60,
                   "length_max": 120, "container": _sq(140), "seed": 0},
    },
    {
        "id": "syn_lr_s5", "family": "long_rods", "split": "tune",
        "params": {"n_parts": 12, "cross_min": 12, "cross_max": 22, "length_min": 60,
                   "length_max": 120, "container": _sq(140), "seed": 5},
    },
]

HOLDOUT_INSTANCES: List[Dict[str, Any]] = [
    # BR instance seckileri — 5 farkli zorluk sinifi
    {
        "id": "br1_idx0",
        "family": "bischoff_ratcliff",
        "split": "holdout",
        "params": {"class_name": "BR1", "instance_idx": 0},
    },
    {
        "id": "br3_idx0",
        "family": "bischoff_ratcliff",
        "split": "holdout",
        "params": {"class_name": "BR3", "instance_idx": 0},
    },
    {
        "id": "br5_idx0",
        "family": "bischoff_ratcliff",
        "split": "holdout",
        "params": {"class_name": "BR5", "instance_idx": 0},
    },
    {
        "id": "br9_idx0",
        "family": "bischoff_ratcliff",
        "split": "holdout",
        "params": {"class_name": "BR9", "instance_idx": 0},
    },
    {
        "id": "br12_idx0",
        "family": "bischoff_ratcliff",
        "split": "holdout",
        "params": {"class_name": "BR12", "instance_idx": 0},
    },
]

# ---------------------------------------------------------------------------
# Dogrulama (import sirasinda calisir)
# ---------------------------------------------------------------------------

_tune_ids = {inst["id"] for inst in TUNE_INSTANCES}
_holdout_ids = {inst["id"] for inst in HOLDOUT_INSTANCES}
_overlap = _tune_ids & _holdout_ids
if _overlap:
    raise ValueError(
        f"benchmark_config: tune ve holdout kesisen ID'ler: {_overlap}"
    )
