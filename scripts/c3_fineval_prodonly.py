"""c3_fineval_prodonly.py — Faz B: SADECE üretim sayısı (heightmap/NFV zaten elde).

c3_fineval.py budget=40 @1.5mm gece bitmedi ([3] üretim basılmadı). heightmap=732,
NFV-greedy=550.5 zaten ölçüldü (fineval_15.log). Bunları yeniden hesaplamak ~12dk boşa;
bu script SADECE solve_coarse_to_fine'i düşük budget ile koşar -> adil same-pitch üretim referansı.

arg1: pitch (mm)   arg2: budget   ÜRETİME DOKUNMAZ (src/ salt-okunur çağrı).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import scipy.fft as _sfft
_sfft.set_workers(max(1, (__import__("os").cpu_count() or 2)))
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.instances.stl_order_loader import build_instance_from_order

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19
N_OR = 4
PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
BUDGET = int(sys.argv[2]) if len(sys.argv) > 2 else 15
# referans (fineval_15.log, aynı pitch=1.5):
HM_REF, NFV_REF, MAGICS, PROD_FINE = 732.0, 550.5, 492.39, 621.0

QTY = {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
}


def main():
    print("=" * 70)
    print(f"C3 FAZ B — ÜRETİM SAYISI  pitch={PITCH}mm  budget={BUDGET}")
    print(f"  ref (fineval_15.log @1.5): heightmap={HM_REF} | NFV-greedy={NFV_REF}")
    print(f"  ref (pitch farklı):       eski üretim fine(0.5)={PROD_FINE} | Magics={MAGICS}")
    print("=" * 70, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(stl_map, QTY, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
                                    persist_dir=_ROOT / "data" / "mail_stl" / "plan2_m1")

    t = time.perf_counter()
    prod = solve_coarse_to_fine(res.instance, plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                                coarse_pitch=PITCH, fine_pitch=PITCH, budget=BUDGET,
                                n_orientations=N_OR)
    ph = prod.height_mm
    dt = time.perf_counter() - t
    print(f"[3] üretim (coarse+SA)    : {ph:7.1f} mm  ({dt:.0f}s)", flush=True)

    print("-" * 70)
    print(f"  pitch={PITCH} budget={BUDGET} | heightmap={HM_REF} | NFV={NFV_REF} | üretim={ph:.1f}")
    print(f"  NFV vs üretim: {(ph-NFV_REF)/ph*100:+.1f}%")
    if NFV_REF < ph - 0.5:
        print(f"  -> [GO] NFV ÜRETİMİ geçti (%{(ph-NFV_REF)/ph*100:.1f}); Magics'e %{(NFV_REF-MAGICS)/MAGICS*100:.0f} kala")
    elif NFV_REF < ph + 0.5:
        print(f"  -> NFV ~üretim (berabere); kaba kazanç fine'da kapanıyor")
    else:
        print(f"  -> NFV üretimden KÖTÜ; üretimin SA'sı öne geçiyor")
    print(f"  NOT: budget={BUDGET} düşük referans (adillik için akılda tut).")
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
