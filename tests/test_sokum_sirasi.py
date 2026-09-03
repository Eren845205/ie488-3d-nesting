# -*- coding: utf-8 -*-
"""P1 — genel sokum sirasi (Sokum Konsolu F2-P1).

Ana bulgu (plan kesfi): sira ZATEN uretiliyor (removable_order), sadece
disari verilmiyordu. Bu faz: (1) tur-ici sira determinizmi (sorted-alive),
(2) rapor_5yon_meshes = kilit_5yon_meshes'in rapor-donduren esi (tek
dogruluk kaynagi), (3) rot yolunda sokum_sirasi telemetrisi, (4) pipeline'da
HER plakada sokum_sirasi (tek-tarafli: uretilemezse alan yok, cozum asla
etkilenmez). Plan: ~/.claude/plans/cheeky-sniffing-corbato.md P1.

Kosum: pytest tests/test_sokum_sirasi.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
import trimesh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _vp(gridshape=(2, 2, 2)):
    grid = np.ones(gridshape, dtype=bool)
    return NS(orientations=[NS(grid=grid)])


def _pl(pid, x, y, z):
    return NS(part_id=pid, orientation_idx=0, x=x, y=y, z=z)


# ---------------------------------------------------------------------------
# (1) Determinizm: ayni girdi -> ayni removable_order; ayni turda serbest
# kalan parcalar INDEX sirasiyla duser (set-iterasyon sansina birakilmaz)
# ---------------------------------------------------------------------------

def test_5dir_removable_order_deterministik_ve_index_sirali():
    from src.nesting3d.accessibility import check_separability_5dir
    # Yan yana 3 serbest kutu — hepsi ilk turda cikar; sira index sirasi olmali
    parts = {f"p{i}": _vp() for i in range(3)}
    pls = [_pl("p0", 0, 0, 0), _pl("p1", 5, 0, 0), _pl("p2", 10, 0, 0)]
    r1 = check_separability_5dir(pls, parts)
    r2 = check_separability_5dir(pls, parts)
    assert r1.removable_order == r2.removable_order == ["p0", "p1", "p2"]
    assert r1.n_locked == 0


def test_rot_removable_order_deterministik():
    from src.nesting3d.rotation_extract import check_separability_rot
    parts = {f"p{i}": _vp() for i in range(3)}
    pls = [_pl("p0", 0, 0, 0), _pl("p1", 5, 0, 0), _pl("p2", 10, 0, 0)]
    r1 = check_separability_rot(pls, parts)
    r2 = check_separability_rot(pls, parts)
    assert r1.removable_order == r2.removable_order == ["p0", "p1", "p2"]


# ---------------------------------------------------------------------------
# (2) rapor_5yon_meshes: kilit_5yon_meshes ile AYNI mekanik, rapor doner
# ---------------------------------------------------------------------------

def _mesh_at(w, d, h, dx=0.0):
    m = trimesh.creation.box(extents=(float(w), float(d), float(h)))
    m.apply_translation(-m.bounds[0])
    m.apply_translation([dx, 0.0, 0.0])
    return m


def test_rapor_5yon_meshes_kilit_esitligi_ve_sira():
    from src.nesting3d.continuous_settle import (kilit_5yon_meshes,
                                                 rapor_5yon_meshes)
    meshes = [_mesh_at(10, 10, 10, 0.0), _mesh_at(10, 10, 10, 20.0)]
    rapor = rapor_5yon_meshes(meshes, pitch=2.0)
    assert rapor.n_locked == kilit_5yon_meshes(meshes, pitch=2.0) == 0
    # m{i} pid'leri mesh listesi sirasina karsilik gelir; hepsi cikti
    assert sorted(rapor.removable_order) == ["m0", "m1"]


# ---------------------------------------------------------------------------
# (3) rot-kabul yolu: tel["rot_kabul"]["sokum_sirasi"] part_id listesi
# ---------------------------------------------------------------------------

def test_rot_kabul_sokum_sirasi_part_id_listesi():
    from src.nesting3d.nfv_solve import solve_nfv_kalite

    class _Ham:
        height_mm = 100.0
        density = 0.5
        n_placed = 2
        placements = [NS(part_id="k_01", name="k"),
                      NS(part_id="k_02", name="k")]
        fine_voxel_parts = {}
        fine_pitch = 2.0
        tune_result = None

    ham = _Ham()

    def solve(inst, **kw):
        return ham

    cert = NS(eksen="Y", aci_deg=-30.0, yon="+Z", lift_vox=0)
    rapor = NS(n_locked=0, certificates={"m1": cert},
               removable_order=["m0", "m1"])
    _, tel = solve_nfv_kalite(
        None, plate_w_mm=80.0, plate_d_mm=80.0, clearance_mm=2.0,
        rot_kabul=True, _solve=solve,
        _check_5dir=lambda p, v: NS(n_locked=1),
        _check_rot=lambda r: rapor)
    rk = tel["rot_kabul"]
    assert rk["uygulandi"] is True
    # Birlesik tam sira (peel + rot ciktiklari anda) part_id'ye eslenmis
    assert rk["sokum_sirasi"] == ["k_01", "k_02"]


# ---------------------------------------------------------------------------
# (4) pipeline: HER plakada sokum_sirasi (kilitsiz sahnede de); tek-tarafli
# ---------------------------------------------------------------------------

def _senaryo():
    from tests.test_parca_kimlik import _iki_siparis_senaryo
    return _iki_siparis_senaryo()


def test_pipeline_sokum_sirasi_uretilir():
    from scripts.demo_pipeline import run_pipeline
    result = run_pipeline(_senaryo())
    rows = [nr for nr in result["nesting_results"].values()
            if nr.get("n_parts", 0) > 0]
    assert rows, "parti cozulmedi"
    for nr in rows:
        sira = nr.get("sokum_sirasi")
        assert sira, "sokum_sirasi eksik"
        # Kilitsiz kutu sahnesi: TUM parcalar sirada, part_id'ler kimlikle uyumlu
        assert len(sira) == nr["n_parts"]
        kimlik = nr.get("parca_kimlik") or {}
        assert set(sira) <= set(kimlik.keys())
        assert len(set(sira)) == len(sira)


def test_pipeline_sokum_sirasi_hata_tek_tarafli(monkeypatch):
    # Sira uretimi patlarsa alan yok + cozum AYNEN (yukseklik degismez)
    import src.nesting3d.accessibility as acc
    from scripts.demo_pipeline import run_pipeline

    r_ref = run_pipeline(_senaryo())

    def patlar(*a, **k):
        raise RuntimeError("sira uretilemedi")

    monkeypatch.setattr(acc, "check_separability_5dir", patlar)
    r = run_pipeline(_senaryo())
    rows_ref = {b: nr for b, nr in r_ref["nesting_results"].items()}
    for b, nr in r["nesting_results"].items():
        if nr.get("n_parts", 0) > 0:
            assert "sokum_sirasi" not in nr
            assert nr["height_mm"] == rows_ref[b]["height_mm"]
