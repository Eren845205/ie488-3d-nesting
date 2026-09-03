"""src/runtime/jobs.py — Job dataclass + JobState enum + durum makinesi.

Durum makinesi (PLAN_SERVIS §3.1):
    RECEIVED -> QUEUED -> RUNNING -> AWAITING_APPROVAL -> APPROVED -> DONE
                              |                               |
                              +-- FAILED (retry<max) --------+-> REJECTED
                              |
                              +-- DEAD_LETTER (retry tukendi / kalici hata)

Kurallar
--------
- Gecersiz gecis ValueError firlatir.
- Her gecis audit listesine eklenir (zaman, eski durum, yeni durum, not).
- Tum alanlar JSON-serileştirilebilir (to_dict / from_dict).
- max 50 satir/fonksiyon, max 4 ic ice blok.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Durum enum
# ---------------------------------------------------------------------------

class JobState(str, Enum):
    """Is durumu (PLAN_SERVIS §3.1 durum makinesi)."""
    RECEIVED = "RECEIVED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DONE = "DONE"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


# ---------------------------------------------------------------------------
# Gecerli gecisler tablosu
# ---------------------------------------------------------------------------

_VALID_TRANSITIONS: Dict[JobState, List[JobState]] = {
    JobState.RECEIVED: [JobState.QUEUED],
    JobState.QUEUED: [JobState.RUNNING, JobState.DEAD_LETTER],
    JobState.RUNNING: [
        JobState.AWAITING_APPROVAL,
        JobState.DONE,
        JobState.FAILED,
        JobState.DEAD_LETTER,
    ],
    JobState.AWAITING_APPROVAL: [JobState.APPROVED, JobState.REJECTED],
    JobState.APPROVED: [JobState.DONE],
    JobState.REJECTED: [],
    JobState.DONE: [],
    JobState.FAILED: [JobState.QUEUED, JobState.DEAD_LETTER],
    JobState.DEAD_LETTER: [],
}


# ---------------------------------------------------------------------------
# Audit kaydi
# ---------------------------------------------------------------------------

@dataclass
class AuditEntry:
    """Tek bir durum gecisinin audit kaydi."""
    timestamp: str        # ISO 8601 UTC
    from_state: str
    to_state: str
    note: str = ""
    worker_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "note": self.note,
            "worker_id": self.worker_id,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AuditEntry":
        return cls(
            timestamp=d["timestamp"],
            from_state=d["from_state"],
            to_state=d["to_state"],
            note=d.get("note", ""),
            worker_id=d.get("worker_id"),
        )


# ---------------------------------------------------------------------------
# Job dataclass
# ---------------------------------------------------------------------------

@dataclass
class Job:
    """Calisma-zamani is birimi.

    Parametreler
    ------------
    job_id           : Benzersiz is kimlik kodu (UUID veya deterministik)
    idempotency_key  : Tekrar islemeyi onleyen anahtar (PLAN_SERVIS §0.4)
    job_type         : Is turu etiketi (orn. "pipeline", "parse", "nest")
    payload          : JSON-serileştirilebilir girdi sozlugu
    state            : Mevcut durum (durum makinesi)
    audit_log        : Durum gecis kayitlari (kronolojik)
    result           : Tamamlanmis isin JSON-serileştirilebilir sonucu
    error            : Son hata mesaji (FAILED/DEAD_LETTER durumunda)
    retry_count      : Kac kez yeniden denendi
    created_at       : Olusturulma zamani (ISO 8601 UTC)
    updated_at       : Son guncelleme zamani (ISO 8601 UTC)
    tenant_id        : Kiracı kimlik kodu (SaaS Faz S2 icin, simdilik None)
    """
    job_id: str
    idempotency_key: str
    job_type: str
    payload: Dict[str, Any]
    state: JobState = JobState.RECEIVED
    audit_log: List[AuditEntry] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    created_at: str = field(default_factory=lambda: _utcnow_iso())
    updated_at: str = field(default_factory=lambda: _utcnow_iso())
    tenant_id: Optional[str] = None

    # -----------------------------------------------------------------------
    # Durum makinesi
    # -----------------------------------------------------------------------

    def transition(
        self,
        new_state: JobState,
        note: str = "",
        worker_id: Optional[str] = None,
    ) -> None:
        """Durumu gecis tablosuna gore degistirir; gecersiz gecis ValueError firlatir."""
        allowed = _VALID_TRANSITIONS.get(self.state, [])
        if new_state not in allowed:
            raise ValueError(
                f"Gecersiz gecis: {self.state!r} -> {new_state!r}. "
                f"Izin verilenler: {[s.value for s in allowed]}"
            )
        entry = AuditEntry(
            timestamp=_utcnow_iso(),
            from_state=self.state.value,
            to_state=new_state.value,
            note=note,
            worker_id=worker_id,
        )
        self.audit_log.append(entry)
        self.state = new_state
        self.updated_at = entry.timestamp

    def is_terminal(self) -> bool:
        """Is sonlanmis mi? (DONE/REJECTED/DEAD_LETTER)"""
        return self.state in (JobState.DONE, JobState.REJECTED, JobState.DEAD_LETTER)

    # -----------------------------------------------------------------------
    # JSON round-trip
    # -----------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "idempotency_key": self.idempotency_key,
            "job_type": self.job_type,
            "payload": self.payload,
            "state": self.state.value,
            "audit_log": [e.to_dict() for e in self.audit_log],
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tenant_id": self.tenant_id,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        return cls(
            job_id=d["job_id"],
            idempotency_key=d["idempotency_key"],
            job_type=d["job_type"],
            payload=d.get("payload", {}),
            state=JobState(d.get("state", JobState.RECEIVED.value)),
            audit_log=[AuditEntry.from_dict(e) for e in d.get("audit_log", [])],
            result=d.get("result"),
            error=d.get("error"),
            retry_count=int(d.get("retry_count", 0)),
            created_at=d.get("created_at", _utcnow_iso()),
            updated_at=d.get("updated_at", _utcnow_iso()),
            tenant_id=d.get("tenant_id"),
        )

    @classmethod
    def from_json(cls, text: str) -> "Job":
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def _utcnow_iso() -> str:
    """Saniyelik hassasiyetle UTC ISO 8601 zaman damgasi."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
