"""Testler: src/llm/audit.py — PLAN_LLM.md L0.6.

Kapsanan:
  - AuditRecord round-trip (to_dict/from_dict/to_jsonl_line)
  - AuditLogger.log() -> audit.jsonl'e yazar
  - AuditLogger.read_records() -> kayitlari okur
  - Maliyet tahmini hesabi
  - payload_logging="none" -> payload dizinine yazilmaz
  - payload_logging="redacted" -> messages govdesi YAZILMAZ, istatistik kalir (C2)
  - payload_logging="full" -> ham metin korunur, e-posta/telefon maskelenir
  - redact_text: e-posta maskesi
  - redact_text: Turkiye telefon maskesi
  - Birden fazla cagri -> birden fazla JSONL satiri
  - _redact_payload JSON parse hatasi -> guvenli fallback (M5)
  - AuditRecord.ref benzersizligi (H2)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.llm.audit import AuditLogger, AuditRecord, redact_text
from src.llm.provider import LLMRequest, LLMResponse
from src.llm.structured import ValidationStatus


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------


def _make_req(template_id: str = "t1") -> LLMRequest:
    return LLMRequest(
        messages=[
            {"role": "system", "content": "Sistem talimati."},
            {"role": "user", "content": "test mesaji"},
        ],
        schema={"type": "object"},
        template_id=template_id,
        role_tag="parser",
    )


def _make_resp(text: str = '{"ad": "test"}') -> LLMResponse:
    return LLMResponse(
        text=text,
        usage_in=100,
        usage_out=20,
        latency_s=1.5,
        model_id="claude-haiku-20240307",
        finish_reason="stop",
    )


def _make_logger(tmp_path: Path, payload_logging: str = "none") -> AuditLogger:
    return AuditLogger(
        log_dir=tmp_path / "logs" / "llm",
        payload_log_dir=tmp_path / "logs" / "llm" / "payload",
        payload_logging=payload_logging,
        in_price_per_m=1.0,
        out_price_per_m=5.0,
    )


# ---------------------------------------------------------------------------
# AuditRecord
# ---------------------------------------------------------------------------


def test_audit_record_to_dict():
    rec = AuditRecord(
        ts="2026-06-13T10:00:00Z",
        role="parser",
        template_id="parser-v1",
        template_version="1.0",
        content_hash="abc123",
        model="claude-haiku",
        usage_in=100,
        usage_out=20,
        cost_usd_estimate=0.0001,
        latency_s=1.5,
        status="VALID",
        payload_ref=None,
    )
    d = rec.to_dict()
    assert d["role"] == "parser"
    assert d["usage_in"] == 100
    assert d["payload_ref"] is None
    # H2: ref olmali
    assert "ref" in d
    assert isinstance(d["ref"], str)


def test_audit_record_round_trip():
    rec = AuditRecord(
        ts="2026-06-13T10:00:00Z",
        role="assistant",
        template_id="assistant-v1",
        template_version="1.0",
        content_hash="def456",
        model="claude-sonnet",
        usage_in=500,
        usage_out=80,
        cost_usd_estimate=0.0015,
        latency_s=2.3,
        status="FALLBACK",
        payload_ref="assistant_abc123.json",
    )
    d = rec.to_dict()
    rec2 = AuditRecord.from_dict(d)
    assert rec2.role == rec.role
    assert rec2.usage_in == rec.usage_in
    assert rec2.payload_ref == rec.payload_ref


def test_audit_record_to_jsonl_line():
    rec = AuditRecord(
        ts="2026-06-13T10:00:00Z",
        role="tuner",
        template_id="tuner-v1",
        template_version="1.0",
        content_hash="xyz",
        model="haiku",
        usage_in=50,
        usage_out=10,
        cost_usd_estimate=0.0,
        latency_s=0.5,
        status="VALID",
    )
    line = rec.to_jsonl_line()
    parsed = json.loads(line)
    assert parsed["role"] == "tuner"


# ---------------------------------------------------------------------------
# AuditLogger: temel log
# ---------------------------------------------------------------------------


def test_audit_logger_creates_jsonl(tmp_path):
    logger = _make_logger(tmp_path)
    req = _make_req()
    resp = _make_resp()
    record = logger.log(
        role="parser",
        template_id="parser-v1",
        template_version="1.0",
        content_hash="abc123",
        req=req,
        resp=resp,
        status=ValidationStatus.VALID,
    )
    audit_file = logger.audit_path
    assert audit_file.exists()
    lines = audit_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["role"] == "parser"
    assert data["status"] == "VALID"


def test_audit_logger_multiple_calls_append(tmp_path):
    logger = _make_logger(tmp_path)
    for _ in range(3):
        logger.log(
            role="parser",
            template_id="parser-v1",
            template_version="1.0",
            content_hash="hash",
            req=_make_req(),
            resp=_make_resp(),
            status="RETRY",
        )
    records = logger.read_records()
    assert len(records) == 3


def test_audit_logger_read_records_empty(tmp_path):
    logger = _make_logger(tmp_path)
    records = logger.read_records()
    assert records == []


# ---------------------------------------------------------------------------
# Maliyet tahmini
# ---------------------------------------------------------------------------


def test_cost_estimate():
    """100 girdi + 20 cikti; in_price=1$/M, out_price=5$/M -> 0.0001 + 0.0001 = 0.0002"""
    logger = AuditLogger(
        log_dir="/tmp/audit_test",
        payload_log_dir="/tmp/audit_payload",
        payload_logging="none",
        in_price_per_m=1.0,
        out_price_per_m=5.0,
    )
    cost = logger._estimate_cost(100, 20)
    expected = (100 * 1.0 + 20 * 5.0) / 1_000_000
    assert abs(cost - expected) < 1e-10


def test_cost_estimate_zero_price():
    logger = _make_logger(Path("/tmp"), "none")
    # fiyat belirtilmemis -> 0
    logger2 = AuditLogger(
        log_dir="/tmp",
        payload_log_dir="/tmp",
        payload_logging="none",
        in_price_per_m=0.0,
        out_price_per_m=0.0,
    )
    assert logger2._estimate_cost(1000, 500) == 0.0


# ---------------------------------------------------------------------------
# payload_logging
# ---------------------------------------------------------------------------


def test_payload_logging_none_no_payload_file(tmp_path):
    logger = _make_logger(tmp_path, payload_logging="none")
    logger.log(
        role="parser",
        template_id="parser-v1",
        template_version="1.0",
        content_hash="h",
        req=_make_req(),
        resp=_make_resp(),
        status=ValidationStatus.VALID,
    )
    payload_dir = tmp_path / "logs" / "llm" / "payload"
    if payload_dir.exists():
        payload_files = list(payload_dir.glob("*.json"))
        assert len(payload_files) == 0


def test_payload_logging_full_writes_payload(tmp_path):
    logger = _make_logger(tmp_path, payload_logging="full")
    record = logger.log(
        role="parser",
        template_id="parser-v1",
        template_version="1.0",
        content_hash="h",
        req=_make_req(),
        resp=_make_resp(text='{"musteri": "Ahmet Yilmaz"}'),
        status=ValidationStatus.VALID,
    )
    assert record.payload_ref is not None
    payload_file = tmp_path / "logs" / "llm" / "payload" / record.payload_ref
    assert payload_file.exists()
    content = json.loads(payload_file.read_text(encoding="utf-8"))
    assert "Ahmet Yilmaz" in json.dumps(content)


def test_payload_logging_redacted_no_messages_body(tmp_path):
    """C2: redacted modda messages govdesi payload dosyasina YAZILMAMALI."""
    audit_logger = _make_logger(tmp_path, payload_logging="redacted")
    req = LLMRequest(
        messages=[
            {"role": "system", "content": "Sistem talimati."},
            {"role": "user", "content": "Parca boyutu 50x30 mm, adet: 100, email: test@example.com"},
        ],
        schema={},
        template_id="t1",
    )
    resp = LLMResponse(text='{"sonuc": "ok"}')
    record = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=req,
        resp=resp,
        status=ValidationStatus.VALID,
    )
    payload_file = tmp_path / "logs" / "llm" / "payload" / record.payload_ref
    content = json.loads(payload_file.read_text(encoding="utf-8"))
    # Govde yazilmamali
    request_block = content["request"]
    assert "messages" not in request_block, "redacted modda messages govdesi yazilmamali"
    # Istatistik olmali
    assert "messages_stats" in request_block
    assert request_block["messages_stats"]["count"] == 2
    assert "system" in request_block["messages_stats"]["roles"]
    assert "user" in request_block["messages_stats"]["roles"]
    assert request_block["messages_stats"]["total_chars_approx"] > 0
    # Govdedeki hassas veri (boyut/adet/email) payload'da gozukmemeli
    raw = payload_file.read_text(encoding="utf-8")
    assert "50x30 mm" not in raw
    assert "adet: 100" not in raw
    assert "test@example.com" not in raw


def test_payload_logging_redacted_response_email_masked(tmp_path):
    """C2: redacted modda yanit metnindeki e-posta maskelenmeli."""
    audit_logger = _make_logger(tmp_path, payload_logging="redacted")
    req = LLMRequest(
        messages=[{"role": "user", "content": "soru"}],
        schema={},
        template_id="t1",
    )
    resp = LLMResponse(text='{"not": "musteri@firma.com haberdar edildi"}')
    record = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=req,
        resp=resp,
        status=ValidationStatus.VALID,
    )
    payload_file = tmp_path / "logs" / "llm" / "payload" / record.payload_ref
    raw = payload_file.read_text(encoding="utf-8")
    assert "musteri@firma.com" not in raw
    assert "<EMAIL>" in raw


def test_payload_logging_redacted_record_ref_in_audit(tmp_path):
    logger = _make_logger(tmp_path, payload_logging="redacted")
    record = logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=_make_req(),
        resp=_make_resp(),
        status="VALID",
    )
    assert record.payload_ref is not None
    # Audit JSONL'de de payload_ref var
    records = logger.read_records()
    assert records[-1].payload_ref == record.payload_ref


# ---------------------------------------------------------------------------
# redact_text
# ---------------------------------------------------------------------------


def test_redact_email():
    text = "Iletisim: ahmet@example.com adresine gonder."
    redacted = redact_text(text)
    assert "ahmet@example.com" not in redacted
    assert "<EMAIL>" in redacted


def test_redact_turkish_phone():
    text = "Tel: 05321234567 ve +90 532 123 4567"
    redacted = redact_text(text)
    assert "0532" not in redacted
    assert "<PHONE>" in redacted


def test_redact_preserves_non_pii():
    text = "Parca boyutu 50x30x20 mm, adet: 100"
    redacted = redact_text(text)
    assert "50x30x20 mm" in redacted
    assert "100" in redacted


def test_redact_multiple_emails():
    text = "a@b.com ve c@d.org ve e@f.net"
    redacted = redact_text(text)
    assert redacted.count("<EMAIL>") == 3


# ---------------------------------------------------------------------------
# H2: ref benzersizligi
# ---------------------------------------------------------------------------


def test_audit_record_has_ref_field():
    """H2: AuditRecord ref alani olmali ve JSONL'e yazilmali."""
    rec = AuditRecord(
        ts="2026-06-13T10:00:00Z",
        role="parser",
        template_id="parser-v1",
        template_version="1.0",
        content_hash="abc123",
        model="claude-haiku",
        usage_in=100,
        usage_out=20,
        cost_usd_estimate=0.0001,
        latency_s=1.5,
        status="VALID",
    )
    assert hasattr(rec, "ref")
    assert isinstance(rec.ref, str)
    assert len(rec.ref) == 12
    # to_dict'te olmali
    d = rec.to_dict()
    assert "ref" in d
    # JSONL satirinda olmali
    line = rec.to_jsonl_line()
    parsed = json.loads(line)
    assert "ref" in parsed


def test_two_records_have_different_refs(tmp_path):
    """H2: Ayni anda uretilen iki kayit farkli ref tasimali."""
    audit_logger = _make_logger(tmp_path)
    req = _make_req()
    resp = _make_resp()
    rec1 = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=req,
        resp=resp,
        status="VALID",
    )
    rec2 = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=req,
        resp=resp,
        status="VALID",
    )
    assert rec1.ref != rec2.ref


def test_ref_written_to_jsonl(tmp_path):
    """H2: ref degeri audit.jsonl satirana yazilmali."""
    audit_logger = _make_logger(tmp_path)
    rec = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=_make_req(),
        resp=_make_resp(),
        status="VALID",
    )
    lines = audit_logger.audit_path.read_text(encoding="utf-8").strip().split("\n")
    data = json.loads(lines[-1])
    assert "ref" in data
    assert data["ref"] == rec.ref


# ---------------------------------------------------------------------------
# M5: _redact_payload guvenli fallback
# ---------------------------------------------------------------------------


def test_redact_payload_fallback_on_corrupt_json(monkeypatch):
    """M5: _redact_payload redaksiyon JSON'u bozarsa guvenli fallback donmeli."""
    from src.llm import audit as audit_mod

    # redact_text'i bozuk JSON uretecek sekilde monkeypatch et
    monkeypatch.setattr(audit_mod, "redact_text", lambda s: s + '"}CORRUPT')

    result = audit_mod._redact_payload({"key": "value@test.com"})
    assert result.get("error") == "redaction_failed"
    assert "ts" in result


def test_redact_payload_fallback_written_to_file(tmp_path, monkeypatch):
    """M5: redaction_failed fallback payload dosyasina yazilmali."""
    from src.llm import audit as audit_mod

    monkeypatch.setattr(audit_mod, "redact_text", lambda s: s + '"}CORRUPT')

    audit_logger = _make_logger(tmp_path, payload_logging="redacted")
    rec = audit_logger.log(
        role="parser",
        template_id="t1",
        template_version="1.0",
        content_hash="h",
        req=_make_req(),
        resp=_make_resp(),
        status="VALID",
    )
    assert rec.payload_ref is not None
    payload_file = tmp_path / "logs" / "llm" / "payload" / rec.payload_ref
    content = json.loads(payload_file.read_text(encoding="utf-8"))
    assert content.get("error") == "redaction_failed"
    assert "ts" in content
