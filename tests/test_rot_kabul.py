"""Rot-kabul katmani — kilit reddi yerine rot-sokum sorgusu (hoca 2026-07-14).

Hoca kriteri: gercek red sebebi yalniz yapisma + CIKARILAMAYAN ic-ice;
"zor cikan ama cikabilen" ihmal edilebilir. Kabul kriterleri:

  1. uretim_r11(rot_kabul=False, default) BIT-OZDES: kilit artisi -> None.
  2. uretim_r11(rot_kabul=True): kilit artisi + rot kilit=0 -> sokum-planli
     KABUL (dict'te sokum_planli/rot_kilit/rot_cert); rot kilit>0 -> None;
     rot denetimi exception -> None (tek-tarafli sozlesme bozulmaz).
  3. Kilit artmadiysa rot denetimi HIC cagrilmaz (maliyet: K-42 dersi).
  4. solve_nfv_kalite(rot_kabul=...): False -> tel'de anahtar yok + eski akis;
     True + ham kilitli + rot kilit=0 -> guard ATLANIR (vergi odenmez), ham
     sokum-planli secilir; rot kilit>0 / hata / kilit-bilinmiyor -> guard eski
     gibi kosulur; "auto" -> parca tavani ustunde atlanir (iz birakir).
  5. check_separability_rot erode_clearance_vox'u int kabul eder (K-52 dersi:
     ciplak 2, _ensure_eroded unpack'inde TypeError'du -> normalize edilir).
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pytest
import trimesh

from src.nesting3d.continuous_settle import kilit_rot_meshes, uretim_r11
from src.nesting3d.nfv_solve import R11_AUTO_PARCA_TAVANI, solve_nfv_kalite
from src.nesting3d.rotation_extract import (RotSeparabilityReport,
                                            check_separability_rot)


def _box(w, d, h, at=(0.0, 0.0, 0.0)):
    m = trimesh.creation.box(extents=[w, d, h])
    m.apply_translation([w / 2 + at[0], d / 2 + at[1], h / 2 + at[2]])
    return m


def _kule():
    """Kazancli sahne (test_r11_uretim ile ayni): 3.5mm bosluklar dusebilir."""
    return [_box(20, 20, 8, at=(0, 0, 0)),
            _box(20, 20, 8, at=(0, 0, 11.5)),
            _box(20, 20, 8, at=(0, 0, 23.0))]


def _kilit_artar():
    """Sayac-tabanli sahte kilit: pre=0 (ilk cagri), post=1 (ikinci) -> artis."""
    sayac = {"n": 0}

    def f(meshes):
        sayac["n"] += 1
        return 0 if sayac["n"] == 1 else 1

    return f


def _boom(*a, **k):
    raise AssertionError("bu yol cagrilmamaliydi")


# ---------- uretim_r11 katmani ----------

def test_r11_kilit_artisi_rot_kapali_none():
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, _kilit_fn=_kilit_artar(),
                   _rot_fn=_boom)  # rot_kabul default False -> rot sorulmaz
    assert r is None


def test_r11_rot_kabul_go_sokum_planli():
    rot = NS(n_locked=0, certificates={"m1": "sert"})
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=lambda ms: rot)
    assert r is not None
    assert r["sokum_planli"] is True
    assert r["rot_kilit"] == 0
    assert r["rot_cert"] == 1
    assert r["kilit_pre"] == 0 and r["kilit_post"] == 1
    assert r["kazanc_mm"] > 0.5
    assert r["min_clearance_mm"] >= 2.0


def test_r11_rot_kilitli_none():
    rot = NS(n_locked=2, certificates={})
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=lambda ms: rot)
    assert r is None


def test_r11_rot_hata_none():
    def patlar(ms):
        raise RuntimeError("rot denetimi kurulamadi")

    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True,
                   _kilit_fn=_kilit_artar(), _rot_fn=patlar)
    assert r is None


def test_r11_kilit_artmadiysa_rot_cagrilmaz():
    # gercek kilit fonksiyonu (kule 0->0) + _boom: rot yoluna hic girilmemeli
    r = uretim_r11(_kule(), clearance_mm=2.0, samples_kompakt=3000,
                   samples_dogrula=3000, rot_kabul=True, _rot_fn=_boom)
    assert r is not None  # normal kabul
    assert "sokum_planli" not in r


# ---------- solve_nfv_kalite katmani ----------

def _ham(h=100.0, n=4):
    return NS(height_mm=h, n_placed=n, placements=list(range(n)),
              fine_voxel_parts={}, fine_pitch=2.0)


def test_kalite_rot_kabul_go_guard_atlanir():
    ham = _ham()

    def solve(inst, **kw):
        assert "exit_guard" not in kw, "guard kosulmamaliydi"
        return ham

    res, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=lambda r: NS(n_locked=0, certificates={"a": 1, "b": 2}))
    assert res is ham
    assert tel["secilen"] == "ham"
    assert tel["guard_kosuldu"] is False
    assert tel["ham_n_locked"] == 3
    assert tel["rot_kabul"] == {"uygulandi": True, "rot_kilit": 0, "cert": 2}


def test_kalite_rot_kilitli_guard_kosulur():
    ham, guard = _ham(100.0), _ham(110.0)

    def solve(inst, **kw):
        return guard if kw.get("exit_guard") else ham

    res, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=lambda r: NS(n_locked=1, certificates={}))
    assert tel["guard_kosuldu"] is True
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"] == "rot_kilitli"
    assert tel["rot_kabul"]["rot_kilit"] == 1
    assert res is ham  # ikisi de kilitli -> alcak olan


def test_kalite_rot_auto_parca_tavani():
    ham = _ham(n=R11_AUTO_PARCA_TAVANI + 1)

    def solve(inst, **kw):
        return ham

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul="auto", _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3), _check_rot=_boom)
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"] == "parca_tavani"
    assert tel["guard_kosuldu"] is True


def test_kalite_rot_false_bit_ozdes():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        _solve=solve, _check_5dir=lambda p, v: NS(n_locked=3),
        _check_rot=_boom)  # rot_kabul default False
    assert "rot_kabul" not in tel
    assert tel["guard_kosuldu"] is True


def test_kalite_rot_hata_guard_kosulur():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    def patlar(r):
        raise RuntimeError("rot kurulamadi")

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=3), _check_rot=patlar)
    assert tel["rot_kabul"]["uygulandi"] is False
    assert tel["rot_kabul"]["neden"].startswith("hata:")
    assert tel["guard_kosuldu"] is True


def test_kalite_kilit_bilinmiyorsa_rot_denenmez():
    ham = _ham()

    def solve(inst, **kw):
        return ham

    def kilit_patlar(p, v):
        raise RuntimeError("denetim kurulamadi")

    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve, _check_5dir=kilit_patlar,
        _check_rot=_boom)
    assert "rot_kabul" not in tel  # kilit sayisi bilinmiyor -> rot sorulmaz
    assert tel["guard_kosuldu"] is True


# ---------- kutuphane katmani ----------

def _vox(grid):
    return NS(orientations=[NS(grid=np.asarray(grid, dtype=bool))])


def test_check_rot_int_erode_normalize():
    # kapali kafes (7^3, 3^3 ic bosluk) + iceride 3^3 kup: ikisi de 5-yon
    # kilitli -> rot asamasi (_ensure_eroded unpack yolu) KESIN kosulur.
    kafes = np.ones((7, 7, 7), bool)
    kafes[2:5, 2:5, 2:5] = False
    kup = np.ones((3, 3, 3), bool)
    parts = {"kafes": _vox(kafes), "kup": _vox(kup)}
    pls = [NS(part_id="kafes", orientation_idx=0, x=0, y=0, z=0),
           NS(part_id="kup", orientation_idx=0, x=2, y=2, z=2)]
    rapor = check_separability_rot(pls, parts, max_grid_vox=50,
                                   sure_butcesi_s=30.0,
                                   erode_clearance_vox=1)  # K-52 dersi: int
    assert isinstance(rapor, RotSeparabilityReport)
    assert rapor.n_parts == 2
    # rot asamasinin (dolayisiyla _ensure_eroded unpack yolunun) gercekten
    # kosuldugunun kaniti: sertifika veya fail-telemetri uretilmis olmali.
    # (normalize oncesi bu cagri TypeError atardi.)
    assert rapor.certificates or rapor.fail_telemetri


def test_kilit_rot_meshes_serbest_sahne_deterministik():
    sahne = [_box(20, 20, 10, at=(0, 0, 0)), _box(20, 20, 10, at=(30, 0, 0))]
    r1 = kilit_rot_meshes(sahne)
    r2 = kilit_rot_meshes(sahne)
    assert r1.n_locked == r2.n_locked == 0
    assert r1.n_parts == 2
