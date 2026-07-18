# -*- coding: utf-8 -*-
"""k57_decode_profil.py — d4 AX24 decode'un ICI (1078s kaleminin kirilimi).

decode_gpu/_blb_xybbox_gpu yeni _tel telemetrisiyle d4'un ILK 60 parcasinda
(sorted-hacim buyukler — temsili orneklem; tam kosu 19dk, orneklem ~4dk)
kalem oranlari olculur: bbox-sync / FFT-conv / blb-tarama / tur sayisi.
Oranlar hangi optimizasyonun (sync azaltma vs FFT vs blb) degecegini soyler.

Kosum: python -m scripts.detach_run k57_decode_profil    SAF ASCII.
Cikti: scripts/k57_decode_profil.log + results/k57_decode_profil.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57_decode_profil.log"
OUT = _ROOT / "results" / "k57_decode_profil.json"
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
    from src.nesting3d.parallel_decode import decode_gpu
    from src.nesting3d import nfv_solve as nfv

    log(f"K-57 DECODE PROFIL (d4 AX24, ilk {N_ORNEKLEM} parca orneklemi)")
    inst = _load_instance("deneme4")
    caps = nfv.probe_capabilities()
    allowed, detail = nfv._quality_max_decision(caps.ram_bytes)
    n_or = (len(allowed) if allowed is not None
            else nfv.NFV_DEFAULT_ORIENTATIONS)
    log(f"poz seti: {detail} n={n_or}")
    t = time.perf_counter()
    parts, used_pitch = nfv._voxelize_nfv(
        inst, CLEAR_MM, CLEAR_MM, n_or, 1,
        allowed_orientations=allowed, clearance_mm=CLEAR_MM)
    log(f"voxelize: {time.perf_counter() - t:.0f}s ({len(parts)} parca)")

    pw, pd = PLATE_STD
    nx, ny = int(pw // used_pitch), int(pd // used_pitch)
    ng = Bin3D.no_go_mask_from_bounds(NOGO_STD, pw, pd, used_pitch)
    orneklem = sorted(parts, key=lambda vp: -vp.volume_voxels)[:N_ORNEKLEM]
    tel = {}
    t = time.perf_counter()
    h, raw = decode_gpu(orneklem, nx, ny, pitch=used_pitch,
                        return_placements=True, no_go_mask=ng, _tel=tel)
    toplam = time.perf_counter() - t
    n_call = sum(len(p.orientations) for p in orneklem)
    bbox = tel.get("bbox_s", 0.0)
    conv = tel.get("conv_s", 0.0)
    blb = tel.get("blb_s", 0.0)
    diger = toplam - bbox - conv - blb
    log(f"DECODE({N_ORNEKLEM}p): {toplam:.1f}s  h={h:.1f}"
        f"  cagri~{n_call}  tur={tel.get('tur')}")
    log(f"KIRILIM: bbox-sync={bbox:.1f}s (%{bbox / toplam * 100:.0f})"
        f"  conv-FFT={conv:.1f}s (%{conv / toplam * 100:.0f})"
        f"  blb={blb:.1f}s (%{blb / toplam * 100:.0f})"
        f"  diger={diger:.1f}s (%{diger / toplam * 100:.0f})")
    OUT.write_text(json.dumps({
        "n_orneklem": N_ORNEKLEM, "toplam_s": round(toplam, 1),
        "bbox_s": round(bbox, 1), "conv_s": round(conv, 1),
        "blb_s": round(blb, 1), "diger_s": round(diger, 1),
        "tur": tel.get("tur"), "n_call": n_call,
        "h": float(h)}, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
