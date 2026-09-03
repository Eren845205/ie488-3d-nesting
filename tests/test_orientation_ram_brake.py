"""Tests for nfv_solve.py parca-duyarli oryantasyon emniyet freni [#24].

Kabul kriterleri:
  1. AX24 total>=13GB kapisi KORUNUR (mevcut _quality_max_orientations davranisi birebir).
  2. Yeni _quality_max_decision: (orients|None, reason) dondurur; ayni kapi + opsiyonel fren.
  3. Emniyet freni parca-sayisi + available-RAM + grid'den TUREYEN esikle calisir (sabit sihirli
     sayi yok); fonksiyon parametresiyle override edilebilir (safety_factor / avail_headroom /
     bytes_per_cell).
  4. Fren girdileri verilmezse (None) davranis DEGISMEZ = mevcut uretim yolu.
  5. solve_nfv default (orient_ram_brake=False) davranisi degismez; True + dusuk available -> n=8.
"""
from __future__ import annotations

import pytest

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d import nfv_solve as ns
from src.nesting3d.nfv_solve import (
    _quality_max_orientations,
    _quality_max_decision,
    NFV_AX24,
    NFV_DEFAULT_ORIENTATIONS,
    solve_nfv,
)
from src.nesting3d.capabilities import Capabilities

PLATE_W = PLATE_D = 100.0
FINE_PITCH = 5.0


def _make_instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id="box_a", name="box_a", qty=2, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="box_b", name="box_b", qty=2, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


# --- 1. AX24 kapisi KORUNUR (mevcut ledder) ---

def test_backward_compat_ram_ladder_unchanged():
    assert _quality_max_orientations(4 * 10 ** 9) is None
    assert _quality_max_orientations(16 * 10 ** 9) == NFV_AX24
    assert _quality_max_orientations(64 * 10 ** 9) == NFV_AX24


def test_decision_low_ram_floor():
    orients, reason = _quality_max_decision(4 * 10 ** 9)
    assert orients is None
    assert "guvenli taban" in reason
    assert reason.isascii()


def test_decision_high_ram_no_brake_inputs_gives_ax24():
    orients, reason = _quality_max_decision(16 * 10 ** 9)
    assert orients == NFV_AX24
    assert "AX24" in reason


# --- 2/3. Emniyet freni: turemis esik + override ---

def test_brake_fires_when_estimate_exceeds_available():
    # yuksek total (kapi acik) ama cok dusuk available + buyuk is -> fren.
    orients, reason = _quality_max_decision(
        16 * 10 ** 9,
        n_parts=200, ram_available_bytes=100 * 10 ** 6,  # 0.1GB available
        grid_cells=50_000,
    )
    assert orients is None
    assert "emniyet freni" in reason and "guvenli taban" in reason
    assert reason.isascii()


def test_brake_does_not_fire_when_estimate_fits():
    orients, reason = _quality_max_decision(
        16 * 10 ** 9,
        n_parts=4, ram_available_bytes=8 * 10 ** 9,  # bol available, kucuk is
        grid_cells=48,
    )
    assert orients == NFV_AX24


def test_brake_threshold_is_parameter_overridable():
    # AYNI girdiler; sadece safety_factor degisiyor -> karar degisiyor (turemis esik, sihirli sabit yok)
    kw = dict(n_parts=50, ram_available_bytes=1 * 10 ** 9, grid_cells=20_000)
    lax, _ = _quality_max_decision(16 * 10 ** 9, safety_factor=0.01, **kw)
    strict, _ = _quality_max_decision(16 * 10 ** 9, safety_factor=100.0, **kw)
    assert lax == NFV_AX24
    assert strict is None
    # avail_headroom override de esigi kaydirir
    tight, _ = _quality_max_decision(16 * 10 ** 9, avail_headroom=1e-6,
                                     n_parts=50, ram_available_bytes=1 * 10 ** 9,
                                     grid_cells=20_000)
    assert tight is None


def test_brake_disabled_when_any_input_missing():
    # available yok -> fren kapali -> AX24 (konservatif DEGIL: bilgi eksik, mevcut davranis)
    assert _quality_max_decision(16 * 10 ** 9, n_parts=999, grid_cells=99_999)[0] == NFV_AX24
    assert _quality_max_decision(16 * 10 ** 9, n_parts=999,
                                 ram_available_bytes=1)[0] == NFV_AX24


# --- 5. solve_nfv wiring ---

def _fake_caps(total_bytes, avail_bytes):
    return Capabilities(cpu_count=4, ram_bytes=int(total_bytes), gpu=False, gpu_fp64=False,
                        fast_fft=False, fast_name=None, slurm=False,
                        ram_available_bytes=int(avail_bytes))


def test_solve_default_brake_off_keeps_ax24(monkeypatch):
    # total>=13GB, brake OFF (default) -> AX24 yolu (davranis degismez)
    monkeypatch.setattr(ns, "probe_capabilities",
                        lambda *a, **k: _fake_caps(16 * 10 ** 9, 50 * 10 ** 6))
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, quality="max", force="cpu-kolA", fine_settle=False)
    assert "quality=max" in r.adaptive_reason
    assert "AX24" in r.adaptive_reason


def test_solve_brake_on_low_available_drops_to_floor(monkeypatch):
    # total>=13GB (kapi acik) ama available cok dusuk + orient_ram_brake=True -> n=8 fren
    monkeypatch.setattr(ns, "probe_capabilities",
                        lambda *a, **k: _fake_caps(16 * 10 ** 9, 50 * 10 ** 3))  # 0.05MB
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, quality="max", force="cpu-kolA",
                  fine_settle=False, orient_ram_brake=True)
    assert "quality=max" in r.adaptive_reason
    assert "emniyet freni" in r.adaptive_reason
    assert "guvenli taban" in r.adaptive_reason
    # fren n=8 tabana dustu -> AX24 (24) oryantasyon yok
    part = next(iter(r.fine_voxel_parts.values()))
    assert len(part.orientations) == NFV_DEFAULT_ORIENTATIONS
