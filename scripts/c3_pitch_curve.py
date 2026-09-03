"""c3_pitch_curve.py — NFV pitch→kalite/süre/bellek EĞRİSİ (ÖLÇ-ÖNCE, backlog #1 girdisi).

SORU: solve_nfv'ye verilecek NFV-farkında pitch nasıl seçilmeli? suggest_pitch heightmap için
optimize (Plan2'de 0.5mm → 155M hücre FFT → ~5h/OOM). NFV'de pitch maliyeti KÜBİK; kalite ise
pitch'e AZ duyarlı (RESUME §8: 2.0=556, 1.5=550.5). Bu script gerçek üretim yolunu (solve_nfv,
GPU-resident dispatcher) farklı pitch'lerde koşar → kalite+süre+grid eğrisi → adaptif seçici tasarımı.

ÜRETİME DOKUNMAZ — sadece scripts/. solve_nfv'yi (src) ÇAĞIRIR ama değiştirmez.

Kullanım: python scripts/c3_pitch_curve.py [plan2|plan3]
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.capabilities import probe_capabilities

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
CFG = {
    "plan2": {"dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19), "qty": {
        "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
        "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
        "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
        "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
        "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
        "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
        "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
        "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "plate": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}

# Eğri noktaları: kaba→ince. 0.5mm KASTEN dışta (pratik dışı olduğu zaten kanıtlı; OOM/saatler).
PITCHES = [3.0, 2.5, 2.0, 1.5, 1.0]


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    c = CFG[ds]
    caps = probe_capabilities()
    print("=" * 78)
    print(f"NFV PITCH EĞRİSİ — dataset={ds}  donanım: {caps.summary()}")
    print("=" * 78, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"pitch_{ds}"}
    if c["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["plate"]
    res = build_instance_from_order(stl_map, c["qty"], **kwargs)
    inst = res.instance
    cont = inst.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    print(f"instance: {len(inst.parts)} parça tip, plaka {pw:.0f}x{pd:.0f}mm", flush=True)
    print(f"{'pitch':>6} | {'yükseklik':>10} | {'süre':>9} | {'grid (nx*ny*nz_lim)':>22} | strateji", flush=True)
    print("-" * 78, flush=True)

    rows = []
    for pit in PITCHES:
        nx, ny = int(pw // pit), int(pd // pit)
        nz = int(800 * 2.0 / pit)  # _nz_limit
        t = time.perf_counter()
        try:
            r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, fine_pitch=pit, n_orientations=4)
            el = time.perf_counter() - t
            strat = r.adaptive_reason
            print(f"{pit:6.2f} | {r.height_mm:9.1f}mm | {el:8.1f}s | "
                  f"{nx}x{ny}x{nz} | {strat}", flush=True)
            rows.append((pit, r.height_mm, el))
        except Exception as e:
            el = time.perf_counter() - t
            print(f"{pit:6.2f} | {'HATA':>9} | {el:8.1f}s | {nx}x{ny}x{nz} | {type(e).__name__}: {e}",
                  flush=True)

    # Özet: kalite-doygunluk (en ince pitch'e göre delta) + süre büyümesi
    print("-" * 78)
    if rows:
        best_h = min(h for _, h, _ in rows)
        print(f"{'pitch':>6} | {'yuk':>8} | {'en-iyiye-d':>10} | {'sure':>8} | {'2.0mm-sure-x':>13}")
        base_t = next((t for p, _, t in rows if abs(p - 2.0) < 1e-6), None)
        for p, h, t in rows:
            dpct = (h - best_h) / best_h * 100 if best_h else 0
            tx = f"{t / base_t:.1f}×" if base_t else "-"
            print(f"{p:6.2f} | {h:7.1f}mm | {dpct:+9.1f}% | {t:7.1f}s | {tx:>13}")
    print("=" * 78)


if __name__ == "__main__":
    main()
