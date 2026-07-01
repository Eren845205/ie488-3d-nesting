"""tests/test_broken_attachment_no_loop.py -- FIX 1 (HIGH) TDD.

Kok sorun: Excel/CSV eki taninmayan baslik / bilinmeyen icerik / bos dosya
oldugunda parse_order_attachment [] doner. ingest_order bunu parts=[] order
olarak dondururdu; needs_review DEGILDI. Poller bu order'i pipeline'a sokar,
run_pipeline "Gecerli siparis yok" ile patlar, poller bunu GECICI hata sanip
mark_processed cagirmaz -> ayni mail her turda sonsuza yeniden islenir.

Hedef davranis (ZIP-STL skipped_no_qty deseniyle SIMETRIK): parse [] donerse
ingest_order order'i needs_review=True isaretler -> poller/manuel akis maili
pending_store'a alir + mark_processed ile KAPATIR -> sonsuz dongu YOK.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.mail_ingest import RawMail, Attachment, ingest_order


def _mail_with_csv(icerik: bytes, mid: str = "<brokencsv@x>") -> RawMail:
    return RawMail(
        gonderen="uretim@firma.com.tr",
        konu="Siparis",
        govde="CSV eki var",
        tarih="2026-06-20T09:00:00+03:00",
        message_id=mid,
        ekler=[Attachment("siparis.csv", icerik, "text/csv")],
        uid="900",
    )


class TestIngestExcelCsvNeedsReview:
    """Bos-parca (kalici-yapisal hata) -> needs_review=True (simetri)."""

    def test_taninmayan_baslik_csv_needs_review(self):
        """Taninmayan basliklar -> parse [] -> ingest_order needs_review dondurur."""
        mail = _mail_with_csv(b"foo,bar,baz\n1,2,3\n")
        order = ingest_order(mail, parser_role=None)
        assert order is not None, "bos-parca order sessizce dusurulmemeli (needs_review)"
        assert order.get("needs_review") is True, (
            "taninmayan baslik/bos parca KALICI hata -> needs_review olmali"
        )
        assert order.get("parts") == []
        assert order.get("review_reason")

    def test_bos_csv_needs_review(self):
        """Bos govdeli CSV (yalniz baslik, veri yok) -> parts [] -> needs_review."""
        mail = _mail_with_csv(b"foo,bar\n", mid="<emptycsv@x>")
        order = ingest_order(mail, parser_role=None)
        assert order is not None
        assert order.get("needs_review") is True

    def test_gecerli_csv_hala_normal_order(self):
        """Regresyon: gecerli basliklar -> normal order (needs_review YOK)."""
        mail = _mail_with_csv(
            b"name,width_mm,depth_mm,height_mm,qty\nparca_a,50,40,30,2\n",
            mid="<goodcsv@x>",
        )
        order = ingest_order(mail, parser_role=None)
        assert order is not None
        assert not order.get("needs_review")
        assert len(order.get("parts", [])) == 1


class _ReservingSource:
    """mark_processed cagrilana kadar ayni maili tekrar tekrar dondurur.

    Gercek IMAP + kalici store davranisini taklit eder: islenmemis (mark
    edilmemis) mail her fetch'te yeniden gorunur. Boylece 'sonsuz retry'
    kok sorunu dogrudan gozlemlenebilir.
    """

    def __init__(self, mails):
        self._mails = list(mails)
        self.marked = set()

    def fetch_new(self):
        return [m for m in self._mails if m.uid not in self.marked]

    def mark_processed(self, mail):
        if mail.uid:
            self.marked.add(mail.uid)


class TestPollerBrokenAttachmentNoInfiniteLoop:
    """process_inbox_once bozuk-ek maili KAPATIR (mark) -> ikinci tur bos."""

    def test_bozuk_csv_ikinci_tur_yeniden_islenmez(self):
        from scripts.demo_pipeline import RICH_SCENARIO
        from src.runtime.mail_poller import process_inbox_once

        mail = _mail_with_csv(b"foo,bar\n1,2\n", mid="<loopcsv@x>")
        source = _ReservingSource([mail])

        class _PendingSpy:
            def __init__(self):
                self.added = []

            def add(self, **kw):
                self.added.append(kw)
                return kw.get("order_id", "")

        pending = _PendingSpy()

        # Tur 1: bozuk ek -> needs_review -> pending'e alinir + mark_processed
        r1 = process_inbox_once(
            source, parser_role=None, base_scenario=RICH_SCENARIO,
            pending_store=pending,
        )
        assert r1 is None, "bozuk ek pipeline'a sokulmamali (None)"
        assert "900" in source.marked, (
            "bozuk-ek maili mark_processed ile KAPATILMALI -> sonsuz dongu yok"
        )
        assert len(pending.added) == 1, "operator gorunurlugu icin pending'e alinmali"

        # Tur 2: mail artik mark'li -> fetch bos -> yeniden islenmez
        r2 = process_inbox_once(
            source, parser_role=None, base_scenario=RICH_SCENARIO,
            pending_store=pending,
        )
        assert r2 is None
        assert len(pending.added) == 1, "ikinci turda tekrar pending'e eklenmemeli"
