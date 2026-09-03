"""tests/test_at_least_once_idempotency.py — At-least-once idempotency TDD.

Kapsam
------
Kok sorun: fetch_new icinde register yapiliyordu (at-most-once — siparis kaybi).
Hedef davranis: register YALNIZ mail kesin sonuclandi sonra yapilir (at-least-once).

- Gecici hata (pipeline exception) -> uid store'a YAZILMAZ -> sonraki tur tekrar dener.
- Basari (pipeline OK) -> order-ureten maillerin uid'leri store'a yazilir -> sonraki tur atlar.
- Spam (ingest None) -> uid store'a yazilir -> sonraki tur tekrar LLM'e gitme.
- needs_review (eksik bilgi) -> pending_store'a alindi -> uid store'a yazilir.

Yapi:
  - Gercek IMAP'a baglanmaz.
  - ImapMailbox.mark_processed + RawMail.uid dogrudan test edilir.
  - process_inbox_once monkeypatch ile test edilir (run_pipeline + ingest_order patch'lenir).
  - Patch hedefleri: "scripts.demo_pipeline.run_pipeline" ve "src.runtime.mail_ingest.ingest_order"
    (process_inbox_once icinde lazy import => kaynak modulden patch'lenir).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.idempotency import SqliteIdempotencyStore
from src.runtime.mail_ingest import ImapMailbox, RawMail, MailSource


# ---------------------------------------------------------------------------
# Yardimcilar
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

_BASE_SCENARIO: Dict[str, Any] = {
    "ref_date": None,
    "orders": [],
    "container": None,
}

_FAKE_PIPELINE_RESULT: Dict[str, Any] = {
    "ranked_orders": [],
    "batches": ["b1"],
    "nesting_results": {"b1": {"height_mm": 100.0, "density": 0.5,
                                "nesting_mode_used": "heightmap"}},
    "pricing_results": {"b1": {"total_price": 100.0}},
    "elapsed_sec": 1.0,
}

_DUMMY_ORDER: Dict[str, Any] = {
    "order_id": "O-TEST",
    "customer": "ACME",
    "deadline": "2099-01-01",
    "priority_class": 2,
    "parts": [{"id": "p1", "name": "p1", "qty": 1, "source": "llm_text",
               "width_mm": 80.0, "depth_mm": 60.0, "height_mm": 30.0}],
    "parse_source": "llm_text",
}


def _make_raw_mail(uid: str, govde: str = "parca 3 adet 80x60x30 mm") -> RawMail:
    """uid tasiyan minimal RawMail uret."""
    return RawMail(
        gonderen="test@example.com",
        konu="Test siparisi",
        govde=govde,
        tarih="2026-06-28T10:00:00+03:00",
        message_id=f"<test-{uid}@example.com>",
        uid=uid,
    )


def _make_spam_mail(uid: str) -> RawMail:
    """Siparis sinyali olmayan mail (ingest None doner)."""
    return RawMail(
        gonderen="newsletter@example.com",
        konu="Haftalik Bulten",
        govde="Bildirim mailidir, siparis bilgisi yok.",
        tarih="2026-06-28T10:00:00+03:00",
        message_id=f"<spam-{uid}@example.com>",
        uid=uid,
    )


class _TrackingSource(MailSource):
    """Test icin uid tasiyan mailleri veren ve mark_processed'i izleyen kaynak.

    Store'a kayit: mark_processed cagirisinda. fetch_new: store'da kayitli
    uid'leri + _seen setini filtreler (ImapMailbox davranisi).
    MailSource'dan turediyor — fetch_new abstract => implement etmek zorundayiz.
    """

    def __init__(self, mails: List[RawMail],
                 store: Optional[SqliteIdempotencyStore] = None) -> None:
        self._mails = mails
        self.store = store or SqliteIdempotencyStore(db_path=":memory:")
        self._seen: set = set()

    def _key(self, uid: str) -> str:
        return f"uid:{uid}"

    def fetch_new(self) -> List[RawMail]:
        result = []
        for m in self._mails:
            if m.uid and m.uid in self._seen:
                continue
            if m.uid and self.store.is_registered(self._key(m.uid)):
                continue
            if m.uid:
                self._seen.add(m.uid)
            result.append(m)
        return result

    def mark_processed(self, mail: RawMail) -> None:
        if not mail.uid:
            return
        try:
            self.store.register(self._key(mail.uid))
        except Exception:
            pass

    def is_processed(self, uid: str) -> bool:
        return self.store.is_registered(self._key(uid))


# ---------------------------------------------------------------------------
# RawMail.uid alani
# ---------------------------------------------------------------------------

class TestRawMailUidAlani:
    """RawMail uid alani zorunlulugu — at-least-once icin."""

    def test_rawmail_uid_none_varsayilan(self):
        """uid verilmezse None olmali (FakeMailbox, geri uyum)."""
        mail = RawMail(
            gonderen="a@b.com",
            konu="x",
            govde="y",
            tarih="2026-01-01",
            message_id="<mid@x>",
        )
        assert mail.uid is None

    def test_rawmail_uid_set_edilebilir(self):
        """uid verilirse saklanmali (ImapMailbox path)."""
        mail = _make_raw_mail("42")
        assert mail.uid == "42"

    def test_rawmail_uid_eski_kodda_bozmuyor(self):
        """ekler= ile olusturulmus RawMail uid=None ile geriye uyumlu."""
        mail = RawMail(
            gonderen="a@b.com", konu="x", govde="y",
            tarih="2026-01-01", message_id="<mid@x>",
            ekler=[],
        )
        assert mail.uid is None


# ---------------------------------------------------------------------------
# MailSource.mark_processed — varsayilan no-op
# ---------------------------------------------------------------------------

class TestMailSourceMarkProcessedDefault:
    """MailSource alt siniflari mark_processed inherit eder, no-op uretir."""

    def test_fakemailbox_mark_processed_noop(self):
        """FakeMailbox mark_processed cagrisi hata vermemeli."""
        from src.runtime.mail_ingest import FakeMailbox
        fb = FakeMailbox()
        mails = fb.fetch_new()
        if mails:
            fb.mark_processed(mails[0])  # AttributeError veya exception olmamali

    def test_mark_processed_none_uid_noop(self):
        """uid=None olan mail icin ImapMailbox.mark_processed no-op olmali."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)
        mail = RawMail(
            gonderen="a@b.com", konu="x", govde="y",
            tarih="2026-01-01", message_id="<mid@x>",
        )
        box.mark_processed(mail)  # uid=None -> no-op, hata vermemeli
        # Store'a hicbir sey eklenmemeli
        assert shared.is_registered("") is False  # trivial check

    def test_tracking_source_mark_processed_kaydeder(self):
        """_TrackingSource.mark_processed store'a yazar."""
        mail = _make_raw_mail("99")
        src = _TrackingSource([mail])
        assert not src.is_processed("99")
        src.mark_processed(mail)
        assert src.is_processed("99")


# ---------------------------------------------------------------------------
# ImapMailbox.mark_processed — birim testler
# ---------------------------------------------------------------------------

class TestImapMailboxMarkProcessed:
    """mark_processed: uid'yi kalici store'a yazar."""

    def test_mark_processed_uid_store_a_kaydeder(self):
        """mark_processed sonrasi uid store'da is_registered True olmali."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)
        mail = _make_raw_mail("55")

        assert not shared.is_registered(box._idem_key("55"))
        box.mark_processed(mail)
        assert shared.is_registered(box._idem_key("55"))

    def test_mark_processed_tekrar_noop(self):
        """Ayni uid iki kez mark_processed -> DuplicateKeyError yutulmali."""
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)
        mail = _make_raw_mail("66")
        box.mark_processed(mail)
        box.mark_processed(mail)  # ikinci cagri da hata atmamalı
        assert shared.is_registered(box._idem_key("66"))

    def test_fetch_new_artik_register_yapmaz(self):
        """fetch_new sonrasi shared store bos olmali — at-least-once: kayit ertelendi.

        Bu testi gecmek icin ImapMailbox.fetch_new icindeki register cagrisi
        KALDIRILMIS olmali. _seen_uids eklenir (process-dedup) ama kalici store'a YAZILMAZ.
        """
        shared = SqliteIdempotencyStore(db_path=":memory:")
        box = ImapMailbox(_IMAP_CFG, idem_store=shared)

        dummy_uid = "77"

        # _fetch_uids ve _connect patch'le — gercek IMAP gerekmesin
        from unittest.mock import patch, MagicMock
        with patch.object(box, "_connect") as mock_conn, \
             patch.object(box, "_fetch_uids", return_value=[dummy_uid]):
            mock_conn.return_value.uid.return_value = (
                "OK",
                [(b"1 (RFC822 {57}",
                  b"From: a@b.com\r\nSubject: t\r\nMessage-ID: <x@y>\r\n\r\nbody")]
            )
            mock_conn.return_value.logout = MagicMock()
            mails = box.fetch_new()

        # fetch sonrasi store BOSKI olmali
        assert not shared.is_registered(box._idem_key(dummy_uid)), (
            "fetch_new register YAPMAMALI — at-least-once: kayit mark_processed'e ertelendi"
        )
        # _seen_uids'e eklenmiş olmali (process-dedup saglanmali)
        assert dummy_uid in box._seen_uids


# ---------------------------------------------------------------------------
# process_inbox_once — at-least-once davranis testleri
# ---------------------------------------------------------------------------

class TestProcessInboxOnceAtLeastOnce:
    """process_inbox_once at-least-once semantigi.

    Patch hedefleri (lazy import edildiği modüller):
      - "scripts.demo_pipeline.run_pipeline"
      - "src.runtime.mail_ingest.ingest_order"
    """

    def test_pipeline_exception_uid_store_a_yazilmaz(self, monkeypatch):
        """run_pipeline exception atarsa uid kalici store'a YAZILMAMALI — sonraki tur tekrar dener."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("101")
        source = _TrackingSource([mail])

        monkeypatch.setattr(
            "scripts.demo_pipeline.run_pipeline",
            MagicMock(side_effect=RuntimeError("pipeline patlasin")),
        )
        monkeypatch.setattr(
            "src.runtime.mail_ingest.ingest_order",
            MagicMock(return_value=dict(_DUMMY_ORDER)),
        )

        result = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)

        assert result is None, "Pipeline exception -> None donmeli"
        assert not source.is_processed("101"), (
            "Pipeline exception: uid kalici store'a yazilmamali — at-least-once"
        )

    def test_pipeline_basarili_uid_store_a_yazilir(self, monkeypatch):
        """run_pipeline basarili -> order-ureten maillerin uid'leri store'a yazilmali."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("102")
        source = _TrackingSource([mail])

        monkeypatch.setattr(
            "scripts.demo_pipeline.run_pipeline",
            MagicMock(return_value=_FAKE_PIPELINE_RESULT),
        )
        monkeypatch.setattr(
            "src.runtime.mail_ingest.ingest_order",
            MagicMock(return_value=dict(_DUMMY_ORDER)),
        )

        result = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)

        assert result is not None, "Basarili pipeline sonucu None olmamali"
        assert source.is_processed("102"), (
            "Pipeline basarisi sonrasi uid kalici store'a yazilmali"
        )

    def test_ikinci_tur_kayitli_uid_atlar(self, monkeypatch):
        """Store'da kayitli uid ikinci turda fetch filtresinden gecmemeli."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("103")
        source = _TrackingSource([mail])

        pipeline_mock = MagicMock(return_value=_FAKE_PIPELINE_RESULT)
        ingest_mock = MagicMock(return_value=dict(_DUMMY_ORDER))
        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", pipeline_mock)
        monkeypatch.setattr("src.runtime.mail_ingest.ingest_order", ingest_mock)

        # Tur 1: basarili isle
        r1 = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)
        assert r1 is not None
        assert pipeline_mock.call_count == 1
        assert source.is_processed("103")

        # Tur 2: ayni mail, ayni store — store'da kayitli -> fetch_new bos donmeli
        r2 = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)
        assert r2 is None, "Ikinci turda kayitli uid None (bos) donmeli"
        assert pipeline_mock.call_count == 1, "Ikinci turda pipeline cagrilmamali"

    def test_spam_uid_store_a_yazilir(self, monkeypatch):
        """ingest_order None dondururse (spam) uid store'a yazilmali — tekrar LLM'e gitmesin."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_spam_mail("104")
        source = _TrackingSource([mail])

        monkeypatch.setattr(
            "src.runtime.mail_ingest.ingest_order",
            MagicMock(return_value=None),
        )

        result = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)

        assert result is None
        assert source.is_processed("104"), (
            "Spam mail uid kalici store'a yazilmali — sonraki tur LLM'e gitmemeli"
        )

    def test_needs_review_uid_store_a_yazilir(self, monkeypatch):
        """needs_review siparis -> pending_store'a alindi -> uid kalici store'a yazilmali."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("105")
        source = _TrackingSource([mail])

        monkeypatch.setattr(
            "src.runtime.mail_ingest.ingest_order",
            MagicMock(return_value={
                "needs_review": True,
                "review_reason": "missing_quantity",
                "order_id": "NR-105", "customer": "A",
                "parts": [], "parse_source": "attachment_zip_stl_incomplete",
                "_stl_map": {}, "stl_names": [],
            }),
        )
        pending_mock = MagicMock()

        result = process_inbox_once(
            source, parser_role=None,
            base_scenario=_BASE_SCENARIO,
            pending_store=pending_mock,
        )

        assert result is None
        assert source.is_processed("105"), (
            "needs_review mail uid kalici store'a yazilmali"
        )

    def test_pipeline_exception_ikinci_tur_tekrar_dener(self, monkeypatch):
        """Pipeline exception atinca -> uid store'da yok -> ikinci tur ayni maili tekrar dener."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("106")
        source = _TrackingSource([mail])

        ingest_mock = MagicMock(return_value=dict(_DUMMY_ORDER))
        monkeypatch.setattr("src.runtime.mail_ingest.ingest_order", ingest_mock)

        # Tur 1: pipeline patiyor
        pipeline_mock = MagicMock(side_effect=RuntimeError("patla"))
        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", pipeline_mock)

        r1 = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)
        assert r1 is None
        assert not source.is_processed("106"), "Exception sonrasi uid store'da olmamali"

        # Tur 2: _seen temizle (yeni tur simule — yeni bag gibi), pipeline calisiyor
        source._seen.clear()
        pipeline_mock.side_effect = None
        pipeline_mock.return_value = _FAKE_PIPELINE_RESULT

        r2 = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)
        assert r2 is not None, "Ikinci basarili turda sonuc donmeli"
        assert source.is_processed("106"), (
            "Ikinci basarili turda uid store'a yazilmali"
        )
        assert pipeline_mock.call_count == 2, "Pipeline iki turda da cagrilmali"

    def test_ingest_exception_uid_store_a_yazilmaz(self, monkeypatch):
        """ingest_order exception atarsa uid kalici store'a YAZILMAMALI."""
        from src.runtime.mail_poller import process_inbox_once

        mail = _make_raw_mail("107")
        source = _TrackingSource([mail])

        monkeypatch.setattr(
            "src.runtime.mail_ingest.ingest_order",
            MagicMock(side_effect=ValueError("parse hatasi")),
        )

        result = process_inbox_once(source, parser_role=None, base_scenario=_BASE_SCENARIO)

        assert result is None
        assert not source.is_processed("107"), (
            "ingest_order exception: uid store'a yazilmamali — at-least-once"
        )
