# -*- coding: utf-8 -*-
"""test_kanopi_zincir.py — K-62 kablo modülü (kanopi_zincir) testleri.

Kapsam: geometrik tetik (ateşler / ateşlemez / no-go yoksa None),
asan_tipler birimi, zincirin tetiksiz instance'ta referansla bire birliği
(bit-özdeşlik yapısal kanıtı) ve tek-taraflılık sözleşmesi (zincir referanstan
kötü sonuç DÖNDÜREMEZ).
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)
from src.nesting3d.instances.synthetic import _cerceve_mesh
from src.nesting3d.kanopi_zincir import (
    asan_tipler,
    kanopi_adayi,
    kanopi_pin,
    kanopi_zinciri_coz,
)

PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 33.0))
CNT = ContainerSpec(width_mm=335.0, depth_mm=335.0, height_mm=None)


def _kutu(pid, w, d, h, qty=1):
    return PartSpec(id=pid, name=pid, qty=qty, source="box",
                    width_mm=w, depth_mm=d, height_mm=h)


def _delikli_cerceve_part(tmp_path, fw=210.0, fd=210.0, t=6.0, delik=70.0):
    """2x2 delikli kare çerçeve (alan_oran ~0.39, doluluk ~0.56 — tetik
    ateşler; fd<=302 -> no-go'dan dy ile kaçış trivial-fizibil)."""
    g = (fw - 2 * delik) / 3.0
    delikler = [(g + i * (delik + g), g + j * (delik + g),
                 g + i * (delik + g) + delik, g + j * (delik + g) + delik)
                for i in range(2) for j in range(2)]
    mesh = _cerceve_mesh(fw, fd, t, delikler)
    yol = tmp_path / "cerceve.stl"
    mesh.export(yol)
    return PartSpec(id="frame", name="frame", qty=1, source="stl",
                    stl_path=str(yol))


def _kati_plaka_part(tmp_path, fw=220.0, fd=220.0, t=6.0):
    mesh = _cerceve_mesh(fw, fd, t, [])  # deliksiz katı plaka
    yol = tmp_path / "kati.stl"
    mesh.export(yol)
    return PartSpec(id="plate", name="plate", qty=1, source="stl",
                    stl_path=str(yol))


# ---------------------------------------------------------------- tetik ----

def test_tetik_delikli_cercevede_atesler(tmp_path):
    inst = NestingInstance(container=CNT, parts=[
        _delikli_cerceve_part(tmp_path), _kutu("k1", 20, 20, 50)])
    aday = kanopi_adayi(inst, *PLATE, NOGO)
    assert aday is not None
    assert aday["part"].name == "frame"
    assert aday["alan_oran"] >= 0.35
    assert aday["fiz"]["doluluk"] < 0.6
    assert aday["fiz"]["pozlar"]


def test_tetik_kati_plakada_ateslemez(tmp_path):
    inst = NestingInstance(container=CNT, parts=[
        _kati_plaka_part(tmp_path), _kutu("k1", 20, 20, 50)])
    assert kanopi_adayi(inst, *PLATE, NOGO) is None  # doluluk ~1.0


def test_tetik_nogo_yoksa_none(tmp_path):
    inst = NestingInstance(container=CNT, parts=[
        _delikli_cerceve_part(tmp_path)])
    assert kanopi_adayi(inst, *PLATE, None) is None


def test_tetik_kucuk_parcalarda_ateslemez():
    inst = NestingInstance(container=CNT, parts=[
        _kutu("k1", 30, 30, 20), _kutu("k2", 40, 25, 15)])
    assert kanopi_adayi(inst, *PLATE, NOGO) is None  # stl yok + alan küçük


def test_kanopi_pin_sekli(tmp_path):
    inst = NestingInstance(container=CNT, parts=[
        _delikli_cerceve_part(tmp_path)])
    aday = kanopi_adayi(inst, *PLATE, NOGO)
    pin = kanopi_pin(aday, 42.0)
    assert pin["ad"] == "frame"
    assert pin["z_mm"] == 42.0
    assert np.asarray(pin["rot"]).shape == (4, 4)


# --------------------------------------------------------- asan_tipler ----

def _fake_res(yerlesimler, pitch=1.0):
    """yerlesimler: [(ad, z_vox, h_vox)] -> sahte CoarseToFineResult."""
    vps = {}
    pls = []
    for i, (ad, z, h) in enumerate(yerlesimler):
        grid = np.ones((2, 2, int(h)), dtype=bool)
        vps[f"p{i}"] = SimpleNamespace(
            id=f"p{i}", name=ad,
            orientations=[SimpleNamespace(grid=grid)])
        pls.append(SimpleNamespace(part_id=f"p{i}", orientation_idx=0,
                                   x=0, y=0, z=int(z)))
    return SimpleNamespace(placements=pls, fine_voxel_parts=vps,
                           fine_pitch=pitch)


def test_asan_tipler_esik_ve_kanopi_haric():
    res = _fake_res([("kanopi", 60, 10),   # kanopi kendisi -> hariç
                     ("kule", 0, 90),      # tepe 90 > 70+1 -> aşan
                     ("alcak", 0, 50)])    # tepe 50 -> aşmaz
    asan = asan_tipler(res, "kanopi", 70.0)
    assert set(asan) == {"kule"}
    assert asan["kule"] == pytest.approx(90.0)


def test_asan_tipler_max_tepe_toplanir():
    res = _fake_res([("kule", 0, 80), ("kule", 0, 95)])
    asan = asan_tipler(res, "kanopi", 70.0)
    assert asan["kule"] == pytest.approx(95.0)


# ------------------------------------------------------------- zincir -----

def test_zincir_tetiksiz_referans_birebir():
    """stl'siz set: tetik yapısal olarak ateşleyemez -> referans cozum
    AYNI NESNE olarak doner (bit-ozdeslik yapısal kanıtı)."""
    inst = NestingInstance(container=CNT, parts=[
        _kutu("k1", 40, 40, 20), _kutu("k2", 30, 50, 25),
        _kutu("k3", 25, 25, 30)])
    res, tel = kanopi_zinciri_coz(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, clearance_mm=2.0, seed=42,
        fine_pitch=2.0)
    assert tel["tetik"] is False
    assert len(tel["adimlar"]) == 1  # yalnız ref koşuldu
    assert int(res.n_placed) == 3


def test_zincir_nogo_yoksa_referans_birebir(tmp_path):
    inst = NestingInstance(container=CNT, parts=[
        _delikli_cerceve_part(tmp_path), _kutu("k1", 20, 20, 50)])
    res, tel = kanopi_zinciri_coz(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=None, clearance_mm=2.0, seed=42,
        fine_pitch=2.0)
    assert tel["tetik"] is False


def test_zincir_ref_eksikken_pin_denenir_ve_tamlik_kazanir(tmp_path, monkeypatch):
    """Kapı-1 dersi (2026-08-05): pinsiz ref tam yerleşemeyebilir (plan1'de
    111/112 — bbox kapısı kanopi parçayı dışarıda bırakır). Zincir yine de
    denenmeli ve kıyas anahtarı (n_placed, sonra h) olmalı: 6/6 yerleştiren
    pin, 5/6'lık daha alçak ref'i YENER."""
    import src.nesting3d.nfv_solve as nfv

    def _sahte_res(n, h):
        return SimpleNamespace(height_mm=h, n_placed=n, placements=[],
                               fine_voxel_parts={}, fine_pitch=1.0)

    cagrilar = []

    def sahte_solve(inst, **kw):
        pinli = kw.get("pinned_placements") is not None
        cagrilar.append("pin" if pinli else "ref")
        return _sahte_res(6, 120.0) if pinli else _sahte_res(5, 100.0)

    monkeypatch.setattr(nfv, "solve_nfv", sahte_solve)
    inst = NestingInstance(container=CNT, parts=[
        _delikli_cerceve_part(tmp_path), _kutu("k1", 20, 20, 50, qty=5)])
    res, tel = kanopi_zinciri_coz(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, clearance_mm=2.0, seed=42, fine_pitch=2.0)
    assert tel["tetik"] is True
    assert "pin" in cagrilar            # ref eksik olsa da zincir denendi
    assert int(res.n_placed) == 6       # tamlık yükseklikten önce gelir
    assert tel["etiket"] == "pin"


# ------------------------------------------------- uretim kablosu (v18) ----
# kanopi_zinciri_uretim: zincir + A2 legalite + geri-düşüş (k62_kapi v3
# deseninin src karşılığı; Eren kararı 2026-08-15 — kalite moduna bağlanır).

def _u_res(n, h, etiket="x"):
    return SimpleNamespace(height_mm=h, n_placed=n, placements=[],
                           fine_voxel_parts={}, fine_pitch=1.0,
                           _etiket=etiket)


def _u_aday():
    import trimesh
    mesh = trimesh.creation.box(extents=(210.0, 210.0, 6.0))
    return {"part": SimpleNamespace(name="frame"), "mesh": mesh,
            "fiz": {"pozlar": [{"rot_deg": 0.0, "dx_mm": 0.0, "dy_mm": 0.0}],
                    "doluluk": 0.5, "duz_kalinlik_mm": 6.0},
            "alan_oran": 0.4}


def test_uretim_tetiksiz_ref_ayni_nesne(monkeypatch):
    import src.nesting3d.kanopi_zincir as kz

    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: None)
    ref = _u_res(5, 100.0, "ref")
    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref)
    assert res is ref
    assert tel["tetik"] is False
    assert tel["secilen"] == "ref"


def test_uretim_kazanan_legal_ve_iyi_kabul(monkeypatch):
    import src.nesting3d.kanopi_zincir as kz

    ref = _u_res(5, 140.0, "ref")
    kazanan = _u_res(5, 129.0, "kanopi")
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: _u_aday())
    monkeypatch.setattr(kz, "kanopi_zinciri_coz",
                        lambda *a, **k: (kazanan, {"tetik": True,
                                                   "etiket": "pin",
                                                   "adimlar": [],
                                                   "z_secilen": 60.0}))
    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref,
        _a2=lambda r: {"min_clearance_mm": 2.4, "kilit_5yon": 0,
                       "rot_kilit": None, "rot_cert": None,
                       "sokum_planli": False, "legal": True})
    assert res is kazanan
    assert tel["secilen"] == "kanopi"
    assert tel["kazanc_mm"] == pytest.approx(11.0)


def test_uretim_kazanan_illegal_geri_dusus_legal(monkeypatch):
    """Kapı-v3 deseni: kazanan A2 geçemezse sıradaki aday (yalnız-pin)
    tam-A2 ile denenir; legal bulunursa o döner."""
    import src.nesting3d.kanopi_zincir as kz

    ref = _u_res(5, 140.0, "ref")
    kazanan = _u_res(5, 129.0, "greedy")
    gd = _u_res(5, 135.6, "pin")
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: _u_aday())
    monkeypatch.setattr(kz, "kanopi_zinciri_coz",
                        lambda *a, **k: (kazanan, {"tetik": True,
                                                   "etiket": "greedy",
                                                   "adimlar": [],
                                                   "z_secilen": 60.0,
                                                   "asan_tipler": {"kule": 90.0},
                                                   "rutbeler": {"kule": 0,
                                                                "t2": 1}}))

    def sahte_solve(inst, **kw):
        assert kw.get("pin_3d") is True
        return gd

    def sahte_a2(r):
        legal = r is gd
        return {"min_clearance_mm": 2.1 if legal else 1.96,
                "kilit_5yon": 0, "rot_kilit": None, "rot_cert": None,
                "sokum_planli": False, "legal": legal}

    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref, _a2=sahte_a2, _solve=sahte_solve)
    assert res is gd
    assert tel["secilen"] == "kanopi"
    assert tel["geri_dusus"]  # en az bir geri-düşüş adayı ölçüldü


def test_uretim_hicbiri_legal_degil_ref_doner(monkeypatch):
    import src.nesting3d.kanopi_zincir as kz

    ref = _u_res(5, 140.0, "ref")
    kazanan = _u_res(5, 129.0, "pin")
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: _u_aday())
    monkeypatch.setattr(kz, "kanopi_zinciri_coz",
                        lambda *a, **k: (kazanan, {"tetik": True,
                                                   "etiket": "pin",
                                                   "adimlar": [],
                                                   "z_secilen": 60.0}))
    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref,
        _a2=lambda r: {"min_clearance_mm": 1.9, "kilit_5yon": 3,
                       "rot_kilit": 2, "rot_cert": 0,
                       "sokum_planli": False, "legal": False})
    assert res is ref
    assert tel["secilen"] == "ref"


def test_uretim_zincir_ref_donerse_a2_olculmez(monkeypatch):
    import src.nesting3d.kanopi_zincir as kz

    ref = _u_res(5, 140.0, "ref")
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: _u_aday())
    monkeypatch.setattr(kz, "kanopi_zinciri_coz",
                        lambda *a, **k: (ref, {"tetik": True, "etiket": "ref",
                                               "adimlar": []}))

    def a2_patlar(r):
        raise AssertionError("ref donduyse A2 olculmemeli")

    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref, _a2=a2_patlar)
    assert res is ref
    assert tel["secilen"] == "ref"


def test_uretim_ref_r11_yuksekligiyle_kiyas(monkeypatch):
    """ref'e R11 dz uygulanmışsa kıyas efektif (r11) yükseklikle yapılır:
    kazanan ham ref'ten iyi ama r11-ref'ten kötüyse REF korunur."""
    import src.nesting3d.kanopi_zincir as kz

    ref = _u_res(5, 140.0, "ref")
    kazanan = _u_res(5, 133.0, "pin")
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: _u_aday())
    monkeypatch.setattr(kz, "kanopi_zinciri_coz",
                        lambda *a, **k: (kazanan, {"tetik": True,
                                                   "etiket": "pin",
                                                   "adimlar": [],
                                                   "z_secilen": 60.0}))
    res, tel = kz.kanopi_zinciri_uretim(
        None, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, ref_res=ref, ref_height_mm=131.5,
        _a2=lambda r: {"min_clearance_mm": 2.4, "kilit_5yon": 0,
                       "rot_kilit": None, "rot_cert": None,
                       "sokum_planli": False, "legal": True})
    assert res is ref
    assert tel["secilen"] == "ref"


def test_zincir_tek_tarafli_ve_tam_yerlesim(tmp_path):
    """Tetikli sette zincir referanstan KOTU donemez; sonuç tam yerleşimli.
    (Kazanç garanti edilmez — tek-taraflılık sözleşmesi test edilir.)"""
    parts = [_delikli_cerceve_part(tmp_path),
             _kutu("tw1", 20, 20, 60, qty=2),
             _kutu("tw2", 24, 24, 55),
             _kutu("fl1", 40, 40, 15), _kutu("fl2", 35, 30, 12)]
    inst = NestingInstance(container=CNT, parts=parts)
    n_total = sum(p.qty for p in inst.parts)

    from src.nesting3d.nfv_solve import solve_nfv
    ref = solve_nfv(inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                    fine_pitch=2.0, seed=42, quality="fast",
                    clearance_mm=2.0, no_go_bounds=NOGO)
    res, tel = kanopi_zinciri_coz(
        inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
        no_go_bounds=NOGO, clearance_mm=2.0, seed=42,
        fine_pitch=2.0, ref_res=ref)
    assert tel["tetik"] is True
    assert float(res.height_mm) <= float(ref.height_mm) + 1e-9
    assert int(res.n_placed) == n_total
    assert tel["adimlar"][0]["adim"] == "ref"
