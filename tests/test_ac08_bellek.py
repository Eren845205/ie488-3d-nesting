# -*- coding: utf-8 -*-
"""AC-08 bellek hijyeni testleri (cozum plani Paket A1, 2026-08-31).

Kapsam:
  - kanopi_adayi zincir boyunca mesh'leri BIR kez yukler (uretim yolunda
    bugun 2 kez: kanopi_zinciri_uretim + kanopi_zinciri_coz) -> kirmizi.
  - decode_gpu donusunde cupy havuzu ve cuFFT plan cache bosaltilmis olur
    (normal donus + istisna yolu) -> kirmizi (bugun temizlik yok).
GPU yoksa GPU testleri skip (CI/dev makinesi esnekligi); kanopi testi GPU'suz.
"""
from __future__ import annotations

import numpy as np
import pytest

import src.nesting3d.kanopi_zincir as kz


# ---------------------------------------------------------------------------
# 1) kanopi_adayi tek-yukleme (host hijyeni)
# ---------------------------------------------------------------------------

class _P:
    def __init__(self, name):
        self.name = name
        self.qty = 1
        self.stl_path = None  # trimesh.load cagrilmadan sayilacak


def test_uretim_kanopi_adayi_tek_cagri(monkeypatch):
    """kanopi_zinciri_uretim + ic zincir toplam 1 kanopi_adayi taramasi
    yapmali (mesh'ler bir kez yuklenir; bugun 2 -> KIRMIZI)."""
    sayac = {"n": 0}
    aday = {"part": _P("kanopi"), "mesh": object(),
            "fiz": {"doluluk": 0.3, "duz_kalinlik_mm": 5.0,
                    "pozlar": [0]},
            "alan_oran": 0.5}

    def sahte_aday(*a, **k):
        sayac["n"] += 1
        return dict(aday)

    # kalinlik >= h_ref: ic zincirin z-adaylari filtrelenir -> hic solve_nfv
    # kosulmadan ref doner; ama IC ZINCIR kendi kanopi_adayi taramasini yapar.
    aday["fiz"]["duz_kalinlik_mm"] = 200.0
    monkeypatch.setattr(kz, "kanopi_adayi", sahte_aday)

    class _Res:
        height_mm = 100.0
        n_placed = 1
        placements = []
        fine_voxel_parts = {}
        fine_pitch = 2.0

    class _Inst:
        parts = [_P("kanopi")]

    kz.kanopi_zinciri_uretim(_Inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                             no_go_bounds=(0, 10, 0, 10),
                             clearance_mm=2.0, ref_res=_Res())
    assert sayac["n"] == 1, (
        f"kanopi_adayi {sayac['n']} kez cagrildi (mesh'ler {sayac['n']} kez "
        "yuklenir) - beklenen 1 (aday zincire aktarilmali)")


# ---------------------------------------------------------------------------
# 2) decode_gpu GPU temizligi (normal + istisna yolu)
# ---------------------------------------------------------------------------

def _cupy_veya_skip():
    from src.nesting3d.capabilities import probe_cupy
    cp = probe_cupy()
    if cp is None:
        pytest.skip("cupy/GPU yok")
    return cp


def _kucuk_parts():
    from src.nesting3d.parallel_decode import decode_gpu  # noqa: F401
    from src.nesting3d.voxelize import voxelize_part

    class _BoxPart:
        pass

    import trimesh
    parts = []
    for i in range(3):
        m = trimesh.creation.box(extents=(8.0, 8.0, 8.0))
        vp = voxelize_part(f"kutu{i}", m, 2.0)
        parts.append(vp)
    return parts


def test_decode_gpu_donuste_havuz_ve_plan_cache_bos():
    cp = _cupy_veya_skip()
    from src.nesting3d.parallel_decode import decode_gpu
    parts = _kucuk_parts()
    mempool = cp.get_default_memory_pool()
    mempool.free_all_blocks()
    try:
        cp.fft.config.get_plan_cache().clear()
    except Exception:
        pass
    decode_gpu(parts, nx=30, ny=30, pitch=2.0, return_placements=True)
    assert mempool.used_bytes() == 0, (
        f"decode_gpu donusunde cupy havuzunda {mempool.used_bytes()} bayt "
        "kullanimda kaldi (grid_cache/occ sizintisi)")
    try:
        n_plan = len(list(cp.fft.config.get_plan_cache()))
    except TypeError:
        n_plan = cp.fft.config.get_plan_cache().get_curr_size()
    assert n_plan == 0, f"cuFFT plan cache bos degil ({n_plan} plan)"


def test_decode_gpu_istisna_yolunda_da_temizlik(monkeypatch):
    cp = _cupy_veya_skip()
    import src.nesting3d.parallel_decode as pd
    parts = _kucuk_parts()
    mempool = cp.get_default_memory_pool()
    mempool.free_all_blocks()

    def patlayan_blb(*a, **k):
        raise RuntimeError("test patlamasi")

    monkeypatch.setattr(pd, "_blb_xybbox_gpu", patlayan_blb)
    with pytest.raises(RuntimeError):
        pd.decode_gpu(parts, nx=30, ny=30, pitch=2.0,
                      return_placements=True)
    assert mempool.used_bytes() == 0, (
        "istisna yolunda cupy havuzu bosaltilmadi")

# ---------------------------------------------------------------------------
# 3) Paket A2 — zincir pitch=clearance (K-38'e donus)
# ---------------------------------------------------------------------------

def _zincir_pitchleri(monkeypatch, fine_pitch):
    """kanopi_zinciri_coz'u sahte solve ile kosup alt-solve'lara giden
    fine_pitch degerlerini topla."""
    import src.nesting3d.nfv_solve as nfv
    gorulen = []

    class _R:
        height_mm = 100.0
        n_placed = 1
        placements = []  # asan_tipler bos gecer (kurgu sade)
        fine_voxel_parts = {}
        fine_pitch = 2.0

    def sahte_solve(inst, **kw):
        gorulen.append(kw.get("fine_pitch"))
        return _R()

    monkeypatch.setattr(nfv, "solve_nfv", sahte_solve)
    aday = {"part": _P("kanopi"), "mesh": object(),
            "fiz": {"doluluk": 0.3, "duz_kalinlik_mm": 5.0, "pozlar": [0]},
            "alan_oran": 0.5}
    monkeypatch.setattr(kz, "kanopi_adayi", lambda *a, **k: dict(aday))
    # kanopi_pin gercek mesh ister; sahte solve pin icerigini kullanmiyor
    monkeypatch.setattr(kz, "kanopi_pin", lambda a, z: None)

    class _Inst:
        parts = [_P("kanopi")]

    class _Ref:
        height_mm = 100.0
        n_placed = 1
        placements = []
        fine_voxel_parts = {}
        fine_pitch = 2.0

    kz.kanopi_zinciri_coz(_Inst(), plate_w_mm=100.0, plate_d_mm=100.0,
                          no_go_bounds=(0, 10, 0, 10), clearance_mm=2.0,
                          fine_pitch=fine_pitch, ref_res=_Ref())
    return gorulen


def test_a2_zincir_default_pitch_clearance(monkeypatch):
    """fine_pitch verilmezse alt-solve'lar clearance (2.0) ile kosmali —
    bugun None gidiyor (zehirli banda dusuyor) -> KIRMIZI."""
    gorulen = _zincir_pitchleri(monkeypatch, fine_pitch=None)
    assert gorulen, "hic solve_nfv cagrilmadi (test kurgusu)"
    assert all(p == 2.0 for p in gorulen), (
        f"alt-solve fine_pitch'leri {set(gorulen)} - beklenen hepsi 2.0 "
        "(K-38: pitch=clearance; None -> suggest zehirli banda dusuyor)")


def test_a2_acik_fine_pitch_korunur(monkeypatch):
    gorulen = _zincir_pitchleri(monkeypatch, fine_pitch=1.5)
    assert gorulen and all(p == 1.5 for p in gorulen)
