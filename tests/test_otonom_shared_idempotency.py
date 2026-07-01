"""tests/test_otonom_shared_idempotency.py -- FIX 2 (HIGH) TDD.

Kok sorun: Manuel /otonom + /otonom/baslat, poller'in kalici _shared_idem_store'unu
ENJEKTE ETMIYORDU -> ImapMailbox her istekte :memory: store yaratip cope atiyor,
mark_processed hic cagrilmiyor, ayni son mailler tekrar tekrar isleniyordu.

Hedef:
  (a) Manuel akis make_mail_source'a paylasilmis idem_store'u enjekte etsin;
      pipeline basarili olan order-ureten mailler mark_processed ile kapatilsin
      (poller ile ORTAK -> ayni mail iki yoldan da BIR kez islenir).
  (b) sync /otonom + async job + poller AYNI tekil-tarama kilidinden gecsin
      (paralel mailbox taramasi yok). Kilit poller inflight-lock ile ORTAK.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.runtime.mail_ingest import RawMail


# ---------------------------------------------------------------------------
# FakeProvider -- parser rolu (test_webapp_otonom deseni)
# ---------------------------------------------------------------------------

def _parser_response() -> str:
    return json.dumps({
        "musteri": {"ad": "Ford Turkiye", "iletisim": "tedarik@ford.com.tr"},
        "termin": {"tarih": "2026-06-19", "ham_ifade": "5 is gunu"},
        "parcalar": [{
            "ad": "Braket", "adet": 4, "boyut_mm": [80.0, 60.0, 30.0],
            "agirlik_kg": None, "kaynak": "box", "guven": "yuksek",
        }],
        "eksik_alanlar": [], "notlar": None, "injection_suphesi": False,
    }, ensure_ascii=False)


def _make_provider() -> Any:
    from src.llm.provider import FakeProvider
    return FakeProvider(fixture_map={
        ("parser-v1", "_any_"): [_parser_response()] * 6,
        ("explainer-v1", "_any_"): [json.dumps({
            "aciklama_md": "x", "karar_tipi": "algoritma",
            "kullanilan_girdiler": [], "topraklama_uyarisi": False,
        }, ensure_ascii=False)] * 6,
        ("report-v1", "_any_"): [json.dumps({
            "baslik": "T", "govde_md": "g", "kullanilan_kaynaklar": [],
            "eksik_bilgi": [],
        }, ensure_ascii=False)] * 6,
    })


@pytest.fixture
def app_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=_make_provider())


class _TrackSource:
    """fetch_new order-sinyalli tek mail dondurur; mark_processed'i izler."""

    def __init__(self, mail: RawMail):
        self._mail = mail
        self.marked = []

    def fetch_new(self):
        if self._mail.uid in self.marked:
            return []
        return [self._mail]

    def mark_processed(self, mail):
        self.marked.append(mail.uid)


# ---------------------------------------------------------------------------
# (a) Paylasilmis idem_store enjeksiyonu + mark_processed
# ---------------------------------------------------------------------------

def test_manuel_otonom_shared_store_enjekte_eder_ve_mark_eder(app_llm, monkeypatch):
    """Manuel /otonom make_mail_source'a SHARED_IDEM_STORE'u iletmeli ve
    pipeline basarisi sonrasi order-ureten maili mark_processed etmeli."""
    captured = {}
    mail = RawMail(
        gonderen="ford@ornek.com", konu="Siparis",
        govde="4 adet braket 80x60x30 mm lazim",
        tarih="2026-06-20T10:00:00+03:00", message_id="<otm-1@x>", uid="500",
    )
    track = _TrackSource(mail)

    def _fake_make(cfg, idem_store=None):
        captured["idem_store"] = idem_store
        return track

    monkeypatch.setattr("src.runtime.mail_ingest.make_mail_source", _fake_make)

    client = app_llm.test_client()
    resp = client.post("/otonom", json={"nesting_mode": "heightmap"})
    assert resp.status_code == 200, f"beklenen 200, gelen {resp.status_code}: {resp.data[:300]}"

    assert captured.get("idem_store") is app_llm.config["SHARED_IDEM_STORE"], (
        "manuel akis paylasilmis idem_store'u make_mail_source'a iletmeli"
    )
    assert "500" in track.marked, (
        "pipeline basarisi sonrasi order-ureten mail mark_processed edilmeli"
    )


# ---------------------------------------------------------------------------
# (b) Tekil-tarama kilidi (sync + async + poller ORTAK)
# ---------------------------------------------------------------------------

def test_scan_lock_config_de_bulunur(app_llm):
    """Ortak tekil-tarama kilidi app.config'de bulunmali."""
    assert "OTONOM_SCAN_LOCK" in app_llm.config


def test_poller_inflight_lock_scan_lock_ile_ortak(app_llm):
    """Poller inflight-lock'u manuel akisin scan-lock'u ile AYNI obje olmali."""
    poller = app_llm.config["MAIL_POLLER"]
    assert poller._inflight_lock is app_llm.config["OTONOM_SCAN_LOCK"], (
        "poller ve manuel akis ayni tekil-tarama kilidini paylasmali"
    )


def test_sync_otonom_kilit_tutuluysa_mesgul_doner(app_llm):
    """Scan-lock (poller taramasi gibi) tutuluyken sync /otonom bloklamadan
    'mesgul' donmeli (409) -- paralel mailbox taramasi engellenir, deadlock yok."""
    lock = app_llm.config["OTONOM_SCAN_LOCK"]
    client = app_llm.test_client()
    assert lock.acquire(blocking=False)
    try:
        resp = client.post("/otonom", json={})
        assert resp.status_code == 409, (
            f"kilit tutuluyken /otonom 409 (mesgul) donmeli, gelen {resp.status_code}"
        )
    finally:
        lock.release()

    # Kilit birakilinca tekrar calismali (deadlock/kilit sizintisi yok)
    resp2 = client.post("/otonom", json={"nesting_mode": "heightmap"})
    assert resp2.status_code == 200
