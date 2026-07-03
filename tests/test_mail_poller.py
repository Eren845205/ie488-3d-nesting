"""tests/test_mail_poller.py — Arka plan poll modu testleri."""

import io
import threading
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


# ---------------------------------------------------------------------------
# Kesin-sonuc tanimi (P0, 2026-07-03 canli dersi): nesting gecerli yukseklik
# uretmediyse mail "islendi" SAYILMAZ -> sonraki tur otomatik yeniden dener.
# ---------------------------------------------------------------------------


class _MarkSpySource(_OnceSource):
    def __init__(self, mails):
        super().__init__(mails)
        self.marked = []

    def mark_processed(self, mail):
        self.marked.append(mail.message_id)


def test_nesting_produced_output_tanimi():
    from src.runtime.mail_poller import nesting_produced_output
    assert nesting_produced_output(None) is False
    assert nesting_produced_output({}) is False
    assert nesting_produced_output({"nesting_results": {}}) is False
    assert nesting_produced_output(
        {"nesting_results": {"B001": {"height_mm": 0.0, "note": "Tuner hatasi"}}}
    ) is False
    assert nesting_produced_output(
        {"nesting_results": {"B001": {"height_mm": 0.0}, "B002": {"height_mm": 12.5}}}
    ) is True


def test_sifir_sonuclu_kosu_mark_edilmez(tmp_path, monkeypatch):
    """Nesting hatasi yutulup height=0 dondugunde mail KALICI kaydedilmez —
    motor duzeltmesi sonrasi sonraki tarama kendiliginden telafi eder.
    (Deneme4 canli olayi: idempotency'yi elle silmek zorunda kalmistik.)"""
    import scripts.demo_pipeline as dp

    def _fake_run_pipeline(scenario):
        return {"nesting_results": {"B001": {"height_mm": 0.0,
                                             "note": "Tuner hatasi: voxel bos"}},
                "ranked_orders": [], "batches": [1], "pricing_results": {}}

    monkeypatch.setattr(dp, "run_pipeline", _fake_run_pipeline)
    src = _MarkSpySource([_zip_mail(mid="<P0-FAIL@x>")])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    assert res is not None          # sonuc doner (gecmis "hata" kaydi icin)
    assert src.marked == []          # ama mail ISLENDI SAYILMADI


def test_gecerli_sonuclu_kosu_mark_edilir(tmp_path, monkeypatch):
    import scripts.demo_pipeline as dp

    def _fake_run_pipeline(scenario):
        return {"nesting_results": {"B001": {"height_mm": 42.0}},
                "ranked_orders": [], "batches": [1], "pricing_results": {}}

    monkeypatch.setattr(dp, "run_pipeline", _fake_run_pipeline)
    src = _MarkSpySource([_zip_mail(mid="<P0-OK@x>")])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    assert res is not None
    assert src.marked == ["<P0-OK@x>"]


def test_kismi_basari_mark_edilmez(tmp_path, monkeypatch):
    """R1 #3: 2 partiden 1'i basarili = KISMI — mail islendi sayilmaz
    (basarisiz partinin siparisleri sessizce kaybolmasin)."""
    import scripts.demo_pipeline as dp

    def _fake_run_pipeline(scenario):
        return {"nesting_results": {
                    "B001": {"height_mm": 42.0},
                    "B002": {"height_mm": 0.0, "note": "Tuner hatasi: X"}},
                "ranked_orders": [], "batches": [1, 2], "pricing_results": {}}

    monkeypatch.setattr(dp, "run_pipeline", _fake_run_pipeline)
    src = _MarkSpySource([_zip_mail(mid="<P0-KISMI@x>")])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path),
    )
    assert res is not None
    assert src.marked == []


def test_on_result_mark_oncesi_ve_hatasi_marki_engeller(tmp_path, monkeypatch):
    """R1 #4: on_result (gecmis kaydi) mark'tan ONCE kosar; istisna atarsa
    mail islendi SAYILMAZ ('gorunmez is' olusamaz)."""
    import scripts.demo_pipeline as dp

    def _fake_run_pipeline(scenario):
        return {"nesting_results": {"B001": {"height_mm": 42.0}},
                "ranked_orders": [], "batches": [1], "pricing_results": {}}

    monkeypatch.setattr(dp, "run_pipeline", _fake_run_pipeline)

    # (a) siralama: on_result cagrildiginda mark HENUZ yapilmamis olmali
    src = _MarkSpySource([_zip_mail(mid="<P0-SIRA@x>")])
    marked_at_callback = []

    def _peek(result):
        marked_at_callback.append(list(src.marked))

    process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), on_result=_peek,
    )
    assert marked_at_callback == [[]]        # callback aninda mark yoktu
    assert src.marked == ["<P0-SIRA@x>"]     # sonrasinda mark yapildi

    # (b) on_result patlarsa mark ATLANIR
    src2 = _MarkSpySource([_zip_mail(mid="<P0-GKAYIT@x>")])

    def _boom(result):
        raise IOError("disk dolu — gecmis yazilamadi")

    res2 = process_inbox_once(
        src2, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), on_result=_boom,
    )
    assert res2 is not None
    assert src2.marked == []


def test_process_inbox_once_on_stage_pipeline_oncesi(tmp_path):
    """on_stage callback'i pipeline BASLARKEN insan-okur metinle cagrilir
    (kullanici istegi: 'islenmeye alindi' gorunurlugu — is bitmeden sinyal)."""
    stages = []
    src = _OnceSource([_zip_mail()])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), on_stage=stages.append,
    )
    assert res is not None
    assert len(stages) == 1
    assert "işlenmeye alındı" in stages[0]
    assert "5 parça" in stages[0]  # braket 3 + kapak 2


def test_process_inbox_once_on_stage_hatasi_yutulur(tmp_path):
    """on_stage patlasa bile akis KIRILMAZ (gorunurluk yan-kanal)."""
    def _bad_stage(_msg):
        raise RuntimeError("UI koptu")
    src = _OnceSource([_zip_mail()])
    res = process_inbox_once(
        src, parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), on_stage=_bad_stage,
    )
    assert res is not None  # pipeline yine kostu


def test_poller_inflight_gorunurlugu(tmp_path):
    """poll_once SIRASINDA inflight=True + detay dolu; bitince temiz."""
    seen = {}

    def _probe(_result):
        # on_result pipeline bitiminde ama poll_once icinde kosar ->
        # inflight hala True olmali (finally'de temizlenir)
        seen["inflight"] = poller.state.inflight
        seen["detail_was_set"] = bool(seen.get("detail_was_set"))

    stages = []
    poller = MailPoller(
        make_source=lambda: _OnceSource([_zip_mail()]),
        parser_role=None, base_scenario=RICH_SCENARIO,
        persist_root=str(tmp_path), interval_s=1,
        on_result=_probe,
    )
    res = poller.poll_once()
    assert res is not None
    assert seen["inflight"] is True             # kosarken gorunur
    assert poller.state.inflight is False       # bitince temiz
    assert poller.state.inflight_detail == ""
    snap = poller.state.snapshot()
    assert "inflight" in snap and "inflight_detail" in snap


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


def test_poller_ilk_tarama_hemen_yapilir(tmp_path):
    """start() -> ilk tarama interval BEKLEMEDEN hemen yapilir.

    Onceki bug: _loop once wait(interval) yapip sonra tariyordu; 5 dk
    interval'de kullanici 'actim ama 0 tarama' goruyordu. interval cok
    buyuk (1 saat) verilir; ilk tarama yine de saniyeler icinde olmali.
    """
    tarandi = threading.Event()

    def _kaynak():
        tarandi.set()
        return _EmptySource()

    poller = MailPoller(
        make_source=_kaynak, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        interval_s=3600,  # 1 saat; eski davranista ilk tarama 1 saat sonra olurdu
    )
    poller.start()
    try:
        assert tarandi.wait(timeout=5.0), "ilk tarama interval beklemeden yapilmali"
        assert poller.state.runs >= 1
    finally:
        poller.stop()


def test_poller_restart_yeni_interval_yeni_thread(tmp_path):
    """restart(): calisan poller'i durdurup yeni interval ile yeniden baslatir.

    Onceki bug: interval degisince state.interval_s guncellenir ama start()
    'zaten calisiyor' deyip no-op olur; thread'in mevcut wait'i eski
    interval'i kullanmaya devam ederdi. restart() yeni thread baslatmali.
    """
    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        interval_s=3600,
    )
    poller.start()
    eski_thread = poller._thread
    poller.state.interval_s = 1
    poller.restart()
    try:
        assert poller._thread is not eski_thread, "restart yeni thread baslatmali"
        assert poller.state.enabled is True
        # Eski thread JOIN edilmez (uzun pipeline UI'i kilitlemesin) -> kendi
        # eski event'iyle asenkron olur; kisa sure icinde olmeli.
        assert eski_thread is not None
        eski_thread.join(timeout=5.0)
        assert not eski_thread.is_alive(), "eski thread stop sinyaliyle olmeli"
    finally:
        poller.stop()


def test_poller_tekrarli_restart_ghost_thread_birakmaz(tmp_path):
    """Reviewer H1/M1: tekrarli restart geride 'ghost' poller thread birakmamali.

    Eski mimari (tek paylasimli _stop + join+clear) uzun pipeline'da olumsuz
    thread biraktirabiliyordu. Per-thread event mimarisinde her eski thread
    KENDI event'iyle oldugu icin stop() sonrasi hic aktif mail-poller kalmamali.
    """
    import time

    poller = MailPoller(
        make_source=_EmptySource, parser_role=None,
        base_scenario=RICH_SCENARIO, persist_root=str(tmp_path),
        interval_s=3600,
    )
    poller.start()
    for _ in range(5):
        poller.restart()
    poller.stop()

    # Tum mail-poller thread'leri kisa sure icinde olmeli (ghost yok).
    for _ in range(50):
        alive = [t for t in threading.enumerate()
                 if t.name == "mail-poller" and t.is_alive()]
        if not alive:
            break
        time.sleep(0.1)
    alive = [t for t in threading.enumerate()
             if t.name == "mail-poller" and t.is_alive()]
    assert not alive, f"ghost thread kaldi: {len(alive)} aktif"
