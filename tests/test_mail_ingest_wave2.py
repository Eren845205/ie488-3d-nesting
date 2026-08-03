"""tests/test_mail_ingest_wave2.py — Dalga-2 (DENETIM_RAPORU_2026-07-03) fixleri.

Kapsam (mail_ingest.py):
  #7  HTML-only govde -> duz metin (tag-soyma fallback, stdlib html.parser)
  #10 Birden fazla .zip eki -> HEPSI islenir, cakismada needs_review
  #9  Kardes .xlsx/.csv adet tablosu -> govde/txt eksikse tabloyla tamamlanir
  #14 RFC2047 kodlu ek dosya adi cozulur (zip + tablo ekleri)
"""

from __future__ import annotations

import email as _email
import io
import zipfile
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytest

from src.runtime.mail_ingest import (
    Attachment,
    ImapMailbox,
    RawMail,
    _extract_text_body,
    ingest_order,
)

trimesh = pytest.importorskip("trimesh")


def _imap_cfg():
    return {"host": "h", "port": 993, "user": "u", "password": "p",
            "folder": "INBOX", "use_ssl": True}


def _zip_bytes(names_extents):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for nm, ext in names_extents:
            mesh = trimesh.creation.box(extents=ext)
            z.writestr(f"{nm}.stl", mesh.export(file_type="stl"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# #7 HTML-only govde -> duz metin
# ---------------------------------------------------------------------------

class TestHtmlOnlyGovde:
    """text/plain parcasi OLMAYAN (yalniz text/html) mailler artik cozulur."""

    def test_multipart_html_only_tags_soyulur(self):
        msg = MIMEMultipart("alternative")
        msg["From"] = "kurumsal@ornek.com"
        msg["Subject"] = "Siparis"
        msg["Message-ID"] = "<html-only-1@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        html_body = "<html><body><p>Ad - 62</p><p>Kapak - 4</p></body></html>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        govde = _extract_text_body(msg)
        assert "<p>" not in govde
        assert "Ad - 62" in govde
        assert "Kapak - 4" in govde

    def test_html_only_signal_tespiti_calisir(self):
        """HTML-only govdeden cozulen metin _has_order_signal/adet cikarimini besler."""
        from src.runtime.mail_ingest import _has_order_signal
        msg = MIMEMultipart("alternative")
        msg["From"] = "kurumsal@ornek.com"
        msg["Subject"] = "Siparis"
        msg["Message-ID"] = "<html-only-2@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        html_body = "<div>Braket 80x60x30 mm, 5 adet gerekiyor.</div>"
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        govde = _extract_text_body(msg)
        assert _has_order_signal(govde) is True

    def test_html_only_script_style_metne_sizmaz(self):
        """script/style icerigi duz metne SIZMAMALI (yanlis sinyal riski)."""
        msg = MIMEMultipart("alternative")
        msg["From"] = "kurumsal@ornek.com"
        msg["Subject"] = "Siparis"
        msg["Message-ID"] = "<html-only-3@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        html_body = (
            "<html><head><style>.x{color:red}</style>"
            "<script>var adet=999999;</script></head>"
            "<body><p>Kanat Nervuru - 5</p></body></html>"
        )
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        govde = _extract_text_body(msg)
        assert "999999" not in govde
        assert "color:red" not in govde
        assert "Kanat Nervuru - 5" in govde

    def test_imap_extract_raw_mail_html_only_uctan_uca(self):
        """ImapMailbox._extract_raw_mail ile uctan uca: RawMail.govde duz metin olur."""
        msg = MIMEMultipart("alternative")
        msg["From"] = "kurumsal@ornek.com"
        msg["Subject"] = "Siparis"
        msg["Message-ID"] = "<html-only-4@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        msg.attach(MIMEText("<p>Ford Braketi - 8</p>", "html", "utf-8"))

        mb = ImapMailbox(_imap_cfg())
        raw_mail = mb._extract_raw_mail("10", msg.as_bytes())
        assert "<p>" not in raw_mail.govde
        assert "Ford Braketi - 8" in raw_mail.govde

    def test_text_plain_varsa_html_yerine_tercih_edilir_geriye_uyum(self):
        """text/plain parcasi VARSA (eski davranis) o kullanilir; html'e dusulmez."""
        msg = MIMEMultipart("alternative")
        msg["From"] = "x@y.com"
        msg["Subject"] = "Test"
        msg["Message-ID"] = "<plain-and-html@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        msg.attach(MIMEText("Duz metin govde.", "plain", "utf-8"))
        msg.attach(MIMEText("<p>Duz metin govde (html).</p>", "html", "utf-8"))

        govde = _extract_text_body(msg)
        assert govde == "Duz metin govde."


# ---------------------------------------------------------------------------
# #14 RFC2047 kodlu ek dosya adi cozulur
# ---------------------------------------------------------------------------

class TestRfc2047EkAdi:
    """Kodlu ek dosya adlari (=?UTF-8?B?...?=) coz."""

    def test_rfc2047_encoded_zip_filename_decoded(self):
        msg = MIMEMultipart()
        msg["From"] = "tedarik@ornek.com"
        msg["Subject"] = "Siparis"
        msg["Message-ID"] = "<rfc2047-1@ornek.com>"
        msg["Date"] = "Mon, 15 Jun 2026 09:00:00 +0300"
        msg.attach(MIMEText("ZIP ekte.", "plain", "utf-8"))

        zip_part = MIMEBase("application", "zip")
        zip_part.set_payload(b"fake zip bytes")
        encoders.encode_base64(zip_part)
        kodlu_ad = str(Header("Sipariş.zip", "utf-8"))
        zip_part.add_header(
            "Content-Disposition", "attachment", filename=kodlu_ad
        )
        msg.attach(zip_part)

        mb = ImapMailbox(_imap_cfg())
        raw_mail = mb._extract_raw_mail("11", msg.as_bytes())
        assert len(raw_mail.ekler) == 1
        assert raw_mail.ekler[0].dosya_adi == "Sipariş.zip"

    def test_rfc2047_ad_zip_uzantisi_taninir(self, tmp_path):
        """Cozulen ad .zip uzantisiyla biterse ingest_order zip yolunu tetikler."""
        zb = _zip_bytes([("braket", (10, 10, 10))])
        kodlu_ad = str(Header("Braket Siparişi.zip", "utf-8"))
        att = Attachment(dosya_adi=kodlu_ad, icerik=zb, mime="application/zip")

        # ingest_order ekler listesindeki dosya_adi'ni ZATEN cozulmus BEKLER
        # (cozme _extract_attachments asamasinda olur) -- burada dogrudan
        # _decode_mime_filename fonksiyonunu kullanarak eki hazirla.
        from src.runtime.mail_ingest import _decode_mime_filename
        decoded_att = Attachment(
            dosya_adi=_decode_mime_filename(att.dosya_adi), icerik=zb, mime=att.mime
        )
        mail = RawMail(
            gonderen="uretim@firma.com.tr",
            konu="Siparis",
            govde="braket 2 adet",
            tarih="2026-06-15",
            message_id="<rfc2047-2@ornek.com>",
            ekler=[decoded_att],
        )
        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order["parse_source"] == "attachment_zip_stl"
        assert order["parts"][0]["name"] == "braket"


# ---------------------------------------------------------------------------
# #10 Birden fazla .zip eki
# ---------------------------------------------------------------------------

class TestBirdenFazlaZipEki:

    def _mail_with_zips(self, zip_atts, govde="braket 2 adet\nkapak 3 adet"):
        return RawMail(
            gonderen="uretim@firma.com.tr",
            konu="Siparis",
            govde=govde,
            tarih="2026-06-19T10:00:00+03:00",
            message_id="<multizip-1@x>",
            ekler=zip_atts,
        )

    def test_iki_zip_hepsi_islenir(self, tmp_path):
        zb1 = _zip_bytes([("braket", (10, 10, 10))])
        zb2 = _zip_bytes([("kapak", (12, 12, 12))])
        mail = self._mail_with_zips([
            Attachment("parca1.zip", zb1, "application/zip"),
            Attachment("parca2.zip", zb2, "application/zip"),
        ])
        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order["parse_source"] == "attachment_zip_stl"
        adlar = {p["name"] for p in order["parts"]}
        assert adlar == {"braket", "kapak"}

    def test_ikinci_zip_bozuksa_ilki_yine_islenir(self, tmp_path):
        zb1 = _zip_bytes([("braket", (10, 10, 10))])
        mail = self._mail_with_zips([
            Attachment("parca1.zip", zb1, "application/zip"),
            Attachment("parca2.zip", b"not a real zip", "application/zip"),
        ], govde="braket 2 adet")
        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order["parts"][0]["name"] == "braket"

    def test_ayni_ad_farkli_icerik_cakismasi_needs_review(self, tmp_path):
        """Iki zip'te AYNI taban ad, FARKLI STL icerigi -> sessiz ezme YOK."""
        zb1 = _zip_bytes([("parca", (10, 10, 10))])
        zb2 = _zip_bytes([("parca", (99, 99, 99))])
        mail = self._mail_with_zips([
            Attachment("parca1.zip", zb1, "application/zip"),
            Attachment("parca2.zip", zb2, "application/zip"),
        ], govde="parca 2 adet")
        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order["needs_review"] is True
        assert order["review_reason"] == "zip_name_collision"
        assert "parca" in order["stl_names"]

    def test_ayni_ad_ayni_icerik_cakisma_sayilmaz(self, tmp_path):
        """Iki zip'te AYNI ad + AYNI icerik -> gercek cakisma degil, sorunsuz birlesir."""
        zb = _zip_bytes([("braket", (10, 10, 10))])
        mail = self._mail_with_zips([
            Attachment("parca1.zip", zb, "application/zip"),
            Attachment("parca2.zip", zb, "application/zip"),
        ], govde="braket 2 adet")
        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order.get("needs_review") is not True
        assert order["parts"][0]["name"] == "braket"


# ---------------------------------------------------------------------------
# #9 Kardes .xlsx/.csv adet tablosu
# ---------------------------------------------------------------------------

class TestKardesTabloAdeti:

    def _mail(self, zb, table_att, govde):
        return RawMail(
            gonderen="uretim@firma.com.tr",
            konu="Siparis",
            govde=govde,
            tarih="2026-06-19T10:00:00+03:00",
            message_id="<tablo-1@x>",
            ekler=[Attachment("parcalar.zip", zb, "application/zip"), table_att],
        )

    def test_govde_eksikse_csv_tablosu_tamamlar(self, tmp_path):
        """Govde YALNIZ 1 parcanin adedini veriyor; CSV eki digerini tamamlar."""
        zb = _zip_bytes([("braket", (10, 10, 10)), ("kapak", (12, 12, 12))])
        csv_text = "name,width_mm,depth_mm,height_mm,qty\nkapak,12,12,12,3\n"
        table_att = Attachment("adetler.csv", csv_text.encode("utf-8"), "text/csv")
        mail = self._mail(zb, table_att, govde="braket 2 adet")

        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order.get("needs_review") is not True
        pmap = {p["name"]: p["qty"] for p in order["parts"]}
        assert pmap == {"braket": 2, "kapak": 3}
        assert "table" in order["quantity_source"]

    def test_govde_tam_kapsiyorsa_tablo_kullanilmaz(self, tmp_path):
        """Govde/txt ZATEN tam kapsiyorsa tablo eki devreye girmez (quantity_source'ta 'table' gecmez)."""
        zb = _zip_bytes([("braket", (10, 10, 10))])
        csv_text = "name,width_mm,depth_mm,height_mm,qty\nbraket,10,10,10,999\n"
        table_att = Attachment("adetler.csv", csv_text.encode("utf-8"), "text/csv")
        mail = self._mail(zb, table_att, govde="braket 2 adet")

        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order["parts"][0]["qty"] == 2
        assert "table" not in order["quantity_source"]

    def test_xlsx_tablosu_da_calisir(self, tmp_path):
        import openpyxl
        zb = _zip_bytes([("braket", (10, 10, 10)), ("kapak", (12, 12, 12))])
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["name", "width_mm", "depth_mm", "height_mm", "qty"])
        ws.append(["kapak", 12, 12, 12, 7])
        buf = io.BytesIO()
        wb.save(buf)
        table_att = Attachment("adetler.xlsx", buf.getvalue(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        mail = self._mail(zb, table_att, govde="braket 2 adet")

        order = ingest_order(mail, parser_role=None, persist_root=str(tmp_path))
        assert order is not None
        assert order.get("needs_review") is not True
        pmap = {p["name"]: p["qty"] for p in order["parts"]}
        assert pmap == {"braket": 2, "kapak": 7}
