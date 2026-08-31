# -*- coding: utf-8 -*-
"""AC-02 K-54 cap fix testleri (cozum plani Paket B / C1+C5, 2026-08-31).

Kok sebep (kesif kaniti): `_max_part_dim_mm` uc eksenin HAM maksimumunu
aldigi icin DIK DURABILEN uzun parca (plan2 356mm, fsm610 399,6mm > plaka
335) tum instance'in yatay margin'ini 0'a kelepceliyor -> olculen bosluk
0,001mm (uretilemez, sessiz). Fix: cap metrigi "parca basina dikey-secime
gore EN KUCUK yatay footprint"; yatayda-zorunlu buyuk plakada eski davranis
(K-51d: cozum olmesin) + acik sinyal korunur.
"""
from __future__ import annotations

import pytest

from src.nesting3d.coarse_to_fine import (
    cap_margin_to_plate, solve_coarse_to_fine)
from src.nesting3d.instances.format import (
    ContainerSpec, NestingInstance, PartSpec)

PLATE = 100.0


def _inst(dims_list):
    parts = []
    for i, (w, d, h) in enumerate(dims_list):
        parts.append(PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                              width_mm=w, depth_mm=d, height_mm=h))
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE, depth_mm=PLATE), parts=parts)


# ---------------------------------------------------------------------------
# C1 birim: dik-durabilen uzun parca cap'i TETIKLEMEMELI
# ---------------------------------------------------------------------------

def test_cap_dik_durabilen_uzun_parca_tetiklemez():
    """(20,20,120) dik cubuk: yatay footprint 20mm << plaka 100 ->
    margin AYNEN kalmali. Bugun ham-max=120 > 100 -> (0, True) = KIRMIZI."""
    inst = _inst([(20.0, 20.0, 120.0), (10.0, 10.0, 10.0)])
    m, capped = cap_margin_to_plate(2, 5.0, inst, PLATE, PLATE)[:2]
    assert (m, capped) == (2, False), (
        f"dik-durabilen parca cap'i tetikledi: margin={m} capped={capped} "
        "(plan2/fsm610 ihlal koku)")


def test_cap_yatay_zorunlu_buyuk_plaka_davranisi_korunur():
    """(96,60,10) yatayda-zorunlu genis plaka: hangi eksen dikey secilirse
    secilsin yatay footprint >= 60,96 -> cap ESKISI GIBI kisar (K-51d
    korunur; cozum olmez)."""
    inst = _inst([(96.0, 60.0, 10.0)])
    sonuc = cap_margin_to_plate(2, 5.0, inst, PLATE, PLATE)
    m, capped = sonuc[0], sonuc[1]
    assert capped is True and m == 0


def test_cap_kucuk_parcalarda_bit_ozdes():
    inst = _inst([(30.0, 20.0, 10.0)])
    sonuc = cap_margin_to_plate(2, 5.0, inst, PLATE, PLATE)
    assert (sonuc[0], sonuc[1]) == (2, False)


# ---------------------------------------------------------------------------
# C5 regresyon: gercek cozumde olculen bosluk (bugun ~0 -> KIRMIZI)
# ---------------------------------------------------------------------------

def test_c5_dik_parcali_sahnede_clearance_korunur():
    """Plaka 100x100 + dik duran (20,20,120) cubuk + 3 kucuk kutu,
    clearance 8mm -> yerlesen GERCEK mesh'ler arasi olculen min bosluk >= 8.
    Bugun: ham-max=120 cap'i tetikler, margin 0 -> bosluk ~0 = KIRMIZI."""
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.export_stl import placed_meshes
    inst = _inst([(20.0, 20.0, 120.0),
                  (12.0, 12.0, 12.0), (10.0, 14.0, 8.0), (9.0, 9.0, 9.0)])
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
        coarse_pitch=10.0, fine_pitch=5.0, budget=6, seed=42,
        clearance_mm=8.0)
    assert r.n_placed == 4, f"yerlesim eksik: {r.n_placed}/4"
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
    rep = min_clearance(meshes, samples_per_mesh=3000, seed=1)
    assert rep.ok(8.0), (
        f"dik-parcali sahnede clearance korunmadi: {rep.min_mm:.3f}mm < 8 "
        "(K-54 cap margin'i sifirladi - AC-02)")


# ---------------------------------------------------------------------------
# C2/C3: kapi bayragi + tuner-kopya metrigi
# ---------------------------------------------------------------------------

def test_c3_gate_ihlalde_bayrak_yazar(monkeypatch):
    from types import SimpleNamespace
    from scripts import demo_pipeline as dp
    import src.nesting3d.export_stl as es
    import src.nesting3d.clearance as cl
    monkeypatch.setattr(es, "placed_meshes", lambda *a, **k: ["m1", "m2"])
    monkeypatch.setattr(cl, "min_clearance",
                        lambda *a, **k: SimpleNamespace(min_mm=0.5))
    instr = {}
    note = dp._clearance_gate(["p1", "p2"], {}, 0.5, instr)
    assert note and instr.get("clearance_violation") is True


def test_c3_gate_temizde_bayrak_yok(monkeypatch):
    from types import SimpleNamespace
    from scripts import demo_pipeline as dp
    import src.nesting3d.export_stl as es
    import src.nesting3d.clearance as cl
    monkeypatch.setattr(es, "placed_meshes", lambda *a, **k: ["m1", "m2"])
    monkeypatch.setattr(cl, "min_clearance",
                        lambda *a, **k: SimpleNamespace(min_mm=2.5))
    instr = {}
    dp._clearance_gate(["p1", "p2"], {}, 0.5, instr)
    assert "clearance_violation" not in instr


def test_h9_kanopi_zincirine_quality_akar(monkeypatch):
    """H9: payload nfv_quality='max' ise kanopi zinciri de max ile cagrilir;
    None ise 'fast' (bit-ozdes eski recete)."""
    import inspect
    from scripts import demo_pipeline as dp
    src = inspect.getsource(dp._process_batch)
    assert 'quality=(nfv_quality or NFV_QUALITY_DEFAULT)' in src, (
        "kanopi zinciri quality payload/sabit-kaynaga bagli degil (H9/KARAR-G)")
    assert 'quality="fast",  # olculen recete' not in src
