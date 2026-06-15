"""JSONL iz kaydi + redaksiyon katmani — PLAN_LLM.md L0.6.

Her LLM cagrisi bir JSONL satirina yazilir:
    {
      "ts": "2026-06-13T10:00:00Z",
      "role": "parser",
      "template_id": "parser-v1",
      "template_version": "1.0",
      "content_hash": "abc123...",
      "model": "claude-haiku-20240307",
      "usage_in": 400,
      "usage_out": 120,
      "cost_usd_estimate": 0.0006,
      "latency_s": 1.23,
      "status": "VALID",
      "payload_ref": null
    }

Redaksiyon katmani (payload_logging = "none"|"redacted"|"full"):
    none     : payload yazilmaz
    redacted : e-posta/telefon/isim maskelenir (regex tabanli)
    full     : ham prompt+yanit ayri dizine yazilir

Maliyet tahmini:
    Audit yazan taraf token birim fiyatini gec (LLMConfig'den yoksa 0).
    Hesaplama: (usage_in * in_price + usage_out * out_price) / 1_000_000
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.llm.provider import LLMRequest, LLMResponse
from src.llm.structured import ValidationStatus

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redaksiyon desenleri
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    (re.compile(r"\b(\+90|0)[\s\-]?[5][0-9]{9}\b"), "<PHONE>"),
    (re.compile(r"\b(\+1[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}\b"), "<PHONE>"),
]


def redact_text(text: str) -> str:
    """E-posta ve telefon numaralarini maskeler."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# AuditRecord
# ---------------------------------------------------------------------------


@dataclass
class AuditRecord:
    """Tek bir LLM cagrisi audit kaydi."""

    ts: str
    role: str
    template_id: str
    template_version: str
    content_hash: str
    model: str
    usage_in: int
    usage_out: int
    cost_usd_estimate: float
    latency_s: float
    status: str
    payload_ref: Optional[str] = None
    # H2: benzersiz referans — uuid4 tabanlı, mikrosaniye carpismasi engeller
    ref: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "ref": self.ref,
            "role": self.role,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "content_hash": self.content_hash,
            "model": self.model,
            "usage_in": self.usage_in,
            "usage_out": self.usage_out,
            "cost_usd_estimate": self.cost_usd_estimate,
            "latency_s": self.latency_s,
            "status": self.status,
            "payload_ref": self.payload_ref,
        }

    def to_jsonl_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AuditRecord":
        return cls(
            ts=d["ts"],
            role=d["role"],
            template_id=d["template_id"],
            template_version=d["template_version"],
            content_hash=d["content_hash"],
            model=d["model"],
            usage_in=int(d["usage_in"]),
            usage_out=int(d["usage_out"]),
            cost_usd_estimate=float(d["cost_usd_estimate"]),
            latency_s=float(d["latency_s"]),
            status=d["status"],
            payload_ref=d.get("payload_ref"),
            ref=d.get("ref", uuid.uuid4().hex[:12]),
        )


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------


class AuditLogger:
    """JSONL audit kaydini yazar.

    Parametreler
    ------------
    log_dir            : audit.jsonl dosyasinin dizini
    payload_log_dir    : ham payload dizini
    payload_logging    : "none"|"redacted"|"full"
    in_price_per_m     : girdi token basina fiyat ($ / 1M token); 0 = maliyet bilinmiyor
    out_price_per_m    : cikti token basina fiyat ($ / 1M token)
    """

    def __init__(
        self,
        log_dir: str | Path = "logs/llm",
        payload_log_dir: str | Path = "logs/llm/payload",
        payload_logging: str = "redacted",
        in_price_per_m: float = 0.0,
        out_price_per_m: float = 0.0,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._payload_dir = Path(payload_log_dir)
        self._payload_logging = payload_logging
        self._in_price = in_price_per_m
        self._out_price = out_price_per_m
        self._log_dir.mkdir(parents=True, exist_ok=True)
        if payload_logging != "none":
            self._payload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def audit_path(self) -> Path:
        return self._log_dir / "audit.jsonl"

    def log(
        self,
        role: str,
        template_id: str,
        template_version: str,
        content_hash: str,
        req: LLMRequest,
        resp: LLMResponse,
        status: ValidationStatus | str,
    ) -> AuditRecord:
        """Cagriyı kaydet ve AuditRecord dondur.

        Parametreler
        ------------
        status : ValidationStatus enum veya string ("VALID", "PARTIAL", "RETRY", "FALLBACK")
        """
        ts = datetime.now(timezone.utc).isoformat()
        cost = self._estimate_cost(resp.usage_in, resp.usage_out)
        status_str = status.value if isinstance(status, ValidationStatus) else str(status)

        payload_ref: Optional[str] = None
        if self._payload_logging != "none":
            payload_ref = self._write_payload(
                ts, role, req, resp, status_str
            )

        record = AuditRecord(
            ts=ts,
            role=role,
            template_id=template_id,
            template_version=template_version,
            content_hash=content_hash,
            model=resp.model_id,
            usage_in=resp.usage_in,
            usage_out=resp.usage_out,
            cost_usd_estimate=cost,
            latency_s=resp.latency_s,
            status=status_str,
            payload_ref=payload_ref,
        )

        with open(self.audit_path, "a", encoding="utf-8") as fh:
            fh.write(record.to_jsonl_line() + "\n")

        return record

    def _estimate_cost(self, usage_in: int, usage_out: int) -> float:
        return round(
            (usage_in * self._in_price + usage_out * self._out_price) / 1_000_000,
            8,
        )

    def _write_payload(
        self,
        ts: str,
        role: str,
        req: LLMRequest,
        resp: LLMResponse,
        status: str,
    ) -> str:
        """Payload'i dosyaya yazar, referans (dosya adi) dondurur."""
        ref_id = uuid.uuid4().hex[:12]
        filename = f"{role}_{ref_id}.json"

        if self._payload_logging == "redacted":
            # C2: redacted modda messages govdesi YAZILMAZ — yalniz alan-adi istatistigi
            messages = req.messages if req.messages else []
            msg_roles = [m.get("role", "unknown") for m in messages]
            total_chars = sum(len(m.get("content", "")) for m in messages)
            request_block: Dict[str, Any] = {
                "messages_stats": {
                    "count": len(messages),
                    "roles": msg_roles,
                    "total_chars_approx": total_chars,
                    "total_tokens_approx": total_chars // 4,
                },
                "template_id": req.template_id,
                "max_tokens": req.max_tokens,
                "temperature": req.temperature,
            }
            # Yanit govdesi: redacted modda govde icerigi yerine ozet (PII koruması)
            resp_text_chars = len(resp.text)
            resp_text_preview = resp.text[:50] if resp.text else ""
            response_block: Dict[str, Any] = {
                "text_summary": f"{resp_text_preview}… ({resp_text_chars} karakter)",
                "model_id": resp.model_id,
            }
            payload_data: Dict[str, Any] = {
                "ref": ref_id,
                "ts": ts,
                "role": role,
                "status": status,
                "request": request_block,
                "response": response_block,
            }
            payload_data = _redact_payload(payload_data)
        else:
            # full mod: ham prompt+yanit, yalniz e-posta/telefon maskelenir
            payload_data = {
                "ref": ref_id,
                "ts": ts,
                "role": role,
                "status": status,
                "request": {
                    "messages": req.messages,
                    "template_id": req.template_id,
                    "max_tokens": req.max_tokens,
                    "temperature": req.temperature,
                },
                "response": {
                    "text": resp.text,
                    "model_id": resp.model_id,
                },
            }
            payload_data = _redact_payload(payload_data)

        (self._payload_dir / filename).write_text(
            json.dumps(payload_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return filename

    def read_records(self) -> list:
        """Mevcut audit kayitlarini okur (test + debug icin)."""
        if not self.audit_path.exists():
            return []
        records = []
        with open(self.audit_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(AuditRecord.from_dict(json.loads(line)))
        return records


# ---------------------------------------------------------------------------
# Redaksiyon yardimcisi (payload icin)
# ---------------------------------------------------------------------------


def _redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Payload sozlugundeki string degerlerinde e-posta/telefon maskeler.

    M5: json.loads basarisiz olursa (redaksiyon JSON'u bozarsa) guvenli fallback doner.
    """
    try:
        return json.loads(redact_text(json.dumps(payload, ensure_ascii=False)))
    except Exception:
        logger.warning("_redact_payload: JSON round-trip basarisiz, guvenli fallback yaziliyor")
        from datetime import datetime, timezone as _tz
        return {
            "error": "redaction_failed",
            "ts": datetime.now(_tz.utc).isoformat(),
        }
