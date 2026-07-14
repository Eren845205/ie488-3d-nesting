"""Sentetik cogaltma jeneratorleri (01_VERI §6): repeat_rod_mix + perturb."""
from __future__ import annotations

from src.nesting3d.instances.synthetic import perturb_instance, repeat_rod_mix


def test_repeat_rod_mix_anatomisi():
    i = repeat_rod_mix(n_rod_models=2, qty_per_rod=40, n_boxes=8, seed=3)
    assert len(i.parts) == 10
    assert sum(p.qty for p in i.parts) == 88          # 2x40 + 8x1
    rodlar = [p for p in i.parts if p.qty > 1]
    assert all(p.height_mm > 4 * max(p.width_mm, p.depth_mm) for p in rodlar)
    assert i.meta["family"] == "repeat_rod_mix"


def test_repeat_rod_mix_deterministik():
    a, b = repeat_rod_mix(seed=5), repeat_rod_mix(seed=5)
    assert [(p.qty, p.width_mm, p.height_mm) for p in a.parts] == \
           [(p.qty, p.width_mm, p.height_mm) for p in b.parts]


def test_perturb_sinirlar_ve_determinizm():
    baz = repeat_rod_mix(seed=1)
    v1 = perturb_instance(baz, seed=7)
    v2 = perturb_instance(baz, seed=7)
    assert [(p.qty, p.width_mm) for p in v1.parts] == \
           [(p.qty, p.width_mm) for p in v2.parts]
    for orij, yeni in zip(baz.parts, v1.parts):
        assert yeni.qty >= 1
        assert abs(yeni.qty - orij.qty) <= max(1, round(orij.qty * 0.30) + 1)
        oran = yeni.width_mm / orij.width_mm
        assert 0.9 - 1e-9 <= oran <= 1.1 + 1e-9
        assert yeni.id.endswith("_p7")
    assert v1.meta["source"] == "perturb(repeat_rod_mix)"
