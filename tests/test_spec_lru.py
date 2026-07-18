# -*- coding: utf-8 -*-
"""K-57 SpecLRU testleri (kernel-spektrum onbellegi — GPU'suz mantik)."""
from __future__ import annotations

import numpy as np

from src.nesting3d.fft_backend import SpecLRU


def _arr(mb):
    return np.zeros(int(mb * 2 ** 20), dtype=np.uint8)


def test_put_get_ve_lru_sirasi():
    c = SpecLRU(budget_bytes=10 * 2 ** 20)
    a, b = _arr(4), _arr(4)
    c.put("a", a)
    c.put("b", b)
    assert c.get("a") is a          # get 'a'yi taze yapar
    c.put("c", _arr(4))             # butce asildi -> en eski ('b') duser
    assert c.get("b") is None
    assert c.get("a") is a
    assert c.get("c") is not None


def test_tek_giris_butceyi_asarsa_cachelenmez():
    c = SpecLRU(budget_bytes=2 * 2 ** 20)
    c.put("buyuk", _arr(4))
    assert c.get("buyuk") is None


def test_clear():
    c = SpecLRU(budget_bytes=10 * 2 ** 20)
    c.put("a", _arr(1))
    c.clear()
    assert c.get("a") is None
    assert c._bytes == 0
