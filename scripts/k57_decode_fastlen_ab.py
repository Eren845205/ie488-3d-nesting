# -*- coding: utf-8 -*-
"""k57_decode_fastlen_ab.py — FFT next_fast_len A/B (d4 orneklemi, tek proses).

Profil kaniti: d4 decode'un %93'u conv-FFT. Mevcut yol s=full (crop+kernel-1)
— cuFFT-dusmani boyutlarda (buyuk asal carpanli) yavas. Aday: s'i
next_fast_len kompozitine yuvarla (lineer konv valid bolgesi ayni matematik).

A = decode_gpu (fast_len=False, eski yol)  ->  h + raw placements + sure
B = decode_gpu (gpu_conv_valid_chunked fast_len=True monkeypatch)
GECER: h VE raw listesi BIREBIR + B < A. Ayni proses = adil sure.
Kosum: python -m scripts.detach_run k57_decode_fastlen_ab    SAF ASCII.
"""
from __future__ import annotations

import functools
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_decode_fastlen_ab.log"
OUT = _ROOT / "results" / "k57_decode_fastlen_ab.json"
N_ORNEKLEM = 60
CLEAR_MM = 2.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import NOGO_STD, PLATE_STD, _load_instance
    from src.nesting3d.bin3d import Bin3D
    from src.nesting3d import parallel_decode as pd
    from src.nesting3d import fft_backend as fb
    from src.nesting3d import nfv_solve as nfv

    log(f"K-57 FASTLEN A/B (d4 AX24 ilk {N_ORNEKLEM} parca; tek proses)")
    inst = _load_instance("deneme4")
    caps = nfv.probe_capabilities()
    allowed, detail = nfv._quality_max_decision(caps.ram_bytes)
    n_or = (len(allowed) if allowed is not None
            else nfv.NFV_DEFAULT_ORIENTATIONS)
    t = time.perf_counter()
    parts, used_pitch = nfv._voxelize_nfv(
        inst, CLEAR_MM, CLEAR_MM, n_or, 1,
        allowed_orientations=allowed, clearance_mm=CLEAR_MM)
    log(f"voxelize: {time.perf_counter() - t:.0f}s"
        f" ({len(parts)} parca, n={n_or})")
    pw, pd_mm = PLATE_STD
    nx, ny = int(pw // used_pitch), int(pd_mm // used_pitch)
    ng = Bin3D.no_go_mask_from_bounds(NOGO_STD, pw, pd_mm, used_pitch)
    orneklem = sorted(parts, key=lambda vp: -vp.volume_voxels)[:N_ORNEKLEM]

    orijinal = pd.gpu_conv_valid_chunked

    def _kos(etiket):
        t0 = time.perf_counter()
        h, raw = pd.decode_gpu(orneklem, nx, ny, pitch=used_pitch,
                               return_placements=True, no_go_mask=ng)
        dt = time.perf_counter() - t0
        log(f"[{etiket}] {dt:.1f}s  h={h:.1f}  n={len(raw)}")
        return dt, h, list(raw)

    ta, ha, ra = _kos("A eski   ")
    pd.gpu_conv_valid_chunked = functools.partial(
        fb.gpu_conv_valid_chunked, fast_len=True)
    try:
        tb, hb, rb = _kos("B fastlen")
    finally:
        pd.gpu_conv_valid_chunked = orijinal

    ozdes = (ha == hb) and (ra == rb)
    log(f"BIT-OZDESLIK: {'BIREBIR (h + tum placements)' if ozdes else 'FARKLI!!'}")
    if not ozdes:
        farkli = [k for k, (a, b) in enumerate(zip(ra, rb)) if a != b][:5]
        log(f"  h: {ha} vs {hb}  ilk-fark-index: {farkli}")
    log(f"KIYAS: A={ta:.1f}s -> B={tb:.1f}s  ({tb - ta:+.1f}s,"
        f" %{(tb / ta - 1) * 100:+.1f})  HUKUM:"
        f" {'KAZANC' if (ozdes and tb < ta * 0.95) else ('NOTR' if ozdes else 'FARKLI-INCELE')}")
    OUT.write_text(json.dumps({
        "a_s": round(ta, 1), "b_s": round(tb, 1), "h_a": float(ha),
        "h_b": float(hb), "ozdes": bool(ozdes),
        "n_orneklem": N_ORNEKLEM}, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
