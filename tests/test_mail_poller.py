"""tests/test_mail_poller.py — Arka plan poll modu testleri."""

import io
import zipfile

import pytest

trimesh = pytest.importorskip("trimesh")

from scripts.demo_pipeline import RICH_SCENARIO
from src.runtime.mail_ingest import Attachment, RawMail
from src.runtime.mail_poller import MailPoller, process_inbox_once


def _zip_mail(mid="<POLL-1@x>"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("braket.stl", trimesh.creation.box(extents=(40, 30, 15)).export(file_type="stl"))
        z.writestr("kapak.stl", trimesh.creation.box(extents=(60, 40, 10)).export(file_type="stl"))
    return RawMail(
        gonderen="uretim@firma.com.tr", konu="Plan1",
        govde="braket 3 adet\nkapak 2 adet",
        tarih="2026-06-14T09:00:00+03:00", message_id=mid,
        ekler=[Attachment("parcalar.zip", buf.getvalue(), "application/zip")],
    )


class _OnceSource:
    """Ilk fetch'te mailleri, sonraki fetch'lerde bos liste (idempotency)."""
    def __init__(self, mails):
        self._mails = mails
        self._served = False

    def fetch_new(self):
        if self._served:
            return []
        self._served = True
        return self._mails


class _EmptySource:
    def fetch_new(self):
        return []


# ---------------------------------------------------------------------------
# process_inbox_once
# ---------------------------------------------------------------------------

def test_process_inbox_once_zip_stl(tmp_path):
    src = _OnceSource([_zip_mail()])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    assert res is not None
    assert res.get("nesting_results")  # gercek nesting kostu


def test_process_inbox_once_yeni_mail_yok(tmp_path):
    res = process_inbox_once(
        _EmptySource(), parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    assert res is None


def test_process_inbox_once_ikinci_tur_bos(tmp_path):
    src = _OnceSource([_zip_mail()])
    r1 = process_inbox_once(src, parser_role=None, base_scenario=RICH_SCENARIO, persist_root=str(tmp_path))
    r2 = process_inbox_once(src, parser_role=None, base_scenario=RICH_SCENARIO, persist_root=str(tmp_path))
    assert r1 is not None and r2 is None  # idempotency: ayni mail tekrar islenmez


# ---------------------------------------------------------------------------
# MailPoller.poll_once
# ---------------------------------------------------------------------------

def test_poller_poll_once_callback_ve_durum(tmp_path):
    sink = []
    poller = MailPoller(
        make_source=lambda: _OnceSource([_zip_mail()]),
        parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), interval_s=1,
        on_result=lambda r: sink.append(r),
        now=lambda: 123.0,
    )
    res = poller.poll_once()
    assert res is not None
    assert len(sink) == 1                       # callback cagrildi
    assert poller.state.runs == 1
    assert poller.state.last_processed >= 1
    assert poller.state.total_processed >= 1
    assert poller.state.last_poll_ts == 123.0
    assert poller.state.last_error is None


def test_poller_hata_yutulur_durum_yazilir(tmp_path):
    def _boom():
        raise RuntimeError("kaynak patladi")
    poller = MailPoller(
        make_source=_boom, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    res = poller.poll_once()  # ATMAMALI
    assert res is None
    assert "kaynak patladi" in (poller.state.last_error or "")


def test_poller_snapshot_serilestirilebilir(tmp_path):
    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
    )
    poller.poll_once()
    snap = poller.state.snapshot()
    assert set(snap) >= {"enabled", "interval_s", "runs", "last_processed"}


def test_poller_start_stop(tmp_path):
    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        interval_s=60,
    )
    poller.start()
    assert poller.state.enabled is True
    poller.stop()
    assert poller.state.enabled is False
