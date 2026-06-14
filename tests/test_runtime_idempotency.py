"""tests/test_runtime_idempotency.py — idempotency_key + IdempotencyStore testleri.

Kapsam
------
- idempotency_key() deterministik ve SHA-256 tabanli
- Farkli girdiler farkli anahtar uretir
- InMemoryIdempotencyStore: register / is_registered / unregister
- SqliteIdempotencyStore: ayni API, disk-kalici (":memory:" kullanilir)
- register() iki kez cagrisi DuplicateKeyError firlatir
"""

from __future__ import annotations

import pytest

from src.runtime.idempotency import (
    DuplicateKeyError,
    IdempotencyStore,
    InMemoryIdempotencyStore,
    SqliteIdempotencyStore,
    idempotency_key,
)


# ---------------------------------------------------------------------------
# idempotency_key() fonksiyon testleri
# ---------------------------------------------------------------------------

class TestIdempotencyKeyFunction:
    def test_deterministic_same_inputs(self):
        k1 = idempotency_key("tenant1", "MSG-001", "abc")
        k2 = idempotency_key("tenant1", "MSG-001", "abc")
        assert k1 == k2

    def test_different_inputs_different_keys(self):
        k1 = idempotency_key("tenant1", "MSG-001")
        k2 = idempotency_key("tenant1", "MSG-002")
        assert k1 != k2

    def test_order_matters(self):
        k1 = idempotency_key("a", "b")
        k2 = idempotency_key("b", "a")
        assert k1 != k2

    def test_returns_hex_string(self):
        k = idempotency_key("x")
        assert isinstance(k, str)
        assert len(k) == 64  # sha256 = 32 bayt = 64 hex karakter
        int(k, 16)  # gecerli hex

    def test_empty_parts_is_consistent(self):
        k1 = idempotency_key()
        k2 = idempotency_key()
        assert k1 == k2

    def test_algorithm_sha1(self):
        k = idempotency_key("x", algorithm="sha1")
        assert len(k) == 40  # sha1 = 20 bayt = 40 hex

    def test_numeric_parts_coerced(self):
        k1 = idempotency_key(1, 2, 3)
        k2 = idempotency_key("1", "2", "3")
        assert k1 == k2  # str()'e cevriliyor


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(params=["memory", "sqlite"])
def idem_store(request) -> IdempotencyStore:
    if request.param == "memory":
        return InMemoryIdempotencyStore()
    return SqliteIdempotencyStore(db_path=":memory:")


# ---------------------------------------------------------------------------
# IdempotencyStore testleri
# ---------------------------------------------------------------------------

class TestIdempotencyStore:
    def test_register_then_is_registered(self, idem_store: IdempotencyStore):
        key = idempotency_key("tenant1", "MSG-001")
        idem_store.register(key)
        assert idem_store.is_registered(key) is True

    def test_not_registered_before_register(self, idem_store: IdempotencyStore):
        key = idempotency_key("new-key")
        assert idem_store.is_registered(key) is False

    def test_duplicate_register_raises(self, idem_store: IdempotencyStore):
        key = idempotency_key("dup-key")
        idem_store.register(key)
        with pytest.raises(DuplicateKeyError):
            idem_store.register(key)

    def test_unregister_removes_key(self, idem_store: IdempotencyStore):
        key = idempotency_key("temp-key")
        idem_store.register(key)
        idem_store.unregister(key)
        assert idem_store.is_registered(key) is False

    def test_unregister_nonexistent_no_error(self, idem_store: IdempotencyStore):
        # discard semantigi: hata firlatmaz
        idem_store.unregister("nonexistent-key")

    def test_different_keys_independent(self, idem_store: IdempotencyStore):
        k1 = idempotency_key("mail1")
        k2 = idempotency_key("mail2")
        idem_store.register(k1)
        # k2 hala kayitsiz olmali
        assert idem_store.is_registered(k2) is False
        idem_store.register(k2)
        assert idem_store.is_registered(k1) is True
        assert idem_store.is_registered(k2) is True

    def test_register_after_unregister(self, idem_store: IdempotencyStore):
        key = idempotency_key("reprocess-mail")
        idem_store.register(key)
        idem_store.unregister(key)
        # Yeniden kayit gecerli olmali
        idem_store.register(key)
        assert idem_store.is_registered(key) is True


# ---------------------------------------------------------------------------
# Dedup senaryosu (is duzeyinde)
# ---------------------------------------------------------------------------

class TestDeduplicationScenario:
    def test_same_mail_processed_once(self, idem_store: IdempotencyStore):
        """Ayni mail iki kez gelince ikincisi atlanir."""
        tenant = "tenant1"
        message_id = "<unique@mail.server>"
        attachment_hash = "abc123"
        key = idempotency_key(tenant, message_id, attachment_hash)

        # Ilk islem
        assert idem_store.is_registered(key) is False
        idem_store.register(key)

        # Ikinci gorume (poll cakismasi)
        with pytest.raises(DuplicateKeyError):
            idem_store.register(key)

        # Islenenlerin sayisi 1 kalmali
        assert idem_store.is_registered(key) is True
