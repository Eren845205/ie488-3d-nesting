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


def _run_cell(pitch, n):
    """Bir (pitch, n) hucresi: voxelize + heightmap + NFV(standart). (hm, h_nfv, strat, dt) doner."""
    nx = int(PLATE // pitch)
    t = time.perf_counter()
    parts = expand_quantities(model_set("numune"), pitch, n_orientations=n, margin=MARGIN,
                              method="slice")
    vt = time.perf_counter() - t
    _, hb = dblf(parts, lambda: Bin3D(PLATE, PLATE, pitch, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    h_nfv, _, strat = best_decode(parts, nx, nx, pitch=pitch)
    return hm, h_nfv, strat, vt + (time.perf_counter() - t - vt)


def main():
    caps = probe_capabilities()
    print("=" * 78)
    print(f"NUMUNE — NFV PITCH x N SUPURME (hedef 170, rekor {REKOR}) — {caps.summary()}")
    print(f"plaka={PLATE:.0f}  (diskret kaldirac doyuyor mu? -> A1 surekli rotasyon karari)")
    print("=" * 78, flush=True)
    print(f"  {'pitch':>6} {'n':>4} {'heightmap':>10} {'NFV':>9} {'NFV-vs-hm':>10} {'sure':>7} {'durum':>10}")
    print("-" * 78, flush=True)

    best = (REKOR, "rekor 181.5 (egik+SA)")
    for pitch in (2.0, 1.5, 1.0, 0.5):
        for n in (8, 12):
            try:
                hm, h_nfv, strat, dt = _run_cell(pitch, n)
                d = (hm - h_nfv) / hm * 100
                if h_nfv < best[0]:
                    best = (h_nfv, f"NFV pitch={pitch} n={n}")
                print(f"  {pitch:>6} {n:>4} {hm:>10.1f} {h_nfv:>9.1f} {d:>+9.1f}% {dt:>6.0f}s {strat:>10}",
                      flush=True)
            except Exception as e:
                nm = type(e).__name__
                durum = "OOM" if "Memory" in nm or "alloc" in str(e).lower() else nm[:10]
                print(f"  {pitch:>6} {n:>4} {'-':>10} {'-':>9} {'-':>10} {'-':>7} {durum:>10}", flush=True)

    print("-" * 78)
    print(f"  EN IYI: {best[0]:.1f} mm  ({best[1]})")
    print(f"  rekor 181.5 | hedef 170 (sozel stretch, ulasilmadi)")
    if best[0] <= 170:
        print(f"  -> HEDEF 170 ASILDI! cross-dataset overfit testi GEREK.")
    elif best[0] < REKOR - 1:
        print(f"  -> rekoru gecti ama 170 altina inmedi (diskret kaldirac sinirli).")
    else:
        print(f"  -> diskret kaldirac (pitch+n) DOYGUN -> 170 icin SUREKLI ROTASYON (A1) gerek.")
    print("=" * 78)


if __name__ == "__main__":
    main()
