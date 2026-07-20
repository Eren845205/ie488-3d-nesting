# -*- coding: utf-8 -*-
"""k56f_pinleme.py — K-56f: buyuk-plaka PINLEME olcumu (duz poz, soft no-go).

Baglam: K-56e kompozisyon-degismezligi kaniti — 170.7'nin surucusu baseplate
acisi degil, 111 parcanin daralan tabanda istifi. Duz poz (40.6mm) dilate-grid
semantiginde acilamiyordu (0-pay + kenar-tasma). K-56f cozumu: baseplate
ARAMAYA SOKULMAZ — pinned_placements ile duz olarak deterministik sabitlenir
(pin MARGIN'SIZ: komsular kendi 2mm marjini tasir, tek-tarafli dilation
bosluk garantisi); 111 parca on-dolu sahnede normal cozulur.

Pin konumu: x ortalanir; y plaka uzak kenarina dayanir (no-go'dan en uzak) —
raw giris no-go'ya ~1.5mm (hoca cevap 9 toleransi 12mm; SERHLI on-olcum).
Beklenti: ~40.6 (plaka) + ~101 (111-parca tabani, K-56d v1 yan-olcumu) ~ 141;
istif verimine gore 130-160 bandi. Referanslar: raw 170.69 · soft 171.70 ·
hard 202.18 · K-37 129.0 · manuel 110.41.

Not: extra_rot_overrides={} gecirilir — pin varken otomatik tilt havuzu
gereksiz (bos acik-override otomatigi susturur, vokselize israfi olmaz).
Kosum: python -m scripts.detach_run k56f_pinleme    (D:\\ie488'den)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

import scripts.eval_gate as eg
from src.nesting3d.voxelize import voxelize_part
from scripts.k56_plan1_uretim_tilt import HEDEF_AD, SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k56f_pinleme.log"
OUT = _ROOT / "results" / "k56f_pinleme.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))
REF = {"raw": 170.68857421875, "soft": 171.70457763671877,
       "hard": 202.18468017578127, "k37": 129.0, "manuel": 110.41,
       "taban111": 101.17}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56f BUYUK-PLAKA PINLEME (duz poz, soft no-go; SERHLI on-olcum)")
    log(f"ref: {REF}")

    eg.NOGO_STD = NOGO_SOFT  # Eren-onayli soft sozlesme (K-56c)

    inst = eg._load_instance("plan1")
    fine_pitch, _w = _uretim_fine_pitch(inst)
    p0 = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()][0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])

    # duz raw ayak izi -> pin konumu (x ortala, y uzak kenara daya)
    vp = voxelize_part(p0.name, mesh, fine_pitch, rot_matrices=[np.eye(4)],
                       method="slice", margin=0)
    fw, fh = vp.orientations[0].filled.shape
    fz = vp.orientations[0].grid.shape[2]
    nx = int(eg.PLATE_STD[0] // fine_pitch)
    ny = int(eg.PLATE_STD[1] // fine_pitch)
    ix, iy = (nx - fw) // 2, ny - fh
    if ix < 0 or iy < 0:
        log(f"HATA: duz raw poz plakaya sigmiyor fp={fw}x{fh} grid={nx}x{ny}")
        log("BITTI")
        return
    giris = NOGO_SOFT[1][1] - iy * fine_pitch
    log(f"pitch={fine_pitch}  duz raw fp={fw}x{fh} z={fz}"
        f" (~{fz * fine_pitch:.1f}mm)  grid={nx}x{ny}")
    log(f"pin: ix={ix} iy={iy} -> x={ix * fine_pitch:.2f}mm"
        f" y={iy * fine_pitch:.2f}mm  no-go girisi={giris:.2f}mm"
        f" (tolerans 12mm)")

    pin = {"ad": p0.name, "x_mm": ix * fine_pitch, "y_mm": iy * fine_pitch,
           "z_mm": 0.0, "rot": None}
    log("[PIN] evaluate_set(plan1, pinned_placements=[duz]) ...")
    try:
        res = eg.evaluate_set("plan1", SEED, pinned_placements=[pin],
                              extra_rot_overrides={})
        log(f"[PIN] SONUC: legal={res['legal_height_mm']}"
            f"  h={res['height_mm']}  clear={res['min_clearance_mm']}"
            f"  kilit={res['n_locked']}  n={res['n_placed']}/{res['n_total']}"
            f"  sure={res['duration_s']}s"
            f"  invalid={res['invalid_reason']}")
    except Exception as e:
        res = {"exception": f"{type(e).__name__}: {e}"}
        log(f"[PIN] EXCEPTION: {type(e).__name__}: {e}")

    lh = res.get("legal_height_mm") if isinstance(res, dict) else None
    log(f"KIYAS: hard {REF['hard']:.1f} -> soft {REF['soft']:.1f} -> raw"
        f" {REF['raw']:.1f} -> PIN {lh}"
        f" | K-37 {REF['k37']} | manuel {REF['manuel']}")
    OUT.write_text(json.dumps({
        "pin": pin, "nogo_soft": NOGO_SOFT, "giris_mm": giris,
        "sonuc": res, "ref": REF,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
