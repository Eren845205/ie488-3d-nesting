"""c3_occfft_profile.py — (A) occ-FFT paylasimi GENEL-FAYDA profili (cross-dataset, ÖLÇ-ÖNCE).

SORU (kullanici overfit endisesi): NFV decode'da her oryantasyon icin occ'tan kirpilan bolgenin
FFT'si (rfftn(crop)) bastan hesaplaniyor. Ama occ bir parcanin TUM oryantasyonlari boyunca SABIT
-> occ-FFT tekrar ediyor (algoritmik redundancy, veri-hilesi DEGIL). Bunu paylasmak (parca basina
1 occ-FFT) ne kadar kazandirir VE bu kazanc GENEL mi (plan1/plan2/plan3 hepsinde) yoksa Plan2'ye mi
ozgu?

YONTEM: gercek seri decode'u kosturup feasible_mask'i INSTRUMENTED scipy ile degistir. Her FFT-konv
adiminin suresini 3 bilesene ayir:
  occ_fft   = rfftn(crop)            <- PAYLASILABILIR (occ sabit, oryantasyonlar arasi tekrar)
  ker_fft   = rfftn(kernel_flipped)  <- paylasilamaz (kernel'e ozgu; ama kernel cache'lenebilir, ayri is)
  mult_inv  = irfftn(Fo*Fk) + slice  <- paylasilamaz
Cikti her veride: occ_fft payi (%) + cagri sayisi + ort. eligible-orient + (A) ust-sinir tasarruf.

(A) ust-sinir tasarruf ~ occ_fft_payi * (1 - 1/avg_orient): paylasimla parca basina ~1 occ-FFT kalir.
occ_fft payi oryantasyon SAYISINDAN bagimsiz (her oryant 1 occ-FFT yapar) -> n=4 olcup n=8'e formulle.

BIREBIR: instrumented mask, _scipy_feasible_mask ile AYNI bool sonucu uretir (fftconvolve'un acik hali).
URETIME DOKUNMAZ — scripts/. Kullanim: python scripts/c3_occfft_profile.py [plan1|plan2|plan3|all]
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import scipy.fft as _sfft

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.parallel_decode import decode, _eligible_orients

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
N_OR, MARGIN = 4, 1  # profil n=4'te (occ-FFT payi n'den bagimsiz); n=8 tasarruf formulle

# c3_xdataset_speed + c3_quality_levers ile BIREBIR qty'ler (tek kaynak; kopya = bagimsiz kosu)
PLAN2_QTY = {"P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}
DATASETS = {
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "wd": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan2": {"dir": VERILER / "Plan2" / "Plan2", "wd": (328.74, 328.19), "qty": PLAN2_QTY},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "wd": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


class Profiler:
    """INSTRUMENTED scipy feasible_mask: _scipy_feasible_mask ile BIREBIR ama 3 bilesen zamanli."""
    def __init__(self):
        self.occ_fft = 0.0
        self.ker_fft = 0.0
        self.mult_inv = 0.0
        self.calls = 0

    def mask(self, occ_sub, grid):
        g = grid[::-1, ::-1, ::-1].astype(np.float64)
        o = occ_sub.astype(np.float64)
        s1 = np.array(o.shape); s2 = np.array(g.shape)
        full = [int(v) for v in (s1 + s2 - 1)]
        t = time.perf_counter(); Fo = _sfft.rfftn(o, s=full); self.occ_fft += time.perf_counter() - t
        t = time.perf_counter(); Fg = _sfft.rfftn(g, s=full); self.ker_fft += time.perf_counter() - t
        t = time.perf_counter()
        C = _sfft.irfftn(Fo * Fg, s=full)
        valid = C[s2[0] - 1:s1[0], s2[1] - 1:s1[1], s2[2] - 1:s1[2]]
        out = valid < 0.5
        self.mult_inv += time.perf_counter() - t
        self.calls += 1
        return out

    def total(self):
        return self.occ_fft + self.ker_fft + self.mult_inv


def _load(ds):
    c = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {}
    if c["wd"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["wd"]
    res = build_instance_from_order(stl_map, c["qty"],
                                    persist_dir=_ROOT / "data" / "mail_stl" / f"occprof_{ds}", **kwargs)
    return res.instance


def avg_eligible(parts, nx, ny):
    """Parca basina ortalama plakaya-sigan oryantasyon (occ-FFT paylasiminin n-faktoru)."""
    tot = sum(len(_eligible_orients(p, nx, ny)) for p in parts)
    return tot / max(1, len(parts))


def run_one(ds, caps):
    print(f"\n{'=' * 74}\n[{ds}]", flush=True)
    inst = _load(ds)
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, feasible, reason = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd,
                                                ram_bytes=caps.ram_bytes)
    parts = to_voxel_parts(inst, pitch, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(pw // pitch), int(pd // pitch)
    avg_or = avg_eligible(parts, nx, ny)
    print(f"  pitch={pitch:.2f} feasible={feasible} | {len(parts)} parca {nx}x{ny}vox "
          f"| ort.eligible-orient={avg_or:.2f}", flush=True)

    prof = Profiler()
    t = time.perf_counter()
    h = decode(parts, nx, ny, feasible_mask=prof.mask, parallel=False, pitch=pitch)
    el = time.perf_counter() - t

    tot = prof.total()
    p_occ = prof.occ_fft / tot * 100 if tot else 0
    p_ker = prof.ker_fft / tot * 100 if tot else 0
    p_inv = prof.mult_inv / tot * 100 if tot else 0
    fft_share = tot / el * 100 if el else 0
    print(f"  decode {h:.1f}mm ({el:.0f}s) | FFT-konv decode'un %{fft_share:.0f}'i | "
          f"{prof.calls} feasibility cagrisi", flush=True)
    print(f"  bilesen: occ-FFT %{p_occ:.0f} | ker-FFT %{p_ker:.0f} | carpim+ters %{p_inv:.0f}",
          flush=True)
    # (A) ust-sinir tasarruf = occ-FFT zamani * (1 - 1/avg_orient), decode'a oranli
    for n_label, n_share in (("n=4", avg_or), ("n=8", min(8, 2 * avg_or))):
        save_frac = (1 - 1 / max(n_share, 1.0))
        save_s = prof.occ_fft * save_frac
        save_pct = save_s / el * 100 if el else 0
        print(f"  (A) ust-sinir tasarruf [{n_label}, ort.orient~{n_share:.1f}]: "
              f"~%{save_pct:.0f} decode hizi (occ-FFT'nin %{save_frac * 100:.0f}'i paylasilir)",
              flush=True)
    return ds, p_occ, fft_share, avg_or, prof.occ_fft / el * 100 if el else 0


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    caps = probe_capabilities()
    print("=" * 74)
    print(f"(A) occ-FFT PAYLASIMI — GENEL-FAYDA PROFILI (CPU scipy, seri) — {caps.summary()}")
    print("=" * 74, flush=True)
    todo = ["plan1", "plan2", "plan3"] if arg == "all" else [arg]
    rows = []
    for ds in todo:
        try:
            rows.append(run_one(ds, caps))
        except Exception as e:
            import traceback
            print(f"\n[{ds}] HATA: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    print(f"\n{'=' * 74}\nOZET — occ-FFT payi HER VERIDE buyuk mu? (genel-fayda karari)")
    print(f"{'veri':>7} | {'occ-FFT/decode':>14} | {'occ-FFT/FFT':>11} | {'ort.orient':>10}")
    for ds, p_occ, fft_share, avg_or, occ_of_decode in rows:
        print(f"{ds:>7} | {occ_of_decode:13.0f}% | {p_occ:10.0f}% | {avg_or:10.2f}", flush=True)
    print("\nKARAR KURALI: occ-FFT/decode payi HER veride buyukse (orn >%20) -> (A) GENEL kazanc,")
    print("tam implementasyona deger. Bir veride bile kucukse -> Plan2-ozgu, NO-GO (pyfftw dersi).")
    print("=" * 74)


if __name__ == "__main__":
    main()
