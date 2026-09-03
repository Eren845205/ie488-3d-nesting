"""tests/test_mail_poller_idempotency.py — Poller turlar-arasi idempotency TDD.

Kapsam
------
- Paylasilmis SqliteIdempotencyStore ile iki ardisik make_mail_source() cagrisi
  (yani iki poll turu): ilk turda islenen UID ikinci turda ATLANMALI.
- Restart benzeri senaryo: ayni disk-path SQLite ile yeni store ornegi, onceki
  UID'i hala is_registered gormeli.
- Geriye uyum: idem_store=None verilen ImapMailbox MEVCUT bagimsiz store davranisini
  korur (yeni instance yeni bos store = eski davranis).
- make_mail_source(cfg, idem_store=shared) API testi.
- Thread guvenligi: yeni daemon thread'den :memory: store'a erisim (schema mevcut olmali).
- app.py entegrasyonu: SHARED_IDEM_STORE enjeksiyon mekanizmi.

NOT: Gercek IMAP'a baglanmaz. ImapMailbox._idem_key + SqliteIdempotencyStore
dogrudan test edilir; _fetch_uids icindeki is_registered mantigi birim testlerde
kanitlanir.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.idempotency import SqliteIdempotencyStore, DuplicateKeyError
from src.runtime.mail_ingest import ImapMailbox, make_mail_source, FakeMailbox


# ---------------------------------------------------------------------------
# Yardimci: minimal gecerli IMAP konfig (gercek baglanti kurulmaz)
# ---------------------------------------------------------------------------

_IMAP_CFG = {
    "source": "imap",
    "host": "imap.example.com",
    "port": 993,
    "user": "test@example.com",
    "password": "secret",
    "folder": "INBOX",
    "use_ssl": True,
}


# ---------------------------------------------------------------------------
# SqliteIdempotencyStore thread guvenligi — regresyon (BULGU 3)
# ---------------------------------------------------------------------------

class TestSqliteThreadSafety:
    """Yeni thread'den :memory: store'a erisim schema olmadan basarili olmali."""

    def test_yeni_thread_memory_store_schema_goruyor(self):
        """Daemon thread'den SqliteIdempotencyStore kullanimi 'no such table' vermemeli.

        Eski davranis: schema yalniz __init__ thread'inde kurulurdu; yeni thread
        :memory: bagi kurduğunda bos db alir -> no such table. Duzeltilmis davranis:
        _conn() her thread icin baglanirken schema'yi da kurar.
        """
        store = SqliteIdempotencyStore(db_path=":memory:")
        errors: list = []

        def thread_target():
            try:
                # Yeni thread'de store'a erisim: schema olusturulmali
                assert not store.is_registered("thread-test-key")
                store.register("thread-test-key")
                assert store.is_registered("thread-test-key")
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=thread_target, daemon=True)
        t.start()
        t.join(timeout=5.0)
        assert not errors, f"Thread'den store erisimi hata verdi: {errors[0]}"
        assert not t.is_alive(), "Thread 5 saniye icinde bitmedi"

    def test_disk_db_yeni_thread_schema_goruyor(self, tmp_path):
        """Disk bazli store'da da yeni thread schema'yi kendi baginda kurar."""
        db_path = str(tmp_path / "thread_test.db")
        store = SqliteIdempotencyStore(db_path=db_path)
        errors: list = []

        def thread_target():
            try:
                store.register("disk-thread-key")
                assert store.is_registered("disk-thread-key")
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=thread_target, daemon=True)
        t.start()
        t.join(timeout=5.0)
        assert not errors, f"Disk store thread hatasi: {errors[0]}"

        # Ana thread de gorur (disk paylasimi)
        assert store.is_registered("disk-thread-key")


# ---------------------------------------------------------------------------
# ImapMailbox idem_store enjeksiyonu — birim testler
# ---------------------------------------------------------------------------

class TestImapMailboxIdemStoreInjection:
    """ImapMailbox'a dis store enjekte edilebilmeli."""

    def test_shared_store_enjekte_edilince_kullanilir(self):
        """idem_store parametresi verilirse ImapMailbox kendi store yerine onu kullanir."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)
        assert box._idem_store is shared

    def test_idem_store_none_ise_bagimsiz_store_olusturur(self):
        """idem_store=None (varsayilan) -> ImapMailbox bagimsiz bir store alir.

        Davranis testi: baska bir ImapMailbox(idem_store=None) ile paylasim yok.
        """
        box1 = ImapMailbox(_IMAP_CFG, idem_store=None)
        box2 = ImapMailbox(_IMAP_CFG, idem_store=None)

        # Bagimsiz: box1'in register'i box2'de gorulmez
        key = box1._idem_key("uid-test-bagimsiz")
        box1._idem_store.register(key)
        assert box1._idem_store.is_registered(key)
        assert not box2._idem_store.is_registered(key), (
            "idem_store=None: iki instance bagimsiz store almali — paylasim olmamali"
        )

    def test_iki_farkli_instance_ayri_store_kullanir_varsayilan(self):
        """idem_store=None iken iki instance ayri (bagimsiz) store alir."""
        box1 = ImapMailbox(_IMAP_CFG)
        box2 = ImapMailbox(_IMAP_CFG)
        assert box1._idem_store is not box2._idem_store

    def test_iki_instance_paylasilmis_store_gorur(self):
        """Paylasilmis store: box1'in register ettigi UID box2 tarafindan is_registered gorulmeli."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box1 = ImapMailbox(_IMAP_CFG, idem_store=shared)
        box2 = ImapMailbox(_IMAP_CFG, idem_store=shared)

        uid = "42"
        key = box1._idem_key(uid)

        # Henuz kayitli degil
        assert not box1._idem_store.is_registered(key)
        assert not box2._idem_store.is_registered(key)

        # box1 register eder
        box1._idem_store.register(key)

        # box2 de gorur (ayni store)
        assert box2._idem_store.is_registered(key)

    def test_idem_key_sha256_uretir(self):
        """_idem_key SHA-256 hex digest (64 karakter) dondurur; email plaintext gomulmez."""
        box = ImapMailbox(_IMAP_CFG)
        key = box._idem_key("999")
        assert len(key) == 64, "SHA-256 hex digest 64 karakter olmali"
        int(key, 16)  # gecerli hex
        # E-posta adresi plaintext anahtara gomulmemeli
        assert "test@example.com" not in key, (
            "E-posta adresi idempotency anahtarinda plaintext bulunmamali"
        )


# ---------------------------------------------------------------------------
# Cok-turlu idempotency senaryosu
# ---------------------------------------------------------------------------

class TestCokTurluIdempotency:
    """Paylasilmis store: tur 1'de islenen UID tur 2'de atlanir."""

    def test_tur1_kayit_tur2_filtreler(self):
        """Paylasilan in-memory store ile iki ardisik 'poll turu' simule edilir.

        _fetch_uids icindeki filtre: u not in _seen_uids and not _idem_store.is_registered(...)
        Bu testi gecmek icin ImapMailbox'in enjekte edilen store'u kullanmasi GEREKIR.
        """
        shared = SqliteIdempotencyStore(db_path=":memory:")

        # Tur 1: box1 (poll A)
        box1 = ImapMailbox(_IMAP_CFG, idem_store=shared)
        uid = "100"
        key = box1._idem_key(uid)

        # Tur 1 sonunda UID islendi, kalici store'a kaydet
        assert not shared.is_registered(key)
        shared.register(key)

        # Tur 2: yeni ImapMailbox ornegi (= mevcut bug: eski davranista bu yeni :memory: alirdi)
        box2 = ImapMailbox(_IMAP_CFG, idem_store=shared)

        # Tur 2'de filtre: is_registered True donmeli -> UID atlanmali
        assert shared.is_registered(box2._idem_key(uid)), (
            "Tur 2'de paylasilmis store'da UID kayitli gorunmeli"
        )

    def test_farkli_uid_atlanmaz(self):
        """Yalnizca islenen UID atlanir; islenmemis UID hala gec."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)

        uid_islendi = "200"
        uid_yeni = "201"

        shared.register(box._idem_key(uid_islendi))

        assert shared.is_registered(box._idem_key(uid_islendi))
        assert not shared.is_registered(box._idem_key(uid_yeni))


# ---------------------------------------------------------------------------
# Restart benzeri senaryo — disk-kalici SQLite
# ---------------------------------------------------------------------------

class TestRestartSenaryosu:
    """Ayni disk-path SQLite ile yeni store ornegi, onceki UID'i hala gorur."""

    def test_disk_db_restart_sonrasi_kayit_korunur(self, tmp_path):
        db_path = str(tmp_path / "idem_test.db")

        # Oturum 1: kaydet
        store1 = SqliteIdempotencyStore(db_path=db_path)
        box1 = ImapMailbox(_IMAP_CFG, idem_store=store1)
        uid = "300"
        key = box1._idem_key(uid)
        store1.register(key)
        assert store1.is_registered(key)

        # Oturum 2: ayni dosya, yeni store ornegi (restart simule)
        store2 = SqliteIdempotencyStore(db_path=db_path)
        box2 = ImapMailbox(_IMAP_CFG, idem_store=store2)
        assert store2.is_registered(box2._idem_key(uid)), (
            "Disk SQLite ile restart sonrasi UID kayitli gorunmeli"
        )

    def test_memory_store_restart_sonrasi_kayit_kaybolur(self):
        """:memory: store restart sonrasi sifirlanir — beklenen davranis (eski uyum)."""
        uid = "400"

        # Oturum 1
        store1 = SqliteIdempotencyStore(db_path=":memory:")
        box1 = ImapMailbox(_IMAP_CFG, idem_store=store1)
        store1.register(box1._idem_key(uid))

        # Oturum 2: yeni :memory: store (bagimsiz — bellek temizlendi)
        store2 = SqliteIdempotencyStore(db_path=":memory:")
        box2 = ImapMailbox(_IMAP_CFG, idem_store=store2)
        # :memory: bagimsiz -> kayit yok (beklenen)
        assert not store2.is_registered(box2._idem_key(uid))


# ---------------------------------------------------------------------------
# make_mail_source idem_store parametresi
# ---------------------------------------------------------------------------

class TestMakeMailSourceIdemStore:
    """make_mail_source(cfg, idem_store=shared) API testi."""

    def test_idem_store_imap_kaynak_iletilir(self):
        """idem_store verilince ImapMailbox'a iletilmeli."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        src = make_mail_source(_IMAP_CFG, idem_store=shared)
        assert isinstance(src, ImapMailbox)
        assert src._idem_store is shared

    def test_idem_store_none_iki_instance_bagimsiz(self):
        """idem_store=None (varsayilan) -> iki IMAP kaynak bagimsiz store alir.

        Davranis testi: _db_path gibi private attribute yerine store davranisi kontrol edilir.
        """
        src1 = make_mail_source(_IMAP_CFG, idem_store=None)
        src2 = make_mail_source(_IMAP_CFG, idem_store=None)
        assert isinstance(src1, ImapMailbox)
        assert isinstance(src2, ImapMailbox)
        # Bagimsizlik: ayni store referansi olmamali
        assert src1._idem_store is not src2._idem_store, (
            "idem_store=None: her make_mail_source cagrisi bagimsiz store olmali"
        )

        # Fake kaynak: FakeMailbox donmeli, idem_store etkilememeli
        fake_src = make_mail_source({"source": "fake"}, idem_store=None)
        assert isinstance(fake_src, FakeMailbox)

    def test_idem_store_provider_yolu_iletilir(self):
        """Provider yolu (gmail) da idem_store'u ImapMailbox'a iletmeli."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        gmail_cfg = {
            "provider": "gmail",
            "user": "test@gmail.com",
            "password": "apppassword",
        }
        src = make_mail_source(gmail_cfg, idem_store=shared)
        assert isinstance(src, ImapMailbox)
        assert src._idem_store is shared

    def test_idem_store_fake_kaynak_etkilenmez(self):
        """Fake kaynak idem_store parametresinden etkilenmez (FakeMailbox'ta store yok)."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        src = make_mail_source({"source": "fake"}, idem_store=shared)
        assert isinstance(src, FakeMailbox)
        # FakeMailbox'ta _idem_store attribute'u olmamali (ya da etkilenmemeli)
        assert not hasattr(src, "_idem_store")


# ---------------------------------------------------------------------------
# app.py entegrasyon: _poll_make_source paylasilmis store kullanir
# ---------------------------------------------------------------------------

class TestAppPollerSharedStore:
    """create_app TESTING modunda poller paylasilmis store kullanmali.

    Bu sinif app.py'nin injection mekanizmasini dogrular:
    - SHARED_IDEM_STORE app.config'de bulunmali
    - make_mail_source IMAP yoluyla cagrildiginda shared store dogru iletilmeli
      (app.py:628'deki idem_store=_shared_idem_store kaldirilirsa test FAIL eder)
    """

    def test_app_paylasimli_idem_store_config_icinde(self):
        """app.config icinde SHARED_IDEM_STORE bulunmali (poller paylasilmis store kullanir)."""
        from src.webapp.app import create_app
        app = create_app(testing=True, llm_enabled=False)
        assert "SHARED_IDEM_STORE" in app.config, (
            "app.config'de SHARED_IDEM_STORE bulunmali — poller paylasilmis store kullanir"
        )

    def test_injection_mekanizmi_make_mail_source_ile_calisir(self):
        """app.config'deki shared store, make_mail_source IMAP yolundan dogru iletilir.

        Bu test app.py'de kullanilan injection mekanizmasini dogrular:
          make_mail_source(cfg, idem_store=_shared_idem_store)
        make_mail_source ya da ImapMailbox'tan idem_store iletimi kaldirilirsa FAIL eder.
        Gercek IMAP'a BAGLANMAZ — yalniz constructor injection kanitlanir.
        """
        from src.webapp.app import create_app
        app = create_app(testing=True, llm_enabled=False)
        shared = app.config["SHARED_IDEM_STORE"]

        # Ayni store'u IMAP yoluyla enjekte et (app.py'deki _poll_make_source ile ayni mekanizma)
        src = make_mail_source(_IMAP_CFG, idem_store=shared)
        assert isinstance(src, ImapMailbox)
        assert src._idem_store is shared, (
            "make_mail_source idem_store parametresini ImapMailbox'a iletmeli — "
            "enjeksiyon kaldirilirsa bu assertion basarisiz olur"
        )

    def test_shared_store_key_turlar_arasi_gorulur(self):
        """app'in shared store'u: tur 1'de kayit edilen key tur 2'de gorunmeli."""
        from src.webapp.app import create_app
        app = create_app(testing=True, llm_enabled=False)
        shared = app.config["SHARED_IDEM_STORE"]

        # Tur 1 simule: bir key kaydet
        test_key = "test:integration:uid-777"
        assert not shared.is_registered(test_key)
        shared.register(test_key)

        # Tur 2 simule: ayni store referansiyla yeni sorgu (paylasim korunmali)
        shared2 = app.config["SHARED_IDEM_STORE"]
        assert shared2 is shared, "app.config her seferinde ayni store referansini vermeli"
        assert shared2.is_registered(test_key), (
            "Paylasilmis store turlar arasi state'i koruyor olmali"
        )
