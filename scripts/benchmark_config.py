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

# ---------------------------------------------------------------------------
# Cozucu parametreleri
# ---------------------------------------------------------------------------

# Voxelizasyon adimi (mm).  Daha kucuk = daha hassas ama daha yavas.
# 15 mm: BR instance'larinin 1-20 birim boyutlarinda makul cozunurluk.
# --quick modunda 20 mm kullanilir (benchmark.py --quick bayragi).
PITCH: float = 15.0

# SA iterasyon butcesi.  Tuning set icin kalibre edildi:
# DBLF icin 0 (deterministik greedy, iterasyon yok).
# SA icin 200: gecmis SA kosusu 181.5 mm rekoru 200 iterasyonla elde edildi.
BUDGET: int = 200

# Ana seed.  Tum kosular bu seed'den turetilir.  Degistirmek sonuclari
# degistirir ve karsilastirmayi bozar.
SEED: int = 42

# Karsilastirilacak cozucu isimleri.  portfolio.py'de kayitli olmali.
# "dblf": deterministik baseline (her zaman dahil — referans noktasi).
# "sa3d": simulated annealing wrapper (SASolver).
SOLVER_NAMES: List[str] = ["dblf", "sa3d"]

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

TUNE_INSTANCES: List[Dict[str, Any]] = [
    # --- random_boxes ---
    {
        "id": "syn_rb_s0",
        "family": "random_boxes",
        "split": "tune",
        "params": {"n_parts": 8, "seed": 0},
    },
    {
        "id": "syn_rb_s1",
        "family": "random_boxes",
        "split": "tune",
        "params": {"n_parts": 8, "seed": 1},
    },
    # --- few_large_many_small ---
    {
        "id": "syn_flms_s0",
        "family": "few_large_many_small",
        "split": "tune",
        "params": {"n_large": 3, "n_small": 10, "seed": 0},
    },
    {
        "id": "syn_flms_s2",
        "family": "few_large_many_small",
        "split": "tune",
        "params": {"n_large": 3, "n_small": 10, "seed": 2},
    },
    # --- high_qty_repeat ---
    {
        "id": "syn_hqr_s0",
        "family": "high_qty_repeat",
        "split": "tune",
        "params": {"n_models": 4, "qty_per_model": 6, "seed": 0},
    },
    {
        "id": "syn_hqr_s3",
        "family": "high_qty_repeat",
        "split": "tune",
        "params": {"n_models": 4, "qty_per_model": 6, "seed": 3},
    },
    # --- thin_plates ---
    {
        "id": "syn_tp_s0",
        "family": "thin_plates",
        "split": "tune",
        "params": {"n_parts": 8, "seed": 0},
    },
    {
        "id": "syn_tp_s4",
        "family": "thin_plates",
        "split": "tune",
        "params": {"n_parts": 8, "seed": 4},
    },
    # --- long_rods ---
    {
        "id": "syn_lr_s0",
        "family": "long_rods",
        "split": "tune",
        "params": {"n_parts": 6, "seed": 0},
    },
    {
        "id": "syn_lr_s5",
        "family": "long_rods",
        "split": "tune",
        "params": {"n_parts": 6, "seed": 5},
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
