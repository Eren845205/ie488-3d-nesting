"""Tests for zaman butcesi [#22] — decode / best_decode / solve_nfv opsiyonel time_budget_sec.

Kabul kriterleri:
  1. time_budget_sec=None (default) -> DAVRANIS AYNEN (mevcut cagrilarla birebir sonuc).
  2. Cok buyuk butce -> tam sonuc (erken kesme yok), None ile birebir.
  3. Butce asiminda TEMIZ dusus: o ana kadarki kismi sonuc + budget_status/strategy izi.
  4. Kismi sonuc yoksa (butce=0) guvenli istisna DEGIL -> bos partial doner, patlamaz.
  5. solve_nfv butce asiminda hatasiz CoarseToFineResult + reason'da ASCII 'budget_exceeded' notu.
"""
from __future__ import annotations

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.fft_backend import get_backend
from src.nesting3d.parallel_decode import decode, best_decode
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.coarse_to_fine import CoarseToFineResult

PLATE_W = PLATE_D = 100.0
PITCH = 5.0


def _make_instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id="box_a", name="box_a", qty=3, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="box_b", name="box_b", qty=3, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


def _parts():
    parts = to_voxel_parts(_make_instance(), PITCH, n_orientations=2, margin=1)
    nx, ny = int(PLATE_W // PITCH), int(PLATE_D // PITCH)
    return parts, nx, ny


# --- 1/2. default None ve buyuk butce = birebir mevcut davranis ---

def test_decode_none_budget_identical_to_baseline():
    parts, nx, ny = _parts()
    fm, _ = get_backend("scipy")
    base_h, base_p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                            return_placements=True)
    h, p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                  return_placements=True, time_budget_sec=None)
    assert h == base_h and p == base_p


def test_decode_large_budget_full_result():
    parts, nx, ny = _parts()
    fm, _ = get_backend("scipy")
    base_h, base_p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                            return_placements=True)
    status = {}
    h, p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                  return_placements=True, time_budget_sec=1e9, budget_status=status)
    assert h == base_h and p == base_p
    assert not status.get("budget_exceeded")


# --- 3/4. butce asimi -> temiz kismi dusus ---

def test_decode_zero_budget_clean_partial():
    parts, nx, ny = _parts()
    fm, _ = get_backend("scipy")
    full_h, full_p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                            return_placements=True)
    status = {}
    h, p = decode(parts, nx, ny, feasible_mask=fm, parallel=False, pitch=PITCH,
                  return_placements=True, time_budget_sec=0.0, budget_status=status)
    assert status.get("budget_exceeded") is True
    assert len(p) < len(full_p)  # erken kesildi (kismi/bos)
    assert isinstance(h, float)  # patlamadan doner


def test_best_decode_default_no_budget_marker():
    parts, nx, ny = _parts()
    h, raw, strat = best_decode(parts, nx, ny, pitch=PITCH, force="cpu-kolA")
    assert "budget_exceeded" not in strat
    assert strat == "cpu-kolA"


def test_best_decode_zero_budget_marks_strategy():
    parts, nx, ny = _parts()
    h, raw, strat = best_decode(parts, nx, ny, pitch=PITCH, force="cpu-kolA",
                                time_budget_sec=0.0)
    assert "budget_exceeded" in strat
    assert strat.isascii()
    # kismi/bos ama patlamadi, raw liste
    assert isinstance(raw, list)


# --- 5. solve_nfv ---

def test_solve_nfv_default_no_budget_note():
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=PITCH, n_orientations=2, force="cpu-kolA")
    assert isinstance(r, CoarseToFineResult)
    assert "budget_exceeded" not in r.adaptive_reason


def test_solve_nfv_zero_budget_clean_descent():
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=PITCH, n_orientations=2, force="cpu-kolA",
                  fine_settle=False, time_budget_sec=0.0)
    assert isinstance(r, CoarseToFineResult)  # istisna DEGIL, temiz dusus
    assert "budget_exceeded" in r.adaptive_reason
    assert r.adaptive_reason.isascii()


def test_solve_nfv_default_settle_budget_exceeded_skips_settle():
    # default fine_settle=True + butce asimi: settle ATLANMALI (decode'un kestigi parcalari geri
    # getirmesin). reason ASCII 'settle skipped (budget)' + 'budget_exceeded' tasimali; n_placed
    # placements ile CELISKISIZ (settle geri-getirme yok) + result pitch coarse'ta kalir (fine'a inmez).
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=PITCH, n_orientations=2, force="cpu-kolA",
                  time_budget_sec=0.0)  # fine_settle default True
    assert isinstance(r, CoarseToFineResult)  # istisna DEGIL, temiz dusus
    assert r.adaptive_reason.isascii()
    assert "budget_exceeded" in r.adaptive_reason
    assert "settle skipped (budget)" in r.adaptive_reason
    assert r.fine_pitch == PITCH        # settle atlandi -> fine pitch'e inmedi
    assert r.n_placed == len(r.placements)  # reason/n_placed tutarli
