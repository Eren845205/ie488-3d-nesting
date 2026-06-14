"""enrich_telemetry.py — selection için telemetriyi zenginleştir (14 → ~70 instance).

Selection katmanı kuruldu ama 14 instance az (model öğrenemiyor). Bu script
AYIRT EDİCİ rejimde (sıkı taban → çözücüler farklılaşır → winner çeşitliliği)
çok sayıda sentetik instance üretip portföyü koşar; telemetri (özellik vektörü +
çözücü sonuçları + winner) data/telemetry/runs.jsonl'a birikir. Sonra
build_selection_model.py anlamlı kural öğrenebilir.

Çeşitlilik: 5 aile × birkaç parametre varyantı × birkaç seed → geniş özellik
yelpazesi + winner dağılımı. budget düşük (hız); drop_map hızlı yolu sayesinde
~5-8 dk.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.benchmark import run_benchmark
from src.nesting3d.instances.format import ContainerSpec

_C = lambda s: ContainerSpec(width_mm=s, depth_mm=s, height_mm=None)
BUDGET = 150
SEED = 42


def _instances():
    """Ayırt edici rejimde ~70 instance (5 aile × varyant × seed)."""
    insts = []
    # random_boxes — sıkı taban, parça/boyut varyasyonu
    for npart, cont in [(12, 110), (15, 120), (20, 130)]:
        for sd in range(5):
            insts.append({"id": f"enr_rb_n{npart}_s{sd}", "family": "random_boxes",
                          "split": "tune",
                          "params": {"n_parts": npart, "min_dim": 20, "max_dim": 60,
                                     "container": _C(cont), "seed": sd}})
    # few_large_many_small — GA güçlü
    for nl, ns, cont in [(3, 16, 120), (4, 20, 130)]:
        for sd in range(5):
            insts.append({"id": f"enr_flms_{nl}_{ns}_s{sd}", "family": "few_large_many_small",
                          "split": "tune",
                          "params": {"n_large": nl, "n_small": ns, "large_min": 50,
                                     "large_max": 90, "small_min": 12, "small_max": 30,
                                     "container": _C(cont), "seed": sd}})
    # high_qty_repeat
    for nm, q, cont in [(4, 8, 100), (5, 10, 110)]:
        for sd in range(5):
            insts.append({"id": f"enr_hqr_{nm}_{q}_s{sd}", "family": "high_qty_repeat",
                          "split": "tune",
                          "params": {"n_models": nm, "qty_per_model": q, "dim_min": 20,
                                     "dim_max": 45, "container": _C(cont), "seed": sd}})
    # thin_plates
    for npart, cont in [(16, 70), (20, 75)]:
        for sd in range(5):
            insts.append({"id": f"enr_tp_n{npart}_s{sd}", "family": "thin_plates",
                          "split": "tune",
                          "params": {"n_parts": npart, "xy_min": 25, "xy_max": 45,
                                     "thickness_min": 6, "thickness_max": 11,
                                     "container": _C(cont), "seed": sd}})
    # long_rods — konteyner >= uzunluk
    for npart, cont in [(10, 130), (12, 140)]:
        for sd in range(5):
            insts.append({"id": f"enr_lr_n{npart}_s{sd}", "family": "long_rods",
                          "split": "tune",
                          "params": {"n_parts": npart, "cross_min": 12, "cross_max": 22,
                                     "length_min": 60, "length_max": 120,
                                     "container": _C(cont), "seed": sd}})
    return insts


def main():
    insts = _instances()
    print(f"enrich_telemetry: {len(insts)} instance × 4 çözücü, budget={BUDGET}", flush=True)
    t = time.perf_counter()
    rows = run_benchmark(
        instances=insts, solver_names=["dblf", "sa3d", "ga", "tabu"],
        pitch=15.0, budget=BUDGET, seed=SEED,
        out_dir=_ROOT / "results", label="enrich",
        telemetry_path=_ROOT / "data" / "telemetry" / "runs.jsonl",
        adaptive_pitch=True, pitch_factor=2.5, pitch_floor=0.5,
        max_voxels_per_axis=170,
    )
    print(f"\nTAMAM: {len(rows)} satır, {(time.perf_counter()-t)/60:.1f} dk", flush=True)
    # winner dağılımı (çeşitlilik göstergesi)
    from collections import Counter
    wins = Counter(r["cozucu"] for r in rows if r.get("winner_flag"))
    print(f"Kazanan dağılımı (winner_flag): {dict(wins)}", flush=True)


if __name__ == "__main__":
    main()
