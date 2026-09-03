"""c3_parverify.py — Paralel NFV doğrulama harness'i (KALİTE-KORUMA kapısı).

PLAN (composed-churning-token.md, Doğrulama harness): hiçbir kol BİREBİR kapısından geçmeden
"kullan" durumuna geçmez. Modlar:
  equiv   : paralel decode == seri decode BİREBİR (yükseklik + placement listesi). subset + plan2.
  backend : her kullanılabilir backend mask == scipy mask (np.array_equal), sentetik fixture
            (donanımdan bağımsız; cupy f32 tripwire). GPU varsa cupy de test edilir.
  bench   : seri(set_workers=cpu) vs Kol A(set_workers=1) hız + oversubscribe probe.

ÜRETİME DOKUNMAZ (scripts/).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.c3_backend import (get_backend, probe_capabilities, _scipy_feasible_mask,
                                 _probe_cupy, _make_cupy_feasible_mask, _probe_fast_backend,
                                 _make_fast_feasible_mask)
from scripts.c3_par_a import decode, load, QTY, QTY_FULL


def _cmp_placements(a, b) -> bool:
    if len(a) != len(b):
        return False
    return all(pa == pb for pa, pb in zip(a, b))


def mode_equiv(testbed: str, pitch: float):
    qty = QTY_FULL if testbed == "plan2" else QTY
    parts, nx, ny = load(qty, pitch)
    fm, bename = get_backend()
    print(f"  testbed={testbed} ({len(parts)} parça {nx}x{ny}) backend={bename} pitch={pitch}", flush=True)

    t = time.perf_counter()
    hs, ps = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=pitch, return_placements=True)
    dts = time.perf_counter() - t
    t = time.perf_counter()
    hp, pp = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch, return_placements=True)
    dtp = time.perf_counter() - t

    h_ok = abs(hs - hp) < 0.01
    p_ok = _cmp_placements(ps, pp)
    print(f"  seri    : {hs:.1f} mm ({dts:.1f}s)")
    print(f"  paralel : {hp:.1f} mm ({dtp:.1f}s)  speedup {dts/max(dtp,1e-9):.2f}x")
    print(f"  yükseklik birebir: {h_ok}   placement listesi birebir: {p_ok}")
    if h_ok and p_ok:
        print(f"  -> [GEÇTİ] paralel == seri BİREBİR ({hs:.1f}, {len(ps)} yerleşim)")
        return True
    print(f"  -> [HATA] BİREBİR DEĞİL — Kol A bozuyor, DUR (h_ok={h_ok} p_ok={p_ok})")
    if not p_ok:
        for i, (a, b) in enumerate(zip(ps, pp)):
            if a != b:
                print(f"     ilk fark idx {i}: seri={a} paralel={b}"); break
    return False


def mode_backend():
    """Sentetik occ/grid battery'sinde her backend == scipy (array_equal). Donanım bağımsız."""
    caps = probe_capabilities()
    print(f"  {caps.summary()}", flush=True)
    rng = np.random.default_rng(12345)
    # küçük/orta/büyük overlap-yoğunluk + farklı grid boyutları (f32 precision sınırını zorla)
    fixtures = []
    for (oshape, gshape, dens) in [((20, 18, 16), (5, 4, 3), 0.3),
                                   ((48, 44, 40), (9, 7, 6), 0.5),
                                   ((80, 76, 60), (13, 11, 9), 0.7),
                                   ((96, 90, 80), (5, 5, 5), 0.9)]:
        occ = rng.random(oshape) < dens
        grid = rng.random(gshape) < 0.6
        fixtures.append((occ, grid))

    backends = []
    fast, fname = _probe_fast_backend()
    if fast is not None:
        backends.append((fname, _make_fast_feasible_mask(fast)))
    cp = _probe_cupy()
    if cp is not None:
        backends.append(("cupy", _make_cupy_feasible_mask(cp)))
    if not backends:
        print("  (scipy dışı backend yok — array_equal trivially scipy==scipy)")
        return True

    all_ok = True
    for name, fn in backends:
        ok = True
        for i, (occ, grid) in enumerate(fixtures):
            ref = _scipy_feasible_mask(occ, grid)
            got = fn(occ, grid)
            if not np.array_equal(ref, got):
                ok = False
                diff = int(np.sum(ref != got))
                print(f"  [{name}] fixture {i} MİSMATCH ({diff} hücre) — BİREBİR BOZUK")
        print(f"  [{name}] tüm fixture array_equal vs scipy: {ok}")
        all_ok = all_ok and ok
    print("  -> [GEÇTİ]" if all_ok else "  -> [HATA] backend birebir değil")
    return all_ok


def mode_bench(testbed: str, pitch: float):
    qty = QTY_FULL if testbed == "plan2" else QTY
    parts, nx, ny = load(qty, pitch)
    caps = probe_capabilities()
    fm, bename = get_backend()
    print(f"  testbed={testbed} ({len(parts)} parça) backend={bename} cpu={caps.cpu_count} pitch={pitch}", flush=True)

    # 1) seri (set_workers=cpu, mevcut davranış / 281s çapası)
    t = time.perf_counter(); hs = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=pitch)
    dts = time.perf_counter() - t
    print(f"  seri (set_workers=cpu)       : {hs:.1f} mm  {dts:.1f}s  (1.00x taban)")

    # 2) Kol A (set_workers=1, n_thread=min(n_or,cpu))
    t = time.perf_counter(); hp = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch)
    dtp = time.perf_counter() - t
    print(f"  Kol A (orient-thread, sw=1)  : {hp:.1f} mm  {dtp:.1f}s  ({dts/max(dtp,1e-9):.2f}x)")

    # 3) oversubscribe probe: paralel orient AMA fft_workers=cpu (kasten yanlış: n_thread × cpu)
    t = time.perf_counter()
    ho = decode(parts, nx, ny, feasible_mask=fm, parallel=True, pitch=pitch, fft_workers=caps.cpu_count)
    dto = time.perf_counter() - t
    print(f"  oversubscribe (thread×cpu)   : {ho:.1f} mm  {dto:.1f}s  ({dts/max(dto,1e-9):.2f}x)")
    print(f"  -> Kol A, oversubscribe'dan {dto/max(dtp,1e-9):.2f}x hızlı olmalı (set_workers=1 doğrulanır)")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "equiv"
    testbed = sys.argv[2] if len(sys.argv) > 2 else "subset"
    pitch = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    print("=" * 70)
    print(f"C3 PARVERIFY  mode={mode} testbed={testbed} pitch={pitch}")
    print("=" * 70, flush=True)
    if mode == "equiv":
        mode_equiv(testbed, pitch)
    elif mode == "backend":
        mode_backend()
    elif mode == "bench":
        mode_bench(testbed, pitch)
    else:
        print(f"bilinmeyen mod: {mode} (equiv|backend|bench)")
    print("=" * 70)


if __name__ == "__main__":
    main()
