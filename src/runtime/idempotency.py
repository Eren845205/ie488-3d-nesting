"""src/runtime/idempotency.py — Deterministik idempotency_key + dedup.

PLAN_SERVIS §3.2 / §0.4
------------------------
- idempotency_key(*parts) : SHA-256 tabanli, deterministik anahtar uretici.
- IdempotencyStore        : Islenmis anahtarlari izleyen basit depo.
  * register(key)   : Anahtar kayit eder; zaten kayitliysa DuplicateKeyError.
  * is_registered(key) : Kayitli mi? (bool)
- Depo arka yuzleri: InMemory (test) + Sqlite (disk-kalici, stdlib).
- Postgres arka yuzu (S0.1/S0.3): IdempotencyStore ABC'yi uygular, UNIQUE
  kisit ile INSERT; mevcut API degismez.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from typing import Any, Set


# ---------------------------------------------------------------------------
# Hata
# ---------------------------------------------------------------------------

class DuplicateKeyError(Exception):
    """Aynı idempotency_key ile register() iki kez cagrilirsa."""


# ---------------------------------------------------------------------------
# Anahtar uretici
# ---------------------------------------------------------------------------

def idempotency_key(*parts: Any, algorithm: str = "sha256") -> str:
    """Girdilerden deterministik bir idempotency anahtari uretir.

    Parametreler
    ------------
    *parts    : Stringe donusturulecek (JSON normalizasyonu ile) veriler.
    algorithm : hashlib algoritma adi (varsayilan "sha256").

    Donус
    -----
    Hex-string anahtar (sha256: 64 karakter).

    Ornek
    -----
    >>> idempotency_key("tenant1", "MSG-001", "abc123hash")
    'a3f...hex...'
    """
    normalized = json.dumps(
        [str(p) for p in parts],
        ensure_ascii=True,
        sort_keys=True,
    )
    h = hashlib.new(algorithm)
    h.update(normalized.encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Soyut temel
# ---------------------------------------------------------------------------

class IdempotencyStore(ABC):
    """Islenmis idempotency anahtarlarini izleyen soyut depo."""

    @abstractmethod
    def register(self, key: str) -> None:
        """Anahtari kaydet; zaten kayitliysa DuplicateKeyError."""

    @abstractmethod
    def is_registered(self, key: str) -> bool:
        """Anahtar daha once kayitli mi?"""

    @abstractmethod
    def unregister(self, key: str) -> None:
        """Anahtari sil (test / yeniden-isleme icin)."""


# ---------------------------------------------------------------------------
# Bellek-ici uygulama
# ---------------------------------------------------------------------------

class InMemoryIdempotencyStore(IdempotencyStore):
    """Thread-safe bellek-ici idempotency deposu."""

    def __init__(self) -> None:
        self._keys: Set[str] = set()
        self._lock = threading.Lock()

    def register(self, key: str) -> None:
        with self._lock:
            if key in self._keys:
                raise DuplicateKeyError(f"Anahtar zaten kayitli: {key!r}")
            self._keys.add(key)

    def is_registered(self, key: str) -> bool:
        with self._lock:
            return key in self._keys

    def unregister(self, key: str) -> None:
        with self._lock:
            self._keys.discard(key)


# ---------------------------------------------------------------------------
# SQLite uygulama
# ---------------------------------------------------------------------------

_DDL_IDEM = """
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key         TEXT PRIMARY KEY,
    registered_at TEXT NOT NULL
);
"""


class SqliteIdempotencyStore(IdempotencyStore):
    """stdlib sqlite3 tabanli idempotency deposu.

    Parametreler
    ------------
    db_path : Veritabani dosya yolu (":memory:" test icin)
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            # Her thread ilk erisimde kendi connection'ini kurar ve schema'yi da olusturur.
            # Bu, daemon thread'den (poller) ilk cagri geldiginde "no such table" hatasini onler.
            # check_same_thread=False: threading.local() zaten her thread'e ayri connection verir,
            # bu yuzden parametre pratikte gereksizdir; ancak sqlite3'un ilave guvenlik kontrolunu
            # kapatmak icin (connection baska contexte gecerse) explicit tutulur.
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.executescript(_DDL_IDEM)
            conn.commit()
            self._local.conn = conn
        return self._local.conn

    def _init_schema(self) -> None:
        # Sadece ana thread'de ilk connection'i (ve schema'yi) olusturur.
        # Yeni thread'ler _conn() uzerinden kendi schema'larini kurar.
        self._conn()

    def register(self, key: str) -> None:
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO idempotency_keys (key, registered_at) VALUES (?, ?)",
                (key, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise DuplicateKeyError(f"Anahtar zaten kayitli: {key!r}")

    def is_registered(self, key: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM idempotency_keys WHERE key = ?", (key,)
        ).fetchone()
        return row is not None

    def unregister(self, key: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
        conn.commit()
