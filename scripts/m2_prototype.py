"""m2_prototype.py — M2 GO/NO-GO: metaheuristic-over-order cavity'yi KURTARIYOR mu?

M1 bulgusu: greedy-cavity decode tek-geçişte DAHA KÖTÜ (Plan2 802 vs bbox 672), çünkü
açgözlü "en-derine" yerel seçim yüzeyi parçalıyor. Literatür: NFV + METAHEURISTIC birlikte.

M2 hipotezi: yerleşim SIRASINI SA ile ararsak, cavity-decode'un iyi çalıştığı bir sıra
bulunur ve greedy-cavity kaybı geri kazanılır (hatta bbox-EP'yi geçer).

GO/NO-GO testbed: cavity decode YAVAS (66-107s Plan2). SA yüzlerce decode ister →
KÜÇÜK/HIZLI instance şart. Plan2'nin büyük konkav (kutuluk~0.07=gerçek oyuk) parçaları +
orta filler'lar, DÜŞÜK qty + KABA pitch (ince NYLON hariç) → decode saniye-altı hedef.

KARAR: SA-cavity < min(bbox-EP, greedy-cavity) belirgin ise M2 GO → fine'a/decode-hızına
yatırım yap. ~esit/kotu ise order-search yetmiyor (sorun yerel placement heuristic).
"""
from __future__ import annotations
import sys, time, math, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point

STL_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
PLATE_W, PLATE_D = 328.74, 328.19

# Küçük testbed: büyük konkav parçalar (oyuk üreticileri) + orta filler'lar, DÜŞÜK qty.
# İnce NYLON kasıtlı YOK (kaba pitch'i bozar). Cavity sinyali büyük parçalardan gelir.
QTY_SMALL = {
    "PO-TR154979-17747_P282335": 3,         # en büyük hacim (vol=121203, oyuk üreticisi)
    "part284676_06B23B8_model_r_0": 4,
    "part282114_07D4114_model_r_0": 3,
    "PO-TR154989-17667_P282407": 4,
    "PO-TR156122-17810_P284641": 4,
    "part282115_07D4113": 3,
    "PO-TR154979-17747_P282334": 3,         # filler (ince-büyük yüzey)
}

PITCH = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
N_OR = 4
MARGIN = 1
SA_ITERS = int(sys.argv[2]) if len(sys.argv) > 2 else 150
SEED = 42


def cavity_decode(parts, order, nx, ny):
    """Decode an EXPLICIT part order via cavity packer. order = list of part objs."""
    pos = {id(p): i for i, p in enumerate(order)}
    _, ob = place_extreme_point(
        parts, lambda: OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH, cavity=True, cavity_cap=15000),
        order_key=lambda vp: pos[id(vp)])
    return ob.height_mm()


def neighbour(order, rng):
    n = len(order); new = list(order)
    if n < 2:
        return new
    m = rng.random()
    if m < 0.5:  # swap
        i, j = rng.randrange(n), rng.randrange(n)
        new[i], new[j] = new[j], new[i]
    elif m < 0.75:  # insert
        i = rng.randrange(n); e = new.pop(i); new.insert(rng.randrange(n), e)
    else:  # reverse segment
        i, j = sorted((rng.randrange(n), rng.randrange(n)))
        new[i:j + 1] = reversed(new[i:j + 1])
    return new


def main():
    print("=" * 70)
    print(f"M2 PROTOTYPE GO/NO-GO  (pitch={PITCH}, n_or={N_OR}, SA_iters={SA_ITERS})")
    print("=" * 70, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(STL_DIR.glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, QTY_SMALL, container_w_mm=PLATE_W, container_d_mm=PLATE_D,
        persist_dir=ROOT / "data" / "mail_stl" / "plan2_m1")
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    print(f"testbed: {len(parts)} parca, taban {nx}x{ny}", flush=True)

    # baseline 1: heightmap
    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(PLATE_W, PLATE_D, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[heightmap]      {hm:.1f} mm  ({time.perf_counter()-t:.1f}s)", flush=True)

    # baseline 2: bbox-EP (largest-first)
    t = time.perf_counter()
    _, ob = place_extreme_point(parts, lambda: OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH))
    bbox = ob.height_mm()
    print(f"[bbox-EP]        {bbox:.1f} mm  ({time.perf_counter()-t:.1f}s)", flush=True)

    # baseline 3: greedy cavity (largest-first) — decode timing reference for SA
    largest_first = sorted(parts, key=lambda vp: -vp.volume_voxels)
    t = time.perf_counter()
    greedy_cav = cavity_decode(parts, largest_first, nx, ny)
    dt_decode = time.perf_counter() - t
    print(f"[greedy-cavity]  {greedy_cav:.1f} mm  ({dt_decode:.2f}s/decode)", flush=True)
    est = dt_decode * (SA_ITERS + 1)
    print(f"  -> SA tahmini ~{est:.0f}s ({SA_ITERS} decode)", flush=True)

    # M2: SA over order, cavity decode
    rng = random.Random(SEED)
    cur = list(largest_first)
    cur_h = greedy_cav
    best, best_h = list(cur), cur_h
    t0, t_min = 3.0, 0.05
    cooling = (t_min / t0) ** (1.0 / max(SA_ITERS - 1, 1))
    temp = t0
    t = time.perf_counter()
    for k in range(SA_ITERS):
        cand = neighbour(cur, rng)
        ch = cavity_decode(parts, cand, nx, ny)
        d = ch - cur_h
        if d <= 0 or rng.random() < math.exp(-d / max(temp, 1e-9)):
            cur, cur_h = cand, ch
            if cur_h < best_h:
                best, best_h = list(cur), cur_h
        temp *= cooling
    sa_t = time.perf_counter() - t
    print(f"[SA-cavity]      {best_h:.1f} mm  ({sa_t:.0f}s, {SA_ITERS} iter)", flush=True)

    print("-" * 70)
    base = min(hm, bbox, greedy_cav)
    print(f"  heightmap {hm:.1f} | bbox-EP {bbox:.1f} | greedy-cav {greedy_cav:.1f} | SA-cav {best_h:.1f}")
    if best_h < base - 0.5:
        print(f"  -> [GO] SA-cavity en iyiyi %{(base-best_h)/base*100:.1f} GECTI -- order-search cavity'yi kurtardi")
    elif best_h < greedy_cav - 0.5:
        print(f"  -> KISMI: SA greedy-cavity'yi gecti ama bbox/heightmap'i gecemedi")
    else:
        print(f"  -> [NO-GO] order-search yetmiyor (sorun yerel placement heuristic)")
    print("=" * 70)


if __name__ == "__main__":
    main()
