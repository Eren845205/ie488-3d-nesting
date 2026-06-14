"""src/runtime/mail_ingest.py — Mail ingest modulu (PLAN_SERVIS S1).

Sorumluluk: posta kutusundan ham mailler CEKMEK (RawMail listesi).
Parse etmez, nesting yapmaz, fiyat hesaplamaz — tek sorumluluk: fetch.

Sinif hiyerarsisi
-----------------
  MailSource (ABC)
    |-- FakeMailbox     : DEMO — kimlik/internet gerekmez; 4 gercekci TR siparis maili
    |-- ImapMailbox     : URETIM — imaplib ile gercek IMAP; UID cursor, zarif dusus

Kullanim (ornek)
----------------
  from src.runtime.mail_ingest import make_mail_source

  src = make_mail_source(config)           # konfig: {"source": "fake"} veya IMAP parametreleri
  mails = src.fetch_new()                  # List[RawMail] -- yalniz yeni/islenmemis
  for mail in mails:
      parser_role.parse(mail.govde)        # RawMail.govde -> ParserRole.parse()

Idempotency: her RawMail.message_id bir kez islenir.
  - FakeMailbox  : instance bazli set -- ilk fetch hepsini, ikinci fetch bos dondurur.
  - ImapMailbox  : _seen_uids set -- UID cursor ile gercek IMAP'ta tekrar cekilmez.

Sirlar: parola KODDA DEGİL. ImapMailbox konfig sozlugundan veya env'den alir.
"""

from __future__ import annotations

import email
import imaplib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Veri modeli
# ---------------------------------------------------------------------------

@dataclass
class RawMail:
    """Posta kutusundan cekilen ham mail.

    Alanlar
    -------
    gonderen   : From adresi (orn. tedarik@ford.com)
    konu       : Subject satirı
    govde      : Duz metin govde (ParserRole.parse()'a beslenecek)
    tarih      : ISO 8601 veya RFC 2822 tarih dizesi
    message_id : RFC 2822 Message-ID (idempotency anahtari)
    """

    gonderen: str
    konu: str
    govde: str
    tarih: str
    message_id: str

    def __repr__(self) -> str:
        return (
            f"RawMail(gonderen={self.gonderen!r}, "
            f"konu={self.konu!r}, "
            f"message_id={self.message_id!r})"
        )


# ---------------------------------------------------------------------------
# Soyut taban
# ---------------------------------------------------------------------------

class MailSource(ABC):
    """Posta kaynagi soyut temeli."""

    @abstractmethod
    def fetch_new(self) -> List[RawMail]:
        """Yeni (islenmemis) mailleri cek.

        Dondurur
        --------
        List[RawMail] -- bos liste eger yeni mail yoksa veya hata olusmusa.
        Hicbir zaman firlatmaz; hata durumunda bos liste + log.
        """


# ---------------------------------------------------------------------------
# Demo sabitleri — 4 gercekci Turkce siparis maili
# ---------------------------------------------------------------------------

_DEMO_MAILS: List[Dict[str, str]] = [
    {
        "gonderen": "tedarik@ford.com.tr",
        "konu": "ACİL Sipariş — Ford Braketi (5 gün termin)",
        "tarih": "2026-06-14T08:15:00+03:00",
        "message_id": "<FORD-ACL-2026061401@ford.com.tr>",
        "govde": (
            "Merhaba,\n\n"
            "Acil üretim ihtiyacımız nedeniyle aşağıdaki parçaların en geç "
            "5 iş günü içinde teslim edilmesi gerekmektedir.\n\n"
            "Parça listesi:\n"
            "  - Ford Motor Braketi (Ref: FB-2240): 8 adet, 80x60x30 mm\n"
            "  - Ford Kapak Plakası (Ref: FK-0881): 4 adet, 100x80x20 mm\n\n"
            "Termin: 19 Haziran 2026\n"
            "Teslim adresi: Ford Otomotiv, Gölcük Tesisi\n\n"
            "Teşekkürler,\n"
            "Ahmet Kaya\n"
            "Tedarik Zinciri Müdürü, Ford Türkiye"
        ),
    },
    {
        "gonderen": "malzeme@baykar.com.tr",
        "konu": "Sipariş Talebi — Baykar İHA Kanat Parçaları",
        "tarih": "2026-06-13T14:30:00+03:00",
        "message_id": "<BAYK-2026061302@baykar.com.tr>",
        "govde": (
            "İyi günler,\n\n"
            "Aşağıdaki parçalar için sipariş oluşturulmasını talep ediyoruz.\n\n"
            "Kalemler:\n"
            "  1. Kanat Nervürü (bayk_rib): 5 adet — 90x45x20 mm, alüminyum\n"
            "  2. Ana Kiriş (bayk_spar): 2 adet — 200x30x25 mm, alüminyum\n"
            "  3. Bağlantı Klipsi (bayk_clip): 10 adet — 38x30x20 mm\n\n"
            "Termin: 30 gün (yaklaşık 14 Temmuz 2026)\n"
            "Tolerans: ±0.2 mm\n"
            "Öncelik: Normal\n\n"
            "Saygılarımızla,\n"
            "Zeynep Arslan\n"
            "Malzeme Temin Departmanı, Baykar Makina"
        ),
    },
    {
        "gonderen": "satin.alma@aselsan.com.tr",
        "konu": "Parça Temin Talebi — ASELSAN EHK Projesi",
        "tarih": "2026-06-12T11:00:00+03:00",
        "message_id": "<ASEL-EHK-2026061201@aselsan.com.tr>",
        "govde": (
            "Sayın İlgili,\n\n"
            "EHK-7 projesi kapsamında aşağıdaki parçaların teminine ihtiyaç duyulmaktadır. "
            "Termin konusunda esneklik beklenmekte, ancak kalite belgesi zorunludur.\n\n"
            "Talepler:\n"
            "  * Muhafaza Gövdesi (asel_housing): 2 adet, 120x90x50 mm\n"
            "  * Bağlantı Plakası (asel_plate): 3 adet, 150x100x15 mm\n"
            "  * Destek Braketi (asel_bracket_sm): 6 adet, 55x40x22 mm\n\n"
            "Termin: Belirsiz — proje takvimi netleşince bilgi verilecektir.\n"
            "Not: ISO 9001 uygunluk belgesi gerekmektedir.\n\n"
            "İyi çalışmalar,\n"
            "Emre Demir\n"
            "Satın Alma Uzmanı, ASELSAN A.Ş."
        ),
    },
    {
        "gonderen": "uretim@tusas.com.tr",
        "konu": "Havacılık Parça Siparişi — TUSAS F/A-X",
        "tarih": "2026-06-11T09:45:00+03:00",
        "message_id": "<TUSAS-FAX-2026061101@tusas.com.tr>",
        "govde": (
            "Merhaba,\n\n"
            "F/A-X programı için aşağıdaki titanyum parçaları talep ediyoruz.\n\n"
            "Parça Detayları:\n"
            "  - Hava Alığı Flanşı: 3 adet, 75x75x28 mm, Ti-6Al-4V\n"
            "  - Bağlantı Köşebenti: 5 adet, 60x50x18 mm, Ti-6Al-4V\n\n"
            "İstenen Termin: 21 Haziran 2026 (acil — uçuş testi öncesi)\n"
            "Onay Süreci: TKYD kalite onayı zorunlu\n\n"
            "Lütfen fiyat teklifi ve üretim süresi bildiriniz.\n\n"
            "Saygılarımla,\n"
            "Mustafa Çelik\n"
            "Üretim Planlama, TUSAS"
        ),
    },
]


# ---------------------------------------------------------------------------
# FakeMailbox
# ---------------------------------------------------------------------------

class FakeMailbox(MailSource):
    """DEMO posta kutusu — 4 gercekci Turkce siparis maili.

    Kimlik gerekmez, internet baglantisi gerekmez.
    Idempotency: ilk fetch tum mailleri dondurur; sonraki fetch bos liste dondurur.
    Yeni FakeMailbox() ornegi mailleri tekrar dondurur (ornek bazli set).
    """

    def __init__(self) -> None:
        self._seen_ids: Set[str] = set()

    def fetch_new(self) -> List[RawMail]:
        """Daha once dondurulmemis demo maillerini dondurur."""
        result: List[RawMail] = []
        for entry in _DEMO_MAILS:
            mid = entry["message_id"]
            if mid not in self._seen_ids:
                result.append(
                    RawMail(
                        gonderen=entry["gonderen"],
                        konu=entry["konu"],
                        govde=entry["govde"],
                        tarih=entry["tarih"],
                        message_id=mid,
                    )
                )
                self._seen_ids.add(mid)
        return result


# ---------------------------------------------------------------------------
# ImapMailbox
# ---------------------------------------------------------------------------

class ImapMailbox(MailSource):
    """URETIM IMAP posta kutusu — imaplib tabanli.

    Parametreler (konfig sozlugu)
    ----------------------------
    host     : IMAP sunucu adresi
    port     : IMAP port (varsayilan 993 SSL, 143 duz)
    user     : Kullanici adi / e-posta adresi
    password : Parola (konfig/env — KODDA SABIT DEGER YOK)
    folder   : Posta klasoru (varsayilan "INBOX")
    use_ssl  : True -> IMAP4_SSL, False -> IMAP4 (varsayilan True)

    Idempotency: _seen_uids set'i ile daha once islenen UID'ler tekrar cekilmez.
    Zarif dusus: baglanti/auth hatasi -> bos liste + log (firlatmaz).
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.host: str = config["host"]
        self.port: int = int(config.get("port", 993))
        self.user: str = config["user"]
        self._password: str = config.get("password", "")
        self.folder: str = config.get("folder", "INBOX")
        self.use_ssl: bool = bool(config.get("use_ssl", True))
        self._seen_uids: Set[str] = set()

    # ------------------------------------------------------------------
    # Internal: baglanti kur
    # ------------------------------------------------------------------

    def _connect(self) -> imaplib.IMAP4:
        """IMAP baglantisi ac ve login yap. Hata firlatabilir.

        Guvenlik: kimlik bilgileri ASLA cleartext gonderilmez. use_ssl=True ->
        dogrudan IMAPS (993). use_ssl=False (143 STARTTLS senaryosu) -> login
        ONCESI STARTTLS ile sifrele; sunucu STARTTLS desteklemiyorsa FAIL-CLOSED
        (login yapmadan hata firlat) — duz parola asla gonderilmez.
        """
        if self.use_ssl:
            conn = imaplib.IMAP4_SSL(self.host, self.port)
        else:
            conn = imaplib.IMAP4(self.host, self.port)
            # STARTTLS zorunlu — desteklenmiyorsa kapali kal (cleartext login YOK)
            if "STARTTLS" not in getattr(conn, "capabilities", ()):
                conn.logout()
                raise RuntimeError(
                    "IMAP sunucu STARTTLS desteklemiyor; cleartext login engellendi "
                    "(use_ssl=True / IMAPS kullanin)."
                )
            conn.starttls()
        conn.login(self.user, self._password)
        return conn

    # ------------------------------------------------------------------
    # Internal: tek mail cekilmesi
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_raw_mail(uid: str, raw_bytes: bytes) -> RawMail:
        """Bayt'tan RawMail uret."""
        msg = email.message_from_bytes(raw_bytes)
        gonderen = msg.get("From", "")
        konu = msg.get("Subject", "")
        tarih = msg.get("Date", "")
        message_id = msg.get("Message-ID", f"<uid-{uid}>")
        govde = _extract_text_body(msg)
        return RawMail(
            gonderen=gonderen,
            konu=konu,
            govde=govde,
            tarih=tarih,
            message_id=message_id,
        )

    # ------------------------------------------------------------------
    # Internal: yeni UID'leri bul
    # ------------------------------------------------------------------

    def _fetch_uids(self, conn: imaplib.IMAP4) -> List[str]:
        """Klasordeki tum UID'leri dondurur."""
        conn.select(self.folder, readonly=True)
        status, data = conn.uid("SEARCH", None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []
        uid_list = data[0].decode().split()
        return [u for u in uid_list if u not in self._seen_uids]

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def fetch_new(self) -> List[RawMail]:
        """Yeni (islenmemis) mailleri IMAP'tan ceker.

        Baglanti veya auth hatasi durumunda bos liste dondurur (FIRLATMAZ).
        """
        try:
            conn = self._connect()
        except Exception as exc:
            logger.warning(
                "ImapMailbox: baglanti kurulamadi (%s:%s) — %s",
                self.host, self.port, exc,
            )
            return []

        result: List[RawMail] = []
        try:
            new_uids = self._fetch_uids(conn)
            if not new_uids:
                return []

            for uid in new_uids:
                try:
                    status, msg_data = conn.uid("FETCH", uid, "(RFC822)")
                    if status != "OK" or not msg_data or not msg_data[0]:
                        logger.warning("ImapMailbox: UID %s cekme basarisiz.", uid)
                        continue
                    raw_bytes = msg_data[0][1]
                    raw_mail = self._extract_raw_mail(uid, raw_bytes)
                    result.append(raw_mail)
                    self._seen_uids.add(uid)
                except Exception as fetch_exc:
                    logger.warning(
                        "ImapMailbox: UID %s isleme hatasi — %s", uid, fetch_exc
                    )
        except Exception as exc:
            logger.warning("ImapMailbox: mail listeleme hatasi — %s", exc)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return result


# ---------------------------------------------------------------------------
# Govde cikarici yardimci
# ---------------------------------------------------------------------------

def _extract_text_body(msg: email.message.Message) -> str:
    """email.Message'dan duz metin govdesini cikarir.

    Oncelik: text/plain; bulunamazsa text/html; her ikisi de yoksa bos dize.
    """
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # text/plain bulunamadi — html dene
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        # decode=False durumu (string payload)
        raw = msg.get_payload()
        return raw if isinstance(raw, str) else ""


# ---------------------------------------------------------------------------
# Fabrika
# ---------------------------------------------------------------------------

def make_mail_source(config: Dict[str, Any]) -> MailSource:
    """Konfig sozlugundan uygun MailSource ornegi olusturur.

    Parametreler
    ------------
    config : {"source": "fake"} veya {"source": "imap", "host": ..., ...}
             "source" anahtari yoksa "fake" varsayilir.

    Dondurur
    --------
    FakeMailbox  : source == "fake" veya source eksik
    ImapMailbox  : source == "imap"

    Firlatir
    --------
    ValueError : Bilinmeyen source degeri
    """
    source = config.get("source", "fake")
    if source == "fake":
        return FakeMailbox()
    if source == "imap":
        return ImapMailbox(config)
    raise ValueError(
        f"Bilinmeyen mail source: {source!r}. "
        f"Gecerli degerler: 'fake', 'imap'."
    )
