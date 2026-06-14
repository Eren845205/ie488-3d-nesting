"""src/runtime — Calisma-zamani iskeleti (PLAN_SERVIS Faz S0).

Modüller
--------
jobs          : Job dataclass + JobState enum + durum makinesi + audit
store         : soyut JobStore + InMemoryJobStore + SqliteJobStore (stdlib)
idempotency   : deterministik idempotency_key + dedup
queue         : soyut JobQueue + SynchronousQueue + stub'lar (Celery/RQ)
pipeline_job  : demo pipeline'i job handler olarak saran sarmalayici

Degismezler (PLAN_SERVIS §0)
-----------------------------
- Motor saf kalir: src/nesting3d/ motoruna DOKUNULMAZ, yalniz read-only cagri.
- Yeni agir bagimlilik yok: yalniz stdlib (sqlite3, dataclasses, enum,
  hashlib, json, threading).
- Job sonucu JSON-serileştirilebilir.
- Idempotency zorunlu; SynchronousQueue bile job'u store'a yazar.
"""

from src.runtime.jobs import Job, JobState
from src.runtime.store import InMemoryJobStore, SqliteJobStore
from src.runtime.idempotency import idempotency_key, IdempotencyStore
from src.runtime.queue import SynchronousQueue

__all__ = [
    "Job",
    "JobState",
    "InMemoryJobStore",
    "SqliteJobStore",
    "idempotency_key",
    "IdempotencyStore",
    "SynchronousQueue",
]
