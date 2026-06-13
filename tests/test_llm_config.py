"""Testler: src/llm/config.py — PLAN_LLM.md L0.3.

Kapsanan:
  - JSON round-trip
  - Gecerli konfig dogrulama
  - Bilinmeyen provider tipi -> ValueError
  - openai_compat + base_url eksik -> ValueError
  - Rol.provider providers'da yok -> ValueError
  - Gecersiz payload_logging -> ValueError
  - A13 senaryo testi: ayni rol kodu iki konfig (anthropic/local) ile kosabilir
  - effective_payload_logging: rol override yoksa audit default
  - role() / provider_for_role() erisim
"""

from __future__ import annotations

import json
import pytest

from src.llm.config import (
    AuditConfig,
    LLMConfig,
    ProviderConfig,
    RoleConfig,
)


# ---------------------------------------------------------------------------
# Fabrika
# ---------------------------------------------------------------------------


def _minimal_config(provider_type: str = "anthropic", local_url: str = "") -> dict:
    providers: dict = {
        "main": {
            "type": provider_type,
            "timeout_s": 30.0,
        }
    }
    if provider_type == "openai_compat":
        providers["main"]["base_url"] = local_url or "http://localhost:11434"
    else:
        providers["main"]["api_key_env"] = "ANTHROPIC_API_KEY"

    return {
        "providers": providers,
        "roles": {
            "parser": {
                "provider": "main",
                "model": "haiku",
                "temperature": 0.0,
                "max_tokens": 512,
                "schema_retry": 2,
            }
        },
        "audit": {
            "log_dir": "logs/llm",
            "payload_log_dir": "logs/llm/payload",
            "payload_logging_default": "redacted",
            "payload_retention_days": 30,
        },
    }


def _make_cfg(provider_type: str = "anthropic") -> LLMConfig:
    return LLMConfig.from_dict(_minimal_config(provider_type))


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_config_round_trip_anthropic():
    d = _minimal_config("anthropic")
    cfg = LLMConfig.from_dict(d)
    cfg.validate()
    out = json.loads(cfg.to_json())
    assert out["providers"]["main"]["type"] == "anthropic"
    assert out["roles"]["parser"]["provider"] == "main"


def test_config_round_trip_local():
    d = _minimal_config("openai_compat", "http://127.0.0.1:11434")
    cfg = LLMConfig.from_dict(d)
    cfg.validate()
    out = json.loads(cfg.to_json())
    assert out["providers"]["main"]["type"] == "openai_compat"
    assert out["providers"]["main"]["base_url"] == "http://127.0.0.1:11434"


def test_config_from_json_roundtrip():
    d = _minimal_config()
    cfg = LLMConfig.from_dict(d)
    json_str = cfg.to_json()
    cfg2 = LLMConfig.from_json(json_str)
    assert cfg2.providers["main"].type == cfg.providers["main"].type


# ---------------------------------------------------------------------------
# Gecerli konfig
# ---------------------------------------------------------------------------


def test_valid_anthropic_config():
    cfg = _make_cfg("anthropic")
    cfg.validate()  # hata olmamali


def test_valid_openai_compat_config():
    cfg = _make_cfg("openai_compat")
    cfg.validate()


def test_valid_fake_config():
    d = {
        "providers": {"test": {"type": "fake", "timeout_s": 1.0}},
        "roles": {
            "parser": {"provider": "test", "model": "fake", "temperature": 0.0, "max_tokens": 128, "schema_retry": 0}
        },
        "audit": {
            "log_dir": "logs/llm",
            "payload_log_dir": "logs/llm/payload",
            "payload_logging_default": "none",
            "payload_retention_days": 1,
        },
    }
    cfg = LLMConfig.from_dict(d)
    cfg.validate()


# ---------------------------------------------------------------------------
# Dogrulama hatalari
# ---------------------------------------------------------------------------


def test_unknown_provider_type_raises():
    d = _minimal_config()
    d["providers"]["main"]["type"] = "gemini"
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="bilinmeyen tip"):
        cfg.validate()


def test_openai_compat_missing_base_url_raises():
    d = {
        "providers": {"local": {"type": "openai_compat", "timeout_s": 30.0}},
        "roles": {
            "parser": {"provider": "local", "model": "qwen", "temperature": 0.0, "max_tokens": 512, "schema_retry": 2}
        },
        "audit": {"log_dir": "logs/llm", "payload_log_dir": "logs/llm/payload",
                  "payload_logging_default": "redacted", "payload_retention_days": 30},
    }
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="base_url zorunlu"):
        cfg.validate()


def test_role_unknown_provider_raises():
    d = _minimal_config()
    d["roles"]["parser"]["provider"] = "hayali_provider"
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="providers listesinde yok"):
        cfg.validate()


def test_invalid_payload_logging_raises():
    d = _minimal_config()
    d["roles"]["parser"]["payload_logging"] = "verbose"
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="payload_logging"):
        cfg.validate()


def test_invalid_audit_payload_logging_default_raises():
    d = _minimal_config()
    d["audit"]["payload_logging_default"] = "maybe"
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="payload_logging_default"):
        cfg.validate()


def test_negative_timeout_raises():
    d = _minimal_config()
    d["providers"]["main"]["timeout_s"] = -1.0
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="timeout_s"):
        cfg.validate()


def test_temperature_out_of_range_raises():
    d = _minimal_config()
    d["roles"]["parser"]["temperature"] = 3.0
    cfg = LLMConfig.from_dict(d)
    with pytest.raises(ValueError, match="temperature"):
        cfg.validate()


# ---------------------------------------------------------------------------
# Erisim
# ---------------------------------------------------------------------------


def test_role_access():
    cfg = _make_cfg()
    cfg.validate()
    rc = cfg.role("parser")
    assert rc.role == "parser"
    assert rc.model == "haiku"


def test_role_unknown_raises():
    cfg = _make_cfg()
    with pytest.raises(ValueError, match="Bilinmeyen rol"):
        cfg.role("nonexistent")


def test_provider_for_role():
    cfg = _make_cfg()
    cfg.validate()
    pc = cfg.provider_for_role("parser")
    assert pc.type == "anthropic"


# ---------------------------------------------------------------------------
# A13 senaryo testi: ayni rol kodu iki konfig ile kosabilir
# ---------------------------------------------------------------------------


def test_a13_same_role_code_works_with_both_provider_types():
    """
    Ayni 'parser' rol tanimlama kodu hem anthropic hem openai_compat konfig ile calisir.
    Tek fark: roles.parser.provider satiri.
    Bu test A13 senaryo degisiminin yalniz konfig satiri oldugunu kanitlar.
    """
    cloud_cfg = LLMConfig.from_dict({
        "providers": {
            "anthropic": {
                "type": "anthropic",
                "api_key_env": "ANTHROPIC_API_KEY",
                "timeout_s": 30.0,
            }
        },
        "roles": {
            "parser": {
                "provider": "anthropic",
                "model": "claude-haiku-20240307",
                "temperature": 0.0,
                "max_tokens": 512,
                "schema_retry": 2,
            }
        },
        "audit": {
            "log_dir": "logs/llm",
            "payload_log_dir": "logs/llm/payload",
            "payload_logging_default": "redacted",
            "payload_retention_days": 30,
        },
    })

    local_cfg = LLMConfig.from_dict({
        "providers": {
            "local": {
                "type": "openai_compat",
                "base_url": "http://localhost:11434",
                "timeout_s": 60.0,
            }
        },
        "roles": {
            "parser": {
                "provider": "local",
                "model": "qwen2.5:14b",
                "temperature": 0.0,
                "max_tokens": 512,
                "schema_retry": 2,
            }
        },
        "audit": {
            "log_dir": "logs/llm",
            "payload_log_dir": "logs/llm/payload",
            "payload_logging_default": "full",
            "payload_retention_days": 30,
        },
    })

    cloud_cfg.validate()
    local_cfg.validate()

    # Her iki konfig de parser rolunu tanimliyor
    cloud_role = cloud_cfg.role("parser")
    local_role = local_cfg.role("parser")

    # Rol adi ayni, provider farkli
    assert cloud_role.role == local_role.role == "parser"
    assert cloud_cfg.provider_for_role("parser").type == "anthropic"
    assert local_cfg.provider_for_role("parser").type == "openai_compat"


# ---------------------------------------------------------------------------
# effective_payload_logging
# ---------------------------------------------------------------------------


def test_effective_payload_logging_uses_role_override():
    d = _minimal_config()
    d["roles"]["parser"]["payload_logging"] = "full"
    cfg = LLMConfig.from_dict(d)
    cfg.validate()
    assert cfg.effective_payload_logging("parser") == "full"


def test_effective_payload_logging_uses_audit_default_when_no_override():
    d = _minimal_config()
    # parser'da payload_logging yok
    assert "payload_logging" not in d["roles"]["parser"]
    cfg = LLMConfig.from_dict(d)
    cfg.validate()
    assert cfg.effective_payload_logging("parser") == "redacted"


# ---------------------------------------------------------------------------
# from_file
# ---------------------------------------------------------------------------


def test_config_from_file(tmp_path):
    d = _minimal_config()
    f = tmp_path / "test_llm.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    cfg = LLMConfig.from_file(str(f))
    cfg.validate()
    assert cfg.roles["parser"].provider == "main"
