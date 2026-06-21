"""profile_plan1.py — (C doğrula) GERÇEK konkav parçalarda darboğaz profili.

profile_thinpart.py kutu proxy'di → drop_map fast-path'e düşüyordu. Plan1 gerçek
STL parçaları KONKAV → drop_map GENEL yolu + gerçek voxelizasyon. Soru: gerçek
veride zaman coarse SA aramasında mı (placement × binlerce) yoksa voxelizasyonda
mı? Buna göre hız lever'ı seçilir (per-part pitch mi, SA-arama mı).
"""
from __future__ import annotations
import cProfile
import pstats
import sys
import time
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.kiyas_harness import PLANS, _load_instance
from src.nesting3d.instances.plate import resolve_container
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine

FINE_PITCH = 1.5
N_ORIENT = 8
SEED = 42


def main():
    cfg = PLANS["plan1"]
    inst = _load_instance("plan1", cfg)
    pdims = [(p.width_mm, p.depth_mm, p.height_mm) for p in inst.parts]
    pw, pd, _ch, _ = resolve_container(
        {"width_mm": None, "depth_mm": None, "height_mm": None}, pdims)
    print(f"Plan1: {len(inst.parts)} parça, plaka {pw:.0f}x{pd:.0f}, "
          f"fine_pitch={FINE_PITCH}, n={N_ORIENT}", flush=True)

    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=float(pw), plate_d_mm=float(pd),
        coarse_pitch=None, fine_pitch=FINE_PITCH, budget=25, seed=SEED,
        n_orientations=N_ORIENT,
    )
    pr.disable()
    dt = time.perf_counter() - t0

    print(f"\nTOPLAM {dt:.1f}s | yükseklik {r.height_mm:.1f}mm | "
          f"coarse {r.coarse_time_s:.1f}s | fine {r.fine_time_s:.1f}s | "
          f"coarse_pitch {r.coarse_pitch:.2f}", flush=True)

    s = StringIO()
    pstats.Stats(pr, stream=s).sort_stats("tottime").print_stats(15)
    print("\n=== EN PAHALI 15 (tottime — gerçek hesap nerede) ===", flush=True)
    print(s.getvalue(), flush=True)


if __name__ == "__main__":
    main()
