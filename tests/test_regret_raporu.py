"""Faz B — scripts/regret_raporu: set/aile x arm matrisi + kural-regret.

Kabul kriterleri:
  1. Matris: arm -> en iyi legal + sure; INVALID arm 'INV(sebep)' (Y-7).
  2. nfv_kalite esdegeri: ham@2 satirinin B_KILIT'ine (5-yon; uretim tetigi)
     gore ham/guard secilir — d4'te 276.5 (231.5 DEGIL; rot-sertifika uretimde
     otomatik degil).
  3. Kural regret = kural-arm legal - argmin legal; kural arm olculmemisse
     kotumser (max-min) ceza + bayrak.
  4. otonom_gecmis satirlari matrise girmez (ayri sayilir).
  5. JSON cikti semasi: set -> {armlar, kural_arm, kural_deger, regret, en_iyi}.
"""
from __future__ import annotations

import pytest

from scripts.regret_raporu import kalite_esdegeri, rapor_uret

FV = [0.5] * 23
FN = [f"f{i}" for i in range(23)]


def _row(iid, mode, recete, pitch, legal, **o):
    r = dict(schema=2, instance_id=iid, mode=mode, recete=recete,
             pitch_fine=pitch, legal_height_mm=legal,
             height_mm=legal if legal is not None else 999.0,
             feature_vector=list(FV), feature_names=list(FN),
             family_f1="mixed_scale", duration_s=600.0, kaynak="backfill")
    r.update(o)
    return r


ROWS = [
    # d4: heightmap INV; nfv ham legal ama b_kilit=363 -> kalite=guard
    _row("deneme4", "heightmap+wall_aware", "n24", 0.5, None,
         invalid_reason="clearance 1.555<2.0"),
    _row("deneme4", "nfv", "ham@2.0", 2.0, 231.5, b_kilit=363),
    _row("deneme4", "nfv", "guard@2.0", 2.0, 276.5, b_kilit=0),
    # d5: ham b_kilit=0 -> kalite=ham; @1.0 daha iyi ama kural @2.0 kalite
    _row("deneme5", "heightmap", "n24", 1.8, 338.4),
    _row("deneme5", "nfv", "ham@2.0", 2.0, 223.5, b_kilit=0),
    _row("deneme5", "nfv", "ham@1.0", 1.0, 218.0, b_kilit=0),
    # otonom satiri matrise girmemeli
    _row("kosuX/B001", "nfv", "uretim", 2.0, 412.0, kaynak="otonom_gecmis"),
]


def _karar(set_adi):
    return {"deneme4": ("nfv", False), "deneme5": ("nfv", False)}[set_adi]


def test_kalite_esdegeri():
    armlar = {"nfv_ham@2": (231.5, {"b_kilit": 363}),
              "nfv_guard@2": (276.5, {"b_kilit": 0})}
    assert kalite_esdegeri(armlar) == ("nfv_guard@2", 276.5)
    armlar2 = {"nfv_ham@2": (223.5, {"b_kilit": 0})}
    assert kalite_esdegeri(armlar2) == ("nfv_ham@2", 223.5)
    assert kalite_esdegeri({}) is None


def test_rapor_uret():
    rapor = rapor_uret(ROWS, _karar)
    assert set(rapor["setler"].keys()) == {"deneme4", "deneme5"}
    d4 = rapor["setler"]["deneme4"]
    assert d4["armlar"]["heightmap+wall_aware"]["legal"] is None
    assert "clearance" in d4["armlar"]["heightmap+wall_aware"]["invalid"]
    assert d4["kural_arm"] == "nfv_guard@2"       # b_kilit=363 -> guard
    assert d4["kural_deger"] == 276.5
    assert d4["en_iyi"] == 231.5
    assert d4["regret"] == pytest.approx(45.0)     # 276.5 - 231.5
    d5 = rapor["setler"]["deneme5"]
    assert d5["kural_deger"] == 223.5              # kalite @2.0 = ham
    assert d5["en_iyi"] == 218.0                   # @1.0
    assert d5["regret"] == pytest.approx(5.5)
    assert rapor["n_otonom_dislanan"] == 1


def test_kural_arm_olculmemisse_kotumser():
    rows = [_row("s", "heightmap", "n24", 0.5, 100.0),
            _row("s", "nfv", "ham@2.0", 2.0, 80.0, b_kilit=0)]
    rapor = rapor_uret(rows, lambda s: ("heightmap", True))  # wall_aware olculmemis
    s = rapor["setler"]["s"]
    assert s["kural_arm"] == "heightmap+wall_aware"
    assert s["kural_deger"] is None
    assert s["regret"] == pytest.approx(20.0)      # kotumser: max-min
    assert s["kotumser_ceza"] is True
