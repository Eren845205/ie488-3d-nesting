"""src/runtime/store.py — Soyut JobStore + InMemoryJobStore + SqliteJobStore.

Uyari: SqliteJobStore yalniz stdlib sqlite3 kullanir; PostgreSQL EKLENMEMISTIR
(S0.1 infra karari sonraya birakildi — PLAN_SERVIS §11.C + §9).

Arayüz sozlesmesi (JobStore ABC)
---------------------------------
  save(job)           : Yeni job yazar; var olan job_id -> JobAlreadyExistsError
  get(job_id)         : Job dondurur; bulunamazsa -> JobNotFoundError
  update(job)         : Mevcut job'u gunceller (durum + audit + result + error)
  list_jobs(...)      : Filtrelenebilir job listesi dondurur
  delete(job_id)      : Job'u siler (test / temizlik amacli)

Postgres icin takılacak yer: SqliteJobStore'u degistir, JobStore ABC'yi koru.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from src.runtime.jobs import Job, JobState


# ---------------------------------------------------------------------------
# Hata turleri
# ---------------------------------------------------------------------------

class JobAlreadyExistsError(Exception):
    """Ayni job_id ile iki kez save() cagrisi."""


class JobNotFoundError(Exception):
    """get() / update() cagrısinda job bulunamazsa."""


# ---------------------------------------------------------------------------
# Soyut temel
# ---------------------------------------------------------------------------

class JobStore(ABC):
    """Calisma-zamani is deposu soyut temeli."""

    @abstractmethod
    def save(self, job: Job) -> None:
        """Yeni job yaz. Var olan job_id -> JobAlreadyExistsError."""

    @abstractmethod
    def get(self, job_id: str) -> Job:
        """Job don; bulunamazsa -> JobNotFoundError."""

    @abstractmethod
    def update(self, job: Job) -> None:
        """Mevcut job'u guncelle; bulunamazsa -> JobNotFoundError."""

    @abstractmethod
    def list_jobs(
        self,
        state: Optional[JobState] = None,
        tenant_id: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Job]:
        """Filtrelenebilir job listesi don."""

    @abstractmethod
    def delete(self, job_id: str) -> None:
        """Job'u sil (JobNotFoundError eger yoksa)."""


# ---------------------------------------------------------------------------
# Bellek-ici uygulama (test + SynchronousQueue icin)
# ---------------------------------------------------------------------------

class InMemoryJobStore(JobStore):
    """Thread-safe bellek-ici job deposu. Surecler arasi kalicilik YOK."""

    def __init__(self) -> None:
        self._store: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def save(self, job: Job) -> None:
        with self._lock:
            if job.job_id in self._store:
                raise JobAlreadyExistsError(f"job_id zaten var: {job.job_id!r}")
            self._store[job.job_id] = job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._store.get(job_id)
        if job is None:
            raise JobNotFoundError(f"Job bulunamadi: {job_id!r}")
        return job

    def update(self, job: Job) -> None:
        with self._lock:
            if job.job_id not in self._store:
                raise JobNotFoundError(f"Job bulunamadi: {job.job_id!r}")
            self._store[job.job_id] = job

    def list_jobs(
        self,
        state: Optional[JobState] = None,
        tenant_id: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Job]:
        with self._lock:
            jobs = list(self._store.values())
        if state is not None:
            jobs = [j for j in jobs if j.state == state]
        if tenant_id is not None:
            jobs = [j for j in jobs if j.tenant_id == tenant_id]
        if job_type is not None:
            jobs = [j for j in jobs if j.job_type == job_type]
        return jobs[:limit]

    def delete(self, job_id: str) -> None:
        with self._lock:
            if job_id not in self._store:
                raise JobNotFoundError(f"Job bulunamadi: {job_id!r}")
            del self._store[job_id]


# ---------------------------------------------------------------------------
# SQLite uygulama (stdlib sqlite3 — tek-islemci, disk-kalici)
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id          TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL,
    job_type        TEXT NOT NULL,
    tenant_id       TEXT,
    state           TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    result_json     TEXT,
    error           TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    audit_log_json  TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_state     ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant    ON jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_type      ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_idem_key  ON jobs(idempotency_key);
"""

# NOT: Postgres entegrasyonu icin SqliteJobStore yerine PostgresJobStore
# yazilir; JobStore ABC ayni kalir — tek dokunma noktasi.


class SqliteJobStore(JobStore):
    """stdlib sqlite3 tabanli is deposu.

    Parametreler
    ------------
    db_path : Veritabani dosya yolu (":memory:" test icin kullanilabilir)
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        # check_same_thread=False: her cagrida kendi baglantisini acar
        self._local = threading.local()
        self._init_schema()

    # -----------------------------------------------------------------------
    # Baglanti yonetimi
    # -----------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self._db_path, check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(_DDL)
        conn.commit()

    # -----------------------------------------------------------------------
    # Yardimcilar
    # -----------------------------------------------------------------------

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            job_id=row["job_id"],
            idempotency_key=row["idempotency_key"],
            job_type=row["job_type"],
            tenant_id=row["tenant_id"],
            state=JobState(row["state"]),
            payload=json.loads(row["payload_json"]),
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            retry_count=int(row["retry_count"]),
            audit_log=[],  # lazy: audit_log_json ile doldurulur asagida
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_job_full(row: sqlite3.Row) -> Job:
        from src.runtime.jobs import AuditEntry
        job = SqliteJobStore._row_to_job(row)
        job.audit_log = [
            AuditEntry.from_dict(e)
            for e in json.loads(row["audit_log_json"] or "[]")
        ]
        return job

    # -----------------------------------------------------------------------
    # JobStore implementasyonu
    # -----------------------------------------------------------------------

    def save(self, job: Job) -> None:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO jobs
                   (job_id, idempotency_key, job_type, tenant_id, state,
                    payload_json, result_json, error, retry_count,
                    audit_log_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.job_id,
                    job.idempotency_key,
                    job.job_type,
                    job.tenant_id,
                    job.state.value,
                    json.dumps(job.payload, ensure_ascii=False),
                    json.dumps(job.result, ensure_ascii=False) if job.result else None,
                    job.error,
                    job.retry_count,
                    json.dumps(
                        [e.to_dict() for e in job.audit_log],
                        ensure_ascii=False,
                    ),
                    job.created_at,
                    job.updated_at,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise JobAlreadyExistsError(f"job_id zaten var: {job.job_id!r}")

    def get(self, job_id: str) -> Job:
        row = self._conn().execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise JobNotFoundError(f"Job bulunamadi: {job_id!r}")
        return self._row_to_job_full(row)

    def update(self, job: Job) -> None:
        conn = self._conn()
        cur = conn.execute(
            """UPDATE jobs SET
               state=?, result_json=?, error=?, retry_count=?,
               audit_log_json=?, updated_at=?
               WHERE job_id=?""",
            (
                job.state.value,
                json.dumps(job.result, ensure_ascii=False) if job.result else None,
                job.error,
                job.retry_count,
                json.dumps(
                    [e.to_dict() for e in job.audit_log],
                    ensure_ascii=False,
                ),
                job.updated_at,
                job.job_id,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise JobNotFoundError(f"Job bulunamadi: {job.job_id!r}")

    def list_jobs(
        self,
        state: Optional[JobState] = None,
        tenant_id: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Job]:
        clauses = []
        params: list = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state.value)
        if tenant_id is not None:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if job_type is not None:
            clauses.append("job_type = ?")
            params.append(job_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn().execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_job_full(r) for r in rows]

    def delete(self, job_id: str) -> None:
        conn = self._conn()
        cur = conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise JobNotFoundError(f"Job bulunamadi: {job_id!r}")
