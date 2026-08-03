# -*- coding: utf-8 -*-
"""K-56f testleri — büyük-parça pinleme (pinned_placements zinciri).

Zincir: solve_coarse_to_fine(pinned_placements) ->
eval_gate._run_champion/evaluate_set(pinned_placements).

Değişmezler (A11 + meta-ders 10):
  - Default (None) bit-özdeş — üretim yolu hiç değişmez.
  - Pin aramadan ÇIKAR (SA/DBLF taşıyamaz): sonuçta pin TAM verilen
    konum+pozdadır.
  - Pin placements + fine_voxel_parts'a girer (n_placed sayımı ve ölçüm
    katmanı pin'i normal parça gibi görür).
  - Pin MARGIN'SİZ voxelize edilir (tek-taraflı dilation özdeşliği).
  - Sınır dışı pin → ValueError (Bin3D.place sessiz kırpmasına karşı).
  - NFV dalında pinned_placements → ValueError (K-56 guard genişletmesi).
"""
from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)

FINE = 2.0


def _instance():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[
            PartSpec(id="plaka", name="plaka", qty=1, source="box",
                     width_mm=60.0, depth_mm=60.0, height_mm=8.0),
            PartSpec(id="kutu", name="kutu", qty=3, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=12.0),
        ],
    )


def _solve(**kw):
    return solve_coarse_to_fine(
        _instance(), plate_w_mm=100.0, plate_d_mm=100.0,
        coarse_pitch=4.0, fine_pitch=FINE, budget=6, seed=42, **kw)


def test_pin_none_bit_ozdes():
    a = _solve()
    b = _solve(pinned_placements=None)
    assert a.height_mm == b.height_mm
    assert [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in a.placements] == \
           [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
            for p in b.placements]


def test_pin_yerlesir_sayilir_ve_tasinmaz():
    pin = {"ad": "plaka", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0, "rot": None}
    r = _solve(pinned_placements=[pin])
    # n_placed = pin + kalanlar (eksik/çift yerleşim yok)
    assert r.n_placed == 4
    pin_pls = [p for p in r.placements if p.part_id.startswith("plaka")]
    assert len(pin_pls) == 1
    p = pin_pls[0]
    # arama taşıyamaz: TAM verilen hücrede, tek-poz (idx 0)
    assert (p.x, p.y, p.z, p.orientation_idx) == (0, 0, 0, 0)
    # ölçüm katmanı sözleşmesi: fine_voxel_parts pin part'ını içerir ve
    # pin part MARGIN'SİZ tek-pozludur
    vp = r.fine_voxel_parts[p.part_id]
    assert len(vp.orientations) == 1
    assert vp.orientations[0].filled.shape == (30, 30)  # 60mm/2.0, dilation'sız


def test_pin_ustune_istif_heightmap_yukselir():
    pin = {"ad": "plaka", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0, "rot": None}
    r = _solve(pinned_placements=[pin])
    # kutular ya plakanın üstünde (z >= plaka tepesi) ya tamamen dışında
    plaka_top_vox = int(round(8.0 / FINE))
    for p in r.placements:
        if p.part_id.startswith("kutu"):
            vp = r.fine_voxel_parts[p.part_id]
            fw, fh = vp.orientations[p.orientation_idx].filled.shape
            disinda = p.x >= 30 or p.y >= 30 or p.x + fw <= 0 or p.y + fh <= 0
            assert disinda or p.z >= plaka_top_vox


def test_pin_sinir_disi_valueerror():
    pin = {"ad": "plaka", "x_mm": 90.0, "y_mm": 0.0, "z_mm": 0.0, "rot": None}
    with pytest.raises(ValueError, match="sinir disi"):
        _solve(pinned_placements=[pin])


def test_pin_bilinmeyen_ad_valueerror():
    pin = {"ad": "yok_boyle_parca", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0}
    with pytest.raises(ValueError, match="yok"):
        _solve(pinned_placements=[pin])


def test_extra_rot_nfv_dalinda_reddedilir(monkeypatch):
    # K-62 v8 (2026-08-04): pinned_placements NFV'de artik MESRU (nfv_solve
    # pin destegi; tests/test_v8_nfv_pin.py) — eski pinned-red testi tersine
    # dondu. extra_rot yasagi SURUYOR (tilt havuzu NFV'de yok), onu pinler.
    from types import SimpleNamespace as NS

    import src.nesting3d.adaptive_params as ap
    from scripts.eval_gate import _run_champion

    monkeypatch.setattr(ap, "predict_nfv_benefit",
                        lambda *a, **k: NS(mode="nfv", wall_aware=False))
    with pytest.raises(ValueError, match="extra_rot_overrides"):
        _run_champion("sentetik", _instance(), 42,
                      extra_rot_overrides={"plaka": [np.eye(4)]})


def test_ayni_ada_coklu_pin_farkli_kopyalar():
    # K-62 v6 (2026-08-04): ayni tipin BIRDEN COK kopyasi pinlenebilir —
    # her pin SIRADAKI kullanilmamis kopyayi tuketir (onceden ayni donor
    # N kez yerlesirdi). Kalan kopyalar aramada cozulur.
    pins = [
        {"ad": "kutu", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0, "rot": None},
        {"ad": "kutu", "x_mm": 40.0, "y_mm": 0.0, "z_mm": 0.0, "rot": None},
    ]
    r = _solve(pinned_placements=pins)
    kutular = [p for p in r.placements if p.part_id.startswith("kutu")]
    assert len(kutular) == 3  # 2 pin + 1 aranan
    pinli = [p for p in kutular
             if (p.x, p.y, p.z) in ((0, 0, 0), (20, 0, 0))]  # /FINE=2.0
    assert len(pinli) == 2, "iki pin TAM verilen konumlarda olmali"
    assert pinli[0].part_id != pinli[1].part_id, \
        "pinler FARKLI kopyalari tuketmeli (ayni donor tekrarlanamaz)"


def test_kopya_sayisindan_fazla_pin_hata():
    pins = [{"ad": "plaka", "x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0,
             "rot": None}] * 2  # plaka qty=1
    with pytest.raises(ValueError):
        _solve(pinned_placements=pins)
