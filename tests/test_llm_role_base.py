"""Testler: src/llm/roles/base.py — PLAN_LLM.md L0.7.

Kapsanan:
  - LLMRole.run(): gecerli yanit -> RoleResult(VALID, data, audit_ref)
  - LLMRole.run(): sahte uctan-uca (FakeProvider + tmp prompt dizini)
  - Audit satiri her cagri sonrasi yazilir
  - INVALID+retry -> fallback ile RoleResult
  - role_cfg None ise varsayilan degerler kullanilir
  - Yanit PARTIAL ise RoleResult.data dolu, fallback None
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider, LLMRequest, _input_hash
from src.llm.roles.base import LLMRole, RoleResult
from src.llm.structured import ValidationStatus


# ---------------------------------------------------------------------------
# Yardimci: minimal sablon dizini olustur (prompts.py testleriyle ayni desen)
# ---------------------------------------------------------------------------


def _make_template_dir(
    tmp_path: Path,
    role: str = "test_role",
    system_content: str = "Sistem {{few_shot}}",
    schema: dict = None,
) -> Path:
    role_dir = tmp_path / "prompts" / role
    role_dir.mkdir(parents=True)
    meta = {"id": f"{role}-v1", "version": "1.0", "model_hint": "test"}
    (role_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (role_dir / "system.md").write_text(system_content, encoding="utf-8")
    (role_dir / "schema.json").write_text(
        json.dumps(schema or _default_schema()), encoding="utf-8"
    )
    return role_dir


def _default_schema() -> dict:
    return {
        "type": "object",
        "required": ["ad", "adet"],
        "properties": {
            "ad": {"type": "string"},
            "adet": {"type": "integer"},
        },
        "additionalProperties": False,
    }


def _make_registry(tmp_path: Path) -> PromptRegistry:
    return PromptRegistry(tmp_path / "prompts", enforce_lock=False)


def _make_audit(tmp_path: Path, payload_logging: str = "none") -> AuditLogger:
    return AuditLogger(
        log_dir=tmp_path / "logs" / "llm",
        payload_log_dir=tmp_path / "logs" / "payload",
        payload_logging=payload_logging,
    )


def _make_role_cfg(
    role: str = "test_role",
    model: str = "fake-model",
    schema_retry: int = 2,
) -> RoleConfig:
    return RoleConfig(
        role=role,
        provider="fake",
        model=model,
        temperature=0.0,
        max_tokens=512,
        schema_retry=schema_retry,
    )


# ---------------------------------------------------------------------------
# Gecerli yanit -> VALID
# ---------------------------------------------------------------------------


def test_role_run_valid(tmp_path):
    _make_template_dir(tmp_path, "test_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("test_role-v1", "_any_"): ['{"ad": "braket", "adet": 5}']}
    )

    role = LLMRole(
        role_name="test_role",
        provider=provider,
        registry=registry,
        audit=audit,
        role_cfg=role_cfg,
    )
    result = role.run({"siparis": "test"})

    assert result.status == ValidationStatus.VALID
    assert result.data == {"ad": "braket", "adet": 5}
    assert result.fallback is None
    assert result.audit_ref != ""


# ---------------------------------------------------------------------------
# Audit satiri yazilir
# ---------------------------------------------------------------------------


def test_role_run_writes_audit(tmp_path):
    _make_template_dir(tmp_path, "audit_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="audit_role")

    provider = FakeProvider(
        fixture_map={("audit_role-v1", "_any_"): ['{"ad": "ring", "adet": 15}']}
    )

    role = LLMRole("audit_role", provider, registry, audit, role_cfg)
    role.run({"x": 1})
    role.run({"x": 2})

    records = audit.read_records()
    assert len(records) == 2
    assert records[0].role == "audit_role"
    assert records[0].status in ("VALID", "PARTIAL", "RETRY", "FALLBACK")


# ---------------------------------------------------------------------------
# INVALID + retry -> fallback
# ---------------------------------------------------------------------------


def test_role_run_invalid_returns_fallback(tmp_path):
    _make_template_dir(tmp_path, "fallback_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="fallback_role", schema_retry=1)

    # Her zaman bozuk metin don
    provider = FakeProvider(
        fixture_map={
            ("fallback_role-v1", "_any_"): ["bozuk metin", "yine bozuk"]
        }
    )

    role = LLMRole("fallback_role", provider, registry, audit, role_cfg)
    result = role.run({"x": 1})

    assert result.status == ValidationStatus.INVALID
    assert result.data is None
    assert result.fallback is not None
    assert "bozuk" in result.fallback.raw_text


# ---------------------------------------------------------------------------
# role_cfg=None -> varsayilan degerler
# ---------------------------------------------------------------------------


def test_role_run_without_role_cfg(tmp_path):
    _make_template_dir(tmp_path, "default_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)

    provider = FakeProvider(
        fixture_map={("default_role-v1", "_any_"): ['{"ad": "test", "adet": 1}']}
    )

    role = LLMRole("default_role", provider, registry, audit, role_cfg=None)
    result = role.run({"data": "ok"})
    assert result.status == ValidationStatus.VALID


# ---------------------------------------------------------------------------
# RoleResult alanlari
# ---------------------------------------------------------------------------


def test_role_result_fields(tmp_path):
    _make_template_dir(tmp_path, "fields_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="fields_role")

    provider = FakeProvider(
        fixture_map={("fields_role-v1", "_any_"): ['{"ad": "X", "adet": 99}']}
    )
    role = LLMRole("fields_role", provider, registry, audit, role_cfg)
    result = role.run({})

    assert isinstance(result, RoleResult)
    assert result.status == ValidationStatus.VALID
    assert result.data["adet"] == 99
    assert result.fallback is None
    assert isinstance(result.audit_ref, str)
    assert result.attempt_count >= 1


# ---------------------------------------------------------------------------
# Retry sonrasi gecerli -> VALID, attempt_count > 1
# ---------------------------------------------------------------------------


def test_role_run_retry_then_valid(tmp_path):
    _make_template_dir(tmp_path, "retry_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="retry_role", schema_retry=2)

    provider = FakeProvider(
        fixture_map={
            ("retry_role-v1", "_any_"): [
                "bozuk metin",
                '{"ad": "ring", "adet": 10}',
            ]
        }
    )

    role = LLMRole("retry_role", provider, registry, audit, role_cfg)
    result = role.run({"data": "test"})

    assert result.status == ValidationStatus.VALID
    assert result.data["ad"] == "ring"
    assert result.attempt_count == 2


# ---------------------------------------------------------------------------
# H1: müşteri girdisi user mesajında, system mesajında değil
# ---------------------------------------------------------------------------


def test_customer_input_in_user_message_not_system(tmp_path):
    """H1: build_request; müşteri girdisi user rolünde <musteri_verisi> sarmalıyla,
    system mesajında input metni OLMAMALI."""
    from src.llm.provider import LLMRequest

    captured: list = []

    class CapturingProvider:
        model_id = "fake-model-v1"

        def complete(self, req: LLMRequest):
            captured.append(req)
            from src.llm.provider import LLMResponse
            return LLMResponse(
                text='{"ad": "vidan", "adet": 3}',
                usage_in=10,
                usage_out=5,
                latency_s=0.01,
                model_id=self.model_id,
            )

    _make_template_dir(tmp_path, "h1_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="h1_role")

    role = LLMRole("h1_role", CapturingProvider(), registry, audit, role_cfg)
    role.run({"siparis": "10 adet braket", "boyut": "50x30"})

    assert len(captured) > 0
    req = captured[0]

    # system mesajı var
    system_msgs = [m for m in req.messages if m["role"] == "system"]
    assert len(system_msgs) == 1, "Tam olarak bir system mesajı olmalı"

    # user mesajı var ve <musteri_verisi> sarmalı içeriyor
    user_msgs = [m for m in req.messages if m["role"] == "user"]
    assert len(user_msgs) >= 1, "En az bir user mesajı olmalı"
    assert "<musteri_verisi>" in user_msgs[0]["content"], (
        "Müşteri girdisi <musteri_verisi> sarmalıyla user mesajında olmalı"
    )
    assert "siparis" in user_msgs[0]["content"], (
        "Girdi içeriği user mesajında bulunmalı"
    )

    # system mesajı girdi içeriğini TAŞIMAMALI
    assert "siparis" not in system_msgs[0]["content"], (
        "Müşteri girdisi system mesajında OLMAMALI"
    )


# ---------------------------------------------------------------------------
# M4: audit'te gerçek usage FakeProvider'dan gelir (dummy değil)
# ---------------------------------------------------------------------------


def test_audit_records_real_usage_from_provider(tmp_path):
    """M4: AuditRecord'daki usage_in/usage_out/latency_s FakeProvider'dan gelir."""
    _make_template_dir(tmp_path, "usage_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="usage_role")

    provider = FakeProvider(
        fixture_map={("usage_role-v1", "_any_"): ['{"ad": "civata", "adet": 7}']},
        model_id="fake-model-v1",
        latency_s=0.05,
    )

    role = LLMRole("usage_role", provider, registry, audit, role_cfg)
    role.run({"siparis": "test"})

    records = audit.read_records()
    assert len(records) == 1
    rec = records[0]

    # FakeProvider usage_in = len(system_content.split()) (first message content)
    # usage_out = len(response_text.split())
    # latency_s = 0.05
    assert rec.usage_out == len('{"ad": "civata", "adet": 7}'.split()), (
        f"usage_out beklenen: {len('{\"ad\": \"civata\", \"adet\": 7}'.split())}, "
        f"gelen: {rec.usage_out}"
    )
    assert rec.latency_s == 0.05, f"latency_s beklenen 0.05, gelen: {rec.latency_s}"
    assert rec.model == "fake-model-v1", f"model beklenen 'fake-model-v1', gelen: {rec.model}"


# ---------------------------------------------------------------------------
# H2: audit_ref == record.ref (record.ts değil)
# ---------------------------------------------------------------------------


def test_audit_ref_is_record_ref_not_ts(tmp_path):
    """H2: result.audit_ref değeri record.ref (uuid4 tabanlı) olmalı, record.ts olmamalı."""
    _make_template_dir(tmp_path, "ref_role")
    registry = _make_registry(tmp_path)
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg(role="ref_role")

    provider = FakeProvider(
        fixture_map={("ref_role-v1", "_any_"): ['{"ad": "somun", "adet": 4}']}
    )

    role = LLMRole("ref_role", provider, registry, audit, role_cfg)
    result = role.run({"data": "test"})

    records = audit.read_records()
    assert len(records) == 1
    rec = records[0]

    # audit_ref harf-rakam hex kodu olmalı (uuid4 tabanlı, 12 karakter)
    assert result.audit_ref == rec.ref, (
        f"audit_ref '{result.audit_ref}' beklenen record.ref '{rec.ref}' ile eşleşmeli"
    )
    # record.ts ISO zaman formatı; audit_ref bununla aynı OLMAMALI
    assert result.audit_ref != rec.ts, (
        "audit_ref, record.ts (ISO zaman) değil record.ref (uuid4) olmalı"
    )
