"""C4 challenger — mode_model_io + predict_nfv_benefit entegrasyonu.

Kabul kriterleri:
  1. save/load round-trip: proba/prediction_set yuklemeden sonra ayni.
  2. karar() CIFT KILIT: allowlist-disi aile -> None; genis kume -> None;
     allowlist + tekil -> (arm, gerekce).
  3. predict_nfv_benefit(mode_model=None) -> BIT-OZDES eski davranis.
  4. mode_model karari kurali ezer (nfv_* -> mode=nfv vb.); model hata
     firlatirsa kurala dusulur (asla cozumu oldurmez).
  5. load_mode_model: dosya yok/bozuk -> None (hata yok).
"""
from __future__ import annotations

import json

import pytest

from src.nesting3d.adaptive_params import predict_nfv_benefit
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.selection.dataset import TrainingRow
from src.nesting3d.selection.mode_model_io import (
    LoadedModeModel,
    load_mode_model,
    save_mode_model,
)
from src.nesting3d.selection.regret_logistic import RegretWeightedLogistic


def _rows(n=12):
    out = []
    for i in range(n):
        f0 = 0.05 + 0.9 * i / (n - 1)
        nfv_iyi = f0 < 0.5
        hs = ({"nfv_ham@2": 50.0, "heightmap": 150.0} if nfv_iyi
              else {"nfv_ham@2": 90.0, "heightmap": 40.0})
        out.append(TrainingRow(
            instance_id=f"s{i}", is_easy=False,
            winner="nfv_ham@2" if nfv_iyi else "heightmap",
            dblf_height=hs["heightmap"], best_height=min(hs.values()),
            feature_vector=[f0, 1.0 - f0], feature_names=["f0", "f1"],
            aile="long_rod" if nfv_iyi else "solid_bulk",
            per_solver_heights=hs))
    return out


def _artefakt(tmp_path, allowlist=("long_rod", "solid_bulk")):
    m = RegretWeightedLogistic(iters=300)
    m.fit(_rows())
    yol = tmp_path / "mode_model.json"
    save_mode_model(yol, m, skorlar=[0.05] * 12,
                    armlar=["heightmap", "nfv_ham@2"],
                    allowlist=list(allowlist),
                    meta={"surum": "test", "alpha": 0.1})
    return yol


def test_roundtrip_ve_karar(tmp_path):
    mm = load_mode_model(_artefakt(tmp_path))
    assert mm is not None
    sonuc = mm.karar([0.1, 0.9], "long_rod")     # net nfv bolgesi
    assert sonuc is not None and sonuc[0] == "nfv_ham@2"
    assert "mode_model" in sonuc[1]
    assert mm.karar([0.1, 0.9], "thin_shell") is None   # allowlist-disi


def test_genis_kume_sustuturur(tmp_path):
    yol = _artefakt(tmp_path)
    d = json.loads(yol.read_text(encoding="utf-8"))
    d["conformal"]["skorlar"] = [0.999] * 12     # esik ~1.0 -> kume genis
    yol.write_text(json.dumps(d), encoding="utf-8")
    mm = load_mode_model(yol)
    assert mm.karar([0.1, 0.9], "long_rod") is None


def test_load_bozuk_dosya_none(tmp_path):
    yok = tmp_path / "yok.json"
    assert load_mode_model(yok) is None
    bozuk = tmp_path / "bozuk.json"
    bozuk.write_text("{{{", encoding="utf-8")
    assert load_mode_model(bozuk) is None


def _inst_rod():
    # uzun-cubuk agirlikli instance (classify long_rod bekleriz)
    return NestingInstance(
        container=ContainerSpec(width_mm=300.0, depth_mm=300.0),
        parts=[PartSpec(id=f"r{i}", name=f"r{i}", qty=1, source="box",
                        width_mm=8.0, depth_mm=8.0, height_mm=150.0)
               for i in range(6)])


def test_predict_default_bit_ozdes():
    a = predict_nfv_benefit(_inst_rod(), family_routing=True)
    b = predict_nfv_benefit(_inst_rod(), family_routing=True, mode_model=None)
    assert (a.mode, a.reason, a.wall_aware) == (b.mode, b.reason, b.wall_aware)


def test_predict_model_karari_ezer_ve_hata_kurala_duser():
    class SahteModel:
        def karar(self, fv, aile):
            return ("heightmap+wall_aware", "mode_model(test): zorla")

    d = predict_nfv_benefit(_inst_rod(), family_routing=True,
                            mode_model=SahteModel())
    assert d.mode == "heightmap" and d.wall_aware is True
    assert "mode_model" in d.reason

    class PatlayanModel:
        def karar(self, fv, aile):
            raise RuntimeError("bom")

    d2 = predict_nfv_benefit(_inst_rod(), family_routing=True,
                             mode_model=PatlayanModel())
    kural = predict_nfv_benefit(_inst_rod(), family_routing=True)
    assert (d2.mode, d2.reason) == (kural.mode, kural.reason)  # kurala dustu
