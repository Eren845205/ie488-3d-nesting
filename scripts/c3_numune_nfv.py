"""c3_numune_nfv.py — GERCEK FFT-NFV'yi NUMUNE verisinde calistir (181.5 rekoruyla kiyas).

Hocanin ILK verdigi numune (8 tip) eski hibrit/SA + EGIK PLAKA ile en iyi 181.5mm vermisti.
NFV "kalite modu"nu (best_decode = gercek geometrik FFT-NFV) bu veride HIC denemedik (NFV
Plan2/Plan3 cavity-zengin verilerde test edildi; numune kutuluk ~0.35 = cavity-fakir, memory
dersi "numune YANILTIR"). OLC-ONCE: ne cikacagini gor.

3 kosu (pitch=2.0, plaka 335, margin=1):
  1. heightmap DBLF (baseline, hibrit egik oryantasyonlar)
  2. NFV best_decode + HIBRIT oryantasyonlar (181.5 ile AYNI poz havuzu = adil)
  3. NFV best_decode + STANDART n=8 (eksen-hizali, NFV default)
Referans: egik-plaka SA rekoru 181.5mm.

URETIME DOKUNMAZ. [[feedback-windows-stdout-ascii]] ASCII print.
Kullanim: python scripts/c3_numune_nfv.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.models import NUMUNE_ORIENTATIONS_HYBRID, model_set
from src.nesting3d.voxelize import expand_quantities
from src.nesting3d.parallel_decode import best_decode
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.capabilities import probe_capabilities

PITCH, PLATE, MARGIN = 2.0, 335.0, 1
REKOR = 181.5  # egik-plaka SA en iyi (2026-06-12)


def main():
    nx = int(PLATE // PITCH)
    caps = probe_capabilities()
    print("=" * 70)
    print(f"NUMUNE — GERCEK FFT-NFV vs egik-plaka rekoru {REKOR}mm — {caps.summary()}")
    print(f"pitch={PITCH} plaka={PLATE:.0f} grid={nx}x{nx}")
    print("=" * 70, flush=True)

    # parcalar: hibrit (egik) + standart (eksen-hizali)
    t = time.perf_counter()
    parts_h = expand_quantities(model_set("numune"), PITCH, n_orientations=8, margin=MARGIN,
                                method="slice", orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID)
    parts_s = expand_quantities(model_set("numune"), PITCH, n_orientations=8, margin=MARGIN,
                                method="slice")
    print(f"voxelize: {len(parts_h)} parca ({time.perf_counter()-t:.0f}s)", flush=True)

    # 1. heightmap baseline (hibrit)
    t = time.perf_counter()
    _, hb = dblf(parts_h, lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[1] HEIGHTMAP (hibrit)  : {hm:6.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    # 2. NFV + hibrit oryantasyonlar (181.5 ile ayni havuz = adil kiyas)
    t = time.perf_counter()
    h_nfv_h, raw_h, strat_h = best_decode(parts_h, nx, nx, pitch=PITCH)
    print(f"[2] NFV (hibrit/egik)   : {h_nfv_h:6.1f} mm  ({time.perf_counter()-t:.0f}s, {strat_h})", flush=True)

    # 3. NFV + standart n=8 (eksen-hizali)
    t = time.perf_counter()
    h_nfv_s, raw_s, strat_s = best_decode(parts_s, nx, nx, pitch=PITCH)
    print(f"[3] NFV (standart n=8)  : {h_nfv_s:6.1f} mm  ({time.perf_counter()-t:.0f}s, {strat_s})", flush=True)

    print("-" * 70)
    best_nfv = min(h_nfv_h, h_nfv_s)
    print(f"  egik-plaka SA rekoru : {REKOR} mm")
    print(f"  heightmap baseline   : {hm:.1f} mm")
    print(f"  EN IYI NFV           : {best_nfv:.1f} mm")
    d_rec = (REKOR - best_nfv) / REKOR * 100
    d_hm = (hm - best_nfv) / hm * 100
    print(f"  NFV vs rekor 181.5   : {d_rec:+.1f}%  ({'GELISME' if d_rec > 0 else 'GERIDE'})")
    print(f"  NFV vs heightmap     : {d_hm:+.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    main()
