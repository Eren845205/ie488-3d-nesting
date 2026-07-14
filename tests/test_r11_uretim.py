"""R11 uretim kablolamasi — uretim_r11 (tek-tarafli post-pass) + kalite entegrasyonu.

Kabul kriterleri:
  1. uretim_r11: kompakt+rafine+kapilar; kazancli+legal ise dict (dz, height,
     clear, kilit, kazanc), degilse None (TEK-TARAFLI — cagiran eski sonucu korur).
  2. kilit artarsa None (d4 dersi, K-50).
  3. kilit_5yon_meshes src'de ve deterministik.
  4. solve_nfv_kalite(r11=...): False -> tel'de r11 yok + davranis BIREBIR;
     True -> tel["r11"] dolu (kazanc varsa) veya {"uygulandi": False, "neden"};
     "auto" -> parca tavani ustunde ATLANIR (neden="parca_tavani").
"""
from __future__ import annotations

import trimesh

from src.nesting3d.continuous_settle import kilit_5yon_meshes, uretim_r11
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.nfv_solve import R11_AUTO_PARCA_TAVANI, solve_nfv_kalite


def _box(w, d, h, at=(0.0, 0.0, 0.0)):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2 + at[0], d / 2 + at[1], h / 2 + at[2]])
    return m


def test_uretim_r11_kazancli_kule():
    kule = [_box(20, 20, 8, at=(0, 0, 0)),
            _box(20, 20, 8, at=(0, 0, 11.5)),     # 3.5 bosluk -> dusebilir
            _box(20, 20, 8, at=(0, 0, 23.0))]
    r = uretim_r11(kule, clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000)
    assert r is not None
    assert r["height_mm"] < 31.0                   # 31.0'dan asagi indi
    assert r["min_clearance_mm"] >= 2.0
    assert r["kilit_pre"] == r["kilit_post"] == 0
    assert r["kazanc_mm"] > 0.5
    assert len(r["dz"]) == 3


def test_uretim_r11_kazanc_yoksa_none():
    # zaten tam oturmus cift (tam 2.0 bosluk) -> kazanc ~0 -> None
    sahne = [_box(20, 20, 8, at=(0, 0, 0)),
             _box(20, 20, 8, at=(0, 0, 10.0))]
    r = uretim_r11(sahne, clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000)
    assert r is None


def test_kilit_5yon_meshes_deterministik():
    sahne = [_box(20, 20, 10, at=(0, 0, 0)), _box(20, 20, 10, at=(0, 0, 12.5))]
    a = kilit_5yon_meshes(sahne)
    b = kilit_5yon_meshes(sahne)
    assert a == b == 0


def test_kalite_r11_false_bit_ozdes():
    inst = NestingInstance(
        container=ContainerSpec(width_mm=80.0, depth_mm=80.0),
        parts=[PartSpec(id="k", name="k", qty=3, source="box",
                        width_mm=20.0, depth_mm=20.0, height_mm=10.0)])
    r0, t0 = solve_nfv_kalite(inst, plate_w_mm=80.0, plate_d_mm=80.0,
                              clearance_mm=2.0, quality="fast", r11=False)
    assert "r11" not in t0
    r1, t1 = solve_nfv_kalite(inst, plate_w_mm=80.0, plate_d_mm=80.0,
                              clearance_mm=2.0, quality="fast", r11=False)
    assert r0.height_mm == r1.height_mm            # determinizm korunur


def test_kalite_r11_auto_parca_tavani():
    inst = NestingInstance(
        container=ContainerSpec(width_mm=80.0, depth_mm=80.0),
        parts=[PartSpec(id="k", name="k", qty=R11_AUTO_PARCA_TAVANI + 1,
                        source="box", width_mm=6.0, depth_mm=6.0,
                        height_mm=6.0)])
    _, tel = solve_nfv_kalite(inst, plate_w_mm=80.0, plate_d_mm=80.0,
                              clearance_mm=2.0, quality="fast", r11="auto")
    assert tel["r11"]["uygulandi"] is False
    assert tel["r11"]["neden"] == "parca_tavani"


def test_kalite_r11_true_kucuk_sette():
    inst = NestingInstance(
        container=ContainerSpec(width_mm=80.0, depth_mm=80.0),
        parts=[PartSpec(id="k", name="k", qty=4, source="box",
                        width_mm=18.0, depth_mm=18.0, height_mm=12.0)])
    res, tel = solve_nfv_kalite(inst, plate_w_mm=80.0, plate_d_mm=80.0,
                                clearance_mm=2.0, quality="fast", r11=True,
                                r11_samples=3000)
    assert "r11" in tel
    if tel["r11"]["uygulandi"]:
        assert tel["r11"]["height_mm"] <= res.height_mm + 1e-9
        assert tel["r11"]["min_clearance_mm"] >= 2.0
        assert len(tel["r11"]["dz"]) == res.n_placed
    else:
        assert "neden" in tel["r11"]               # durust iz
