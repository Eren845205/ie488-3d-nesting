# -*- coding: utf-8 -*-
"""Telemetri v2 testleri (STRATEJI Faz-2 — append_run_v2 legal-metrik tureyimi).

ANAYASA A2: legal_height ancak (tam yerlesim + clearance>=req + 0 kilit);
olculemeyen bilesen (None) = INVALID. v1 dosya/format bu isten ETKILENMEZ.
"""
import json

from src.nesting3d.telemetry import append_run_v2, load_telemetry


def _base(tmp_path, **kw):
    args = dict(kaynak="pipeline", instance_id="B001", mode="heightmap",
                height_mm=264.0, n_placed=588, n_total=588,
                min_clearance_mm=1.023, n_locked=0)
    args.update(kw)
    return append_run_v2(tmp_path / "v2.jsonl", **args)


def test_v2_legal_satir(tmp_path):
    row = _base(tmp_path)
    assert row["legal_height_mm"] == 264.0
    assert row["invalid_reason"] is None
    assert row["schema"] == 2


def test_v2_clearance_ihlali_invalid(tmp_path):
    row = _base(tmp_path, min_clearance_mm=0.083)
    assert row["legal_height_mm"] is None
    assert "clearance 0.083" in row["invalid_reason"]


def test_v2_kilit_invalid(tmp_path):
    row = _base(tmp_path, n_locked=81)
    assert row["legal_height_mm"] is None
    assert "81 kilit" in row["invalid_reason"]


def test_v2_olculemeyen_invalid(tmp_path):
    # kanitsizlik gecer not degildir (A2)
    row = _base(tmp_path, min_clearance_mm=None)
    assert row["legal_height_mm"] is None and "olculemedi" in row["invalid_reason"]
    row2 = _base(tmp_path, n_locked=None)
    assert row2["legal_height_mm"] is None


def test_v2_eksik_yerlesim_invalid(tmp_path):
    row = _base(tmp_path, n_placed=193)
    assert row["legal_height_mm"] is None and "193/588" in row["invalid_reason"]


def test_v2_append_ve_ekstra_alan(tmp_path):
    p = tmp_path / "v2.jsonl"
    append_run_v2(p, kaynak="eval_gate", instance_id="plan1",
                  mode="heightmap", height_mm=125.0, n_placed=112, n_total=112,
                  min_clearance_mm=1.02, n_locked=0, winning_config="dblf")
    append_run_v2(p, kaynak="pipeline", instance_id="B002", mode="nfv",
                  height_mm=120.7, n_placed=112, n_total=112,
                  min_clearance_mm=0.083, n_locked=81)
    rows = load_telemetry(p)  # v1 okuyucu v2 satirlarini da okuyabilmeli
    assert len(rows) == 2
    assert rows[0]["winning_config"] == "dblf"          # **extra korunur
    assert rows[1]["legal_height_mm"] is None            # illegal NFV ornegi
    # dosya gecerli JSONL
    for line in p.read_text(encoding="utf-8").splitlines():
        json.loads(line)


def test_v2_clearance_req_parametrik(tmp_path):
    # yogun plakada hoca 2mm isterse: ayni olcum farkli esikle INVALID olabilir
    ok = _base(tmp_path, min_clearance_mm=1.5, clearance_req_mm=1.0)
    assert ok["legal_height_mm"] is not None
    bad = _base(tmp_path, min_clearance_mm=1.5, clearance_req_mm=2.0)
    assert bad["legal_height_mm"] is None


# ---------------------------------------------------------------------------
# M1 (2026-08-18): additive alanlar — pitch_coarse, nfv_quality, peak_ram_mb
# (STRATEJI/01_VERI.md §5). v1/eski v2 cagri imzasi DONUK kalir (None-default).
# ---------------------------------------------------------------------------

def test_v2_yeni_alanlar_verilmezse_none(tmp_path):
    """Eski cagri imzasi (yeni parametreler gecilmeden) hala calisir; yeni
    alanlar satirda None olarak gorunur (eksik anahtar degil)."""
    row = _base(tmp_path)
    assert row["pitch_coarse"] is None
    assert row["nfv_quality"] is None
    assert row["peak_ram_mb"] is None


def test_v2_yeni_alanlar_verilince_satira_yazilir(tmp_path):
    row = _base(tmp_path, pitch_coarse=4.0, nfv_quality="max", peak_ram_mb=812.5)
    assert row["pitch_coarse"] == 4.0
    assert row["nfv_quality"] == "max"
    assert row["peak_ram_mb"] == 812.5
    # dosyaya da GERCEKTEN yazilmis mi (JSONL round-trip)
    rows = load_telemetry(tmp_path / "v2.jsonl")
    assert rows[-1]["pitch_coarse"] == 4.0
    assert rows[-1]["nfv_quality"] == "max"
    assert rows[-1]["peak_ram_mb"] == 812.5
