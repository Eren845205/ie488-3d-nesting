"""test_llm_explainer.py — src/llm/roles/explainer.py testleri.

Kapsam:
  - Algoritma aciklamasi: FakeProvider gecerli JSON -> VALID ExplainerResult
  - Fiyat aciklamasi: FakeProvider fiyat girdi -> VALID, dogan aciklama_md
  - Oncelik aciklamasi: FakeProvider oncelik girdi -> VALID karar_tipi
  - Sayi-topraklama UYARI: aciklamada girdide olmayan rakam -> number_flag=True
  - Topraklama TEMIZ: aciklamadaki rakamlar girdiden geliyor -> number_flag=False
  - Fallback: LLM bozuk JSON donduruyor -> INVALID + fallback
  - Retry: ilk yanit gecersiz, ikinci gecerli -> attempt_count=2, VALID
  - ExplainerInput.to_dict() icerigi dogru
  - ExplainerInput.to_source_doc() SourceDoc olusturuyor
  - ExplainerResult ozellikleri (status, data, fallback, audit_ref)

TDD: FakeProvider — ag baglantisi YOK.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider
from src.llm.roles.explainer import ExplainerInput, ExplainerResult, ExplainerRole
from src.llm.structured import ValidationStatus


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _make_registry() -> PromptRegistry:
    root = Path(__file__).resolve().parent.parent
    return PromptRegistry(
        prompts_dir=str(root / "prompts"),
        enforce_lock=True,
    )


def _make_audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(
        log_dir=tmp_path / "logs" / "llm",
        payload_log_dir=tmp_path / "logs" / "payload",
        payload_logging="none",
    )


def _make_role_cfg() -> RoleConfig:
    return RoleConfig(
        role="explainer",
        provider="fake",
        model="fake-model",
        temperature=0.0,
        max_tokens=512,
        schema_retry=2,
    )


def _valid_explainer_json(
    aciklama: str = "GA secildi cunku tekrar parca var.",
    karar_tipi: str = "algoritma",
    kullanilan_girdiler: list = None,
    topraklama_uyarisi: bool = False,
) -> str:
    return json.dumps(
        {
            "aciklama_md": aciklama,
            "karar_tipi": karar_tipi,
            "kullanilan_girdiler": kullanilan_girdiler or ["kazanan_algoritma"],
            "topraklama_uyarisi": topraklama_uyarisi,
        },
        ensure_ascii=False,
    )


def _algoritma_input() -> ExplainerInput:
    return ExplainerInput(
        karar_tipi="algoritma",
        sistem_ciktisi={
            "kazanan_algoritma": "GA",
            "nesting_yuksekligi_mm": 187.5,
            "doluluk_orani": 0.81,
            "portfoy_kiyasi": [
                {"algoritma": "SA", "yukseklik_mm": 203.0},
                {"algoritma": "GA", "yukseklik_mm": 187.5},
            ],
            "sebep_notlari": "Cok sayida tekrar parca",
        },
    )


def _fiyat_input() -> ExplainerInput:
    return ExplainerInput(
        karar_tipi="fiyat",
        sistem_ciktisi={
            "nihai_fiyat_usd": 2340.0,
            "fiyat_kalemleri": [
                {"kalem": "temel_fiyat", "tutar_usd": 1200.0},
                {"kalem": "mesafe_kademesi", "tutar_usd": 840.0},
                {"kalem": "aci_surcharge", "tutar_usd": 300.0},
            ],
            "mesafe_km": 1450,
        },
    )


def _oncelik_input() -> ExplainerInput:
    return ExplainerInput(
        karar_tipi="oncelik",
        sistem_ciktisi={
            "siralama": [
                {"sira": 1, "siparis_id": "BAYKAR-07", "termin_gun": 5},
                {"sira": 2, "siparis_id": "ASELSAN-12", "termin_gun": 14},
            ],
            "oncelik_kurali": "EDF",
        },
    )


# ---------------------------------------------------------------------------
# TESt: ExplainerInput yapisi
# ---------------------------------------------------------------------------


class TestExplainerInput:
    def test_to_dict_icerigi(self):
        inp = _algoritma_input()
        d = inp.to_dict()
        assert d["karar_tipi"] == "algoritma"
        assert "kazanan_algoritma" in d["sistem_ciktisi"]
        assert d["sistem_ciktisi"]["nesting_yuksekligi_mm"] == 187.5

    def test_to_source_doc_tip_ve_id(self):
        inp = _algoritma_input()
        doc = inp.to_source_doc()
        assert doc.id == "sistem_ciktisi#input"
        assert doc.tip == "termin"
        assert "187.5" in doc.icerik
        assert "GA" in doc.icerik

    def test_to_source_doc_icinde_rakamlar_var(self):
        inp = _fiyat_input()
        doc = inp.to_source_doc()
        assert "2340.0" in doc.icerik
        assert "1200.0" in doc.icerik


# ---------------------------------------------------------------------------
# TEST: Basarili algoritma aciklamasi
# ---------------------------------------------------------------------------


class TestExplainerRoleAlgoritma:
    def test_valid_algoritma_aciklamasi(self, tmp_path):
        aciklama = "GA secildi cunku girdide tekrar parca notu var. Yukseklik 187.5 mm."
        fake_resp = _valid_explainer_json(
            aciklama=aciklama,
            karar_tipi="algoritma",
            kullanilan_girdiler=["kazanan_algoritma", "nesting_yuksekligi_mm"],
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())

        assert result.status == ValidationStatus.VALID
        assert result.fallback is None
        assert result.data is not None
        assert result.data["karar_tipi"] == "algoritma"
        assert "187.5" in result.data["aciklama_md"]
        assert result.audit_ref != ""

    def test_valid_algoritma_kullanilan_girdiler(self, tmp_path):
        fake_resp = _valid_explainer_json(
            kullanilan_girdiler=["kazanan_algoritma", "portfoy_kiyasi"],
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert "kazanan_algoritma" in result.data["kullanilan_girdiler"]
        assert "portfoy_kiyasi" in result.data["kullanilan_girdiler"]


# ---------------------------------------------------------------------------
# TEST: Fiyat aciklamasi
# ---------------------------------------------------------------------------


class TestExplainerRoleFiyat:
    def test_valid_fiyat_aciklamasi(self, tmp_path):
        aciklama = (
            "Toplam fiyat 2340.0 USD. Temel fiyat 1200.0 USD, "
            "mesafe kademesi 840.0 USD, surcharge 300.0 USD."
        )
        fake_resp = _valid_explainer_json(
            aciklama=aciklama,
            karar_tipi="fiyat",
            kullanilan_girdiler=["nihai_fiyat_usd", "fiyat_kalemleri"],
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_fiyat_input())
        assert result.status == ValidationStatus.VALID
        assert result.data["karar_tipi"] == "fiyat"
        assert "2340.0" in result.data["aciklama_md"]


# ---------------------------------------------------------------------------
# TEST: Oncelik aciklamasi
# ---------------------------------------------------------------------------


class TestExplainerRoleOncelik:
    def test_valid_oncelik_aciklamasi(self, tmp_path):
        aciklama = (
            "BAYKAR-07 once isleniyor cunku termini 5 gun kaldi. "
            "ASELSAN-12 ikinci sirada (14 gun). Kural: EDF."
        )
        fake_resp = _valid_explainer_json(
            aciklama=aciklama,
            karar_tipi="oncelik",
            kullanilan_girdiler=["siralama", "oncelik_kurali"],
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_oncelik_input())
        assert result.status == ValidationStatus.VALID
        assert result.data["karar_tipi"] == "oncelik"


# ---------------------------------------------------------------------------
# TEST: Sayi-topraklama
# ---------------------------------------------------------------------------


class TestExplainerTopraklama:
    def test_sayi_topraklama_temiz(self, tmp_path):
        """Aciklamadaki rakamlar girdiden gelince number_flag=False."""
        # 187.5 sistem_ciktisi'nda var
        aciklama = "GA yukseklik 187.5 mm ile kazandi."
        fake_resp = _valid_explainer_json(
            aciklama=aciklama,
            topraklama_uyarisi=False,
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == ValidationStatus.VALID
        assert result.number_flag is False
        assert result.ungrounded_numbers == []

    def test_sayi_topraklama_uyari(self, tmp_path):
        """Aciklamada girdide olmayan rakam kullanilinca number_flag=True."""
        # 999.9 girdide YOK -> topraklama uyarisi
        aciklama = "GA en iyi algoritma, beklenen tasarruf 999.9 USD."
        fake_resp = _valid_explainer_json(
            aciklama=aciklama,
            topraklama_uyarisi=True,
        )
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == ValidationStatus.VALID
        # number_flag=True cunku 999.9 sistem_ciktisi'nda yok
        assert result.number_flag is True
        assert "999.9" in result.ungrounded_numbers

    def test_sayi_topraklama_blok_degil(self, tmp_path):
        """Topraklama uyarisi: UYARI modunda; status INVALID OLMAMALI."""
        aciklama = "Hesaplanamayan deger 77777.0 USD."
        fake_resp = _valid_explainer_json(aciklama=aciklama)
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        # Blok modunda degil: status VALID kalmali
        assert result.status == ValidationStatus.VALID
        assert result.fallback is None
        assert result.number_flag is True


# ---------------------------------------------------------------------------
# TEST: Fallback ve retry
# ---------------------------------------------------------------------------


class TestExplainerFallback:
    def test_bozuk_json_fallback(self, tmp_path):
        """LLM gecersiz JSON donduruyor -> INVALID + fallback."""
        provider = FakeProvider(
            fixture_map={
                ("explainer-v1", "_any_"): [
                    "Bu JSON degil",
                    "Hala JSON degil",
                    "Yine de degil",
                ]
            }
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None
        assert result.fallback.call_ref != ""
        assert result.data is None

    def test_retry_ikinci_yanit_gecerli(self, tmp_path):
        """Ilk yanit bozuk JSON, ikinci yanit gecerli -> VALID, attempt_count=2."""
        gecerli = _valid_explainer_json()
        provider = FakeProvider(
            fixture_map={
                ("explainer-v1", "_any_"): [
                    "gecersiz metin",
                    gecerli,
                ]
            }
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == ValidationStatus.VALID
        assert result.role_result.attempt_count == 2

    def test_eksik_zorunlu_alan_fallback(self, tmp_path):
        """aciklama_md eksik -> schema INVALID -> fallback."""
        bad_json = json.dumps(
            {"karar_tipi": "algoritma", "kullanilan_girdiler": []}
        )
        provider = FakeProvider(
            fixture_map={
                ("explainer-v1", "_any_"): [bad_json, bad_json, bad_json]
            }
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None


# ---------------------------------------------------------------------------
# TEST: ExplainerResult ozellikleri
# ---------------------------------------------------------------------------


class TestExplainerResult:
    def test_result_status_proxy(self, tmp_path):
        gecerli = _valid_explainer_json()
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [gecerli]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.status == result.role_result.status
        assert result.data == result.role_result.data
        assert result.fallback == result.role_result.fallback
        assert result.audit_ref == result.role_result.audit_ref

    def test_topraklama_uyarisi_alani_aktarilir(self, tmp_path):
        """LLM'nin topraklama_uyarisi=true doldurdugu alan data'da gorunmeli."""
        fake_resp = _valid_explainer_json(topraklama_uyarisi=True)
        provider = FakeProvider(
            fixture_map={("explainer-v1", "_any_"): [fake_resp]}
        )
        role = ExplainerRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.explain(_algoritma_input())
        assert result.data is not None
        assert result.data["topraklama_uyarisi"] is True


# ---------------------------------------------------------------------------
# TEST: Prompt registry ve lock hash
# ---------------------------------------------------------------------------


class TestExplainerPrompt:
    def test_prompt_lockfile_eslesmesi(self):
        """Explainer sablon hash'i lock.json ile uyusmali."""
        registry = _make_registry()
        tpl = registry.load("explainer")
        assert tpl.id == "explainer-v1"
        assert tpl.version == "1.0"
        assert len(tpl.examples) == 3

    def test_few_shot_uc_ornek(self):
        registry = _make_registry()
        tpl = registry.load("explainer")
        few_shot_text = tpl.few_shot_text()
        assert "Ornek 1" in few_shot_text
        assert "Ornek 2" in few_shot_text
        assert "Ornek 3" in few_shot_text

    def test_schema_zorunlu_alanlar(self):
        registry = _make_registry()
        tpl = registry.load("explainer")
        required = tpl.schema.get("required", [])
        assert "aciklama_md" in required
        assert "karar_tipi" in required
        assert "kullanilan_girdiler" in required
