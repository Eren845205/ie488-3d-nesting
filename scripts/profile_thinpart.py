"""profile_thinpart.py — (C) Faz 1 H1 ÖN-ÖLÇÜM: ince parça fine-pitch darboğazı nerede?

Yol haritası Açık Soru 1: "drop_map çözülünce TEKRAR profil al." drop_map artık
vektörize; şimdi ince-parça-fine-pitch senaryosunda zamanın NEREYE gittiğini ölç
(voxelizasyon mu, coarse arama mı, fine yerleştirme/drop_map mı?). Buna göre
per-part pitch (two-level grid) doğru lever mı karar ver — kör mimari değişim yok.

Sentetik instance: kalın + orta + İNCE (1mm) kutular → min_feature=1 → pitch 0.5mm.
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

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.pitch import suggest_pitch
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine

PLATE = 200.0


def _instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE, depth_mm=PLATE),
        parts=[
            PartSpec(id="kalin", name="kalin", qty=6, source="box",
                     width_mm=60.0, depth_mm=40.0, height_mm=30.0),
            PartSpec(id="orta", name="orta", qty=4, source="box",
                     width_mm=30.0, depth_mm=30.0, height_mm=20.0),
            PartSpec(id="ince", name="ince", qty=5, source="box",
                     width_mm=1.0, depth_mm=30.0, height_mm=20.0),  # 1mm → pitch 0.5
        ],
    )


def main():
    inst = _instance()
    fp = suggest_pitch(inst)
    print(f"suggest_pitch (ince parça yüzünden) = {fp} mm", flush=True)
    print("solve_coarse_to_fine profilleniyor...", flush=True)

    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
        coarse_pitch=None, fine_pitch=fp, budget=15, seed=42,
    )
    pr.disable()
    dt = time.perf_counter() - t0

    print(f"\nTOPLAM {dt:.1f}s | yükseklik {r.height_mm:.1f}mm | "
          f"coarse {r.coarse_time_s:.1f}s | fine {r.fine_time_s:.1f}s "
          f"| coarse_pitch {r.coarse_pitch} fine_pitch {r.fine_pitch}", flush=True)

    s = StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(20)
    print("\n=== EN PAHALI 20 FONKSİYON (cumulative) ===", flush=True)
    print(s.getvalue(), flush=True)

    # tottime (kendi içinde geçen) da önemli — gerçek hesap nerede
    s2 = StringIO()
    pstats.Stats(pr, stream=s2).sort_stats("tottime").print_stats(12)
    print("=== EN PAHALI 12 (tottime — kendi içinde) ===", flush=True)
    print(s2.getvalue(), flush=True)


if __name__ == "__main__":
    main()
