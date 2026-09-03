"""c3_gpu_596set.py — P3 doğrulama: 596s'lik gerçek ağır cavity seti (Plan1+Plan3
birleşik, nfv quality=fast) GPU-resident vs CPU Kol A. (2026-06-30)

ARKAPLAN: 2026-06-28b canlı demosunda poller 2 forward'ı (Plan1+Plan3) yakalayıp tek
nesting'e birleştirdi → /gecmis kaydı (nfv, quality=fast, h=667.5mm, doluluk 0.369,
596.9s). O an cupy ALGILANMADIĞINDAN CPU'ya düşmüştü. Bu script aynı gerçek geometriyle
GPU vs CPU'yu ölçer. force ile strateji zorlanır; ikisi BİREBİR aynı layout üretir
(H-04/H-05 invariant) → height eşitliği kanıt, süre farkı net kazanç.

Demo STL'leri data/mail_stl/ altında kalıcı: Plan1=mail_stl_4F427959, Plan3=mail_stl_CADD13C2.
Adetler (mail gövdesi) saklı olmadığından mult ile ölçeklenip 596s seti (h=667.5) kuşatılır.

ÜRETİME DOKUNMAZ (scripts/). Kullanım:
  python scripts/c3_gpu_596set.py calib            # qty=1 CPU kalibrasyon
  python scripts/c3_gpu_596set.py run <mult> both  # GPU vs CPU end-to-end
  python scripts/c3_gpu_596set.py split <mult>     # voxelize vs decode ayrı

BULGU (2026-06-30, RTX 3060 6GB / 16GB RAM): h=397→1.67×, h=512→1.93×, h=727→2.01×
end-to-end; decode-only (h=727) 2.67×; voxelize 54s paylaşılan (GPU hızlandırmaz).
596s seti (h=667.5, mult 3-4 arası) ~2× hızlanır, kalite birebir.
"""
from __future__ import annotations
import sys, time, tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.capabilities import probe_capabilities

PLAN1 = _ROOT / "data" / "mail_stl" / "mail_stl_4F427959"
PLAN3 = _ROOT / "data" / "mail_stl" / "mail_stl_CADD13C2"


def _load_stl_map(*dirs):
    m = {}
    for d in dirs:
        for f in sorted(Path(d).glob("*.stl")):
            m[f.stem] = f.read_bytes()
    return m


def build(mult: int):
    stl_map = _load_stl_map(PLAN1, PLAN3)
    qty = {name: mult for name in stl_map}
    persist = Path(tempfile.gettempdir()) / "c3_596set_stl"
    res = build_instance_from_order(stl_map, qty, persist_dir=persist)  # container=None -> auto plaka
    inst = res.instance
    return inst, inst.container.width_mm, inst.container.depth_mm, sum(p.qty for p in inst.parts), len(inst.parts)


def run_once(mult: int, force: str, label: str):
    inst, pw, pd, n_total, n_distinct = build(mult)
    t0 = time.perf_counter()
    r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, quality="fast", force=force)
    dt = time.perf_counter() - t0
    print(f"[{label}] mult={mult} distinct={n_distinct} toplam_parca={n_total} "
          f"plaka={pw:.1f}x{pd:.1f} pitch={r.fine_pitch:.2f} yukseklik={r.height_mm:.1f}mm "
          f"doluluk={r.density:.3f} sure={dt:.1f}s | {r.adaptive_reason}")
    return dt, r.height_mm


def run_split(mult: int):
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.parallel_decode import best_decode
    inst, pw, pd, n_total, _ = build(mult)
    nx, ny = int(pw // 2.5), int(pd // 2.5)
    t = time.perf_counter(); parts = to_voxel_parts(inst, 2.5, n_orientations=8, margin=1); t_vox = time.perf_counter() - t
    t = time.perf_counter(); hc, _, sc = best_decode(parts, nx, ny, pitch=2.5, force="cpu-kolA"); t_c = time.perf_counter() - t
    t = time.perf_counter(); hg, _, sg = best_decode(parts, nx, ny, pitch=2.5, force="gpu-resident"); t_g = time.perf_counter() - t
    print(f"[SPLIT mult={mult} parca={n_total}] voxelize={t_vox:.1f}s(paylasilan) "
          f"decode-CPU={t_c:.1f}s decode-GPU={t_g:.1f}s decode-hizlanma={t_c/t_g:.2f}x "
          f"({sc}/{sg}) birebir={'EVET' if abs(hc-hg)<0.05 else 'HAYIR'}")
    print(f"   end-to-end: CPU={t_vox+t_c:.1f}s GPU={t_vox+t_g:.1f}s = {(t_vox+t_c)/(t_vox+t_g):.2f}x")


def main():
    print("CAPS:", probe_capabilities(refresh=True).summary())
    mode = sys.argv[1] if len(sys.argv) > 1 else "calib"
    if mode == "calib":
        run_once(1, "cpu-kolA", "CALIB-CPU")
    elif mode == "split":
        run_split(int(sys.argv[2]))
    elif mode == "run":
        mult = int(sys.argv[2]); strat = sys.argv[3] if len(sys.argv) > 3 else "both"
        dt_c = h_c = dt_g = h_g = None
        if strat in ("cpu", "both"):
            dt_c, h_c = run_once(mult, "cpu-kolA", "CPU")
        if strat in ("gpu", "both"):
            dt_g, h_g = run_once(mult, "gpu-resident", "GPU")
        if strat == "both":
            ok = abs(h_c - h_g) < 0.05
            print(f"\n==> BIREBIR={'EVET' if ok else 'HAYIR %.2f vs %.2f' % (h_c, h_g)} "
                  f"| CPU={dt_c:.1f}s GPU={dt_g:.1f}s HIZLANMA={dt_c/dt_g:.2f}x")


if __name__ == "__main__":
    main()
