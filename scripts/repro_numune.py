"""repro_numune.py — Faz 0.2: 181.5 mm rekor reproduksiyonu (PLAN_DEMO1.md).

Tam reproduksiyon scripti: run3d'yi rekor konfigurasyonla cagirip sonucu
beklenen degerle karsilastirir, PASS/FAIL basar.

Rekor konfigurasyon (ILERLEME_2026-06-11_hoca_feedback.md, commit 4898648/8070c61):
  --scenario numune
  --algo sa
  --iters 2000
  --pitch 1.5
  --orient hybrid
  --seed 13
  --plate 335  (numune default'u)
  --margin 1   (numune default'u)

Beklenen sonuc: 181.5 mm (+-0.5 mm tolerans)

Kullanim:
  python scripts/repro_numune.py

Uyari: SA ~8.5 dakika surebilir. Bu script unit test DEGILDIR —
gece/manuel kosus icin tasarlanmistir.
"""

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import (
    NUMUNE_DIR,
    NUMUNE_ORIENTATIONS_HYBRID,
    model_set,
)
from src.nesting3d.sa3d import simulated_annealing_3d
from src.nesting3d.voxelize import expand_quantities

# Rekor konfigurasyon — kesinlikle degistirme
PITCH = 1.5
PLATE = 335.0
MARGIN = 1
SEED = 13
ITERS = 2000
N_ORIENTATIONS = 8  # 8-poz master set (0-7)

# Beklenen altin deger ve tolerans
EXPECTED_HEIGHT_MM = 181.5
TOLERANCE_MM = 0.5  # +-0.5 mm: float yuvarlama ve voxel sinir kaymasindan


def main() -> None:
    print("=" * 60)
    print("repro_numune.py — 181.5 mm rekor reproduksiyonu")
    print("=" * 60)
    print(f"Konfigurasyon: pitch={PITCH}, plate={PLATE}, margin={MARGIN}, "
          f"seed={SEED}, iters={ITERS}, orient=hybrid")
    print(f"Beklenen: {EXPECTED_HEIGHT_MM} mm (+- {TOLERANCE_MM} mm)")
    print()

    if not NUMUNE_DIR.exists():
        print(f"HATA: Numuneler/ klasoru bulunamadi: {NUMUNE_DIR}")
        print("Numune STL dosyalari olmadan bu script calismaz.")
        sys.exit(2)

    # --- Voxelization ---
    print("Adim 1/3: Parcalar voxelize ediliyor (slice, ~1-2 dk)...")
    t_start = time.perf_counter()
    parts = expand_quantities(
        model_set("numune"),
        PITCH,
        n_orientations=N_ORIENTATIONS,
        margin=MARGIN,
        method="slice",
        orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID,
    )
    t_vox = time.perf_counter() - t_start
    print(f"  {len(parts)} parca voxelize edildi ({t_vox:.0f} s)")

    bin_factory = lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN)

    # --- DBLF Baseline ---
    print("Adim 2/3: DBLF baseline hesaplaniyor...")
    t0 = time.perf_counter()
    _base_placements, base_bin = dblf(parts, bin_factory)
    dblf_ms = (time.perf_counter() - t0) * 1000
    dblf_height = base_bin.max_height_mm()
    print(f"  DBLF baseline: {dblf_height:.1f} mm ({dblf_ms:.0f} ms)")

    # --- SA ---
    print(f"Adim 3/3: SA ({ITERS} iterasyon, seed={SEED}) basliyor (~8-10 dk)...")
    t0 = time.perf_counter()
    res = simulated_annealing_3d(
        parts, bin_factory,
        seed=SEED,
        iterations=ITERS,
    )
    sa_s = time.perf_counter() - t0
    sa_height = res.best_height_mm
    gain = res.baseline_height_mm - sa_height

    print(f"  SA sonucu: {sa_height:.1f} mm  (kazanc {gain:+.1f} mm, "
          f"density {res.best_density:.3f}, {sa_s:.0f} s)")
    print()

    # --- Karar ---
    diff = abs(sa_height - EXPECTED_HEIGHT_MM)
    total_s = time.perf_counter() - t_start
    print(f"Toplam sure: {total_s:.0f} s ({total_s/60:.1f} dk)")
    print()

    if diff <= TOLERANCE_MM:
        print(f"PASS: {sa_height:.1f} mm — beklenen {EXPECTED_HEIGHT_MM} mm, "
              f"fark {diff:.1f} mm (<= {TOLERANCE_MM} mm tolerans)")
        sys.exit(0)
    else:
        print(f"FAIL: {sa_height:.1f} mm — beklenen {EXPECTED_HEIGHT_MM} mm, "
              f"fark {diff:.1f} mm (> {TOLERANCE_MM} mm tolerans)")
        print("  Olasilik: motor degisikligi, poz seti farkliligi veya seed tutarsizligi.")
        sys.exit(1)


if __name__ == "__main__":
    main()
