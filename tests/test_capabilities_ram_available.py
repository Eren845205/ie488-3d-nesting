"""Tests for capabilities.py RAM guard [#23] — ayri ram_available_bytes alani.

Kabul kriterleri:
  1. Capabilities'e ram_available_bytes alani eklendi; mevcut ram_bytes (TOPLAM) korunur.
  2. _ram_available_bytes() None veya pozitif int dondurur (alinamazsa None = konservatif).
  3. available <= total fiziksel degismezi (ikisi de olculuyse).
  4. Geriye uyum: Capabilities ram_available_bytes verilmeden construct edilebilir (default None).
  5. summary() halen ram bilgisini tasir + patlamaz.
"""
from __future__ import annotations

from src.nesting3d.capabilities import (
    Capabilities,
    probe_capabilities,
    _ram_available_bytes,
    _ram_bytes,
)


def test_probe_has_ram_available_field():
    caps = probe_capabilities(refresh=True)
    assert hasattr(caps, "ram_available_bytes")
    # total semantigi KORUNUR
    assert isinstance(caps.ram_bytes, int) and caps.ram_bytes > 0


def test_ram_available_none_or_positive():
    v = _ram_available_bytes()
    assert v is None or (isinstance(v, int) and v > 0)


def test_available_leq_total_when_both_measured():
    caps = probe_capabilities(refresh=True)
    if caps.ram_available_bytes is not None:
        assert caps.ram_available_bytes <= caps.ram_bytes


def test_capabilities_backward_compat_default_none():
    # ram_available_bytes verilmeden construct (scripts/c3_backend.py:262 gibi eski cagrilar)
    caps = Capabilities(cpu_count=4, ram_bytes=8 * 10 ** 9, gpu=False, gpu_fp64=False,
                        fast_fft=False, fast_name=None, slurm=False)
    assert caps.ram_available_bytes is None


def test_total_ram_helper_still_total():
    # _ram_bytes toplam semantigini korur (available'dan >= olmali normalde)
    total = _ram_bytes()
    assert isinstance(total, int) and total > 0


def test_summary_contains_ram_and_does_not_raise():
    caps = probe_capabilities(refresh=True)
    s = caps.summary()
    assert "ram=" in s
    assert isinstance(s, str) and s.isascii()
