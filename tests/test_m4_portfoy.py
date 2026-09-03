# -*- coding: utf-8 -*-
"""test_m4_portfoy.py — M4 portfoy kosusu saf-mantik testleri.

Kosu YAPILMAZ (run_pipeline cagrilmaz): etiket turetimi (kol_legal_mi /
etiket_hesapla), senaryo kurulumu ve aile kayitlari test edilir.
"""
from __future__ import annotations

import pytest

from pathlib import Path

from scripts.m4_portfoy_kosu import (
    ARMS, FAMILY_BUILDERS, etiket_hesapla, kol_legal_mi, scenario_kur)
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec

REQ = 2.0


def _kol(h=100.0, placed=5, total=5, cl=2.5, k5=0, **extra):
    d = {"height_mm": h, "n_placed": placed, "n_total": total,
         "min_clearance_mm": cl, "n_locked_5dir": k5, "n_locked_z": 0}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# kol_legal_mi — A2 uc-sart (tam yerlesim + clearance + 5-yon kilit)
# ---------------------------------------------------------------------------

def test_legal_kol_none_doner():
    assert kol_legal_mi(_kol(), REQ) is None


def test_eksik_yerlesim_invalid():
    sebep = kol_legal_mi(_kol(placed=4), REQ)
    assert sebep is not None and "eksik yerlesim" in sebep


def test_clearance_ihlal_invalid():
    sebep = kol_legal_mi(_kol(cl=1.2), REQ)
    assert sebep is not None and "clearance" in sebep


def test_clearance_olculemedi_invalid():
    # ANAYASA: kanitsizlik gecer not degildir
    assert kol_legal_mi(_kol(cl=None), REQ) is not None


def test_5yon_kilit_invalid():
    sebep = kol_legal_mi(_kol(k5=3), REQ)
    assert sebep is not None and "5-yon" in sebep


def test_5yon_olculemedi_invalid():
    assert kol_legal_mi(_kol(k5=None), REQ) is not None


def test_zplus_kilidi_tek_basina_legal_bozmaz():
    # Telemetrideki +Z-tek kilit yalniz kayit; legallik 5-yonden
    assert kol_legal_mi(_kol(n_locked_z=353), REQ) is None


def test_kosu_hatasi_invalid():
    sebep = kol_legal_mi({"hata": "patladi", "n_total": 5}, REQ)
    assert sebep is not None and "kosu hatasi" in sebep


# ---------------------------------------------------------------------------
# etiket_hesapla — winner + regret
# ---------------------------------------------------------------------------

def test_winner_ve_regret():
    arms = {"heightmap": _kol(h=120.0), "nfv_fast": _kol(h=100.0),
            "nfv_max": _kol(h=95.0)}
    et = etiket_hesapla(arms, REQ)
    assert et["winner_mode"] == "nfv_max"
    assert et["regret_mm"]["nfv_max"] == 0.0
    assert et["regret_mm"]["nfv_fast"] == pytest.approx(5.0)
    assert et["regret_mm"]["heightmap"] == pytest.approx(25.0)
    assert et["n_legal"] == 3


def test_invalid_kol_regret_none():
    arms = {"heightmap": _kol(h=90.0, cl=0.5), "nfv_max": _kol(h=110.0)}
    et = etiket_hesapla(arms, REQ)
    # Daha alcak ama ILLEGAL kol winner OLAMAZ (A2: ihlal maskeleyen metrik sisirir)
    assert et["winner_mode"] == "nfv_max"
    assert et["regret_mm"]["heightmap"] is None
    assert et["invalid_reasons"]["heightmap"] is not None


def test_hicbir_kol_legal_degil():
    arms = {"heightmap": _kol(cl=0.1), "nfv_max": _kol(k5=7)}
    et = etiket_hesapla(arms, REQ)
    assert et["winner_mode"] is None
    assert et["n_legal"] == 0
    assert all(v is None for v in et["regret_mm"].values())


# ---------------------------------------------------------------------------
# scenario_kur — zorlanmis mod + stl_path korunumu
# ---------------------------------------------------------------------------

def _inst(parts):
    return NestingInstance(
        container=ContainerSpec(width_mm=335.0, depth_mm=335.0,
                                height_mm=None),
        parts=parts)


def test_scenario_zorlanmis_mod():
    inst = _inst([PartSpec(id="a", name="a", qty=2, source="box",
                           width_mm=10.0, depth_mm=20.0, height_mm=5.0)])
    sc = scenario_kur(inst, "nfv", "max", 42, "m4:test:s0",
                      {"taban": True})
    assert sc["nesting_mode"] == "nfv"
    assert sc["nfv_quality"] == "max"
    assert sc["auto_family_routing"] is False
    assert sc["kaynak"] == "m4:test:s0"
    assert sc["taban"] is True  # rich_scenario tabani korunur
    assert sc["orders"][0]["parts"][0]["qty"] == 2


def test_scenario_heightmap_nfv_quality_yok():
    inst = _inst([PartSpec(id="a", name="a", qty=1, source="box",
                           width_mm=10.0, depth_mm=20.0, height_mm=5.0)])
    sc = scenario_kur(inst, "heightmap", None, 42, "k", {})
    assert sc["nesting_mode"] == "heightmap"
    assert "nfv_quality" not in sc


def test_scenario_stl_path_korunur():
    inst = _inst([PartSpec(id="f", name="f", qty=1, source="stl",
                           stl_path="D:/x/frame.stl",
                           width_mm=100.0, depth_mm=100.0, height_mm=5.0)])
    sc = scenario_kur(inst, "nfv", "fast", 42, "k", {})
    p = sc["orders"][0]["parts"][0]
    assert p["source"] == "stl"
    assert p["stl_path"] == "D:/x/frame.stl"


# ---------------------------------------------------------------------------
# Aile kayitlari
# ---------------------------------------------------------------------------

def test_kabuk_aileleri_dislandi():
    # shell_bells box-koprude ici-bos geometriyi kaybeder (synthetic.py
    # uyarisi) — portfoye GIREMEZ. hollow_tubes 2026-09-02'den itibaren
    # STL varyantiyla (hollow_tubes_stl, source="stl") portfoyde.
    assert "shell_bells" not in FAMILY_BUILDERS
    assert "hollow_tubes" in FAMILY_BUILDERS


def test_hollow_tubes_stl_kaynakli(tmp_path):
    """hollow_tubes ailesi gercek geometriyle (source=stl, dosya var, bbox
    dolu) ve deterministik girer; orta olcek adet dokusu 1..2."""
    b = FAMILY_BUILDERS["hollow_tubes"]
    inst = b(1, "orta", tmp_path)
    assert len(inst.parts) == 24 and inst.meta["family"] == "hollow_tubes"
    for p in inst.parts:
        assert p.source == "stl" and p.stl_path and Path(p.stl_path).exists()
        assert p.width_mm > 0 and p.depth_mm > 0 and p.height_mm > 0
        assert 1 <= p.qty <= 2
    inst2 = b(1, "orta", tmp_path)
    assert [(p.id, p.qty, p.width_mm) for p in inst2.parts] == \
        [(p.id, p.qty, p.width_mm) for p in inst.parts]
    # scenario koprusu stl_path'i korur (gercek geometri nesting'e gider)
    sc = scenario_kur(inst, "nfv", "max", 42, "k", {})
    assert all(pp.get("stl_path") for pp in sc["orders"][0]["parts"])


def test_arms_uc_kol():
    adlar = [a[0] for a in ARMS]
    assert adlar == ["heightmap", "nfv_fast", "nfv_max"]
    # nfv kollari mode=nfv + kalite; heightmap kalitesiz
    assert ARMS[0][1] == "heightmap" and ARMS[0][2] is None
    assert ARMS[1][1] == "nfv" and ARMS[1][2] == "fast"
    assert ARMS[2][1] == "nfv" and ARMS[2][2] == "max"


def test_kafes_kollari_tanimli():
    """Kafes kollari TETIKLI (uretim ARMS'ina girmez; pitch==clearance K-38)."""
    from scripts.m4_portfoy_kosu import KAFES_ARMS, KAFES_PITCH
    assert [a[0] for a in KAFES_ARMS] == ["kafes", "kafes_duruskoru"]
    assert KAFES_ARMS[0][1] is False and KAFES_ARMS[1][1] is True
    assert KAFES_PITCH == 2.0


def test_kol_kafes_tetiksiz_ailede_none():
    """Tetiksiz ailede _kol_kafes None doner (kol satira girmez) —
    cozum kosulmadan, saf siniflandirmadan (ucuz)."""
    from scripts.m4_portfoy_kosu import _kol_kafes
    from src.nesting3d.instances.synthetic import random_boxes
    inst = random_boxes(n_parts=16, container=ContainerSpec(
        width_mm=335.0, depth_mm=335.0, height_mm=None), seed=0)
    assert _kol_kafes(inst, False, 2.0) is None


def test_etiket_kafes_kolu_winner_olabilir():
    """etiket_hesapla kol-adi bagimsiz: kafes kolu legal + en alcaksa
    winner_mode='kafes' doner (ML plani: mekanizma M4 portfoyune KOL)."""
    arms = {"heightmap": _kol(h=120.0), "nfv_fast": _kol(h=100.0),
            "kafes": _kol(h=90.0), "kafes_duruskoru": _kol(h=95.0)}
    et = etiket_hesapla(arms, REQ)
    assert et["winner_mode"] == "kafes"
    assert et["regret_mm"]["kafes_duruskoru"] == pytest.approx(5.0)


def test_box_aileleri_uretilebilir():
    for ad in ("thin_plates", "long_rods", "random_boxes",
               "few_large_many_small", "high_qty_repeat",
               "repeat_rod_mix", "mass_plate_rod_mix"):
        inst = FAMILY_BUILDERS[ad](0, "kucuk", None)
        assert sum(int(p.qty) for p in inst.parts) > 0, ad


def test_mass_plate_scale_kucuk_ucuz():
    inst = FAMILY_BUILDERS["mass_plate_rod_mix"](0, "kucuk", None)
    n = sum(int(p.qty) for p in inst.parts)
    assert n < 150  # smoke-ucuz kalmali (fsm-olcegi 'buyuk' gece isidir)


def test_holey_frames_stl_uretir(tmp_path):
    inst = FAMILY_BUILDERS["holey_frames"](0, "kucuk", tmp_path)
    stl_parts = [p for p in inst.parts if str(p.source) == "stl"]
    assert len(stl_parts) == 1
    from pathlib import Path
    assert Path(stl_parts[0].stl_path).exists()

# ---------------------------------------------------------------------------
# A2 rot-sokum katmani (2026-08-30, Eren onayi): etiket hukmu eval_gate.legal_of
# ile AYNI — 5-yon kilit>0 tek basina RED degil; rot kilit=0 -> sokum-planli
# LEGAL. (plan1 dersi: 136,20 uretimde LEGAL iken etiket INVALID demisti.)
# ---------------------------------------------------------------------------

def test_5yon_kilit_rot_sifir_sokum_planli_legal():
    assert kol_legal_mi(_kol(k5=12, n_locked_rot=0), REQ) is None


def test_5yon_kilit_rot_pozitif_invalid_sebep_rot_tasir():
    sebep = kol_legal_mi(_kol(k5=12, n_locked_rot=3), REQ)
    assert sebep is not None and "12 kilit" in sebep and "rot-sokum 3" in sebep


def test_5yon_kilit_rot_none_eski_davranis():
    sebep = kol_legal_mi(_kol(k5=12, n_locked_rot=None), REQ)
    assert sebep == "12 kilit (5-yon)"


def test_rot_sifir_diger_sartlari_aklamaz():
    # rot kilit=0 yalniz kilit sartini aklar; clearance ihlali yine INVALID
    sebep = kol_legal_mi(_kol(k5=12, n_locked_rot=0, cl=1.5), REQ)
    assert sebep is not None and "clearance" in sebep


def test_etiket_sokum_planli_kol_kazanabilir():
    arms = {"heightmap": _kol(h=171.7, k5=0),
            "nfv_fast": _kol(h=136.2, k5=12, n_locked_rot=0),
            "nfv_max": _kol(h=190.2, k5=0)}
    et = etiket_hesapla(arms, REQ)
    assert et["winner_mode"] == "nfv_fast" and et["n_legal"] == 3
    assert et["regret_mm"]["heightmap"] == pytest.approx(35.5)
    assert et["sokum_planli"] == {"heightmap": False, "nfv_fast": True,
                                  "nfv_max": False}



# ---------------------------------------------------------------------------
# asama2 kampanya: sidecar yeniden-kullanim (olcum tekrar edilmez) — 2026-08-30
# ---------------------------------------------------------------------------

def _sidecar_yaz(dizin, ad, kol):
    import json
    (dizin / f"{ad}_20260830_120000.json").write_text(
        json.dumps({"kol_ozet": kol}), encoding="utf-8")


def test_sidecar_bul_tam_ve_hatasiz_kolu_alir(tmp_path, monkeypatch):
    import scripts.asama2_devset_etiket as a2
    monkeypatch.setattr(a2, "SIDECAR_DIR", tmp_path)
    monkeypatch.setenv("A2_REUSE_SIDECAR", "1")
    _sidecar_yaz(tmp_path, "asama2_planX_heightmap", _kol(h=100.0))
    r = a2._sidecar_bul("asama2:planX", "heightmap", None)
    assert r is not None and r["height_mm"] == 100.0 and r["yeniden_kullanildi"]


def test_sidecar_bul_h0_veya_eksik_yerlesim_reddeder(tmp_path, monkeypatch):
    import scripts.asama2_devset_etiket as a2
    monkeypatch.setattr(a2, "SIDECAR_DIR", tmp_path)
    monkeypatch.setenv("A2_REUSE_SIDECAR", "1")
    _sidecar_yaz(tmp_path, "asama2_planX_nfv_fast", _kol(h=0.0, placed=0))
    assert a2._sidecar_bul("asama2:planX", "nfv", "fast") is None
    _sidecar_yaz(tmp_path, "asama2_planY_nfv_max", _kol(h=50.0, placed=4))
    assert a2._sidecar_bul("asama2:planY", "nfv", "max") is None


def test_sidecar_bul_kapali_env(tmp_path, monkeypatch):
    import scripts.asama2_devset_etiket as a2
    monkeypatch.setattr(a2, "SIDECAR_DIR", tmp_path)
    monkeypatch.setenv("A2_REUSE_SIDECAR", "0")
    _sidecar_yaz(tmp_path, "asama2_planX_heightmap", _kol(h=100.0))
    assert a2._sidecar_bul("asama2:planX", "heightmap", None) is None
