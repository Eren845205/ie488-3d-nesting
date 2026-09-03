# -*- coding: utf-8 -*-
"""k57_decode_teshis.py — K-57 DECODE teshisi: GPU gercekten kosuyor mu +
decode/settle ayrimi (anatomi 'ham decode' 1926s = %50 kaleminin ici).

Soru-1: choose_strategy=gpu-resident SECIYOR ama decode_gpu buyuk sette
sessiz exception'la CPU'ya dusuyor olabilir (verbose kapali; K-57c acik yonu).
Soru-2: anatomi solve_ham_s = voxelize + DECODE + fine_settle toplami —
saf decode payi bilinmiyor.

Yontem: 3 NFV setinde uretim parametreleriyle IZOLE zincir:
_voxelize_nfv (sure) -> best_decode(verbose=True) (sure + strateji + h).
Strateji 'gpu-resident' = GPU KOSTU; 'cpu-kolA' = fallback/CPU. Fark
solve_ham_s - (vox+decode) ~= fine_settle payi.

Kosum: python -m scripts.detach_run k57_decode_teshis    SAF ASCII.
Cikti: scripts/k57_decode_teshis.log + results/k57_decode_teshis.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_decode_teshis.log"
OUT = _ROOT / "results" / "k57_decode_teshis.json"
CLEAR_MM = 2.0
# anatomi referanslari (solve_ham_s): kiyas icin
ANATOMI_HAM = {"plan2": 266.3, "plan3": 519.5, "deneme4": 1140.9}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import NOGO_STD, PLATE_STD, _load_instance
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    from src.nesting3d.bin3d import Bin3D
    from src.nesting3d.parallel_decode import best_decode
    from src.nesting3d import nfv_solve as nfv

    log("K-57 DECODE TESHISI (izole voxelize+best_decode, verbose=True)")
    _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    pw, pd = PLATE_STD
    rapor = {}
    for ad in ("plan2", "plan3", "deneme4"):
        log(f"--- {ad} ({time.strftime('%H:%M')}) ---")
        inst = _load_instance(ad)
        dec = predict_nfv_benefit(inst, family_routing=True, mode_model=_mm,
                                  rot_sokum=True, no_go_bounds=NOGO_STD)
        quality = getattr(dec, "nfv_quality", "fast")
        allowed = None
        if quality == "max":
            caps = nfv.probe_capabilities()
            allowed, detail = nfv._quality_max_decision(caps.ram_bytes)
            n_or = (len(allowed) if allowed is not None
                    else nfv.NFV_DEFAULT_ORIENTATIONS)
        else:
            n_or = nfv.NFV_DEFAULT_ORIENTATIONS
        t = time.perf_counter()
        parts, used_pitch = nfv._voxelize_nfv(
            inst, CLEAR_MM, CLEAR_MM, n_or, 1,
            allowed_orientations=allowed, clearance_mm=CLEAR_MM)
        vox_s = time.perf_counter() - t
        nx, ny = int(pw // used_pitch), int(pd // used_pitch)
        ng = Bin3D.no_go_mask_from_bounds(NOGO_STD, pw, pd, used_pitch)
        log(f"  voxelize @p{used_pitch} n{n_or}: {vox_s:.1f}s"
            f" ({len(parts)} parca) — decode basliyor...")
        t = time.perf_counter()
        h, raw, strategy = best_decode(parts, nx, ny, pitch=used_pitch,
                                       verbose=True, no_go_mask=ng)
        dec_s = time.perf_counter() - t
        settle_tahmin = ANATOMI_HAM[ad] - vox_s - dec_s
        log(f"  DECODE: {dec_s:.1f}s  h={h:.1f}  STRATEJI={strategy}")
        log(f"  KIYAS: anatomi solve_ham={ANATOMI_HAM[ad]}s ->"
            f" settle+diger tahmini ~{settle_tahmin:.0f}s")
        rapor[ad] = {"quality": quality, "n_or": n_or, "pitch": used_pitch,
                     "voxelize_s": round(vox_s, 1),
                     "decode_s": round(dec_s, 1),
                     "decode_h": float(h), "strateji": strategy,
                     "anatomi_solve_ham_s": ANATOMI_HAM[ad],
                     "settle_tahmin_s": round(settle_tahmin, 1)}
    OUT.write_text(json.dumps(rapor, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
