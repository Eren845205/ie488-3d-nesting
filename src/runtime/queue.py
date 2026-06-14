"""src/runtime/queue.py — Soyut JobQueue + SynchronousQueue + stub'lar.

Uygulama secenekleri (PLAN_SERVIS §11.A):
  - SynchronousQueue : handler'i surecici HEMEN kosturur (Celery/Redis GEREKMEZ).
                       S0 kabul kriteri: isin store'a QUEUED olarak kaydedildigi
                       garanti edilir, sonra RUNNING -> DONE/FAILED gecisi yapilir.
  - CeleryQueue      : STUB (NotImplementedError) — S0.3'te gercek Celery impl.
  - RQQueue          : STUB (NotImplementedError) — S0.3 alternatifi.

Handler sozlesmesi
------------------
  handler(job: Job) -> Dict[str, Any]
    - JSON-serileştirilebilir bir dict dondurur.
    - Basarili donuste job.result bu dict olur, durum DONE/AWAITING_APPROVAL.
    - Istisna firlatirsa job FAILED/DEAD_LETTER'a gecer.

Dikkat: SynchronousQueue handler'i SENKRON kosturur — uzun nestin isleri
iceride bloklayabilir. Bu S0 kabul kriterini gecmek icin yeterlidir; asenkron
calisma S0.3 (Celery/Redis) fazina birakildi.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

from src.runtime.jobs import Job, JobState
from src.runtime.store import JobStore


# ---------------------------------------------------------------------------
# Handler tipi
# ---------------------------------------------------------------------------

JobHandler = Callable[[Job], Dict[str, Any]]


# ---------------------------------------------------------------------------
# Soyut temel
# ---------------------------------------------------------------------------

class JobQueue(ABC):
    """Calisma-zamani is kuyrugu soyut temeli."""

    @abstractmethod
    def enqueue(
        self,
        job: Job,
        handler: JobHandler,
        *,
        max_retries: int = 3,
    ) -> str:
        """Is'i kuyruga ekle; job_id dondur.

        Sozlesme
        --------
        - Job, enqueue oncesinde store'a QUEUED durumuyla KAYDEDILMIS olur.
        - SynchronousQueue hemen isler; asenkron impl'lar kuyruga birakir.
        """

    @abstractmethod
    def retry(self, job_id: str, handler: JobHandler) -> None:
        """FAILED/DEAD_LETTER is'i yeniden kuyruga ekle."""


# ---------------------------------------------------------------------------
# Senkron uygulama (S0 — Celery/Redis gerekmez)
# ---------------------------------------------------------------------------

class SynchronousQueue(JobQueue):
    """Handler'i hemen (surecici, senkron) kosuran is kuyrugu.

    Parametreler
    ------------
    store      : is durumlarini saklayan JobStore uygulamasi.
    max_retries: varsayilan yeniden-deneme limiti (handler override edebilir).
    """

    def __init__(self, store: JobStore, max_retries: int = 3) -> None:
        self._store = store
        self._default_max_retries = max_retries

    def enqueue(
        self,
        job: Job,
        handler: JobHandler,
        *,
        max_retries: Optional[int] = None,
    ) -> str:
        limit = max_retries if max_retries is not None else self._default_max_retries
        # Store'a kaydet (RECEIVED -> QUEUED)
        job.transition(JobState.QUEUED, note="SynchronousQueue: kuyruga eklendi")
        self._store.save(job)
        # Hemen isle
        self._run(job, handler, limit)
        return job.job_id

    def retry(self, job_id: str, handler: JobHandler) -> None:
        """FAILED veya DEAD_LETTER isi yeniden dene."""
        job = self._store.get(job_id)
        if job.state not in (JobState.FAILED, JobState.DEAD_LETTER):
            raise ValueError(
                f"retry yalniz FAILED veya DEAD_LETTER is'lerde gecerli; "
                f"mevcut durum: {job.state!r}"
            )
        job.transition(
            JobState.QUEUED,
            note=f"Manuel yeniden-deneme #{job.retry_count + 1}",
        )
        self._store.update(job)
        self._run(job, handler, self._default_max_retries)

    # -----------------------------------------------------------------------
    # Dahili: handler calistirma + durum yonetimi
    # -----------------------------------------------------------------------

    def _run(self, job: Job, handler: JobHandler, max_retries: int) -> None:
        """Handler'i kostur; basarili veya basarisiz duruma gec."""
        job.transition(JobState.RUNNING, note="SynchronousQueue: isleniyor")
        self._store.update(job)
        try:
            result = handler(job)
            self._on_success(job, result)
        except Exception as exc:  # noqa: BLE001
            self._on_failure(job, exc, max_retries)

    def _on_success(self, job: Job, result: Dict[str, Any]) -> None:
        """Basarili handler sonrasinda durumu guncelle."""
        needs_approval = result.get("_needs_approval", False)
        next_state = (
            JobState.AWAITING_APPROVAL if needs_approval else JobState.DONE
        )
        job.result = {k: v for k, v in result.items() if k != "_needs_approval"}
        job.error = None
        job.transition(next_state, note="Handler tamamlandi")
        self._store.update(job)

    def _on_failure(self, job: Job, exc: Exception, max_retries: int) -> None:
        """Handler hatasi sonrasinda durumu guncelle."""
        job.error = str(exc)
        job.retry_count += 1
        if job.retry_count >= max_retries:
            job.transition(
                JobState.DEAD_LETTER,
                note=f"Max retry ({max_retries}) asild: {exc}",
            )
        else:
            job.transition(
                JobState.FAILED,
                note=f"Hata (deneme {job.retry_count}/{max_retries}): {exc}",
            )
        self._store.update(job)


# ---------------------------------------------------------------------------
# Stub'lar — S0.3 infra fazina birakildi
# ---------------------------------------------------------------------------

class CeleryQueue(JobQueue):
    """Celery + Redis tabanli asenkron kuyruk.

    NOT: Bu sinif bir STUB'dir. Gercek implementasyon S0.3'te yapilacak.
    Bagimliliklar: celery, redis (stdlib DISINDA — PLAN_SERVIS §11.A).

    Takma noktasi: CeleryQueue(store, app=celery_app, queue_name="default")
    JobQueue ABC uygulayan bu sinifi SynchronousQueue yerine inject et.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "CeleryQueue S0.3 fazinda uygulanacak. "
            "Su an SynchronousQueue kullanin."
        )

    def enqueue(self, job: Job, handler: JobHandler, **kwargs: Any) -> str:
        raise NotImplementedError

    def retry(self, job_id: str, handler: JobHandler) -> None:
        raise NotImplementedError


class RQQueue(JobQueue):
    """RQ (Redis Queue) tabanli asenkron kuyruk.

    NOT: Bu sinif bir STUB'dir. Celery vs RQ karari S0.3'te verilecek
    (PLAN_SERVIS §11.A). Gercek implementasyon o fazda yapilacak.
    Bagimliliklar: rq, redis (stdlib DISINDA).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "RQQueue S0.3 fazinda uygulanacak. "
            "Su an SynchronousQueue kullanin."
        )

    def enqueue(self, job: Job, handler: JobHandler, **kwargs: Any) -> str:
        raise NotImplementedError

    def retry(self, job_id: str, handler: JobHandler) -> None:
        raise NotImplementedError
