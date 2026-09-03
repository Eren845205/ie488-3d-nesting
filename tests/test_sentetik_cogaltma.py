"""Sentetik cogaltma jeneratorleri (01_VERI §6): repeat_rod_mix + perturb."""
from __future__ import annotations

from src.nesting3d.instances.format import ContainerSpec
from src.nesting3d.instances.synthetic import (
    mass_plate_rod_mix,
    perturb_instance,
    repeat_rod_mix,
)


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


# ---------------------------------------------------------------------------
# mass_plate_rod_mix (M3 / STRATEJI ML_YENIDEN_YAPILANMA_PLANI §2.3 —
# K-65 dagilim smoke prototipinin kalici jeneratoru)
# ---------------------------------------------------------------------------

def test_mass_plate_rod_mix_deterministik():
    a = mass_plate_rod_mix(seed=11)
    b = mass_plate_rod_mix(seed=11)
    assert len(a.parts) == len(b.parts)
    assert [(p.qty, p.width_mm, p.depth_mm, p.height_mm) for p in a.parts] == \
           [(p.qty, p.width_mm, p.depth_mm, p.height_mm) for p in b.parts]
    assert a.meta == b.meta


def test_mass_plate_rod_mix_farkli_seed_farkli_boyut():
    a = mass_plate_rod_mix(seed=1)
    b = mass_plate_rod_mix(seed=2)
    dims_a = [(p.width_mm, p.depth_mm, p.height_mm) for p in a.parts]
    dims_b = [(p.width_mm, p.depth_mm, p.height_mm) for p in b.parts]
    assert dims_a != dims_b


def test_mass_plate_rod_mix_plaka_asan_cubuk_garanti():
    cnt = ContainerSpec(width_mm=335.0, depth_mm=335.0, height_mm=None)
    taban = max(cnt.width_mm, cnt.depth_mm)
    inst = mass_plate_rod_mix(n_rod_models=3, container=cnt, seed=4)
    cubuklar = [p for p in inst.parts if p.id.startswith("mprm_rod_")]
    assert len(cubuklar) == 3
    for p in cubuklar:
        dims = sorted((float(p.width_mm), float(p.depth_mm), float(p.height_mm)))
        # en buyuk boyut (uzunluk) konteynerin max(w,d) tabanini asmali —
        # duz-yatista sigmama garantisi (K-65 tetiginin bagimsiz beklentisi)
        assert dims[2] > taban


def test_mass_plate_rod_mix_yuksek_adet():
    inst = mass_plate_rod_mix(n_plate_models=2, qty_per_plate=300, seed=6)
    plaka_toplam = sum(p.qty for p in inst.parts if p.id.startswith("mprm_plate_"))
    assert plaka_toplam == 600


def test_mass_plate_rod_mix_ince_plaka_baskinligi():
    inst = mass_plate_rod_mix(
        n_plate_models=2, qty_per_plate=300,
        n_rod_models=3, qty_per_rod=3, seed=8,
    )
    plaka_toplam = sum(p.qty for p in inst.parts if p.id.startswith("mprm_plate_"))
    cubuk_toplam = sum(p.qty for p in inst.parts if p.id.startswith("mprm_rod_"))
    assert plaka_toplam > 20 * cubuk_toplam
    # az sayida model, yuksek toplam adet -> kitle homojen
    assert len([p for p in inst.parts if p.id.startswith("mprm_plate_")]) \
        == 2


def test_mass_plate_rod_mix_plaka_ince():
    inst = mass_plate_rod_mix(
        n_plate_models=3,
        plate_xy_min=40.0, plate_xy_max=100.0,
        plate_thickness_min=3.0, plate_thickness_max=8.0,
        seed=9,
    )
    plakalar = [p for p in inst.parts if p.id.startswith("mprm_plate_")]
    assert len(plakalar) == 3
    for p in plakalar:
        ratio = p.height_mm / max(p.width_mm, p.depth_mm)
        assert ratio < 0.25, f"Plate not thin: ratio={ratio:.3f}"


def test_mass_plate_rod_mix_meta_family():
    inst = mass_plate_rod_mix(seed=0)
    assert inst.meta["family"] == "mass_plate_rod_mix"


def test_mass_plate_rod_mix_default_container_open_dimension():
    inst = mass_plate_rod_mix(seed=0)
    assert inst.container.height_mm is None
