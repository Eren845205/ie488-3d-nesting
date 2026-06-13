"""test_llm_report.py — src/llm/roles/report.py testleri (PLAN_LLM.md L1).

Kapsam:
  - Basarili ozet: FakeProvider gecerli JSON dondurur -> VALID ReportResult
  - Topraklama reddi: LLM ciktisinda baglamsiz sayi -> grounding_blocked=True
  - Fallback: LLM bozuk JSON dondurur -> INVALID + fallback
  - ReportInput.to_dict() icerigi dogru
  - ReportResult ozellikleri (status, data, fallback, audit_ref)

TDD: FakeProvider — ag baglatisi YOK.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import GroundedContext, SourceDoc
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider
from src.llm.roles.report import ReportInput, ReportResult, ReportRole
from src.llm.structured import ValidationStatus


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------


def _make_registry(tmp_path: Path) -> PromptRegistry:
    """Gercek prompts/ dizinini kullanir (report sablonu zaten orada)."""
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
        role="report",
        provider="fake",
        model="fake-model",
        temperature=0.0,
        max_tokens=512,
        schema_retry=2,
    )


def _make_context(height_mm: float = 180.0, price: float = 1250.50) -> GroundedContext:
    """Test GroundedContext — gerçek sayilarla."""
    docs = [
        SourceDoc(
            id="yerlesim#B001",
            tip="yerlesim",
            icerik=f"Yukseklik: {height_mm} mm\nDoluluk: 72.3%\nCozucu: DBLF",
            uretici="nesting3d.dblf",
        ),
        SourceDoc(
            id="fiyat#B001",
            tip="fiyat",
            icerik=f"Nihai fiyat: {price} USD",
            uretici="pricing.engine",
        ),
    ]
    return GroundedContext(is_id="test-job", kaynaklar=docs)


def _make_report_input(
    context: GroundedContext = None,
    n_warnings: int = 0,
    total_revenue: float = 1250.50,
) -> ReportInput:
    ctx = context or _make_context()
    return ReportInput(
        is_id="test-job",
        n_orders=3,
        n_batches=2,
        n_warnings=n_warnings,
        total_revenue_usd=total_revenue,
        context=ctx,
    )


def _valid_report_json(
    govde: str = "Bu kosuda 3 siparis 2 partiye ayrildi. Nesting yuksekligi 180.0 mm, doluluk %72.3 olarak gerceklesti. Toplam fiyat 1250.50 USD.",
) -> str:
    return json.dumps({
        "baslik": "Pipeline Sonucu: 3 Siparis, 2 Parti",
        "govde_md": govde,
        "kullanilan_kaynaklar": ["yerlesim#B001", "fiyat#B001"],
        "eksik_bilgi": [],
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Test 1: Basarili ozet
# ---------------------------------------------------------------------------


def test_report_valid_result(tmp_path):
    """FakeProvider gecerli JSON dondurur -> ReportResult.status==VALID."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): [_valid_report_json()]}
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    report_input = _make_report_input()
    result = role.run(report_input)

    assert result.status == ValidationStatus.VALID
    assert result.data is not None
    assert result.data["baslik"] != ""
    assert result.data["govde_md"] != ""
    assert result.fallback is None
    assert result.grounding_blocked is False
    assert result.audit_ref != ""


# ---------------------------------------------------------------------------
# Test 2: Topraklama reddi (BLOK mod)
# ---------------------------------------------------------------------------


def test_report_grounding_blocked(tmp_path):
    """LLM ciktisindaki sayi baglamda yoksa grounding_blocked=True, status=INVALID."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # govde_md'de 9999.99 sayisi baglamda YOK
    bad_govde = "Bu kosuda toplam fiyat 9999.99 USD oldu ve yukseklik 180.0 mm."
    bad_json = json.dumps({
        "baslik": "Hatalı Ozet",
        "govde_md": bad_govde,
        "kullanilan_kaynaklar": ["yerlesim#B001"],
        "eksik_bilgi": [],
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): [bad_json]}
    )

    # Yukseklik 180.0 baglam'da var ama 9999.99 yok
    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    context = _make_context(height_mm=180.0, price=1250.50)
    report_input = _make_report_input(context=context)
    result = role.run(report_input)

    assert result.grounding_blocked is True
    assert result.status == ValidationStatus.INVALID
    assert result.fallback is not None
    assert "9999.99" in result.grounding_detail or len(result.grounding_detail) > 0


# ---------------------------------------------------------------------------
# Test 3: LLM bozuk JSON -> fallback
# ---------------------------------------------------------------------------


def test_report_invalid_json_returns_fallback(tmp_path):
    """LLM bozuk metin dondururse -> INVALID + fallback."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): ["bozuk metin", "yine bozuk", "hala bozuk"]}
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    result = role.run(_make_report_input())

    assert result.status == ValidationStatus.INVALID
    assert result.fallback is not None
    assert result.data is None
    assert result.grounding_blocked is False


# ---------------------------------------------------------------------------
# Test 4: ReportInput.to_dict()
# ---------------------------------------------------------------------------


def test_report_input_to_dict():
    """ReportInput.to_dict() dogru alanlari icerir."""
    ctx = _make_context()
    ri = _make_report_input(context=ctx)
    d = ri.to_dict()

    assert d["is_id"] == "test-job"
    assert d["n_orders"] == 3
    assert d["n_batches"] == 2
    assert d["n_warnings"] == 0
    assert d["total_revenue_usd"] == 1250.50
    assert isinstance(d["kaynaklar"], list)
    assert len(d["kaynaklar"]) == 2
    ids = [k["id"] for k in d["kaynaklar"]]
    assert "yerlesim#B001" in ids
    assert "fiyat#B001" in ids


# ---------------------------------------------------------------------------
# Test 5: Uyari varsa govde_md bunu icermelidir (topraklama gecerse)
# ---------------------------------------------------------------------------


def test_report_with_warnings(tmp_path):
    """n_warnings>0 ile olusturulan ozet topraklama gecerse VALID donmeli."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    govde = "Bu kosuda 2 siparis partilendi. Nesting yuksekligi 180.0 mm, fiyat 1250.50 USD. 1 termin uyarisi var."
    ozet_json = json.dumps({
        "baslik": "Uyarili Sonuc",
        "govde_md": govde,
        "kullanilan_kaynaklar": ["yerlesim#B001", "fiyat#B001"],
        "eksik_bilgi": [],
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): [ozet_json]}
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    result = role.run(_make_report_input(n_warnings=1))

    assert result.status == ValidationStatus.VALID
    assert result.data is not None


# ---------------------------------------------------------------------------
# Test 6: ReportResult ozellikleri
# ---------------------------------------------------------------------------


def test_report_result_properties(tmp_path):
    """ReportResult.status/.data/.fallback/.audit_ref proxy ozellikleri calisir."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): [_valid_report_json()]}
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    result = role.run(_make_report_input())

    assert isinstance(result, ReportResult)
    assert result.status == ValidationStatus.VALID
    assert isinstance(result.audit_ref, str) and result.audit_ref != ""
    assert result.data["kullanilan_kaynaklar"] == ["yerlesim#B001", "fiyat#B001"]


# ---------------------------------------------------------------------------
# Test 7: Normalizasyon — kullanilan_kaynaklar dict elemanlari id string'e indirgenir
# ---------------------------------------------------------------------------


def test_report_normalization_dict_sources_accepted(tmp_path):
    """Model kullanilan_kaynaklar'a tam kaynak dict kopyalarsa normalizasyon id string'e ceker -> VALID."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # Kucuk model halusinasyonu: string ID yerine tam kaynak nesnesi kopyalanmis
    hallucinated_json = json.dumps({
        "baslik": "Pipeline Sonucu: 3 Siparis, 2 Parti",
        "govde_md": (
            "Bu kosuda 3 siparis 2 partiye ayrildi. "
            "Nesting yuksekligi 180.0 mm, doluluk %72.3 olarak gerceklesti. "
            "Toplam fiyat 1250.50 USD."
        ),
        "kullanilan_kaynaklar": [
            {"id": "yerlesim#B001", "tip": "yerlesim", "icerik": "Yukseklik: 180.0 mm"},
            {"id": "fiyat#B001", "tip": "fiyat", "icerik": "Nihai fiyat: 1250.50 USD"},
        ],
        "eksik_bilgi": [],
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={("report-v1", "_any_"): [hallucinated_json]}
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    result = role.run(_make_report_input())

    # Normalizasyon sayesinde schema gecmeli
    assert result.status == ValidationStatus.VALID, (
        f"Normalizasyon sonrasi VALID beklendi, aldi: {result.status}. "
        f"Fallback: {result.fallback}"
    )
    assert result.data is not None
    # id'ler string'e indirgenmeli
    assert "yerlesim#B001" in result.data["kullanilan_kaynaklar"]
    assert "fiyat#B001" in result.data["kullanilan_kaynaklar"]
    assert result.grounding_blocked is False


def test_report_normalization_idless_dict_stays_invalid(tmp_path):
    """id anahtari olmayan dict -> normalizasyon dokunmaz -> schema hatasi surmeli."""
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # id'siz dict: normalizasyon yapmamali -> schema INVALID
    idless_json = json.dumps({
        "baslik": "Test",
        "govde_md": "Test ozeti.",
        "kullanilan_kaynaklar": [
            {"tip": "yerlesim", "icerik": "yok"},  # id anahtari yok
        ],
        "eksik_bilgi": [],
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={
            ("report-v1", "_any_"): [idless_json, idless_json, idless_json]
        }
    )

    role = ReportRole(provider=provider, registry=registry, audit=audit, role_cfg=role_cfg)
    result = role.run(_make_report_input())

    # id'siz dict schema'yi gecemiyor — INVALID olmali
    assert result.status == ValidationStatus.INVALID, (
        "id'siz dict normalizasyon sonrasi hala gecersiz olmali"
    )
