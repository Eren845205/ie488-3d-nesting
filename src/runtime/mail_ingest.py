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
import email.utils
import hashlib
import imaplib
import io
import logging
import re
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.runtime.idempotency import idempotency_key as _idempotency_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Veri modeli
# ---------------------------------------------------------------------------

@dataclass
class Attachment:
    """Mail ekini temsil eden veri modeli.

    Alanlar
    -------
    dosya_adi : ek dosya adi (orn. "siparis.xlsx")
    icerik    : ham bayt dizisi (get_payload(decode=True) ciktisi)
    mime      : MIME tipi (orn. "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    """

    dosya_adi: str
    icerik: bytes
    mime: str


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
    ekler      : Mail ekleri (varsayilan bos liste — geriye uyum)
    """

    gonderen: str
    konu: str
    govde: str
    tarih: str
    message_id: str
    ekler: List[Attachment] = field(default_factory=list)
    uid: Optional[str] = None  # IMAP UID (ImapMailbox doldurur; FakeMailbox None birakir — geriye uyum)

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

    def mark_processed(self, mail: "RawMail") -> None:
        """Mail kesin olarak islendi — kalici idempotency kaydini yap.

        Varsayilan: no-op. ImapMailbox override eder ve _idem_store'a yazar.
        at-least-once semantigi icin process_inbox_once BASARILI islem sonrasi
        bu metodu cagirir. Hicbir zaman firlatmaz.
        """


# ---------------------------------------------------------------------------
# Demo sabitleri — 4 gercekci Turkce siparis maili + 1 Excel ekli mail
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
    {
        "gonderen": "satin.alma@bosch.com.tr",
        "konu": "Sipariş — Bosch Parça Listesi (Excel Ek)",
        "tarih": "2026-06-15T10:00:00+03:00",
        "message_id": "<BOSCH-XLS-2026061501@bosch.com.tr>",
        "govde": (
            "Merhaba,\n\n"
            "Talep ettiğimiz parçaların listesini ek Excel dosyasında bulabilirsiniz. "
            "Boyutlar ve adet bilgileri dosyada mevcut.\n\n"
            "Termin: 25 Haziran 2026\n\n"
            "Saygılarımla,\n"
            "Mehmet Yılmaz\n"
            "Satın Alma, Bosch Türkiye"
        ),
    },
]


# ---------------------------------------------------------------------------
# FakeMailbox — Excel ek uretici
# ---------------------------------------------------------------------------

def _make_demo_xlsx_attachment() -> Attachment:
    """Bellek-ici sabit Excel dosyasi uretir (deterministik, seed yok).

    Basliklar: ad, en_mm, boy_mm, yukseklik_mm, adet
    Satirlar : 3 demo parca (Bosch senaryo)
    """
    try:
        import openpyxl
    except ImportError:
        logger.warning("FakeMailbox: openpyxl yuklu degil — xlsx eki bos bayt olarak olusturuldu.")
        return Attachment(
            dosya_adi="bosch_siparis.xlsx",
            icerik=b"",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Siparis"
    ws.append(["ad", "en_mm", "boy_mm", "yukseklik_mm", "adet"])
    ws.append(["bosch_klips",   55.0, 38.0, 20.0, 10])
    ws.append(["bosch_kapak",   90.0, 70.0, 25.0,  4])
    ws.append(["bosch_gövde",  110.0, 85.0, 45.0,  2])

    buf = io.BytesIO()
    wb.save(buf)
    return Attachment(
        dosya_adi="bosch_siparis.xlsx",
        icerik=buf.getvalue(),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# FakeMailbox
# ---------------------------------------------------------------------------

class FakeMailbox(MailSource):
    """DEMO posta kutusu — 4 gercekci Turkce siparis maili + 1 Excel ekli mail.

    Kimlik gerekmez, internet baglantisi gerekmez.
    Idempotency: ilk fetch tum mailleri dondurur; sonraki fetch bos liste dondurur.
    Yeni FakeMailbox() ornegi mailleri tekrar dondurur (ornek bazli set).

    Geriye uyum: mevcut 4 mailin ekler=[] olarak kalir.
    5. mail (Bosch): xlsx eki vardir.
    """

    def __init__(self) -> None:
        self._seen_ids: Set[str] = set()

    def fetch_new(self) -> List[RawMail]:
        """Daha once dondurulmemis demo maillerini dondurur."""
        result: List[RawMail] = []
        for idx, entry in enumerate(_DEMO_MAILS):
            mid = entry["message_id"]
            if mid not in self._seen_ids:
                # Son entry (5. mail) Excel eki tasiyor; oncekiler ek tasimaz
                if idx == len(_DEMO_MAILS) - 1:
                    ekler = [_make_demo_xlsx_attachment()]
                else:
                    ekler = []

                result.append(
                    RawMail(
                        gonderen=entry["gonderen"],
                        konu=entry["konu"],
                        govde=entry["govde"],
                        tarih=entry["tarih"],
                        message_id=mid,
                        ekler=ekler,
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
    max_fetch: Tek turda islenecek EN YENI mail sayisi (varsayilan 20).
               Gelen kutusunun TAMAMINI degil; en son gelen N maili tarar
               (siparis maili her zaman yenidir). 0/negatif -> sinirsiz.
    unseen_only: True ise yalniz OKUNMAMIS (UNSEEN) mailleri tarar
               (varsayilan False — demo'da mailler okunmus olabilir).

    Idempotency: _seen_uids set'i ile daha once islenen UID'ler tekrar cekilmez.
    Zarif dusus: baglanti/auth hatasi -> bos liste + log (firlatmaz).
    """

    def __init__(self, config: Dict[str, Any], *, idem_store: Optional[Any] = None) -> None:
        self.host: str = config["host"]
        self.port: int = int(config.get("port", 993))
        self.user: str = config["user"]
        self._password: str = config.get("password", "")
        # Fix-3: bos parola sessizce kabul edilmez (cleartext gonderilmeden once hata)
        if not self._password:
            raise ValueError(
                "ImapMailbox: 'password' konfig'de eksik veya bos — "
                "IMAP kimlik dogrulamasi icin parola zorunludur."
            )
        self.folder: str = config.get("folder", "INBOX")
        self.use_ssl: bool = bool(config.get("use_ssl", True))
        # Limit: gelen kutusunun tamamini DEGIL, en yeni N maili tara.
        self.max_fetch: int = int(config.get("max_fetch", 20))
        self.unseen_only: bool = bool(config.get("unseen_only", False))
        # Saglam mail-secimi (opt-in, geri-uyumlu — default'lar eski "ALL" davranisini korur):
        #   provider          : "gmail" ise X-GM-RAW kategorisi/ek filtresi tetiklenir (None -> kapali)
        #   category_filter   : Gmail kategorisi ("primary" -> reklamlari atla, birincil maillere bak)
        #   prefer_attachments: ek-iceren mailleri yakala (siparis = ZIP-STL eki -> kesin sinyal)
        # NEDEN: duz "ALL" + son-20 penceresi reklamlarla dolup siparis mailini disari itiyordu.
        self.provider: Optional[str] = config.get("provider", None)
        self.category_filter: Optional[str] = config.get("category_filter", None)
        self.prefer_attachments: bool = bool(config.get("prefer_attachments", False))
        self._seen_uids: Set[str] = set()
        # Fix-5: idem_store enjeksiyonu — None ise kendi :memory: store'u olustur (geriye uyum).
        # Dis store verilirse poller turlar arasi idempotency state'i paylasir.
        if idem_store is not None:
            self._idem_store = idem_store
        else:
            from src.runtime.idempotency import SqliteIdempotencyStore
            self._idem_store = SqliteIdempotencyStore()

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
            # STARTTLS zorunlu: taze capability listesini sunucudan cek (Fix-1)
            _status, _caps = conn.capability()
            cap_str = (_caps[0].decode() if _caps and _caps[0] else "").upper()
            if "STARTTLS" not in cap_str:
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
        """Bayt'tan RawMail uret (govde + ekler)."""
        msg = email.message_from_bytes(raw_bytes)
        gonderen = msg.get("From", "")
        konu = msg.get("Subject", "")
        # Fix-6: RFC 2822 Date basligini ISO 8601'e donustur
        _raw_date = msg.get("Date", "")
        try:
            tarih = email.utils.parsedate_to_datetime(_raw_date).isoformat()
        except Exception:
            tarih = _raw_date  # parse basarisizsa ham deger koru
        message_id = msg.get("Message-ID", f"<uid-{uid}>")
        govde = _extract_text_body(msg)
        ekler = _extract_attachments(msg)
        return RawMail(
            gonderen=gonderen,
            konu=konu,
            govde=govde,
            tarih=tarih,
            message_id=message_id,
            ekler=ekler,
            uid=uid,  # at-least-once: mark_processed icin IMAP UID sakla
        )

    # ------------------------------------------------------------------
    # Internal: yeni UID'leri bul
    # ------------------------------------------------------------------

    def _idem_key(self, uid: str) -> str:
        """SHA-256 tabanli kalici idempotency anahtari uretir.

        Girdi: "imap" sabiti + kullanici adresi + UID. E-posta adresi
        plaintext gomulmez; idempotency_key() SHA-256 ozeti alir.
        """
        return _idempotency_key("imap", self.user, uid)

    def idem_key_for(self, mail: "RawMail") -> Optional[str]:
        """Bir RawMail icin idempotency anahtarini dondurur (register ETMEZ).

        "Gecmisten sil -> yeniden islenebilir" ozelligi icin: gecmis kaydina
        islenen mail(ler)in anahtarlari yazilir; kayit silinince bu anahtarlar
        idempotency store'dan da dusurulur (mail.uid None ise None doner —
        FakeMailbox/geriye uyum, sessizce atlanir).
        """
        if not mail.uid:
            return None
        return self._idem_key(mail.uid)

    def _fetch_uids(self, conn: imaplib.IMAP4) -> List[str]:
        """Islenecek UID'leri dondurur.

        Gelen kutusunun TAMAMINI degil yalniz en yeni `max_fetch` maili tarar
        (UID SEARCH artan sirali doner -> son N = en yeni N). Boylece ilk
        calistirmada yuzlerce eski mail LLM'e sokulmaz. unseen_only=True ise
        once OKUNMAMIS suzgeci uygulanir. Kalici store + in-memory set ile
        daha once islenenler atlanir.
        """
        conn.select(self.folder, readonly=True)
        base = "UNSEEN" if self.unseen_only else "ALL"

        # Gmail X-GM-RAW kategori/ek filtresi (provider-aware, opt-in). Birincil maillere ve/veya
        # ek-iceren maillere odaklan -> reklamlar son-N penceresini doldurup siparisi disari itemez.
        gmail_raw = None
        if self.provider == "gmail":
            parts = []
            if self.category_filter:
                parts.append(f"category:{self.category_filter}")
            if self.prefer_attachments:
                parts.append("has:attachment")
            if parts:
                # primary VEYA ekli -> siparis (Primary'de ya da ek tasiyan) kacmaz
                gmail_raw = " OR ".join(parts) if len(parts) > 1 else parts[0]

        status = data = None
        if gmail_raw is not None:
            try:
                if self.unseen_only:
                    status, data = conn.uid("SEARCH", None, "UNSEEN",
                                            "X-GM-RAW", f'"{gmail_raw}"')
                else:
                    status, data = conn.uid("SEARCH", None, "X-GM-RAW", f'"{gmail_raw}"')
            except imaplib.IMAP4.error as exc:
                # X-GM-RAW desteklenmeyen sunucu (Outlook vb.) -> duz aramaya dus, kirilmaz
                logger.warning("X-GM-RAW desteklenmiyor (%s) — duz '%s' aramaya dusuluyor.",
                               exc, base)
                status = data = None

        if status is None:
            status, data = conn.uid("SEARCH", None, base)

        if status != "OK" or not data or not data[0]:
            return []
        uid_list = data[0].decode().split()
        # Limit: yalniz en yeni N maili degerlendir (artan sirali -> son N).
        if self.max_fetch and self.max_fetch > 0:
            uid_list = uid_list[-self.max_fetch:]
        # Fix-4: in-memory set VE kalici store kontrolu
        return [
            u for u in uid_list
            if u not in self._seen_uids and not self._idem_store.is_registered(self._idem_key(u))
        ]

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
                    # at-least-once: kalici store'a kayit BURDA DEGİL — mark_processed'e ertelendi.
                    # _seen_uids bu-process dedup'u saglar; kalici kayit ancak kesin islem sonrasi.
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

    def mark_processed(self, mail: "RawMail") -> None:
        """Mail'i kalici idempotency store'a kaydet (at-least-once).

        process_inbox_once tarafindan kesin islem sonrasi cagirilir:
          - spam / parse-fail (ingest None) -> LLM tekrar yakma
          - needs_review -> pending_store'a alindi
          - order + pipeline basarili -> kesin islem

        mail.uid None ise no-op (FakeMailbox / geriye uyum).
        DuplicateKeyError sessizce yutulur (tekrar cagri guvenli); diger store
        hatalari (OperationalError/IOError vb.) LOGLANIR -- sessiz yutma
        double-processing'i gorunmez yapardi.
        """
        if not mail.uid:
            return
        from src.runtime.idempotency import DuplicateKeyError
        try:
            self._idem_store.register(self._idem_key(mail.uid))
        except DuplicateKeyError:
            pass  # idempotent cagri -- beklenen, zaten kayitli
        except Exception as exc:
            logger.warning(
                "mark_processed: store yazimi basarisiz uid=%s -- %s "
                "(mail sonraki turda tekrar islenebilir)", mail.uid, exc,
            )


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
# Ek cikarici yardimci
# ---------------------------------------------------------------------------

# Sikistirilmis ek (ZIP/Excel) ust siniri. GERCEK STL siparis zip'leri buyuktur
# (orn. hocanin Plan3.zip ~24.5 MB) — 5 MB cok dusuktu, gercek siparisleri
# sessizce eliyordu. 50 MB on-prem tek-kiraci araci icin makul DoS siniri;
# acilan toplam STL ayrica zip_stl_extractor max_total_mb=200 ile sinirli.
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024  # 50 MB


def _extract_attachments(msg: email.message.Message) -> List[Attachment]:
    """email.Message'dan ekleri cikarir.

    Kriter: Content-Disposition 'attachment' olan veya dosya adi olan MIME parcalari.
    Fix-2: Ek payload MAX_ATTACHMENT_BYTES (5 MB) sinirini asarsa atlanir.
    Dondurur: List[Attachment] — ek bulunamazsa bos liste.
    """
    attachments: List[Attachment] = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        content_disposition = part.get_content_disposition() or ""
        filename = part.get_filename()

        if content_disposition.lower() == "attachment" or filename:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            # Fix-2: boyut siniri kontrol
            if len(payload) > MAX_ATTACHMENT_BYTES:
                logger.warning(
                    "_extract_attachments: ek boyutu siniri asildi (%d bayt > %d) — atlanıyor: %s",
                    len(payload), MAX_ATTACHMENT_BYTES, filename or "isimsiz",
                )
                continue
            mime = part.get_content_type() or "application/octet-stream"
            dosya_adi = filename or f"ek_{len(attachments)+1}"
            attachments.append(
                Attachment(
                    dosya_adi=dosya_adi,
                    icerik=payload,
                    mime=mime,
                )
            )

    return attachments


# ---------------------------------------------------------------------------
# ingest_order — yonlendirme (dosyali + metinli)
# ---------------------------------------------------------------------------

_STRUCTURED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv"}
_ZIP_EXTENSIONS = {".zip"}
# Adet listesi eki: "Adet listesi.txt" gibi duz-metin adet kaynagi (Deneme4
# gercek maili boyle geldi — govde + txt eki AYNI listeyi tasiyordu).
_TXT_EXTENSIONS = {".txt"}

# Boyut deseni: 3D olcu "80x60x30", "80 x 60 x 30" — siparis sinyali (parca olcusu).
# P2: 2D (NxN) KASITLI haric — 2D olculer spam'de cok gecer (ekran/oda/tarih: "80x60",
# "2x4", "14x00") ve yanlis-pozitif uretip maili gereksiz LLM'e sokardi. Gercek uretim
# parcasi 3 boyutludur; gercek serbest-metin siparisleri (Ford/Baykar demo) NxNxN tasir.
_DIM_PATTERN = re.compile(r"\d+\s*[x×]\s*\d+\s*[x×]\s*\d+", re.IGNORECASE)


def _has_order_signal(text: str) -> bool:
    """Mail govdesinde SIPARIS SINYALI var mi? (LLM'e gitmeden ucuz on-kontrol)

    Sinyal = '<ad> <sayi> adet' deseni VEYA boyut deseni (NxN). Ikisi de yoksa
    mail muhtemelen siparis DEGIL (reklam/kisisel/bildirim) — LLM'e sokulmaz.
    Aksi halde LLM siparis olmayan maili parse etmeye zorlanip UYDURUR
    (hallucination -> sahte siparis). Bu kapi yanlis-pozitifi engeller; gercek
    siparis ya ek ya bu desenlerden birini tasidigi icin kacmaz.
    """
    from src.runtime.quantity_text_parser import parse_quantities
    if parse_quantities(text):
        return True
    if _DIM_PATTERN.search(text):
        return True
    return False


def _resolve_plate() -> tuple[Optional[float], Optional[float]]:
    """Gercek plaka (width, depth) coz — configs/plate.local.json > env PLATE_*.

    Tanimliysa o GERCEK yazici plakasi (UI'dan girilen) kullanilir. Tanimsizsa
    (None, None) -> plaka parcalardan otomatik turetilir. Tek kaynak:
    src/runtime/plate_config.resolve_plate (height bu akista kullanilmaz).
    """
    from src.runtime.plate_config import resolve_plate
    w, d, _h = resolve_plate()
    return w, d


def _find_attachment(mail: RawMail, extensions: Set[str]) -> Optional[Attachment]:
    """Mail eklerinde verilen uzantilardan ilkini bul (yoksa None)."""
    for att in (mail.ekler or []):
        ext = "." + att.dosya_adi.rsplit(".", 1)[-1].lower() if "." in att.dosya_adi else ""
        if ext in extensions:
            return att
    return None


_STL_ADET_RE = None  # lazy-compile (module import maliyeti sifir kalsin)


def _qty_from_stl_name_and_bytes(name: str, data: bytes):
    """STL-ici adet cikarimi -> (qty|None, kaynak|None, celiski|None).

    Kaynaklar: (a) dosya adi soneki '-NAdet'/'-Npcs', (b) binary STL 80-bayt
    header'daki solid-adi soneki, (c) ASCII STL ilk 'solid <ad>' satiri.
    Bulunan TUM kaynaklar ayni degeri veriyorsa (deger, 'kaynak+kaynak', None);
    celisiyorsa (None, None, {kaynak: deger}) — cagiran doldurmaz, operator
    yolu calisir. Hic yoksa (None, None, None).
    """
    import re
    global _STL_ADET_RE
    if _STL_ADET_RE is None:
        _STL_ADET_RE = re.compile(
            r"[-_ ](\d{1,4})\s*(adet|ad|pcs|prc)\.?\s*$", re.IGNORECASE)
    found = {}
    m = _STL_ADET_RE.search(name.strip())
    if m:
        found["dosya_adi"] = int(m.group(1))
    try:
        is_ascii = data[:5] == b"solid" and b"facet" in data[:400]
        if is_ascii:
            first = data[:200].decode("latin-1", "replace").splitlines()[0]
            m2 = _STL_ADET_RE.search(first.strip())
            if m2:
                found["solid_adi"] = int(m2.group(1))
        else:
            head = data[:80].decode("latin-1", "replace")
            m3 = _STL_ADET_RE.search(head.rstrip("\x00 ").strip())
            if m3:
                found["header"] = int(m3.group(1))
    except Exception:
        pass  # bozuk baytlar adet-cikarimini engellemesin (STL loader ayri dogrular)
    if not found:
        return None, None, None
    if len(set(found.values())) == 1:
        return next(iter(found.values())), "+".join(sorted(found)), None
    return None, None, found


def _decode_text_bytes(data: bytes) -> str:
    """Duz-metin ek baytlarini metne cevir (TR mail gercekligi: UTF-8 ya da
    Windows cp1254; ikisi de degilse latin-1 replace ile asla firlatmaz)."""
    for enc in ("utf-8-sig", "cp1254"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _llm_zip_quantity_fallback(
    parser_role: Any,
    body: str,
    txt_text: str,
    stl_names: list,
) -> Optional[Dict[str, int]]:
    """LLM'den adet cikarimi — cikti ZIP'in GERCEK dosya adlarina TOPRAKLANIR.

    Deterministik parser govdeyi cozemediginde son care: mevcut ParserRole
    (yapilandirilmis siparis semasi + injection kontrolu + audit) calistirilir,
    dondurdugu kalem listesi match_quantities_to_stls ile ZIP'teki gercek
    dosya adlarina eslenir. LLM'in uydurdugu adlar hicbir dosyaya eslesmez ->
    kendiliginden duser (halusinasyon topraklamasi). Kabul karari CAGIRANDA:
    tam kapsama + checksum dogrulamasi gecmeyen sonuc KULLANILMAZ.

    Returns:
        {gercek_stl_adi: adet} veya None (LLM yok/basarisiz/injection).
    """
    from src.runtime.quantity_text_parser import MAX_QTY, match_quantities_to_stls

    text = body if not txt_text else f"{body}\n\n[Adet listesi eki]\n{txt_text}"
    try:
        result = parser_role.parse(text)
    except Exception as exc:
        logger.warning("ingest_order: LLM adet fallback hatasi — %s", exc)
        return None
    order_dict = getattr(result, "order_dict", None)
    if order_dict is None:
        return None
    if getattr(result, "injection_suphesi", False):
        logger.warning(
            "ingest_order: LLM adet fallback injection_suphesi bildirdi — "
            "sonuc KULLANILMIYOR (guvenli taraf)."
        )
        return None

    llm_q: Dict[str, int] = {}
    for p in order_dict.get("parts", []) or []:
        name = str(p.get("name") or p.get("id") or "").strip()
        try:
            qty = int(p.get("qty", 0))
        except (TypeError, ValueError):
            continue
        if name and 0 < qty:
            llm_q[name] = min(qty, MAX_QTY)
    if not llm_q:
        return None

    matched, _uk, _us = match_quantities_to_stls(llm_q, stl_names)
    return matched or None


def _ingest_zip_stl_order(
    mail: RawMail,
    zip_att: Attachment,
    persist_root: Optional[str],
    parser_role: Any = None,
) -> Optional[Dict[str, Any]]:
    """ZIP ekli STL siparisini isle: zip ac + adet cikar + esleme + bbox.

    ADET KAYNAKLARI (katmanli — insansiz otomatik isleme hedefi):
      1. Mail govdesi — '<ad> <adet> adet' VE '<ad> - <adet>' kaliplari.
      2. .txt eki ("Adet listesi.txt") — govdede olmayan adlari tamamlar.
      3. LLM fallback (parser_role verildiyse) — YALNIZ deterministik katman
         tam kapsayamadiginda; cikti ZIP'in gercek dosya adlarina topraklanir
         ve asagidaki dogrulamayi gecmeden KULLANILMAZ.

    ESLEME: match_quantities_to_stls (toleransli — case/TR-karakter/altcizgi
    + "-25pcs" tipi adet-ipucu sonekleri; belirsiz coklu aday eslenmez).

    CAPRAZ DOGRULAMA (checksum): govde/txt "588 parça" tipi toplam beyani
    tasiyorsa, eslenen adetlerin toplami bu beyanla TUTMALI. Tutarsizlik =
    celiski -> needs_review 'quantity_conflict' (yanlis adetle uretim
    planlamaktansa istisna kuyruguna dusur). Beyan yoksa eski davranis korunur.

    Dondurur: SCENARIO uyumlu order dict (parts source='stl', stl_path kalici)
    + 'skipped_*' alanlari. Eslesen parca yoksa None.

    Plaka: GERCEK plaka (env PLATE_*) verildiyse order'a 'container' olarak
    eklenir; verilmediyse 'container' KOYULMAZ — karar tamamen run_pipeline'a
    birakilir (cekirdek politika her parti icin parcalardan otomatik turetir).
    """
    from src.runtime.zip_stl_extractor import extract_stls
    from src.runtime.quantity_text_parser import (
        match_quantities_to_stls,
        parse_declared_total,
        parse_quantities,
    )
    from src.nesting3d.instances.stl_order_loader import build_instance_from_order

    try:
        stl_map = extract_stls(zip_att.icerik)
    except ValueError as exc:  # boyut bombasi vb.
        logger.warning("ingest_order: ZIP acilamadi (%s) — %s", zip_att.dosya_adi, exc)
        return None
    if not stl_map:
        logger.warning("ingest_order: ZIP icinde STL bulunamadi — %s", zip_att.dosya_adi)
        return None

    body = mail.govde or ""
    stl_names = list(stl_map)

    # Katman 1+2: govde + .txt eki (govde oncelikli, txt eksikleri tamamlar)
    quantities_raw = parse_quantities(body)
    quantity_source = "body" if quantities_raw else "none"
    txt_att = _find_attachment(mail, _TXT_EXTENSIONS)
    txt_text = _decode_text_bytes(txt_att.icerik) if txt_att is not None else ""
    if txt_text:
        txt_q = parse_quantities(txt_text)
        added = False
        for k, v in txt_q.items():
            if k not in quantities_raw:
                quantities_raw[k] = v
                added = True
        if added:
            quantity_source = "body+txt" if quantity_source == "body" else "txt"

    declared_total = parse_declared_total(body)
    if declared_total is None and txt_text:
        declared_total = parse_declared_total(txt_text)

    matched, unmatched_keys, unmatched_stls = match_quantities_to_stls(
        quantities_raw, stl_names
    )

    def _validated(q: Dict[str, int]) -> bool:
        """Insansiz kabul kosulu: TAM kapsama + (beyan varsa) checksum."""
        return bool(q) and len(q) == len(stl_names) and (
            declared_total is None or sum(q.values()) == declared_total
        )

    # Katman 3: LLM fallback — yalniz deterministik katman dogrulanamadiysa.
    # Kabul esigi deterministik katmandan SIKI: tam kapsama + checksum sart
    # (LLM ciktisi ancak matematiksel teyitle insansiz akisa girer).
    if parser_role is not None and not _validated(matched):
        llm_matched = _llm_zip_quantity_fallback(parser_role, body, txt_text, stl_names)
        if llm_matched is not None and _validated(llm_matched):
            logger.info(
                "ingest_order: LLM adet fallback DOGRULANDI (%d parca, toplam %d"
                "%s) — insansiz akista kullaniliyor.",
                len(llm_matched), sum(llm_matched.values()),
                f", beyan {declared_total} tuttu" if declared_total else "",
            )
            matched = llm_matched
            unmatched_keys = []
            unmatched_stls = []
            quantity_source = "llm_grounded"

    # Celiski kapisi: beyan var ama eslenen toplam tutmuyor -> istisna kuyrugu.
    # (Yanlis adetle nesting kosturmak sessiz uretim hatasi olur; operator
    # /adet-gir'den gercek adetleri girer. Beyan yoksa eski davranis surer.)
    if matched and declared_total is not None and sum(matched.values()) != declared_total:
        _det_hex = hashlib.sha256(mail.message_id.encode("utf-8")).hexdigest()[:8].upper()
        logger.warning(
            "ingest_order: adet celiskisi — beyan %d, eslenen toplam %d (%s); "
            "operator incelemesine alindi.",
            declared_total, sum(matched.values()), zip_att.dosya_adi,
        )
        return {
            "needs_review": True,
            "review_reason": "quantity_conflict",
            "order_id": f"ZIP-{_det_hex}",
            "customer": mail.gonderen.split("@")[-1].split(".")[0].upper(),
            "parse_source": "attachment_zip_stl_incomplete",
            "stl_names": sorted(stl_names),
            "declared_total": declared_total,
            "parsed_total": sum(matched.values()),
            "_stl_map": dict(stl_map),
            "parts": [],
        }

    quantities = matched

    # ------------------------------------------------------------------
    # STL-ICI ADET (hoca 2026-07-07, YAPILACAKLAR #2): bazi musteriler adedi
    # maile degil STL'ye yazar — dosya adi ve/veya binary-header/solid adi
    # sonunda "-NAdet"/"-Npcs". KURALLAR: (1) mail govdesi HER ZAMAN ezer
    # (yalniz govdede adedi OLMAYAN STL'lere bakilir); (2) kaynaklar celisirse
    # SESSIZ KABUL YOK -> doldurulmaz, mevcut eksik-bilgi/operator yolu calisir
    # (kanitli tuzaklar: '-25pcs'=26 [deneme4], ornek dosya adi 2 / header 4);
    # (3) doldurulan her adet kaynak etiketiyle order'a yazilir (telemetri).
    # ------------------------------------------------------------------
    stl_qty_info: Dict[str, dict] = {}
    _q_lower = {k.lower() for k in quantities}
    for _nm in sorted(stl_map):
        if _nm.lower() in _q_lower:
            continue  # mail govdesi ezer
        _q, _src, _conf = _qty_from_stl_name_and_bytes(_nm, stl_map[_nm])
        if _conf:
            stl_qty_info[_nm] = {"celiski": _conf}
            logger.warning(
                "ingest_order: STL-ici adet CELISKISI (%s): %s — operator "
                "onayina birakildi (sessiz kabul yok).", _nm, _conf)
        elif _q is not None:
            quantities[_nm] = _q
            stl_qty_info[_nm] = {"qty": _q, "kaynak": _src}
            logger.info("ingest_order: STL-ici adet kullanildi: %s=%d (%s)",
                        _nm, _q, _src)
    if any("qty" in v for v in stl_qty_info.values()):
        quantity_source = f"{quantity_source}+stl_icinden"

    # STL'leri mesaj-bazli kalici klasore yaz (nesting voxelize edene kadar yasamali)
    _det_hex = hashlib.sha256(mail.message_id.encode("utf-8")).hexdigest()[:8].upper()
    base = Path(persist_root) if persist_root else Path(tempfile.gettempdir())
    session_dir = base / f"mail_stl_{_det_hex}"

    # Gercek plaka (env) varsa pipeline'a iletilir; yoksa karar pipeline'da.
    plate_w, plate_d = _resolve_plate()
    res = build_instance_from_order(
        stl_map, quantities,
        container_w_mm=plate_w, container_d_mm=plate_d,
        persist_dir=session_dir,
    )
    if not res.instance.parts:
        # AYRIM: bos parca iki sebepten olabilir —
        #  (a) ZIP'te GECERLI STL var ama govdede ADET yok (skipped_no_qty dolu)
        #      -> SESSIZCE DUSURME. Bu bir EKSIK-BILGI sinyali; operatore
        #      "adet gir / beklet" diye yuzeye cikar (needs_review marker).
        #  (b) STL'lerin hepsi bozuk/okunamaz (yalniz skipped_no_stl) -> gercek
        #      basarisizlik -> None.
        if res.skipped_no_qty:
            logger.info(
                "ingest_order: ZIP-STL eksik bilgi — %d STL var ama govdede adet "
                "yok; operator incelemesine alindi (%s)",
                len(res.skipped_no_qty), zip_att.dosya_adi,
            )
            # Operatorun /adet-gir'den adet girip yeniden kurabilmesi icin
            # GECERLI (adeti eksik) STL byte'larini markere koy. Bozuk mesh'ler
            # skipped_no_stl'de — onlar tasinmaz. _stl_map underscore: app/poller
            # icin ic alan; JSON yanitina serialize EDILMEZ.
            valid_stl_map = {nm: stl_map[nm] for nm in res.skipped_no_qty if nm in stl_map}
            return {
                "needs_review": True,
                "review_reason": "missing_quantity",
                "order_id": f"ZIP-{_det_hex}",
                "customer": mail.gonderen.split("@")[-1].split(".")[0].upper(),
                "parse_source": "attachment_zip_stl_incomplete",
                "stl_names": sorted(res.skipped_no_qty),
                "_stl_map": valid_stl_map,
                "parts": [],
            }
        logger.warning(
            "ingest_order: ZIP+govde eslesmedi — hicbir parca uretilmedi (%s)",
            zip_att.dosya_adi,
        )
        return None

    parts = [
        {
            "id": p.id, "name": p.name, "qty": p.qty, "source": "stl",
            "stl_path": p.stl_path, "width_mm": p.width_mm,
            "depth_mm": p.depth_mm, "height_mm": p.height_mm,
            # #17/#19: gercek-hacim doluluk% icin true_fill tasi (None ise
            # 'hacim eksik' sayilir). wall/family raporlama meta'si.
            "true_fill": p.true_fill, "wall_mm": p.wall_mm, "family": p.family,
            # P0 kimlik: loader'in doldurdugu icerik imzasi + kaynak dosya adi
            # pipeline'a tasinir (order_id flatten'da enjekte edilir).
            "geo_imza": p.geo_imza, "kaynak_ad": p.kaynak_ad,
        }
        for p in res.instance.parts
    ]
    order: Dict[str, Any] = {
        "order_id": f"ZIP-{_det_hex}",
        "customer": mail.gonderen.split("@")[-1].split(".")[0].upper(),
        "deadline": "",
        "priority_class": 2,
        "parts": parts,
        "parse_source": "attachment_zip_stl",
        "quantity_source": quantity_source,
        # skipped_no_stl: bozuk mesh'ler (loader) + mailde olup ZIP'te
        # eslesmeyen adlar (on-eslestirme artigi — eski davranisla uyumlu).
        "skipped_no_stl": res.skipped_no_stl + [
            k for k in unmatched_keys if k not in res.skipped_no_stl
        ],
        "skipped_no_qty": res.skipped_no_qty,
    }
    # Yalniz GERCEK plaka (env) verildiyse pipeline'a ilet; aksi halde
    # run_pipeline parti-bazli otomatik turetir (tek karar noktasi pipeline).
    if plate_w is not None and plate_d is not None:
        order["container"] = {"width_mm": plate_w, "depth_mm": plate_d, "height_mm": None}
    return order


def ingest_order(
    mail: RawMail,
    parser_role: Any,
    persist_root: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Mail'den siparis dict'i cikar — ek tipine gore yonlendirir.

    Oncelik sirasi:
      1. .zip eki  -> STL siparisi (zip ac + govde/txt-eki adet + toleransli
         esleme; deterministik cozulemezse TOPRAKLANMIS LLM fallback — cikti
         gercek dosya adlarina eslenip checksum'la dogrulanmadan kullanilmaz)
      2. .xlsx/.csv eki -> parse_order_attachment (LLM YOK)
      3. ek yok -> parser_role.parse(mail.govde) (LLM — serbest metin)

    Parametreler
    ------------
    mail         : RawMail ornegi (ekler alani kontrol edilir)
    parser_role  : ParserRole ornegi (metin parse icin; ek varsa cagrilmaz)
    persist_root : ZIP-STL yolu icin STL'lerin yazilacagi kok dizin (None=tempdir)

    Dondurur
    --------
    dict | None — SCENARIO siparis formatiyla uyumlu dict:
      {order_id, customer, deadline, priority_class, parts, parse_source}
      parse_source: "attachment_zip_stl" | "attachment_excel" | "attachment_csv" | "llm_text"
      None: parse basarisiz / eslesme yok
    """
    from src.runtime.order_attachment_parser import parse_order_attachment

    # --- En yuksek oncelik: ZIP-STL eki ---
    zip_att = _find_attachment(mail, _ZIP_EXTENSIONS)
    if zip_att is not None:
        # parser_role: deterministik adet cikarimi tam kapsayamazsa
        # topraklanmis LLM fallback icin (bkz. _ingest_zip_stl_order).
        return _ingest_zip_stl_order(mail, zip_att, persist_root, parser_role)

    # Yapılandırılmış ek kontrolu
    structured_att = _find_attachment(mail, _STRUCTURED_EXTENSIONS)

    if structured_att is not None:
        # --- Deterministik yol: Excel/CSV ---
        ext = "." + structured_att.dosya_adi.rsplit(".", 1)[-1].lower()
        parts = parse_order_attachment(structured_att.dosya_adi, structured_att.icerik)
        source_tag = "attachment_excel" if ext in (".xlsx", ".xls", ".xlsm") else "attachment_csv"
        # Fix-7: deterministik order_id — uuid4 yerine sha256(message_id + dosya_adi)
        _det_raw = (mail.message_id + structured_att.dosya_adi).encode("utf-8")
        _det_hex = hashlib.sha256(_det_raw).hexdigest()[:8].upper()
        if not parts:
            # FIX 1: parca uretilemedi = KALICI-YAPISAL hata (taninmayan baslik /
            # bos dosya / desteklenmeyen icerik). ZIP-STL 'skipped_no_qty' yolu ile
            # SIMETRIK: sessizce parts=[] dondurup pipeline'i "Gecerli siparis yok"
            # ile patlatma. Poller bunu GECICI hata sanip mark_processed CAGIRMAZ
            # -> ayni mail her turda sonsuza yeniden islenir (veri kaybi, operatore
            # gorunmez). needs_review ile isaretle: mail mark_processed ile KAPANIR
            # + pending_store/operator gorunurlugune duser (adet-gir sayfasi).
            logger.warning(
                "ingest_order: ek parse edildi ama parca listesi bos "
                "(kalici-yapisal hata) — operator incelemesine alindi: %s",
                structured_att.dosya_adi,
            )
            return {
                "needs_review": True,
                "review_reason": "attachment_unparseable",
                "order_id": f"ATT-{_det_hex}",
                "customer": mail.gonderen.split("@")[-1].split(".")[0].upper(),
                "parse_source": source_tag + "_incomplete",
                "stl_names": [],
                "_stl_map": {},
                "parts": [],
            }
        return {
            "order_id": f"ATT-{_det_hex}",
            "customer": mail.gonderen.split("@")[-1].split(".")[0].upper(),
            "deadline": "",
            "priority_class": 2,
            "parts": parts,
            "parse_source": source_tag,
        }

    # --- LLM yolu: serbest metin ---
    # KAPI: ek yok; govdede siparis sinyali (adet/boyut deseni) yoksa LLM'e
    # SOKMA. Sinyalsiz mail (reklam/kisisel/bildirim) LLM'e gidince model
    # parca uydurur (sahte siparis). parser_role None ise zaten LLM yok.
    if parser_role is None or not _has_order_signal(mail.govde or ""):
        logger.info(
            "ingest_order: siparis sinyali yok (adet/boyut deseni) — LLM atlandi: %s",
            mail.gonderen,
        )
        return None

    parse_result = parser_role.parse(mail.govde)
    if parse_result is None:
        return None

    # injection_suphesi kontrolu — fail-closed: karantinaya al, pipeline'a sokma
    injection = False
    if hasattr(parse_result, "injection_suphesi"):
        injection = bool(parse_result.injection_suphesi)
    if injection:
        logger.warning(
            "ingest_order: injection_suphesi=True — siparis karantinaya alindi, "
            "pipeline'a sokulmadi. gonderen=%r",
            mail.gonderen,
        )
        return None

    # ParserResult veya dogrudan dict kontrolu
    if hasattr(parse_result, "order_dict"):
        order = parse_result.order_dict
    else:
        order = parse_result  # mock veya dict

    if order is None:
        return None

    if isinstance(order, dict):
        order = dict(order)
        order["parse_source"] = "llm_text"
    return order


# ---------------------------------------------------------------------------
# Fabrika — provider preset tablosu
# ---------------------------------------------------------------------------

_PROVIDER_PRESETS: Dict[str, Dict[str, Any]] = {
    "gmail": {
        "host": "imap.gmail.com",
        "port": 993,
        "use_ssl": True,
    },
    "outlook": {
        "host": "outlook.office365.com",
        "port": 993,
        "use_ssl": True,
    },
    "hotmail": {
        "host": "outlook.office365.com",
        "port": 993,
        "use_ssl": True,
    },
}

_VALID_PROVIDERS = frozenset(_PROVIDER_PRESETS.keys())


def make_mail_source(config: Dict[str, Any], *, idem_store: Optional[Any] = None) -> MailSource:
    """Konfig sozlugundan uygun MailSource ornegi olusturur.

    Parametreler
    ------------
    config : Asagidaki bicimlerden biri kabul edilir:

      {"source": "fake"}
          -> FakeMailbox (demo, kimlik gerekmez)

      {"source": "imap", "host": ..., "user": ..., "password": ...}
          -> ImapMailbox (geriye uyum — host elle verilir)

      {"provider": "gmail"|"outlook"|"hotmail", "user": ..., "password": ...}
          -> ImapMailbox; host/port/use_ssl preset'ten doldurulur.
            config'te acikca host verilmisse preset'i EZER (override).
            user + password yine config'ten gelir (preset doldurmaz).

      {} (ne source ne provider)
          -> FakeMailbox (varsayilan geriye uyum)

    idem_store : Opsiyonel paylasilmis IdempotencyStore. Verilirse ImapMailbox'a
        iletilir; poller turlar arasi idempotency state'ini paylasir. None ise
        ImapMailbox kendi :memory: store'unu olusturur (geriye uyum).
        FakeMailbox bu parametreyi yoksayar.

    Firlatir
    --------
    ValueError : Bilinmeyen source veya bilinmeyen provider degeri
    """
    provider = config.get("provider")

    if provider is not None:
        # Provider yolu
        if provider not in _VALID_PROVIDERS:
            raise ValueError(
                f"Bilinmeyen mail provider: {provider!r}. "
                f"Gecerli degerler: {sorted(_VALID_PROVIDERS)}."
            )
        preset = _PROVIDER_PRESETS[provider]
        # Preset ile baslayan sonra config'teki acik degerler ezer (override)
        resolved: Dict[str, Any] = {**preset, **config}
        # "provider" anahtari KORUNUR — ImapMailbox provider'a gore Gmail X-GM-RAW
        # kategori/ek filtresini tetikler (eskiden pop ediliyordu -> Gmail filtresi calismyordu).
        resolved["provider"] = provider
        # source acikca verilmediyse "imap" sayilir
        resolved.setdefault("source", "imap")
        return ImapMailbox(resolved, idem_store=idem_store)

    # Klasik source yolu
    source = config.get("source", "fake")
    if source == "fake":
        return FakeMailbox()
    if source == "imap":
        return ImapMailbox(config, idem_store=idem_store)
    raise ValueError(
        f"Bilinmeyen mail source: {source!r}. "
        f"Gecerli degerler: 'fake', 'imap'."
    )
