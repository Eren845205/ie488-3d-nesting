# -*- coding: utf-8 -*-
"""K-56g testleri — sipariş-notu motor kısıtlarının ÜRETİM kablosu.

Zincir: order dict `motor_kisitlari` -> run_pipeline payload ->
_process_batch dal zorlaması -> solve_coarse_to_fine(
orientation_overrides / pinned_placements).

Değişmezler (A11 + K-56f deseni):
  - Default (alan yok / boş dict) bit-özdeş — üretim yolu hiç değişmez.
  - orientation_overrides: adı eşleşen model YALNIZ verilen pozlarda
    voxelize edilir (kaynak_ad fallback dahil); eşleşmeyenler etkilenmez.
  - Kısıt varken parti NFV/tuner dalına GİRMEZ (coarse_to_fine'a zorlanır)
    ve `kisit_yonlendirme` telemetrisi görünür.
  - Kısıtsız yolda `kisit_yonlendirme` anahtarı HİÇ oluşmaz.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.demo_pipeline import _process_batch, run_pipeline  # noqa: E402
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.instances.format import (  # noqa: E402
    ContainerSpec,
    NestingInstance,
    PartSpec,
)

FINE = 2.0


def _instance(kaynak_ad=None):
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="dik", name="dikdortgen", qty=2, source="box",
                     width_mm=40.0, depth_mm=20.0, height_mm=12.0,
                     kaynak_ad=kaynak_ad),
            PartSpec(id="kutu", name="kutu", qty=2, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=12.0),
        ],
    )


def _solve(instance=None, **kw):
    return solve_coarse_to_fine(
        instance or _instance(), plate_w_mm=100.0, plate_d_mm=100.0,
        coarse_pitch=4.0, fine_pitch=FINE, budget=6, seed=42, **kw)


# ---------------------------------------------------------------------------
# solve_coarse_to_fine katmanı
# ---------------------------------------------------------------------------


def test_orientation_overrides_none_bit_ozdes():
    a = _solve()
    b = _solve(orientation_overrides=None)
    assert a.height_mm == b.height_mm
    assert [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in a.placements] == \
           [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in b.placements]


def test_orientation_overrides_poz_kilidi():
    # Kısıtsız: dikdörtgen model birden çok poz taşır (kilit anlamlı olsun)
    serbest = _solve()
    dik_free = [p for p in serbest.placements
                if p.part_id.startswith("dik")][0]
    assert len(serbest.fine_voxel_parts[dik_free.part_id].orientations) > 1

    # Kilitli: yalnız poz 0 — hem voxel seti hem seçilen poz kilitli
    kilitli = _solve(orientation_overrides={"dikdortgen": (0,)})
    dik_pls = [p for p in kilitli.placements if p.part_id.startswith("dik")]
    assert len(dik_pls) == 2  # tüm kopyalar yerleşti
    for p in dik_pls:
        vp = kilitli.fine_voxel_parts[p.part_id]
        assert len(vp.orientations) == 1
        assert p.orientation_idx == 0
    # Eşleşmeyen model etkilenmez (kısıtsız çözümle aynı poz sayısı)
    kutu_p = [p for p in kilitli.placements
              if p.part_id.startswith("kutu")][0]
    kutu_free = [p for p in serbest.placements
                 if p.part_id.startswith("kutu")][0]
    assert len(kilitli.fine_voxel_parts[kutu_p.part_id].orientations) == \
        len(serbest.fine_voxel_parts[kutu_free.part_id].orientations)


def test_orientation_overrides_kaynak_ad_eslesmesi():
    # Anahtar display ile değil kaynak_ad ile eşleşir (extra_rot deseni)
    inst = _instance(kaynak_ad="ORJINAL AD.stl")
    r = _solve(instance=inst,
               orientation_overrides={"ORJINAL AD.stl": (0,)})
    dik_pls = [p for p in r.placements if p.part_id.startswith("dik")]
    for p in dik_pls:
        assert len(r.fine_voxel_parts[p.part_id].orientations) == 1


# ---------------------------------------------------------------------------
# NFV kolu (hoca S2 2026-07-22: durus kilidi NFV dalinda da tasinir)
# ---------------------------------------------------------------------------


def _nfv_solve(**kw):
    from src.nesting3d.nfv_solve import solve_nfv_kalite
    return solve_nfv_kalite(
        _instance(), plate_w_mm=100.0, plate_d_mm=100.0,
        clearance_mm=2.0, quality="fast", seed=42, **kw)


def test_nfv_orientation_overrides_none_bit_ozdes():
    a, _ = _nfv_solve()
    b, _ = _nfv_solve(orientation_overrides=None)
    assert a.height_mm == b.height_mm
    assert [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in a.placements] == \
           [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in b.placements]


def test_nfv_orientation_overrides_poz_kilidi():
    r, _ = _nfv_solve(orientation_overrides={"dikdortgen": (0, 1)})
    dik_pls = [p for p in r.placements if p.part_id.startswith("dik")]
    assert len(dik_pls) == 2
    for p in dik_pls:
        vp = r.fine_voxel_parts[p.part_id]
        assert len(vp.orientations) <= 2  # yalniz izinli pozlar voxelize edildi
        assert p.orientation_idx < len(vp.orientations)


# ---------------------------------------------------------------------------
# _process_batch dal zorlaması
# ---------------------------------------------------------------------------

_PRICING = {
    "version": "1.0",
    "name": "kisit_test_rules",
    "rules": [
        {"id": "r_volume", "type": "unit_price", "input_field": "hacim_m3",
         "unit_price": 500.0, "description": "Hacim birim fiyat"},
        {"id": "r_min", "type": "min_clamp", "min_price": 100.0,
         "description": "Minimum fiyat"},
    ],
}


def _payload(**over):
    pl = {
        "batch_id": "B-KISIT",
        "siparis_musteri": {"T1": "TestCo"},
        "all_parts": [
            {"id": "p1", "name": "box_small", "qty": 2, "source": "box",
             "width_mm": 40.0, "depth_mm": 20.0, "height_mm": 12.0,
             "order_id": "T1"},
            {"id": "p2", "name": "box_medium", "qty": 1, "source": "box",
             "width_mm": 60.0, "depth_mm": 50.0, "height_mm": 40.0,
             "order_id": "T1"},
        ],
        "batch_volume_cm3": 100.0,
        "container_cfg": {"width_mm": 220.0, "depth_mm": 220.0},
        "pitch_fallback": 20.0,
        "n_orient": 2,
        "seed": 42,
        "pricing_rules": _PRICING,
        "nesting_mode": "heightmap",
    }
    pl.update(over)
    return pl


def test_kisitsiz_payload_bit_ozdes():
    """Alan yok == boş dict: aynı sonuç, telemetri anahtarı HİÇ oluşmaz."""
    a = _process_batch(_payload())
    b = _process_batch(_payload(motor_kisitlari={}))
    assert a["nesting"]["height_mm"] == b["nesting"]["height_mm"]
    assert "kisit_yonlendirme" not in a["nesting"]
    assert "kisit_yonlendirme" not in b["nesting"]


def test_kisit_tuner_atlanir_c2f_dali():
    """Parça sayısı eşiğin altında da kısıt varsa c2f dalına zorlanır."""
    r = _process_batch(_payload(
        motor_kisitlari={"orientation_overrides": {"box_small": [0]}}))
    yon = r["nesting"].get("kisit_yonlendirme")
    assert yon is not None
    assert yon["dal"] == "c2f"
    assert yon["tuner_atlandi"] is True
    assert yon["orient_kilit"] == ["box_small"]
    assert r["nesting"]["height_mm"] > 0


def test_kisit_nfv_modu_c2f_zorlanir():
    """nfv modu + kısıt -> heightmap/c2f'e çevrilir (NFV pin taşıyamaz)."""
    r = _process_batch(_payload(
        nesting_mode="nfv",
        motor_kisitlari={"pinned_placements": [
            {"ad": "box_medium", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0,
             "rot": None}]}))
    assert r["nesting"]["nesting_mode_used"] == "heightmap"
    yon = r["nesting"].get("kisit_yonlendirme")
    assert yon is not None and yon["n_pin"] == 1
    assert r["nesting"]["height_mm"] > 0


# ---------------------------------------------------------------------------
# run_pipeline uçtan uca kablo
# ---------------------------------------------------------------------------

_SCENARIO = {
    "ref_date": date(2026, 6, 13),
    "seed": 42,
    "capacity": {
        "num_machines": 1,
        "batch_duration_hours": 8.0,
        "shifts_per_day": 1,
        "max_volume_per_batch_cm3": 200_000.0,
    },
    "container": {"width_mm": 220.0, "depth_mm": 220.0},
    "pitch": 20.0,
    "n_orientations": 2,
    "portfolio_budget": 10,
    "orders": [
        {
            "order_id": "KISIT-A",
            "customer": "TestCo",
            "deadline": "2026-07-01",
            "priority_class": 1,
            "parts": [
                {"id": "p1", "name": "box_small", "qty": 2, "source": "box",
                 "width_mm": 40.0, "depth_mm": 40.0, "height_mm": 30.0},
            ],
        },
        {
            "order_id": "KISIT-B",
            "customer": "TestCo2",
            "deadline": "2026-07-15",
            "priority_class": 2,
            "parts": [
                {"id": "p2", "name": "box_medium", "qty": 2, "source": "box",
                 "width_mm": 60.0, "depth_mm": 50.0, "height_mm": 40.0},
            ],
            "motor_kisitlari": {
                "pinned_placements": [
                    {"ad": "box_medium", "x_mm": 0.0, "y_mm": 0.0,
                     "z_mm": 0.0, "rot": None}],
            },
        },
    ],
    "pricing_rules": _PRICING,
}


def test_run_pipeline_kisit_kablosu():
    """Sipariş alanındaki kısıt payload'a taşınır; yalnız o parti işaretlenir."""
    result = run_pipeline(_SCENARIO)
    yonlu = [nr for nr in result["nesting_results"].values()
             if "kisit_yonlendirme" in nr]
    assert len(yonlu) == 1, \
        f"tam 1 parti kisitli olmali, bulunan: {len(yonlu)}"
    assert yonlu[0]["kisit_yonlendirme"]["n_pin"] == 1
    assert yonlu[0]["height_mm"] > 0
    # kısıtsız parti dokunulmadı
    temiz = [nr for nr in result["nesting_results"].values()
             if "kisit_yonlendirme" not in nr]
    assert all(nr["height_mm"] > 0 for nr in temiz if nr.get("n_parts"))


def test_run_pipeline_kisitsiz_alan_yok():
    """Kısıt alanı olmayan senaryoda hiçbir partide telemetri anahtarı yok."""
    sc = {**_SCENARIO,
          "orders": [o for o in _SCENARIO["orders"]
                     if "motor_kisitlari" not in o]}
    result = run_pipeline(sc)
    for nr in result["nesting_results"].values():
        assert "kisit_yonlendirme" not in nr
