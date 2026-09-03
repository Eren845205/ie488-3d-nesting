"""tests/test_runtime_store.py — InMemoryJobStore + SqliteJobStore testleri.

Her sinif icin ayni test suite calıstırilir (parametrized fixture).
"""

from __future__ import annotations

import pytest

from src.runtime.jobs import Job, JobState
from src.runtime.store import (
    InMemoryJobStore,
    JobAlreadyExistsError,
    JobNotFoundError,
    JobStore,
    SqliteJobStore,
)


# ---------------------------------------------------------------------------
# Fixture: her iki store implementasyonu
# ---------------------------------------------------------------------------

@pytest.fixture(params=["memory", "sqlite"])
def store(request) -> JobStore:
    if request.param == "memory":
        return InMemoryJobStore()
    return SqliteJobStore(db_path=":memory:")


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------

def make_job(job_id: str = "j1", state: JobState = JobState.RECEIVED) -> Job:
    return Job(
        job_id=job_id,
        idempotency_key=f"key-{job_id}",
        job_type="test",
        payload={"v": 42},
        state=state,
    )


# ---------------------------------------------------------------------------
# save + get
# ---------------------------------------------------------------------------

class TestSaveGet:
    def test_save_and_get_roundtrip(self, store: JobStore):
        job = make_job()
        store.save(job)
        retrieved = store.get("j1")
        assert retrieved.job_id == "j1"
        assert retrieved.state == JobState.RECEIVED

    def test_get_missing_raises(self, store: JobStore):
        with pytest.raises(JobNotFoundError):
            store.get("nonexistent")

    def test_save_duplicate_raises(self, store: JobStore):
        job = make_job()
        store.save(job)
        with pytest.raises(JobAlreadyExistsError):
            store.save(make_job())  # ayni job_id

    def test_payload_preserved(self, store: JobStore):
        job = make_job()
        job.payload = {"scenario": {"x": 99}}
        store.save(job)
        retrieved = store.get("j1")
        assert retrieved.payload["scenario"]["x"] == 99


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------

class TestUpdate:
    def test_update_state(self, store: JobStore):
        job = make_job()
        store.save(job)
        job.transition(JobState.QUEUED)
        store.update(job)
        retrieved = store.get("j1")
        assert retrieved.state == JobState.QUEUED

    def test_update_result(self, store: JobStore):
        job = make_job()
        store.save(job)
        job.result = {"total_price": 500.0}
        job.transition(JobState.QUEUED)
        store.update(job)
        retrieved = store.get("j1")
        assert retrieved.result["total_price"] == 500.0

    def test_update_nonexistent_raises(self, store: JobStore):
        job = make_job("ghost")
        with pytest.raises(JobNotFoundError):
            store.update(job)

    def test_update_audit_log_persisted(self, store: JobStore):
        job = make_job()
        store.save(job)
        job.transition(JobState.QUEUED, note="gecis notu")
        store.update(job)
        retrieved = store.get("j1")
        assert len(retrieved.audit_log) == 1
        assert retrieved.audit_log[0].note == "gecis notu"

    def test_update_error_persisted(self, store: JobStore):
        job = make_job()
        store.save(job)
        job.transition(JobState.QUEUED)
        job.transition(JobState.RUNNING)
        job.error = "beklenmedik hata"
        job.transition(JobState.FAILED)
        store.update(job)
        retrieved = store.get("j1")
        assert retrieved.error == "beklenmedik hata"


# ---------------------------------------------------------------------------
# list_jobs
# ---------------------------------------------------------------------------

class TestListJobs:
    def _populate(self, store: JobStore):
        j1 = make_job("j1", JobState.QUEUED)
        j1.tenant_id = "t1"
        j2 = make_job("j2", JobState.RUNNING)
        j2.tenant_id = "t1"
        j3 = make_job("j3", JobState.DONE)
        j3.tenant_id = "t2"
        j3.job_type = "pipeline"
        for j in (j1, j2, j3):
            store.save(j)
        return j1, j2, j3

    def test_list_all(self, store: JobStore):
        self._populate(store)
        result = store.list_jobs()
        assert len(result) == 3

    def test_filter_by_state(self, store: JobStore):
        self._populate(store)
        result = store.list_jobs(state=JobState.QUEUED)
        assert all(j.state == JobState.QUEUED for j in result)
        assert len(result) == 1

    def test_filter_by_tenant(self, store: JobStore):
        self._populate(store)
        result = store.list_jobs(tenant_id="t1")
        assert len(result) == 2

    def test_filter_by_job_type(self, store: JobStore):
        self._populate(store)
        result = store.list_jobs(job_type="pipeline")
        assert len(result) == 1
        assert result[0].job_id == "j3"

    def test_limit(self, store: JobStore):
        self._populate(store)
        result = store.list_jobs(limit=2)
        assert len(result) == 2

    def test_empty_store_returns_empty_list(self, store: JobStore):
        assert store.list_jobs() == []


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_delete_existing(self, store: JobStore):
        store.save(make_job("del1"))
        store.delete("del1")
        with pytest.raises(JobNotFoundError):
            store.get("del1")

    def test_delete_nonexistent_raises(self, store: JobStore):
        with pytest.raises(JobNotFoundError):
            store.delete("ghost")


# ---------------------------------------------------------------------------
# Coklu job / thread guvenlik (InMemoryJobStore icin)
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_multiple_saves_and_gets(self, store: JobStore):
        jobs = [make_job(f"j{i}") for i in range(10)]
        for j in jobs:
            store.save(j)
        for j in jobs:
            retrieved = store.get(j.job_id)
            assert retrieved.job_id == j.job_id
