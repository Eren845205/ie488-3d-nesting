"""LLM konfigurasyon semasi + dogrulayici — PLAN_LLM.md L0.3.

JSON yapisi (configs/llm.example.json'a bakikabilir):
{
  "providers": {
    "<id>": {
      "type": "anthropic" | "openai_compat" | "fake",
      "base_url": "...",        # openai_compat icin zorunlu
      "api_key_env": "...",     # anthropic/openai_compat icin; env-var adi
      "timeout_s": 30.0,
      "rate_limit": {"requests_per_minute": 60}
    }
  },
  "roles": {
    "<rol_adi>": {
      "provider": "<provider_id>",
      "model": "...",
      "temperature": 0.0,
      "max_tokens": 1024,
      "schema_retry": 2,
      "payload_logging": "none" | "redacted" | "full"
    }
  },
  "audit": {
    "log_dir": "logs/llm",
    "payload_log_dir": "logs/llm/payload",
    "payload_logging_default": "redacted",
    "payload_retention_days": 30
  }
}

Dogrulama kurallari:
  - Bilinmeyen sağlayıcı tipi -> ValueError
  - rol.provider -> providers'da olmali -> ValueError
  - openai_compat icin base_url zorunlu -> ValueError
  - payload_logging gecersiz deger -> ValueError
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sabitler
# ---------------------------------------------------------------------------

PROVIDER_TYPES = frozenset({"anthropic", "openai_compat", "fake"})
PAYLOAD_LOGGING_VALUES = frozenset({"none", "redacted", "full"})
KNOWN_ROLES = frozenset({"parser", "tuner", "hypothesis", "assistant", "report"})


# ---------------------------------------------------------------------------
# Dataclass'lar
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Tek bir saglayici kurulum ayarlari."""

    id: str
    type: str
    base_url: Optional[str] = None
    api_key_env: Optional[str] = None
    timeout_s: float = 30.0
    rate_limit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": self.type,
            "timeout_s": self.timeout_s,
        }
        if self.base_url is not None:
            d["base_url"] = self.base_url
        if self.api_key_env is not None:
            d["api_key_env"] = self.api_key_env
        if self.rate_limit:
            d["rate_limit"] = self.rate_limit
        return d

    @classmethod
    def from_dict(cls, id: str, d: Dict[str, Any]) -> "ProviderConfig":
        return cls(
            id=id,
            type=d["type"],
            base_url=d.get("base_url"),
            api_key_env=d.get("api_key_env"),
            timeout_s=float(d.get("timeout_s", 30.0)),
            rate_limit=dict(d.get("rate_limit", {})),
        )


@dataclass
class RoleConfig:
    """Tek bir LLM rolunun calisma parametreleri."""

    role: str
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    schema_retry: int = 2
    payload_logging: Optional[str] = None  # None => audit default'u kullan

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "schema_retry": self.schema_retry,
        }
        if self.payload_logging is not None:
            d["payload_logging"] = self.payload_logging
        return d

    @classmethod
    def from_dict(cls, role: str, d: Dict[str, Any]) -> "RoleConfig":
        return cls(
            role=role,
            provider=d["provider"],
            model=d["model"],
            temperature=float(d.get("temperature", 0.0)),
            max_tokens=int(d.get("max_tokens", 1024)),
            schema_retry=int(d.get("schema_retry", 2)),
            payload_logging=d.get("payload_logging"),
        )


@dataclass
class AuditConfig:
    """Audit JSONL + payload loglama ayarlari."""

    log_dir: str = "logs/llm"
    payload_log_dir: str = "logs/llm/payload"
    payload_logging_default: str = "redacted"
    payload_retention_days: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_dir": self.log_dir,
            "payload_log_dir": self.payload_log_dir,
            "payload_logging_default": self.payload_logging_default,
            "payload_retention_days": self.payload_retention_days,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AuditConfig":
        return cls(
            log_dir=d.get("log_dir", "logs/llm"),
            payload_log_dir=d.get("payload_log_dir", "logs/llm/payload"),
            payload_logging_default=d.get("payload_logging_default", "redacted"),
            payload_retention_days=int(d.get("payload_retention_days", 30)),
        )


@dataclass
class LLMConfig:
    """Tum LLM gateway konfigurasyonu.

    Kullanim:
        cfg = LLMConfig.from_file("configs/llm.example.json")
        cfg.validate()
        role_cfg = cfg.role("parser")
        prov_cfg = cfg.provider_for_role("parser")
    """

    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    roles: Dict[str, RoleConfig] = field(default_factory=dict)
    audit: AuditConfig = field(default_factory=AuditConfig)

    # ------------------------------------------------------------------
    # Erisim
    # ------------------------------------------------------------------

    def role(self, role_name: str) -> RoleConfig:
        """Rol konfigurasyonunu dondurur; yoksa ValueError."""
        if role_name not in self.roles:
            raise ValueError(
                f"Bilinmeyen rol: {role_name!r}. "
                f"Tanimli roller: {sorted(self.roles.keys())}"
            )
        return self.roles[role_name]

    def provider_for_role(self, role_name: str) -> ProviderConfig:
        """Rolun saglayici konfigurasyonunu dondurur."""
        rc = self.role(role_name)
        if rc.provider not in self.providers:
            raise ValueError(
                f"Rol {role_name!r} icin saglayici {rc.provider!r} tanimlanmamis."
            )
        return self.providers[rc.provider]

    def effective_payload_logging(self, role_name: str) -> str:
        """Rol override'i yoksa audit default'unu kullanir."""
        rc = self.role(role_name)
        if rc.payload_logging is not None:
            return rc.payload_logging
        return self.audit.payload_logging_default

    # ------------------------------------------------------------------
    # Dogrulama
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Konfigurasyon tutarliligini dogrular; hata varsa ValueError firlatir."""
        self._validate_providers()
        self._validate_roles()
        self._validate_audit()

    def _validate_providers(self) -> None:
        for pid, pc in self.providers.items():
            if pc.type not in PROVIDER_TYPES:
                raise ValueError(
                    f"Saglayici {pid!r}: bilinmeyen tip {pc.type!r}. "
                    f"Gecerli tipler: {sorted(PROVIDER_TYPES)}"
                )
            if pc.type == "openai_compat" and not pc.base_url:
                raise ValueError(
                    f"Saglayici {pid!r}: openai_compat tipi icin base_url zorunlu."
                )
            if pc.timeout_s <= 0:
                raise ValueError(
                    f"Saglayici {pid!r}: timeout_s pozitif olmali."
                )

    def _validate_roles(self) -> None:
        for rname, rc in self.roles.items():
            if rc.provider not in self.providers:
                raise ValueError(
                    f"Rol {rname!r}: provider {rc.provider!r} providers listesinde yok."
                )
            if rc.temperature < 0.0 or rc.temperature > 2.0:
                raise ValueError(
                    f"Rol {rname!r}: temperature 0.0-2.0 araliginda olmali."
                )
            if rc.max_tokens <= 0:
                raise ValueError(
                    f"Rol {rname!r}: max_tokens pozitif olmali."
                )
            if rc.schema_retry < 0:
                raise ValueError(
                    f"Rol {rname!r}: schema_retry negatif olamaz."
                )
            if rc.payload_logging is not None:
                if rc.payload_logging not in PAYLOAD_LOGGING_VALUES:
                    raise ValueError(
                        f"Rol {rname!r}: gecersiz payload_logging {rc.payload_logging!r}. "
                        f"Gecerli degerler: {sorted(PAYLOAD_LOGGING_VALUES)}"
                    )

    def _validate_audit(self) -> None:
        if self.audit.payload_logging_default not in PAYLOAD_LOGGING_VALUES:
            raise ValueError(
                f"audit.payload_logging_default gecersiz: "
                f"{self.audit.payload_logging_default!r}"
            )
        if self.audit.payload_retention_days <= 0:
            raise ValueError("audit.payload_retention_days pozitif olmali.")

    # ------------------------------------------------------------------
    # JSON round-trip
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "providers": {k: v.to_dict() for k, v in self.providers.items()},
            "roles": {k: v.to_dict() for k, v in self.roles.items()},
            "audit": self.audit.to_dict(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LLMConfig":
        providers = {
            k: ProviderConfig.from_dict(k, v)
            for k, v in d.get("providers", {}).items()
        }
        roles = {
            k: RoleConfig.from_dict(k, v)
            for k, v in d.get("roles", {}).items()
        }
        audit = AuditConfig.from_dict(d.get("audit", {}))
        return cls(providers=providers, roles=roles, audit=audit)

    @classmethod
    def from_json(cls, text: str) -> "LLMConfig":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_file(cls, path: str) -> "LLMConfig":
        with open(path, encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
