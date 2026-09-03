"""tests/test_runtime_queue.py — SynchronousQueue testleri + pipeline_job smoke.

Kapsam
------
SynchronousQueue
  - Basarili handler: job DONE durumuna gecer, result kaydedilir
  - _needs_approval=True: AWAITING_APPROVAL durumuna gecer
  - Hata fırlatan handler: FAILED durumuna gecer (retry<max)
  - max_retries dolduğunda: DEAD_LETTER durumuna gecer
  - Job her durumda store'a yazilir (idempotency guvencesi)
  - retry() API: FAILED job'u yeniden kuyruga atar
  - Stub'lar (CeleryQueue/RQQueue): NotImplementedError

pipeline_job smoke
  - pipeline_handler() calisir, JSON-serileştirilebilir sonuc uretir
"""

from __future__ import annotations

import pytest

from src.runtime.jobs import Job, JobState
from src.runtime.store import InMemoryJobStore
from src.runtime.queue import CeleryQueue, JobQueue, RQQueue, SynchronousQueue


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------

def make_job(job_id: str = "q-job-1") -> Job:
    return Job(
        job_id=job_id,
        idempotency_key=f"key-{job_id}",
        job_type="test",
        payload={"x": 1},
    )


def success_handler(job: Job):
    return {"answer": 42, "batch_count": 3}


def approval_handler(job: Job):
    return {"draft": "teklif metni", "_needs_approval": True}


def failing_handler(job: Job):
    raise RuntimeError("simule hata")


# ---------------------------------------------------------------------------
# SynchronousQueue — basarili akis
# ---------------------------------------------------------------------------

class TestSynchronousQueueSuccess:
    def test_job_saved_to_store(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job()
        q.enqueue(job, success_handler)
        saved = store.get("q-job-1")
        assert saved is not None

    def test_job_done_after_success(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job()
        q.enqueue(job, success_handler)
        assert store.get("q-job-1").state == JobState.DONE

    def test_result_stored(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job()
        q.enqueue(job, success_handler)
        saved = store.get("q-job-1")
        assert saved.result == {"answer": 42, "batch_count": 3}

    def test_enqueue_returns_job_id(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job_id = q.enqueue(make_job("ret-1"), success_handler)
        assert job_id == "ret-1"

    def test_needs_approval_flag_sets_awaiting_state(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job("ap-1")
        q.enqueue(job, approval_handler)
        saved = store.get("ap-1")
        assert saved.state == JobState.AWAITING_APPROVAL

    def test_needs_approval_not_in_result(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job("ap-2")
        q.enqueue(job, approval_handler)
        saved = store.get("ap-2")
        assert "_needs_approval" not in (saved.result or {})

    def test_audit_log_has_transitions(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job("audit-1")
        q.enqueue(job, success_handler)
        saved = store.get("audit-1")
        states = [e.to_state for e in saved.audit_log]
        assert "QUEUED" in states
        assert "RUNNING" in states
        assert "DONE" in states


# ---------------------------------------------------------------------------
# SynchronousQueue — hata ve retry
# ---------------------------------------------------------------------------

class TestSynchronousQueueFailure:
    def test_handler_error_sets_failed(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store, max_retries=3)
        job = make_job("fail-1")
        q.enqueue(job, failing_handler)
        saved = store.get("fail-1")
        assert saved.state == JobState.FAILED

    def test_error_message_stored(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store, max_retries=3)
        job = make_job("fail-err")
        q.enqueue(job, failing_handler)
        saved = store.get("fail-err")
        assert "simule hata" in (saved.error or "")

    def test_retry_count_increments(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store, max_retries=3)
        job = make_job("fail-cnt")
        q.enqueue(job, failing_handler)
        saved = store.get("fail-cnt")
        assert saved.retry_count == 1

    def test_dead_letter_when_retries_exhausted(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store, max_retries=1)
        job = make_job("dl-1")
        q.enqueue(job, failing_handler, max_retries=1)
        saved = store.get("dl-1")
        assert saved.state == JobState.DEAD_LETTER

    def test_retry_failed_job(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store, max_retries=3)
        job = make_job("retry-1")
        q.enqueue(job, failing_handler)
        # Ilk deneme FAILED olduktan sonra basarili handler ile retry
        q.retry("retry-1", success_handler)
        saved = store.get("retry-1")
        assert saved.state == JobState.DONE

    def test_retry_non_failed_raises(self):
        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = make_job("no-retry")
        q.enqueue(job, success_handler)  # DONE oluyor
        with pytest.raises(ValueError, match="retry"):
            q.retry("no-retry", success_handler)


# ---------------------------------------------------------------------------
# Stub'lar
# ---------------------------------------------------------------------------

class TestStubs:
    def test_celery_queue_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            CeleryQueue()

    def test_rq_queue_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            RQQueue()

    def test_celery_queue_is_subclass(self):
        assert issubclass(CeleryQueue, JobQueue)

    def test_rq_queue_is_subclass(self):
        assert issubclass(RQQueue, JobQueue)


# ---------------------------------------------------------------------------
# pipeline_job smoke testi
# ---------------------------------------------------------------------------

class TestPipelineJobSmoke:
    @pytest.mark.slow
    def test_pipeline_handler_returns_serializable_result(self):
        """Tam pipeline kosar; bu test slow olarak isaretlendi."""
        import json
        from src.runtime.pipeline_job import pipeline_handler

        job = Job(
            job_id="smoke-pipeline-1",
            idempotency_key="smoke-key",
            job_type="pipeline",
            payload={},  # varsayilan SCENARIO kullanilir
        )
        result = pipeline_handler(job)
        # JSON-serileştirilebilir olmali
        text = json.dumps(result)
        assert isinstance(text, str)
        # Temel anahtarlar var olmali
        assert "ranked_orders" in result
        assert "batches" in result
        assert "nesting_results" in result
        assert "pricing_results" in result

    def test_pipeline_handler_sets_needs_approval(self):
        """_needs_approval anahtari True olmali (insan onay kapisı)."""
        from src.runtime.pipeline_job import pipeline_handler

        job = Job(
            job_id="smoke-pipeline-2",
            idempotency_key="smoke-key-2",
            job_type="pipeline",
            payload={},
        )
        result = pipeline_handler(job)
        assert result.get("_needs_approval") is True

    def test_pipeline_job_via_queue_awaiting_approval(self):
        """SynchronousQueue + pipeline_handler birlikte AWAITING_APPROVAL'a gecer."""
        from src.runtime.pipeline_job import pipeline_handler

        store = InMemoryJobStore()
        q = SynchronousQueue(store)
        job = Job(
            job_id="smoke-q-1",
            idempotency_key="smoke-q-key-1",
            job_type="pipeline",
            payload={},
        )
        q.enqueue(job, pipeline_handler)
        saved = store.get("smoke-q-1")
        assert saved.state == JobState.AWAITING_APPROVAL
