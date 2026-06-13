"""Testler: src/llm/grounding.py — PLAN_LLM.md L0.8.

Kapsanan:
  - SourceDoc validate: gecerli tipler
  - SourceDoc validate: gecersiz tip -> ValueError
  - SourceDoc validate: bos id -> ValueError
  - GroundedContext: kaynak erisim (kaynak_by_id, kaynak_ids)
  - GroundedContext: to_context_text deterministik
  - from_solve_result: SolveResult duck-typing
  - from_pricing_result: PricingResult breakdown satirlari
  - from_schedule_report: scheduling raporu
  - Adapter ciktilari deterministik (ayni giris -> ayni icerik)
  - verify_number_grounding: pozitif (sayi kaynakta var)
  - verify_number_grounding: negatif (sayi kaynakta yok)
  - extract_numbers_from_text: karma formatlari normalize eder
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import pytest

from src.llm.grounding import (
    GroundedContext,
    NumberGroundingResult,
    SourceDoc,
    extract_numbers_from_text,
    from_pricing_result,
    from_schedule_report,
    from_solve_result,
    verify_number_grounding,
)


# ---------------------------------------------------------------------------
# Duck-typing test nesneleri
# ---------------------------------------------------------------------------


@dataclass
class MockPlacement:
    part_id: str = "p1"
    name: str = "braket"
    x: int = 0
    y: int = 0
    z: int = 0
    orientation_idx: int = 0


@dataclass
class MockSolveResult:
    bin_id: str = "bin1"
    height_mm: float = 181.5
    utilization: float = 0.72
    solver_name: str = "SA3D"
    seed: int = 42
    placements: List[MockPlacement] = field(default_factory=list)


@dataclass
class MockBreakdownLine:
    rule_id: str
    rule_type: str
    rule_description: str
    input_field: Optional[str]
    input_value: Optional[float]
    intermediate_value: float
    subtotal_after: float
    note: str = ""


@dataclass
class MockPricingResult:
    total_price: float = 1250.0
    breakdown: List[MockBreakdownLine] = field(default_factory=list)
    rule_set_name: str = "test_ruleset"
    rule_set_version: str = "1.0"


@dataclass
class MockScheduleReport:
    markdown: str = "## Cizelge\n\n| Siparis | Termin |\n|---|---|\n| S001 | 2026-07-01 |"
    warnings: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# SourceDoc
# ---------------------------------------------------------------------------


def test_source_doc_valid():
    doc = SourceDoc(id="yerlesim#bin1", tip="yerlesim", icerik="icerik", uretici="sa3d")
    doc.validate()  # hata olmamali


def test_source_doc_invalid_type_raises():
    doc = SourceDoc(id="x", tip="bilinmeyen", icerik="", uretici="test")
    with pytest.raises(ValueError, match="gecersiz tip"):
        doc.validate()


def test_source_doc_empty_id_raises():
    doc = SourceDoc(id="", tip="yerlesim", icerik="", uretici="test")
    with pytest.raises(ValueError, match="id bos olamaz"):
        doc.validate()


def test_source_doc_all_valid_types():
    for tip in ("yerlesim", "fiyat", "termin", "telemetri", "siparis_notu"):
        doc = SourceDoc(id=f"test#{tip}", tip=tip, icerik="", uretici="")
        doc.validate()


def test_source_doc_to_dict():
    doc = SourceDoc(id="fiyat#r1", tip="fiyat", icerik="icerik", uretici="engine", versiyon="1.0")
    d = doc.to_dict()
    assert d["id"] == "fiyat#r1"
    assert d["versiyon"] == "1.0"


# ---------------------------------------------------------------------------
# GroundedContext
# ---------------------------------------------------------------------------


def test_grounded_context_kaynak_by_id():
    doc = SourceDoc(id="yerlesim#bin1", tip="yerlesim", icerik="x", uretici="sa3d")
    ctx = GroundedContext(is_id="job1", kaynaklar=[doc])
    found = ctx.kaynak_by_id("yerlesim#bin1")
    assert found is doc


def test_grounded_context_kaynak_by_id_not_found():
    ctx = GroundedContext(is_id="job1", kaynaklar=[])
    assert ctx.kaynak_by_id("nonexistent") is None


def test_grounded_context_kaynak_ids():
    docs = [
        SourceDoc(id="yerlesim#bin1", tip="yerlesim", icerik="", uretici=""),
        SourceDoc(id="fiyat#r1", tip="fiyat", icerik="", uretici=""),
    ]
    ctx = GroundedContext(is_id="j1", kaynaklar=docs)
    ids = ctx.kaynak_ids()
    assert "yerlesim#bin1" in ids
    assert "fiyat#r1" in ids


def test_grounded_context_to_context_text():
    doc = SourceDoc(id="yerlesim#bin1", tip="yerlesim", icerik="icerik metni", uretici="sa3d")
    ctx = GroundedContext(is_id="j1", kaynaklar=[doc])
    text = ctx.to_context_text()
    assert "yerlesim#bin1" in text
    assert "icerik metni" in text


def test_grounded_context_empty():
    ctx = GroundedContext(is_id="empty_job")
    assert ctx.kaynak_ids() == []
    assert ctx.to_context_text() == ""


# ---------------------------------------------------------------------------
# from_solve_result
# ---------------------------------------------------------------------------


def test_from_solve_result_basic():
    sr = MockSolveResult(bin_id="bin1", height_mm=181.5, utilization=0.72)
    doc = from_solve_result(sr)
    assert doc.id == "yerlesim#bin1"
    assert doc.tip == "yerlesim"
    assert "181.5" in doc.icerik
    assert "SA3D" in doc.icerik
    assert "42" in doc.icerik  # seed


def test_from_solve_result_with_placements():
    sr = MockSolveResult(
        bin_id="bin2",
        placements=[
            MockPlacement(part_id="p1", name="braket", x=0, y=0, z=0, orientation_idx=1),
            MockPlacement(part_id="p2", name="ring", x=5, y=5, z=3, orientation_idx=0),
        ]
    )
    doc = from_solve_result(sr)
    assert "p1" in doc.icerik
    assert "braket" in doc.icerik
    assert "ring" in doc.icerik


def test_from_solve_result_deterministic():
    sr = MockSolveResult()
    doc1 = from_solve_result(sr)
    doc2 = from_solve_result(sr)
    assert doc1.icerik == doc2.icerik


def test_from_solve_result_no_seed():
    @dataclass
    class NoSeedResult:
        bin_id: str = "bin0"
        height_mm: float = 100.0
        utilization: float = 0.5
        solver_name: str = "DBLF"
        placements: list = field(default_factory=list)

    sr = NoSeedResult()
    doc = from_solve_result(sr)
    assert "DBLF" in doc.icerik
    assert doc.id == "yerlesim#bin0"


# ---------------------------------------------------------------------------
# from_pricing_result
# ---------------------------------------------------------------------------


def test_from_pricing_result_basic():
    pr = MockPricingResult(
        total_price=1250.0,
        breakdown=[
            MockBreakdownLine(
                rule_id="r1", rule_type="unit_price",
                rule_description="Hacim bazli", input_field="hacim_m3",
                input_value=5.0, intermediate_value=2500.0, subtotal_after=2500.0,
                note="5.0 * 500.0"
            )
        ]
    )
    docs = from_pricing_result(pr)
    assert len(docs) == 1
    assert docs[0].id == "fiyat#r1"
    assert docs[0].tip == "fiyat"
    assert "1250" in docs[0].icerik
    assert "hacim_m3" in docs[0].icerik


def test_from_pricing_result_multiple_breakdowns():
    pr = MockPricingResult(
        breakdown=[
            MockBreakdownLine("r1", "unit_price", "D1", "h", 5.0, 100.0, 100.0),
            MockBreakdownLine("r2", "tier_table", "D2", "k", 10.0, 200.0, 300.0),
        ]
    )
    docs = from_pricing_result(pr)
    assert len(docs) == 2
    ids = [d.id for d in docs]
    assert "fiyat#r1" in ids
    assert "fiyat#r2" in ids


def test_from_pricing_result_deterministic():
    pr = MockPricingResult(
        breakdown=[
            MockBreakdownLine("r1", "unit_price", "D", "h", 5.0, 100.0, 100.0)
        ]
    )
    docs1 = from_pricing_result(pr)
    docs2 = from_pricing_result(pr)
    assert docs1[0].icerik == docs2[0].icerik


def test_from_pricing_result_empty_breakdown():
    pr = MockPricingResult(breakdown=[])
    docs = from_pricing_result(pr)
    assert docs == []


# ---------------------------------------------------------------------------
# from_schedule_report
# ---------------------------------------------------------------------------


def test_from_schedule_report_markdown():
    report = MockScheduleReport(markdown="## Cizelge\nDurum: OK")
    doc = from_schedule_report(report)
    assert doc.tip == "termin"
    assert "Cizelge" in doc.icerik
    assert doc.id == "termin#cizelge"


def test_from_schedule_report_with_dict():
    report_dict = {"markdown": "## Rapor\nOk", "warnings": []}
    doc = from_schedule_report(report_dict)
    assert "Rapor" in doc.icerik


def test_from_schedule_report_deterministic():
    report = MockScheduleReport()
    doc1 = from_schedule_report(report)
    doc2 = from_schedule_report(report)
    assert doc1.icerik == doc2.icerik


# ---------------------------------------------------------------------------
# extract_numbers_from_text
# ---------------------------------------------------------------------------


def test_extract_numbers_integer():
    nums = extract_numbers_from_text("Adet: 10 parca")
    assert "10" in nums


def test_extract_numbers_float():
    nums = extract_numbers_from_text("Yukseklik: 181.5 mm")
    assert "181.5" in nums


def test_extract_numbers_comma_decimal():
    nums = extract_numbers_from_text("Carpan: 181,5")
    assert "181.5" in nums


def test_extract_numbers_empty():
    nums = extract_numbers_from_text("hicbir sayi yok burada.")
    assert nums == []


# ---------------------------------------------------------------------------
# verify_number_grounding
# ---------------------------------------------------------------------------


def test_verify_grounding_positive():
    """LLM ciktisindaki sayi kaynakta var -> is_clean=True."""
    doc = SourceDoc(
        id="yerlesim#bin1", tip="yerlesim",
        icerik="Yukseklik: 181.5 mm, Doluluk: 72%",
        uretici="sa3d"
    )
    result = verify_number_grounding("Yukseklik 181.5 mm'dir.", [doc])
    assert result.is_clean
    assert "181.5" in result.grounded


def test_verify_grounding_negative():
    """LLM ciktisindaki sayi kaynakta yok -> is_clean=False."""
    doc = SourceDoc(
        id="yerlesim#bin1", tip="yerlesim",
        icerik="Yukseklik: 181.5 mm",
        uretici="sa3d"
    )
    result = verify_number_grounding("Yukseklik 200 mm'dir.", [doc])
    assert not result.is_clean
    assert "200" in result.ungrounded


def test_verify_grounding_comma_normalization():
    """181,5 ve 181.5 esit sayilmali."""
    doc = SourceDoc(
        id="y1", tip="yerlesim",
        icerik="Mesafe: 181.5 mm",
        uretici="test"
    )
    result = verify_number_grounding("Mesafe 181,5'tir.", [doc])
    assert result.is_clean


def test_verify_grounding_no_numbers_in_text():
    doc = SourceDoc(id="y1", tip="yerlesim", icerik="100 kg", uretici="")
    result = verify_number_grounding("Hicbir sayi yok.", [doc])
    assert result.is_clean
    assert result.grounded == []
    assert result.ungrounded == []


def test_verify_grounding_multiple_sources():
    """Birden fazla kaynak; sayi herhangi birinde varsa grounded."""
    doc1 = SourceDoc(id="y1", tip="yerlesim", icerik="Yukseklik: 181.5", uretici="")
    doc2 = SourceDoc(id="f1", tip="fiyat", icerik="Toplam: 1250 TL", uretici="")
    result = verify_number_grounding("Yukseklik 181.5, fiyat 1250.", [doc1, doc2])
    assert result.is_clean


# ---------------------------------------------------------------------------
# M1: Float deger esitligi — "72" vs "72.0", "181.5" vs "181.50"
# ---------------------------------------------------------------------------


def test_verify_grounding_int_vs_float_string():
    """Kaynak '72.0', LLM '72' yazarsa esit sayilmali (false ungrounded olmamali)."""
    doc = SourceDoc(id="y1", tip="yerlesim", icerik="Doluluk: 72.0%", uretici="test")
    result = verify_number_grounding("Doluluk orani 72.", [doc])
    assert result.is_clean, f"ungrounded: {result.ungrounded}"


def test_verify_grounding_float_trailing_zero():
    """Kaynak '181.5', LLM '181.50' yazarsa esit sayilmali."""
    doc = SourceDoc(id="y1", tip="yerlesim", icerik="Yukseklik: 181.5 mm", uretici="test")
    result = verify_number_grounding("Sonuc: 181.50 mm", [doc])
    assert result.is_clean, f"ungrounded: {result.ungrounded}"


def test_verify_grounding_float_vs_int_reverse():
    """Kaynak '72', LLM '72.0' yazarsa esit sayilmali."""
    doc = SourceDoc(id="y1", tip="yerlesim", icerik="Adet: 72 parca", uretici="test")
    result = verify_number_grounding("Toplam 72.0 parca.", [doc])
    assert result.is_clean, f"ungrounded: {result.ungrounded}"


# ---------------------------------------------------------------------------
# M3: GroundedContext.to_context_text() olusturma_zamani ICERMEMELI
# ---------------------------------------------------------------------------


def test_to_context_text_does_not_contain_olusturma_zamani():
    """to_context_text() ciktisi olusturma_zamani degerini icermemeli.

    Bu test deterministik sozlesmeyi korur: timestamp prompt'a sizarsa
    ayni kaynak farkli oturumlarda farkli prompt uretir (non-determinizm).
    """
    doc = SourceDoc(id="yerlesim#bin1", tip="yerlesim", icerik="Yukseklik: 181.5", uretici="sa3d")
    ctx = GroundedContext(is_id="job1", kaynaklar=[doc])
    text = ctx.to_context_text()
    # olusturma_zamani ISO timestamp icermesin (ornek: "2026-06-12T...")
    assert ctx.olusturma_zamani not in text, (
        "to_context_text() olusturma_zamani degerini iceriyor — "
        "determinizm sozlesmesi ihlal edildi."
    )
