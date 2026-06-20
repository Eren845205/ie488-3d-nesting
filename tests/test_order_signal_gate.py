"""tests/test_order_signal_gate.py — LLM siparis-sinyali kapisi.

ingest_order, EK YOK + govdede siparis sinyali (adet/boyut deseni) yoksa maili
LLM'e SOKMAZ (sahte siparis hallucination engeli). Gercek siparis ya ek ya bu
desenlerden birini tasidigi icin kacmaz.
"""
from __future__ import annotations

from src.runtime.mail_ingest import RawMail, ingest_order, _has_order_signal


# ---------------------------------------------------------------------------
# Birim: _has_order_signal
# ---------------------------------------------------------------------------

def test_sinyal_adet_deseni():
    assert _has_order_signal("ENG-500053_L-Bracket 22 adet\nbaseplate_v2 1 adet")


def test_sinyal_boyut_deseni():
    assert _has_order_signal("Braket gonderin lutfen, olcu 80x60x30 mm")


def test_sinyal_yok_reklam():
    assert not _has_order_signal(
        "Merhaba, kampanyamizdan haberdar olmak ister misiniz? "
        "Bu hafta tum urunlerde %20 indirim!"
    )


def test_sinyal_yok_kisisel():
    assert not _has_order_signal("Selam, yarinki toplanti saat kacta? Tesekkurler.")


# ---------------------------------------------------------------------------
# Entegrasyon: ingest_order LLM kapisi
# ---------------------------------------------------------------------------

class _SpyParser:
    """parse cagrildi mi izleyen sahte LLM parser."""
    def __init__(self):
        self.called = False

    def parse(self, govde):
        self.called = True
        # gercek bir siparis dict dondur (kapi gectiginde islensin)
        return {
            "order_id": "LLM-1", "customer": "X", "deadline": "",
            "priority_class": 2,
            "parts": [{"id": "p", "name": "p", "qty": 1,
                       "width_mm": 80, "depth_mm": 60, "height_mm": 30}],
        }


def _text_mail(govde):
    return RawMail(
        gonderen="biri@firma.com",
        konu="konu",
        govde=govde,
        tarih="2026-06-19T10:00:00+03:00",
        message_id="<TXT-1@x>",
        ekler=[],  # EK YOK -> LLM yolu
    )


def test_sinyalsiz_mail_llm_cagrilmaz():
    parser = _SpyParser()
    order = ingest_order(_text_mail("Bu hafta kampanya! Hemen tikla."), parser)
    assert order is None
    assert parser.called is False  # LLM'e HIC gitmedi -> sahte siparis yok


def test_adet_desenli_mail_llm_cagrilir():
    parser = _SpyParser()
    order = ingest_order(_text_mail("braket 5 adet\nkapak 2 adet"), parser)
    assert parser.called is True
    assert order is not None
    assert order["parse_source"] == "llm_text"


def test_boyut_desenli_mail_llm_cagrilir():
    parser = _SpyParser()
    order = ingest_order(_text_mail("Parca olcusu 80x60x30 mm, acil."), parser)
    assert parser.called is True
    assert order is not None


def test_parser_none_ise_none_doner():
    # parser_role None + sinyal olsa bile LLM yok -> None (patlamamali)
    order = ingest_order(_text_mail("braket 5 adet"), parser_role=None)
    assert order is None
