"""H-17: FFT bellek tavani — eksen-adaptif dilimli feasibility konvolusyonu.

K-39/K-39b MemErr koku: scipy fftconvolve tam-boy padded float64 tamponu
(pitch 1.0 plakada (486,432,625) = 1001MiB tekil alloc, tepe ~5GB). Fix:
'valid' konvolusyon ciktisi kernel'in kucuk oldugu eksende dilimlenir; her
dilim ayri FFT — tepe bellek dilim boyutuyla sinirli, KARARLAR (C<0.5,
tamsayi cakisma sayisi, f64 hata ~1e-11) BIREBIR.

Kabul kriterleri:
  1. plan_fft_chunks: tam-boy tahmin butceye sigarsa None (eski yol, bit-ozdes);
     sigmazsa (eksen, dilim) deterministik. Eksen secimi out/ker orani en buyuk
     olan: kanat-tipi kernel (z ince) -> z ekseni; cubuk-tipi (xy ince) -> x.
  2. chunked_feasible_mask == referans fftconvolve maskesi BIREBIR
     (rastgele + sinir vakalari: bos occ, dolu occ, kernel==occ, tek-cakisma).
  3. blb_xybbox dilimli fn ile ayni BLB pozisyonunu verir (kucuk butce zorlanmis).
  4. NFV_FFT_BUDGET_MB env override deterministik.
  5. (GPU varsa) gpu_conv_valid_chunked ayni maskeyi doner (dilimli + dilimsiz).
"""
from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.capabilities import probe_cupy
from src.nesting3d.fft_backend import (
    _scipy_feasible_mask,
    blb_xybbox,
    chunked_feasible_mask,
    plan_fft_chunks,
)

rng = np.random.default_rng(7)


def _case(occ_shape, ker_shape, density=0.25, seed=7):
    r = np.random.default_rng(seed)
    occ = r.random(occ_shape) < density
    ker = r.random(ker_shape) < 0.7
    ker[0, 0, 0] = True  # kernel asla bos degil
    return occ, ker


# ---------------------------------------------------------------- plan ----

def test_plan_none_when_fits():
    # kucuk grid, buyuk butce -> tam-boy yol (None) = eski davranis bit-ozdes
    assert plan_fft_chunks((40, 40, 60), (10, 8, 5), budget_bytes=1 << 30) is None


def test_plan_axis_wing_z():
    # kanat: kernel z'si kucuk (out/ker orani z'de buyuk) -> z ekseninde dilim
    plan = plan_fft_chunks((336, 336, 600), (151, 97, 26), budget_bytes=768 * 1e6)
    assert plan is not None
    axis, chunk = plan
    assert axis == 2
    assert 1 <= chunk < 600 - 26 + 1


def test_plan_axis_rod_x():
    # cubuk: kernel xy'si kucuk -> x ekseninde dilim (esitlikte kucuk indeks)
    plan = plan_fft_chunks((336, 336, 600), (8, 8, 220), budget_bytes=768 * 1e6)
    assert plan is not None
    axis, chunk = plan
    assert axis == 0
    assert 1 <= chunk < 336 - 8 + 1


def test_plan_deterministic():
    a = plan_fft_chunks((336, 336, 600), (151, 97, 26), budget_bytes=768 * 1e6)
    b = plan_fft_chunks((336, 336, 600), (151, 97, 26), budget_bytes=768 * 1e6)
    assert a == b


def test_plan_env_override(monkeypatch):
    # dev butce -> None; minik butce -> dilim. Env yalniz default'u degistirir.
    monkeypatch.setenv("NFV_FFT_BUDGET_MB", "100000")
    assert plan_fft_chunks((336, 336, 600), (151, 97, 26)) is None
    monkeypatch.setenv("NFV_FFT_BUDGET_MB", "50")
    assert plan_fft_chunks((336, 336, 600), (151, 97, 26)) is not None


# ---------------------------------------------------------- birebirlik ----

@pytest.mark.parametrize("occ_shape,ker_shape,seed", [
    ((40, 40, 60), (12, 9, 5), 1),
    ((40, 40, 60), (3, 3, 30), 2),    # cubuk-tipi
    ((30, 50, 40), (11, 40, 7), 3),   # y'de genis kernel
    ((25, 25, 25), (1, 1, 1), 4),     # birim kernel
])
def test_chunked_identity_random(occ_shape, ker_shape, seed):
    occ, ker = _case(occ_shape, ker_shape, seed=seed)
    ref = _scipy_feasible_mask(occ, ker)
    got = chunked_feasible_mask(_scipy_feasible_mask, occ, ker, budget_bytes=1e5)
    assert got.shape == ref.shape
    assert bool((got == ref).all())


def test_chunked_identity_empty_and_full():
    ker = np.ones((4, 4, 4), dtype=bool)
    bos = np.zeros((20, 20, 20), dtype=bool)
    dolu = np.ones((20, 20, 20), dtype=bool)
    for occ in (bos, dolu):
        ref = _scipy_feasible_mask(occ, ker)
        got = chunked_feasible_mask(_scipy_feasible_mask, occ, ker, budget_bytes=1e4)
        assert bool((got == ref).all())


def test_chunked_identity_kernel_equals_occ():
    occ, ker = _case((16, 16, 16), (16, 16, 16), seed=5)
    ref = _scipy_feasible_mask(occ, ker)   # valid = (1,1,1)
    got = chunked_feasible_mask(_scipy_feasible_mask, occ, ker, budget_bytes=1e3)
    assert got.shape == (1, 1, 1)
    assert bool((got == ref).all())


def test_chunked_identity_single_overlap():
    # tek-voxel cakisma karari: C=1.0 hucresi infeasible kalmali
    occ = np.zeros((30, 30, 30), dtype=bool)
    occ[10, 10, 10] = True
    ker = np.zeros((5, 5, 5), dtype=bool)
    ker[2, 2, 2] = True
    ref = _scipy_feasible_mask(occ, ker)
    got = chunked_feasible_mask(_scipy_feasible_mask, occ, ker, budget_bytes=1e3)
    assert int((~got).sum()) == 1
    assert bool((got == ref).all())


def test_blb_same_with_tiny_budget():
    # entegrasyon: dilimli fn blb_xybbox icinde ayni BLB pozisyonunu vermeli
    occ, ker = _case((40, 40, 80), (12, 9, 6), density=0.35, seed=11)
    ref = blb_xybbox(occ, ker, _scipy_feasible_mask)
    kucuk = lambda o, g: chunked_feasible_mask(_scipy_feasible_mask, o, g, budget_bytes=5e4)
    got = blb_xybbox(occ, ker, kucuk)
    assert got == ref


# ----------------------------------------------------------------- GPU ----

@pytest.mark.skipif(probe_cupy() is None, reason="cupy/GPU yok")
def test_gpu_conv_valid_chunked_identity():
    from src.nesting3d.fft_backend import gpu_conv_valid_chunked
    cp = probe_cupy()
    occ, ker = _case((36, 36, 48), (10, 8, 5), seed=13)
    ref = _scipy_feasible_mask(occ, ker)
    g_occ = cp.asarray(occ)
    g_flip = cp.asarray(ker[::-1, ::-1, ::-1], dtype=cp.float64)
    # dilimsiz (buyuk butce) + dilimli (minik butce) ikisi de birebir
    for budget in (1 << 30, 1e5):
        got = cp.asnumpy(gpu_conv_valid_chunked(cp, g_occ, g_flip, ker.shape,
                                                budget_bytes=budget))
        assert got.shape == ref.shape
        assert bool((got == ref).all())
