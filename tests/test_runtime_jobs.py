"""tests/test_runtime_jobs.py — Job dataclass + JobState durum makinesi testleri.

Kapsam
------
- JobState gecis tablosu: gecerli gecisler gecmeli, gecersizler ValueError
- Job.transition() audit kaydi biriktirir
- Job.is_terminal() dogru sonuc dondurur
- Job.to_dict() / from_dict() round-trip
- Job.to_json() / from_json() round-trip
- AuditEntry.to_dict() / from_dict()
"""

from __future__ import annotations

import json
import pytest

from src.runtime.jobs import Job, JobState, AuditEntry


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------

def make_job(
    job_id: str = "test-job-1",
    state: JobState = JobState.RECEIVED,
) -> Job:
    return Job(
        job_id=job_id,
        idempotency_key="idem-key-1",
        job_type="test",
        payload={"x": 1},
        state=state,
    )


# ---------------------------------------------------------------------------
# JobState enum
# ---------------------------------------------------------------------------

class TestJobStateEnum:
    def test_all_states_exist(self):
        expected = {
            "RECEIVED", "QUEUED", "RUNNING", "AWAITING_APPROVAL",
            "APPROVED", "REJECTED", "DONE", "FAILED", "DEAD_LETTER",
        }
        actual = {s.value for s in JobState}
        assert expected == actual

    def test_str_enum_equality(self):
        assert JobState.RECEIVED == "RECEIVED"
        assert JobState.DONE == "DONE"


# ---------------------------------------------------------------------------
# Gecerli gecisler
# ---------------------------------------------------------------------------

class TestValidTransitions:
    def test_received_to_queued(self):
        job = make_job()
        job.transition(JobState.QUEUED)
        assert job.state == JobState.QUEUED

    def test_queued_to_running(self):
        job = make_job(state=JobState.QUEUED)
        job.transition(JobState.RUNNING)
        assert job.state == JobState.RUNNING

    def test_running_to_awaiting_approval(self):
        job = make_job(state=JobState.RUNNING)
        job.transition(JobState.AWAITING_APPROVAL)
        assert job.state == JobState.AWAITING_APPROVAL

    def test_running_to_done(self):
        job = make_job(state=JobState.RUNNING)
        job.transition(JobState.DONE)
        assert job.state == JobState.DONE

    def test_running_to_failed(self):
        job = make_job(state=JobState.RUNNING)
        job.transition(JobState.FAILED)
        assert job.state == JobState.FAILED

    def test_running_to_dead_letter(self):
        job = make_job(state=JobState.RUNNING)
        job.transition(JobState.DEAD_LETTER)
        assert job.state == JobState.DEAD_LETTER

    def test_awaiting_approval_to_approved(self):
        job = make_job(state=JobState.AWAITING_APPROVAL)
        job.transition(JobState.APPROVED)
        assert job.state == JobState.APPROVED

    def test_awaiting_approval_to_rejected(self):
        job = make_job(state=JobState.AWAITING_APPROVAL)
        job.transition(JobState.REJECTED)
        assert job.state == JobState.REJECTED

    def test_approved_to_done(self):
        job = make_job(state=JobState.APPROVED)
        job.transition(JobState.DONE)
        assert job.state == JobState.DONE

    def test_failed_to_queued(self):
        job = make_job(state=JobState.FAILED)
        job.transition(JobState.QUEUED)
        assert job.state == JobState.QUEUED

    def test_failed_to_dead_letter(self):
        job = make_job(state=JobState.FAILED)
        job.transition(JobState.DEAD_LETTER)
        assert job.state == JobState.DEAD_LETTER

    def test_queued_to_dead_letter(self):
        job = make_job(state=JobState.QUEUED)
        job.transition(JobState.DEAD_LETTER)
        assert job.state == JobState.DEAD_LETTER


# ---------------------------------------------------------------------------
# Gecersiz gecisler -> ValueError
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    def test_received_cannot_go_running(self):
        job = make_job()
        with pytest.raises(ValueError, match="Gecersiz gecis"):
            job.transition(JobState.RUNNING)

    def test_done_is_terminal(self):
        job = make_job(state=JobState.DONE)
        with pytest.raises(ValueError):
            job.transition(JobState.QUEUED)

    def test_rejected_is_terminal(self):
        job = make_job(state=JobState.REJECTED)
        with pytest.raises(ValueError):
            job.transition(JobState.APPROVED)

    def test_dead_letter_is_terminal(self):
        job = make_job(state=JobState.DEAD_LETTER)
        with pytest.raises(ValueError):
            job.transition(JobState.QUEUED)

    def test_running_cannot_go_received(self):
        job = make_job(state=JobState.RUNNING)
        with pytest.raises(ValueError):
            job.transition(JobState.RECEIVED)

    def test_approved_cannot_go_rejected(self):
        job = make_job(state=JobState.APPROVED)
        with pytest.raises(ValueError):
            job.transition(JobState.REJECTED)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_transition_appends_audit_entry(self):
        job = make_job()
        job.transition(JobState.QUEUED, note="test notu")
        assert len(job.audit_log) == 1
        entry = job.audit_log[0]
        assert entry.from_state == "RECEIVED"
        assert entry.to_state == "QUEUED"
        assert entry.note == "test notu"

    def test_multiple_transitions_accumulate(self):
        job = make_job()
        job.transition(JobState.QUEUED)
        job.transition(JobState.RUNNING)
        job.transition(JobState.DONE)
        assert len(job.audit_log) == 3

    def test_audit_worker_id_stored(self):
        job = make_job()
        job.transition(JobState.QUEUED, worker_id="worker-42")
        assert job.audit_log[0].worker_id == "worker-42"

    def test_audit_timestamp_not_empty(self):
        job = make_job()
        job.transition(JobState.QUEUED)
        assert job.audit_log[0].timestamp != ""

    def test_updated_at_changes_on_transition(self):
        job = make_job()
        before = job.updated_at
        job.transition(JobState.QUEUED)
        # updated_at en az gecis zamanina esit olmali
        assert job.updated_at >= before


# ---------------------------------------------------------------------------
# is_terminal()
# ---------------------------------------------------------------------------

class TestIsTerminal:
    def test_done_is_terminal(self):
        assert make_job(state=JobState.DONE).is_terminal() is True

    def test_rejected_is_terminal(self):
        assert make_job(state=JobState.REJECTED).is_terminal() is True

    def test_dead_letter_is_terminal(self):
        assert make_job(state=JobState.DEAD_LETTER).is_terminal() is True

    def test_running_not_terminal(self):
        assert make_job(state=JobState.RUNNING).is_terminal() is False

    def test_awaiting_approval_not_terminal(self):
        assert make_job(state=JobState.AWAITING_APPROVAL).is_terminal() is False


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_to_dict_from_dict(self):
        job = make_job()
        job.transition(JobState.QUEUED, note="seri test")
        d = job.to_dict()
        restored = Job.from_dict(d)
        assert restored.job_id == job.job_id
        assert restored.state == job.state
        assert len(restored.audit_log) == 1
        assert restored.audit_log[0].note == "seri test"

    def test_to_json_from_json(self):
        job = make_job()
        job.transition(JobState.QUEUED)
        text = job.to_json()
        restored = Job.from_json(text)
        assert restored.job_id == job.job_id
        assert isinstance(text, str)

    def test_to_dict_is_json_serializable(self):
        job = make_job()
        job.transition(JobState.QUEUED)
        d = job.to_dict()
        text = json.dumps(d)
        assert isinstance(text, str)

    def test_payload_preserved(self):
        job = Job(
            job_id="p-1",
            idempotency_key="k",
            job_type="pipeline",
            payload={"scenario": {"ref_date": "2026-06-14"}},
        )
        restored = Job.from_dict(job.to_dict())
        assert restored.payload["scenario"]["ref_date"] == "2026-06-14"

    def test_result_roundtrip(self):
        job = make_job()
        job.result = {"total_price": 123.45, "items": ["a", "b"]}
        restored = Job.from_dict(job.to_dict())
        assert restored.result == job.result


# ---------------------------------------------------------------------------
# AuditEntry round-trip
# ---------------------------------------------------------------------------

class TestAuditEntry:
    def test_roundtrip(self):
        entry = AuditEntry(
            timestamp="2026-06-14T10:00:00+00:00",
            from_state="QUEUED",
            to_state="RUNNING",
            note="basladi",
            worker_id="w1",
        )
        d = entry.to_dict()
        restored = AuditEntry.from_dict(d)
        assert restored.from_state == "QUEUED"
        assert restored.to_state == "RUNNING"
        assert restored.worker_id == "w1"
