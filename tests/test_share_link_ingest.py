"""tests/test_share_link_ingest.py — dosya-paylasim linki yolu + LLM bos-siparis kalkani.

2026-07-20 canli dersi (Plan7 maili): buyuk STL ZIP'i mail ekine sigmaz,
gonderen Drive/WeTransfer linki paylasir; adet listesi .txt ekinde gelir.
Ayrica LLM, sinyalli-ama-parcasiz mailden bos siparis uretip run_pipeline'i
dusurebilir ("Gecerli siparis yok" -> otonom is 500). Iki mekanizma da
uretim kodunda (mail_ingest.ingest_order); bu dosya sozlesmelerini kilitler.
"""
from __future__ import annotations

import json

from src.runtime.mail_ingest import (
    Attachment,
    RawMail,
    _adet_listesi_from_text_attachments,
    _find_share_links,
    ingest_order,
)
from src.runtime.pending_orders import PendingOrderStore


# ---------------------------------------------------------------------------
# Birim: _find_share_links
# ---------------------------------------------------------------------------

def test_drive_linki_bulunur():
    text = "Plan7'yi ekte paylasiyorum https://drive.google.com/file/d/1AbC_x-9/view?usp=sharing tesekkurler"
    assert _find_share_links(text) == [
        "https://drive.google.com/file/d/1AbC_x-9/view?usp=sharing"]


def test_wetransfer_kisa_linki_bulunur():
    assert _find_share_links("dosya: https://we.tl/t-AbCdEf") == [
        "https://we.tl/t-AbCdEf"]


def test_allowlist_disi_host_yok_sayilir():
    assert _find_share_links("bkz https://evil.example.com/dosya.zip") == []


def test_host_taklidi_eslesmez():
    # "drive.google.com.evil.com" allowlist SONEKI degil — suffix kontrolu
    # host SONU ile yapilir, icinde-gecen ile degil.
    assert _find_share_links(
        "https://drive.google.com.evil.com/file/d/x/view") == []


def test_ayni_link_tekillenir_ve_sirali():
    text = ("once https://we.tl/t-AAA sonra https://drive.google.com/file/d/B/view "
            "ve tekrar https://we.tl/t-AAA")
    assert _find_share_links(text) == [
        "https://we.tl/t-AAA", "https://drive.google.com/file/d/B/view"]


def test_bos_metin_bos_liste():
    assert _find_share_links("") == []
    assert _find_share_links(None) == []


# ---------------------------------------------------------------------------
# Birim: _adet_listesi_from_text_attachments
# ---------------------------------------------------------------------------

def _mail(govde, ekler=None, msg_id="<SL-1@x>"):
    return RawMail(
        gonderen="mcoskun@fsm.edu.tr",
        konu="RE: Plan1 ve Plan 3 Nesting",
        govde=govde,
        tarih="2026-07-20T16:18:14+03:00",
        message_id=msg_id,
        ekler=ekler or [],
    )


def _txt_ek(icerik, ad="Plan7- Adet Listesi.txt"):
    return Attachment(dosya_adi=ad, icerik=icerik, mime="text/plain")


def test_txt_ekinden_adet_cikar():
    mail = _mail("govde", ekler=[
        _txt_ek(b"174100684-a 22 adet\n174100700-a 96 adet\n")])
    assert _adet_listesi_from_text_attachments(mail) == {
        "174100684-a": 22, "174100700-a": 96}


def test_txt_olmayan_ek_atlanir():
    jpg = Attachment(dosya_adi="image001.jpg", icerik=b"\xff\xd8", mime="image/jpeg")
    mail = _mail("govde", ekler=[jpg])
    assert _adet_listesi_from_text_attachments(mail) == {}


def test_adetsiz_txt_bos_dict():
    mail = _mail("govde", ekler=[_txt_ek(b"Merhaba, iyi calismalar.")])
    assert _adet_listesi_from_text_attachments(mail) == {}


# ---------------------------------------------------------------------------
# Entegrasyon: ingest_order dosya-paylasim yolu
# ---------------------------------------------------------------------------

class _SpyParser:
    def __init__(self):
        self.called = False

    def parse(self, govde):
        self.called = True
        return {"order_id": "LLM-1", "customer": "X", "deadline": "",
                "priority_class": 2,
                "parts": [{"id": "p", "name": "p", "qty": 1,
                           "width_mm": 80, "depth_mm": 60, "height_mm": 30}]}


_DRIVE_GOVDE = ("Merhaba Eren, Plan7'yi ekte paylasiyorum. "
                "https://drive.google.com/file/d/1OzX/view Uretim yuksekligi 595 mm'dir.")


def test_linkli_mail_beklemeye_alinir_llm_cagrilmaz():
    parser = _SpyParser()
    mail = _mail(_DRIVE_GOVDE, ekler=[_txt_ek(b"174100684-a 22 adet\n")])
    order = ingest_order(mail, parser)
    assert parser.called is False  # veri elde yok -> LLM'e SOKULMAZ
    assert order["needs_review"] is True
    assert order["review_reason"] == "share_link_dosya_bekleniyor"
    assert order["parse_source"] == "share_link"
    assert order["share_links"] == ["https://drive.google.com/file/d/1OzX/view"]
    assert order["adet_listesi"] == {"174100684-a": 22}
    assert order["parts"] == []  # pipeline'a girecek parca YOK
    assert order["order_id"].startswith("LINK-")


def test_linkli_mail_order_id_deterministik():
    # kanit: govdede .zip imasi (adet listesi yok — dal yine tetiklenir)
    govde = _DRIVE_GOVDE + " Dosya: Plan7.zip"
    m1 = _mail(govde, msg_id="<AYNI@x>")
    m2 = _mail(govde, msg_id="<AYNI@x>")
    o1 = ingest_order(m1, _SpyParser())
    o2 = ingest_order(m2, _SpyParser())
    assert o1["order_id"] == o2["order_id"]  # ayni mail 2x islenirse COGALMAZ


def test_linkli_mail_adet_govdeden_de_okunur():
    mail = _mail(_DRIVE_GOVDE + "\n174100684-a 22 adet\n174100686-a 10 adet")
    order = ingest_order(mail, _SpyParser())
    assert order["review_reason"] == "share_link_dosya_bekleniyor"
    assert order["adet_listesi"] == {"174100684-a": 22, "174100686-a": 10}


def test_linkli_ama_siparis_kaniti_yoksa_beklemeye_alinmaz():
    # Alakasiz paylasim bildirimi: adet yok, .zip/.stl imasi yok, sinyal yok
    # -> LLM kapisina duser; sinyalsiz oldugundan LLM de cagrilmaz -> None.
    parser = _SpyParser()
    order = ingest_order(_mail(
        "Size bir klasor paylasildi: https://drive.google.com/drive/folders/xyz "
        "Goruntulemek icin tiklayin."), parser)
    assert order is None
    assert parser.called is False


def test_linkli_zip_imasi_yeterli_kanit():
    # Adet listesi yok ama govde .zip'ten bahsediyor -> dosya bekleniyor.
    order = ingest_order(_mail(
        "Parcalar Plan7.zip icinde: https://we.tl/t-AbC"), _SpyParser())
    assert order is not None
    assert order["review_reason"] == "share_link_dosya_bekleniyor"
    assert order["adet_listesi"] == {}


# ---------------------------------------------------------------------------
# Entegrasyon: LLM bos-siparis kalkani
# ---------------------------------------------------------------------------

class _BosParser:
    """Sinyalli mailden PARCASIZ siparis ureten LLM (2026-07-20 canli vakasi)."""
    def __init__(self, parts):
        self._parts = parts

    def parse(self, govde):
        return {"order_id": "LLM-B1", "customer": "FSM", "deadline": "",
                "priority_class": 2, "parts": self._parts}


def _sinyalli_mail():
    # "5 adet" -> siparis sinyali VAR -> LLM kapisi acilir
    return _mail("kapak 5 adet gonderir misiniz", msg_id="<BOS-1@x>")


def test_llm_bos_parca_listesi_pipeline_yerine_incelemeye():
    order = ingest_order(_sinyalli_mail(), _BosParser([]))
    assert order["needs_review"] is True
    assert order["review_reason"] == "llm_bos_siparis"
    assert order["parse_source"] == "llm_text_incomplete"
    assert order["parts"] == []


def test_llm_sifir_adetli_parcalar_da_bos_sayilir():
    order = ingest_order(_sinyalli_mail(), _BosParser(
        [{"id": "p", "name": "p", "qty": 0,
          "width_mm": 10, "depth_mm": 10, "height_mm": 10}]))
    assert order["review_reason"] == "llm_bos_siparis"


def test_llm_qty_eksikse_1_sayilir_kalkan_tetiklenmez():
    # run_pipeline semantigi: qty eksik -> 1. Kalkan bunu bos SAYMAZ.
    order = ingest_order(_sinyalli_mail(), _BosParser(
        [{"id": "p", "name": "p",
          "width_mm": 10, "depth_mm": 10, "height_mm": 10}]))
    assert order.get("review_reason") != "llm_bos_siparis"
    assert order["parse_source"] == "llm_text"


def test_llm_normal_siparis_kalkandan_etkilenmez():
    order = ingest_order(_sinyalli_mail(), _SpyParser())
    assert order["parse_source"] == "llm_text"
    assert order["parts"]


# ---------------------------------------------------------------------------
# PendingOrderStore: link-siparis meta alanlari (additive, geriye uyumlu)
# ---------------------------------------------------------------------------

def test_store_link_alanlari_meta_json_da(tmp_path):
    s = PendingOrderStore(tmp_path / "pending")
    s.add(order_id="LINK-AB12CD34", customer="FSM", sender="mcoskun@fsm.edu.tr",
          deadline="", priority_class=2, konu="RE: Plan1 ve Plan 3 Nesting",
          stl_map={},  # STL'ler linkte — depoda dosya yok
          review_reason="share_link_dosya_bekleniyor",
          share_links=["https://drive.google.com/file/d/1OzX/view"],
          adet_listesi={"174100684-a": 22})
    meta = s.get("LINK-AB12CD34")
    assert meta["review_reason"] == "share_link_dosya_bekleniyor"
    assert meta["share_links"] == ["https://drive.google.com/file/d/1OzX/view"]
    assert meta["adet_listesi"] == {"174100684-a": 22}
    # diskteki meta.json da ayni sozlesmeyi tasir (operator UI okuyacak)
    raw = json.loads(next((tmp_path / "pending").rglob("*.json")).read_text(
        encoding="utf-8"))
    assert raw["share_links"]


def test_store_eski_cagri_geriye_uyumlu(tmp_path):
    s = PendingOrderStore(tmp_path / "pending")
    s.add(order_id="ZIP-ESKI", customer="C", sender="s", deadline="",
          priority_class=2, konu="", stl_map={"a": b"x"})
    meta = s.get("ZIP-ESKI")
    assert meta["review_reason"] == ""
    assert meta["share_links"] == []
    assert meta["adet_listesi"] == {}
