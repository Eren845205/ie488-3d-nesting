"""Faz A2 — scripts/backfill_v2: K-xx olcumlerini telemetri v2'ye geri-doldurma.

Kabul kriterleri (ML plani Faz A2):
  1. Kayit -> v2 satiri: INVALID turetimi append_run_v2'de (d4 heightmap
     288.0 + clear 1.555 @req 2.0 -> legal None + sebep).
  2. Idempotent: ayni kayitlarla ikinci kosum 0 yeni satir (backfill_id).
  3. --dry-run dosyaya yazmaz.
  4. Feature saglayici satira 23'luk vektor + aile gomer; saglanamayan set
     atlanir + sayilir (sessiz iyimserlik yok).
  5. otonom_gecmis detay JSON'u -> kaynak etiketi + olculmemis alanlar None
     (dogal invalid_reason; uydurma deger yok) + kanit_seviyesi=dusuk.
  6. Gercek KAYITLAR transkripsiyon butunlugu: zorunlu alanlar + bilinen
     sampiyon sayilari birebir.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.backfill_v2 import (
    KAYITLAR,
    backfill_id,
    otonom_satirlari,
    satirlari_uret,
)

FAKE_OZ = {
    "feature_vector": [0.1] * 23,
    "feature_names": [f"f{i}" for i in range(23)],
    "family_f1": "mixed_scale",
    "family_conf": 0.7,
}


def _kayit(**o):
    k = dict(set="deneme4", mode="heightmap+wall_aware", recete="n24",
             pitch=0.5, height_mm=288.0, min_clearance_mm=1.555, n_locked=0,
             n_placed=588, n_total=588, duration_s=21.5 * 60,
             clearance_req_mm=2.0, plate=(335.0, 335.0),
             kosu_id="ax24/deneme4_n24", log="scripts/ax24_kuyruk_335.log",
             alinti="[deneme4_n24] h=288.0 ... clear=1.555")
    k.update(o)
    return k


def test_invalid_turetimi_ve_yazim(tmp_path):
    out = tmp_path / "v2.jsonl"
    n_yeni, n_atlanan = satirlari_uret([_kayit()], lambda s: FAKE_OZ, out)
    assert (n_yeni, n_atlanan) == (1, 0)
    s = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert s["legal_height_mm"] is None            # 1.555 < 2.0
    assert "clearance 1.555<2.0" in s["invalid_reason"]
    assert s["kaynak"] == "backfill"
    assert s["recete"] == "n24"
    assert s["kosu_id"] == "ax24/deneme4_n24"
    assert len(s["feature_vector"]) == 23
    assert s["backfill_id"] == backfill_id(_kayit())


def test_idempotent(tmp_path):
    out = tmp_path / "v2.jsonl"
    kayitlar = [_kayit(), _kayit(recete="nfv_ham", mode="nfv",
                               height_mm=231.5, min_clearance_mm=2.018,
                               kosu_id="K-46/nfv_ham")]
    n1, _ = satirlari_uret(kayitlar, lambda s: FAKE_OZ, out)
    n2, _ = satirlari_uret(kayitlar, lambda s: FAKE_OZ, out)
    assert n1 == 2 and n2 == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


def test_dry_run_yazmaz(tmp_path):
    out = tmp_path / "v2.jsonl"
    n, _ = satirlari_uret([_kayit()], lambda s: FAKE_OZ, out, dry_run=True)
    assert n == 1
    assert not out.exists()


def test_feature_saglanamayan_atlanir(tmp_path):
    out = tmp_path / "v2.jsonl"
    n_yeni, n_atlanan = satirlari_uret([_kayit()], lambda s: None, out)
    assert (n_yeni, n_atlanan) == (0, 1)
    assert not out.exists()


def test_otonom_satirlari(tmp_path):
    detay = tmp_path / "detay"
    detay.mkdir()
    (detay / "kosu1.json").write_text(json.dumps({
        "nesting_results": {"B001": {
            "height_mm": 412.0, "n_parts": 40, "nesting_mode_used": "nfv",
            "elapsed_sec": 88.4, "plate_w_mm": 335.0, "plate_d_mm": 335.0,
            "applied_pitch_mm": 2.0}},
    }), encoding="utf-8")
    out = tmp_path / "v2.jsonl"
    n, atlanan = otonom_satirlari(detay, out)
    assert n == 1
    s = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert s["kaynak"] == "otonom_gecmis"
    assert s["kanit_seviyesi"] == "dusuk"
    assert s["legal_height_mm"] is None
    assert "clearance olculemedi" in s["invalid_reason"]
    assert "erisilebilirlik olculemedi" in s["invalid_reason"]
    # idempotent
    n2, _ = otonom_satirlari(detay, out)
    assert n2 == 0


def test_gercek_kayitlar_transkripsiyonu():
    """Elle-transkribe KAYITLAR'in butunlugu (sampiyon sayilari birebir)."""
    zorunlu = {"set", "mode", "recete", "height_mm", "min_clearance_mm",
               "n_locked", "n_placed", "n_total", "clearance_req_mm",
               "plate", "kosu_id", "log", "alinti"}
    for k in KAYITLAR:
        assert zorunlu <= set(k.keys()), f"eksik alan: {k.get('kosu_id')}"
        assert k["plate"] == (335.0, 335.0)
        assert k["clearance_req_mm"] == 2.0
    def _h(set_, recete):
        return [k["height_mm"] for k in KAYITLAR
                if k["set"] == set_ and k["recete"] == recete]
    assert _h("deneme5", "ham@1.0") == [218.0]
    assert _h("deneme5", "ham@2.0") == [223.5]
    assert _h("deneme4", "ham@2.0") == [231.5]
    assert _h("plan2", "guard@2.0") == [544.5]
    assert _h("plan3", "derin@2.0") == [598.5]
    # plan2 ham 532 INVALID satiri da tabloda (29 kilitle)
    p2ham = [k for k in KAYITLAR if k["set"] == "plan2" and k["recete"] == "ham@2.0"]
    assert p2ham and p2ham[0]["n_locked"] == 29
