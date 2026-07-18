# -*- coding: utf-8 -*-
"""K-57 süre-kırılım telemetrisi testleri (davranış-nötr zamanlayıcılar).

Kapı süresinin anatomisi için: solve_nfv_kalite tel'ine solve_ham_s /
solve_guard_s / kilit5_s (+ r11/rot_kabul sure_s), evaluate_set dönüşüne
sure_kirilim. Değişmez: alanlar YALNIZ eklenir — mevcut değerler/akış
bit-özdeş (r11 kapalıyken tel'de "r11" anahtarı YOKTUR, aynı kalır).
"""
from __future__ import annotations

from types import SimpleNamespace as NS

from src.nesting3d.nfv_solve import solve_nfv_kalite


def _ham(h=100.0, n=5):
    return NS(height_mm=h, n_placed=n, placements=[], fine_voxel_parts={},
              fine_pitch=2.0)


def test_kalite_tel_solve_ham_ve_kilit5_suresi():
    ham = _ham()
    res, tel = solve_nfv_kalite(
        NS(parts=[]), plate_w_mm=100, plate_d_mm=100,
        _solve=lambda inst, **kw: ham,
        _check_5dir=lambda p, v: NS(n_locked=0))
    assert res is ham
    assert isinstance(tel["solve_ham_s"], float)
    assert isinstance(tel["kilit5_s"], float)
    assert "solve_guard_s" not in tel  # guard kosulmadi
    assert "r11" not in tel            # r11 kapali -> anahtar yok (bit-ozdes)


def test_kalite_tel_guard_suresi():
    ham, guard = _ham(100.0), _ham(90.0)
    res, tel = solve_nfv_kalite(
        NS(parts=[]), plate_w_mm=100, plate_d_mm=100,
        _solve=lambda inst, **kw: guard if kw.get("exit_guard") else ham,
        _check_5dir=lambda p, v: NS(n_locked=3))
    assert tel["guard_kosuldu"] is True
    assert isinstance(tel["solve_guard_s"], float)
    assert isinstance(tel["kilit5_s"], float)


def test_kalite_r11_sure_alani():
    """r11 auto + parca-tavani dali: tel['r11'] yazilir -> sure_s eklenir
    (ucuz yol — gercek R11 kosmaz)."""
    from src.nesting3d.nfv_solve import R11_AUTO_PARCA_TAVANI
    ham = _ham(n=R11_AUTO_PARCA_TAVANI + 1)
    _, tel = solve_nfv_kalite(
        NS(parts=[]), plate_w_mm=100, plate_d_mm=100, r11="auto",
        _solve=lambda inst, **kw: ham,
        _check_5dir=lambda p, v: NS(n_locked=0))
    assert tel["r11"]["uygulandi"] is False
    assert tel["r11"]["neden"] == "parca_tavani"
    assert isinstance(tel["r11"]["sure_s"], float)


def test_kalite_rot_kabul_sure_alani():
    ham = _ham()
    cert = NS(eksen="x", aci_deg=5.0, yon="+z", lift_vox=1)
    _, tel = solve_nfv_kalite(
        NS(parts=[]), plate_w_mm=100, plate_d_mm=100,
        rot_kabul=True,
        _solve=lambda inst, **kw: ham,
        _check_5dir=lambda p, v: NS(n_locked=2),
        _check_rot=lambda r: NS(n_locked=0, certificates={"m0": cert}))
    assert tel["rot_kabul"]["uygulandi"] is True
    assert isinstance(tel["rot_kabul"]["sure_s"], float)


def test_evaluate_set_sure_kirilim(monkeypatch):
    import scripts.eval_gate as eg

    class _R:
        placements = ["pl"]
        fine_voxel_parts = {"k": "vp"}
        fine_pitch = 1.0
        height_mm = 220.7
        n_placed = 588

    monkeypatch.setattr(eg, "_load_instance",
                        lambda name: NS(parts=[NS(qty=588)]))
    monkeypatch.setattr(eg, "_run_champion",
                        lambda name, inst, seed, budget=None,
                        n_orientations=None,
                        extra_rot_overrides=None:
                        (_R(), {"sure_s": 9.9, "solve_ham_s": 7.7,
                                "kilit5_s": 0.5,
                                "r11": {"uygulandi": True, "sure_s": 1.1}}))
    monkeypatch.setattr(eg, "placed_meshes", lambda *a, **k: ["m"])
    monkeypatch.setattr(eg, "min_clearance",
                        lambda m, samples_per_mesh=6000: NS(min_mm=2.1))
    monkeypatch.setattr(eg, "check_placements",
                        lambda p, v: NS(n_locked=0))
    r = eg.evaluate_set("t", 42)
    sk = r["sure_kirilim"]
    assert isinstance(sk["solve_s"], float)
    assert isinstance(sk["clearance_s"], float)
    assert isinstance(sk["kilit_s"], float)
    assert sk["rot_s"] is None            # kilit 0 -> rot denetimi kosmadi
    assert sk["nfv_sure_s"] == 9.9
    assert sk["nfv_solve_ham_s"] == 7.7
    assert sk["r11_s"] == 1.1
    assert sk["rot_kabul_s"] is None
    assert sk["decode_strateji"] is None  # _R'de adaptive_reason yok
