"""tests/test_poller_attachment_priority.py — P2: ek-li mailleri once isle.

Kesin siparis (ZIP/Excel eki -> LLM'siz deterministik yol) serbest-metin
spam-LLM kuyrugunun ARKASINDA beklememeli. process_inbox_once mailleri ingest
etmeden ONCE ek-li olanlari basa alir (stable: goreli sira korunur).
"""
from __future__ import annotations

from src.runtime.mail_ingest import RawMail, Attachment
from src.runtime.mail_poller import _attachment_first


def _mail(mid, ekler=None):
    return RawMail(
        gonderen="x@firma.com", konu="k", govde="g",
        tarih="2026-06-19T10:00:00+03:00", message_id=mid,
        ekler=ekler or [],
    )


def _zip(mid):
    return _mail(mid, [Attachment(dosya_adi="Plan1.zip", icerik=b"PK\x03\x04",
                                  mime="application/zip")])


def _xlsx(mid):
    return _mail(mid, [Attachment(dosya_adi="liste.xlsx", icerik=b"PK",
                                  mime="application/vnd.openxmlformats")])


def test_ekli_mail_basa_alinir():
    text = _mail("<txt@x>")
    zipm = _zip("<zip@x>")
    out = _attachment_first([text, zipm])
    assert out[0] is zipm  # ek-li ONCE
    assert out[1] is text


def test_excel_eki_de_oncelikli():
    text = _mail("<txt@x>")
    xls = _xlsx("<xls@x>")
    out = _attachment_first([text, xls])
    assert out[0] is xls


def test_stable_goreli_sira_korunur():
    # Iki ek-li + iki metin: ek-liler basta, her grup icinde GIRIS sirasi korunur
    z1, z2 = _zip("<z1@x>"), _zip("<z2@x>")
    t1, t2 = _mail("<t1@x>"), _mail("<t2@x>")
    out = _attachment_first([t1, z1, t2, z2])
    assert out == [z1, z2, t1, t2]


def test_bos_liste_ve_hepsi_ekli():
    assert _attachment_first([]) == []
    z1, z2 = _zip("<z1@x>"), _zip("<z2@x>")
    assert _attachment_first([z1, z2]) == [z1, z2]
