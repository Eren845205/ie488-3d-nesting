"""c3_fastcpu_bench.py — FastCPU (pyfftw/mkl_fft) backend hız+birebir ölçümü (backlog #4).

GPU'suz müşteri/cluster node hedefi: scipy CPU FFT vs pyfftw/mkl_fft CPU FFT. GPU KASTEN devre dışı
(NFV_BACKEND ile backend zorla; CPU Kol A decode). Birebir: iki backend AYNI yükseklik üretmeli
(array_equal mask → aynı placement). Kazanç: t_scipy / t_fast.

ÜRETİME DOKUNMAZ — scripts/. Kullanım: python scripts/c3_fastcpu_bench.py
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.fft_backend import get_backend
from src.nesting3d.parallel_decode import decode

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
PLAN2 = {"dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19), "qty": {
    "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
    "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
    "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
    "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
    "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
    "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
    "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
    "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}}


def main():
    caps = probe_capabilities()
    print("=" * 70)
    print(f"FastCPU BENCH (GPU devre disi) — donanim: {caps.summary()}")
    print("=" * 70, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(PLAN2["dir"].glob("*.stl"))}
    res = build_instance_from_order(stl_map, PLAN2["qty"],
                                    persist_dir=_ROOT / "data" / "mail_stl" / "fastcpu",
                                    container_w_mm=PLAN2["plate"][0], container_d_mm=PLAN2["plate"][1])
    inst = res.instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, _, reason = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd, ram_bytes=caps.ram_bytes)
    parts = to_voxel_parts(inst, pitch, n_orientations=4, margin=1)
    nx, ny = int(pw // pitch), int(pd // pitch)
    print(f"Plan2: {len(parts)} parca, pitch={pitch:.2f}mm, grid={nx}x{ny}", flush=True)
    print(f"  {reason}\n", flush=True)

    results = {}
    for be_name in ("scipy", "fast"):
        fn, real = get_backend(be_name)
        t = time.perf_counter()
        h = decode(parts, nx, ny, feasible_mask=fn, parallel=True, pitch=pitch)
        el = time.perf_counter() - t
        results[real] = (h, el)
        print(f"[{real:8}] yukseklik={h:.1f}mm  sure={el:.1f}s", flush=True)

    print("-" * 70)
    names = list(results)
    hs = {h for h, _ in results.values()}
    print(f"BIREBIR (ayni yukseklik): {'EVET' if len(hs) == 1 else 'HAYIR ' + str(hs)}")
    if "scipy" in results and len(names) == 2:
        other = [n for n in names if n != "scipy"][0]
        sp = results["scipy"][1]; fp = results[other][1]
        print(f"HIZ: scipy {sp:.1f}s vs {other} {fp:.1f}s  ->  {sp / fp:.2f}x "
              f"({'FastCPU KAZANDI' if fp < sp else 'scipy daha hizli — FastCPU NO-GO bu makinede'})")
    print("=" * 70)


if __name__ == "__main__":
    main()
