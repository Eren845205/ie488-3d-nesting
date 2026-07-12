"""Faz A1 — scripts/kxx_telemetri.kaydet: K-xx deney scriptleri icin
mod-duzeyi telemetri v2 sarmalayicisi.

Kabul kriterleri (ML plani Faz A1):
  1. kaydet(...) v2 satirini verilen dosyaya yazar; append_run_v2'nin
     legal-turetimi calisir (kilit>0 -> legal None + invalid_reason).
  2. kosu_id / log_yolu eksik veya bos -> ValueError (kaynak-izi zorunlu).
  3. mode kanon-disi -> ValueError.
  4. recete/kosu_id/log extra alanlari satirda korunur (schema additive).
  5. ozellik_cikar(instance) -> feature_vector(23)+names+family; kaydet'e
     instance verilirse satira gomulur.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.kxx_telemetri import GECERLI_MODLAR, kaydet, ozellik_cikar
from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec


def _inst():
    return NestingInstance(
        container=ContainerSpec(width_mm=100.0, depth_mm=100.0),
        parts=[PartSpec(id="rod", name="rod", qty=6, source="box",
                        width_mm=8.0, depth_mm=8.0, height_mm=60.0)],
    )


def _kaydet(tmp_path, **override):
    kw = dict(
        instance_id="deneme5", mode="nfv", recete="ham@1.0",
        height_mm=218.0, n_placed=352, n_total=352,
        min_clearance_mm=2.000, n_locked=0, duration_s=344.6 * 60,
        kosu_id="K-47a/ham", log_yolu="scripts/k47a_d5_pitch1.log",
        pitch=1.0, seed=42, path=tmp_path / "v2.jsonl",
    )
    kw.update(override)
    return kaydet(**kw)


def _satirlar(p: Path):
    return [json.loads(s) for s in p.read_text(encoding="utf-8").splitlines()]


def test_satir_yazilir_ve_legal_turetilir(tmp_path):
    row = _kaydet(tmp_path)
    satirlar = _satirlar(tmp_path / "v2.jsonl")
    assert len(satirlar) == 1
    s = satirlar[0]
    assert s["schema"] == 2
    assert s["mode"] == "nfv"
    assert s["legal_height_mm"] == 218.0          # kilit 0 + clear 2.0 >= 2.0
    assert s["recete"] == "ham@1.0"
    assert s["kosu_id"] == "K-47a/ham"
    assert s["log"] == "scripts/k47a_d5_pitch1.log"
    assert s["kaynak"] == "deney"
    assert s["clearance_req_mm"] == 2.0
    assert row["legal_height_mm"] == 218.0


def test_kilitli_kosu_invalid_turetilir(tmp_path):
    _kaydet(tmp_path, n_locked=29, height_mm=532.0, instance_id="plan2",
            kosu_id="K-39b/p2", log_yolu="scripts/k39b_plan2_nfv_v2.log")
    s = _satirlar(tmp_path / "v2.jsonl")[0]
    assert s["legal_height_mm"] is None
    assert "29 kilit" in s["invalid_reason"]


def test_kosu_id_zorunlu(tmp_path):
    with pytest.raises(ValueError):
        _kaydet(tmp_path, kosu_id="")
    with pytest.raises(ValueError):
        _kaydet(tmp_path, log_yolu=None)


def test_mode_kanonu(tmp_path):
    for m in GECERLI_MODLAR:
        _kaydet(tmp_path, mode=m)
    with pytest.raises(ValueError):
        _kaydet(tmp_path, mode="nfv_guard")   # recete'ye ait, mode DEGIL


def test_ozellik_cikar_ve_gomme(tmp_path):
    oz = ozellik_cikar(_inst())
    assert len(oz["feature_vector"]) == len(oz["feature_names"]) == 23
    assert oz["family_f1"]
    _kaydet(tmp_path, instance=_inst())
    s = _satirlar(tmp_path / "v2.jsonl")[0]
    assert len(s["feature_vector"]) == 23
    assert s["family_f1"] == oz["family_f1"]
