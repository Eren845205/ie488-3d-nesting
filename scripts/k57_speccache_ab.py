# -*- coding: utf-8 -*-
"""k57_speccache_ab.py — kernel-spektrum LRU A/B (d4 orneklemi, tek proses).

fastlen sonrasi conv'un icinde kernel rfftn'i her cagri yeniden hesaplaniyor;
SpecLRU ayni (kernel, fshape) spektrumunu onbellekler (cuFFT deterministik ->
BIT-OZDES). A = spec_cache_mb=0 (kapali) · B = 1024MB LRU.
GECER: h + raw placements BIREBIR + B < A.
Kosum: python -m scripts.detach_run k57_speccache_ab    SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_speccache_ab.log"
OUT = _ROOT / "results" / "k57_speccache_ab.json"
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
    from src.nesting3d import parallel_decode as pdek
    from src.nesting3d import nfv_solve as nfv

    log(f"K-57 SPEC-CACHE A/B (d4 AX24 ilk {N_ORNEKLEM} parca; tek proses)")
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

    def _kos(etiket, mb):
        t0 = time.perf_counter()
        h, raw = pdek.decode_gpu(orneklem, nx, ny, pitch=used_pitch,
                                 return_placements=True, no_go_mask=ng,
                                 spec_cache_mb=mb)
        dt = time.perf_counter() - t0
        log(f"[{etiket}] {dt:.1f}s  h={h:.1f}  n={len(raw)}")
        return dt, h, list(raw)

    ta, ha, ra = _kos("A cache'siz", 0)
    tb, hb, rb = _kos("B 1024MB  ", 1024.0)

    ozdes = (ha == hb) and (ra == rb)
    log(f"BIT-OZDESLIK: {'BIREBIR (h + tum placements)' if ozdes else 'FARKLI!!'}")
    log(f"KIYAS: A={ta:.1f}s -> B={tb:.1f}s  ({tb - ta:+.1f}s,"
        f" %{(tb / ta - 1) * 100:+.1f})  HUKUM:"
        f" {'KAZANC' if (ozdes and tb < ta * 0.95) else ('NOTR' if ozdes else 'FARKLI-INCELE')}")
    OUT.write_text(json.dumps({
        "a_s": round(ta, 1), "b_s": round(tb, 1), "h_a": float(ha),
        "h_b": float(hb), "ozdes": bool(ozdes)}, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
