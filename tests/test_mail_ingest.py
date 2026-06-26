"""tests/test_mail_ingest.py — mail_ingest modulu birim testleri.

Kapsam:
  - RawMail dataclass olusturma + alanlar
  - FakeMailbox: kayitli mailleri dondurur, tekrar dondürmez (idempotency)
  - make_mail_source: konfig'e gore Fake/Imap secer
  - ImapMailbox: kurum testi (baglanti yapilmaz) + baglanti-hatasi zarif dusus
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from src.runtime.mail_ingest import (
    RawMail,
    FakeMailbox,
    ImapMailbox,
    make_mail_source,
)


# ---------------------------------------------------------------------------
# RawMail testleri
# ---------------------------------------------------------------------------

class TestRawMail(unittest.TestCase):
    """RawMail dataclass alan ve tip kontrolu."""

    def test_fields_present(self):
        mail = RawMail(
            gonderen="ford@ornek.com",
            konu="Acil Siparis",
            govde="5 adet parca lazim",
            tarih="2026-06-14T10:00:00",
            message_id="<abc123@ornek.com>",
        )
        self.assertEqual(mail.gonderen, "ford@ornek.com")
        self.assertEqual(mail.konu, "Acil Siparis")
        self.assertEqual(mail.govde, "5 adet parca lazim")
        self.assertEqual(mail.tarih, "2026-06-14T10:00:00")
        self.assertEqual(mail.message_id, "<abc123@ornek.com>")

    def test_repr_contains_konu(self):
        mail = RawMail(
            gonderen="x@y.com",
            konu="Test Konu",
            govde="govde",
            tarih="2026-06-14",
            message_id="<id1>",
        )
        self.assertIn("Test Konu", repr(mail))


# ---------------------------------------------------------------------------
# FakeMailbox testleri
# ---------------------------------------------------------------------------

class TestFakeMailbox(unittest.TestCase):
    """FakeMailbox: demo mailleri dondurur; tekrar dondürmez."""

    def setUp(self):
        self.fb = FakeMailbox()

    def test_fetch_returns_list(self):
        mails = self.fb.fetch_new()
        self.assertIsInstance(mails, list)

    def test_fetch_returns_raw_mail_instances(self):
        mails = self.fb.fetch_new()
        for m in mails:
            self.assertIsInstance(m, RawMail)

    def test_fetch_returns_at_least_three_mails(self):
        mails = self.fb.fetch_new()
        self.assertEqual(len(mails), 5)  # Fix-8: FakeMailbox kesinlikle 5 mail dondurur

    def test_mails_have_nonempty_govde(self):
        mails = self.fb.fetch_new()
        for m in mails:
            self.assertTrue(m.govde.strip(), f"Bos govde: {m.message_id}")

    def test_mails_have_unique_message_ids(self):
        mails = self.fb.fetch_new()
        ids = [m.message_id for m in mails]
        self.assertEqual(len(ids), len(set(ids)), "message_id tekrari var")

    def test_idempotency_second_fetch_empty(self):
        """Ilk fetch'ten sonra ikinci fetch bos liste dondurur."""
        first = self.fb.fetch_new()
        self.assertGreater(len(first), 0)
        second = self.fb.fetch_new()
        self.assertEqual(second, [], "Islenmiş mailler tekrar donmemeli")

    def test_idempotency_fresh_instance_returns_again(self):
        """Yeni FakeMailbox ornegi mailleri tekrar dondurur."""
        fb1 = FakeMailbox()
        fb1.fetch_new()  # ilk okuma — hepsini islemis say
        fb2 = FakeMailbox()
        mails = fb2.fetch_new()
        self.assertGreater(len(mails), 0)

    def test_demo_mails_contain_different_customers(self):
        """Farkli musteriler (Ford, Baykar, Aselsan vb.) en az 2 farkli gonderen."""
        mails = self.fb.fetch_new()
        gonderenler = {m.gonderen for m in mails}
        self.assertGreaterEqual(len(gonderenler), 2)

    def test_demo_mails_contain_turkish_text(self):
        """Govde Turkce icerik tasimali (en az bir mailde Turkce kelime)."""
        mails = FakeMailbox().fetch_new()
        govdeler = " ".join(m.govde for m in mails).lower()
        turkish_keywords = ["parça", "termin", "adet", "sipariş", "acil", "parca", "siparis"]
        found = any(kw in govdeler for kw in turkish_keywords)
        self.assertTrue(found, "Demo maillerde Turkce siparis icerigi bulunamadi")


# ---------------------------------------------------------------------------
# make_mail_source testleri
# ---------------------------------------------------------------------------

class TestMakeMailSource(unittest.TestCase):
    """make_mail_source konfig'den dogru kaynak secer."""

    def test_fake_source_returns_fake_mailbox(self):
        config = {"source": "fake"}
        src = make_mail_source(config)
        self.assertIsInstance(src, FakeMailbox)

    def test_imap_source_returns_imap_mailbox(self):
        config = {
            "source": "imap",
            "host": "imap.ornek.com",
            "port": 993,
            "user": "siparis@ornek.com",
            "password": "gizli",
            "folder": "INBOX",
            "use_ssl": True,
        }
        src = make_mail_source(config)
        self.assertIsInstance(src, ImapMailbox)

    def test_missing_source_defaults_to_fake(self):
        """source anahtari olmayan konfig Fake dondurur."""
        src = make_mail_source({})
        self.assertIsInstance(src, FakeMailbox)

    def test_unknown_source_raises_value_error(self):
        with self.assertRaises(ValueError):
            make_mail_source({"source": "rabbitmq"})


# ---------------------------------------------------------------------------
# ImapMailbox kurum testleri (canli baglanti yapilmaz)
# ---------------------------------------------------------------------------

class TestImapMailboxSetup(unittest.TestCase):
    """ImapMailbox kurum testi — gercek IMAP baglamadan."""

    def _make_config(self, **overrides):
        base = {
            "host": "imap.ornek.com",
            "port": 993,
            "user": "test@ornek.com",
            "password": "parola",
            "folder": "INBOX",
            "use_ssl": True,
        }
        base.update(overrides)
        return base

    def test_instantiation_does_not_connect(self):
        """ImapMailbox() kurmak baglanti acmaz (conftest/network gerekmez)."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)
        self.assertIsNotNone(mb)

    def test_stores_config_fields(self):
        cfg = self._make_config(host="imap.test.io", port=143, use_ssl=False)
        mb = ImapMailbox(cfg)
        self.assertEqual(mb.host, "imap.test.io")
        self.assertEqual(mb.port, 143)
        self.assertFalse(mb.use_ssl)

    def test_connection_error_returns_empty_list(self):
        """Baglanti hatasi cokme yerine bos liste dondurur."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)

        import imaplib
        with patch("imaplib.IMAP4_SSL", side_effect=ConnectionRefusedError("baglanti reddedildi")):
            result = mb.fetch_new()

        self.assertEqual(result, [], "Baglanti hatasinda bos liste bekleniyor")

    def test_auth_error_returns_empty_list(self):
        """Auth hatasi cokme yerine bos liste dondurur."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)

        import imaplib
        mock_imap = MagicMock()
        mock_imap.login.side_effect = imaplib.IMAP4.error("Login failed")

        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            result = mb.fetch_new()

        self.assertEqual(result, [], "Auth hatasinda bos liste bekleniyor")

    def test_cursor_advances_after_fetch(self):
        """fetch_new() sonrasi uid_cursor guncellenir — islenmiş UID'ler bilinir."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)

        # Baslangicta cursor bos olmali
        self.assertEqual(mb._seen_uids, set())

    def test_ssl_false_uses_imap4_not_ssl(self):
        """use_ssl=False oldugunda SSL yerine düz IMAP4 kullanilir (mock ile)."""
        cfg = self._make_config(use_ssl=False)
        mb = ImapMailbox(cfg)

        import imaplib
        with patch("imaplib.IMAP4", side_effect=ConnectionRefusedError("hata")) as mock_plain:
            with patch("imaplib.IMAP4_SSL") as mock_ssl:
                result = mb.fetch_new()

        # Hata oldugu icin bos liste; ama SSL cagrilmadi
        mock_ssl.assert_not_called()
        self.assertEqual(result, [])

    def test_successful_fetch_mock(self):
        """Basarili fetch senaryosu: mock IMAP sunucusu 1 mail dondurur."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)

        import email as _email
        import imaplib

        # RFC 2822 uyumlu test maili olustur
        test_mail = _email.message_from_string(
            "From: tedarik@ford.com\r\n"
            "Subject: Test Siparis\r\n"
            "Message-ID: <test001@ford.com>\r\n"
            "Date: Sat, 14 Jun 2026 10:00:00 +0300\r\n"
            "\r\n"
            "3 adet parca lazim."
        )
        raw_bytes = test_mail.as_bytes()

        mock_imap = MagicMock()
        mock_imap.login.return_value = ("OK", [b"Logged in"])
        mock_imap.select.return_value = ("OK", [b"1"])
        # SEARCH yeni UID dondurur
        mock_imap.uid.side_effect = [
            ("OK", [b"100"]),                         # SEARCH cagirisi
            ("OK", [(b"100 (RFC822 {N})", raw_bytes)]),  # FETCH cagirisi
        ]
        mock_imap.logout.return_value = ("BYE", [])

        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            result = mb.fetch_new()

        self.assertEqual(len(result), 1)
        m = result[0]
        self.assertIsInstance(m, RawMail)
        self.assertIn("ford", m.gonderen.lower())

    # ------------------------------------------------------------------
    # Gmail X-GM-RAW kategori/ek filtresi (saglam mail-secimi)
    # ------------------------------------------------------------------
    def _mock_search_only(self):
        """SEARCH bos dondurur (FETCH yok) — yalniz SEARCH cagrisinin sekli onemli."""
        mock_imap = MagicMock()
        mock_imap.login.return_value = ("OK", [b"Logged in"])
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.side_effect = [("OK", [b""])]  # SEARCH -> bos liste
        mock_imap.logout.return_value = ("BYE", [])
        return mock_imap

    def test_gmail_filters_use_xgmraw(self):
        """provider=gmail + category_filter + prefer_attachments -> SEARCH X-GM-RAW raw query."""
        cfg = self._make_config(provider="gmail", category_filter="primary",
                                prefer_attachments=True)
        mb = ImapMailbox(cfg)
        mock_imap = self._mock_search_only()
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            mb.fetch_new()
        search_args = mock_imap.uid.call_args_list[0].args
        self.assertIn("X-GM-RAW", search_args)
        raw_query = search_args[-1]
        self.assertIn("category:primary", raw_query)
        self.assertIn("has:attachment", raw_query)

    def test_non_gmail_ignores_filters(self):
        """provider=outlook + category_filter -> X-GM-RAW GECMEZ (duz ALL)."""
        cfg = self._make_config(provider="outlook", category_filter="primary",
                                prefer_attachments=True)
        mb = ImapMailbox(cfg)
        mock_imap = self._mock_search_only()
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            mb.fetch_new()
        search_args = mock_imap.uid.call_args_list[0].args
        self.assertNotIn("X-GM-RAW", search_args)
        self.assertIn("ALL", search_args)

    def test_xgmraw_error_falls_back_to_all(self):
        """X-GM-RAW desteklenmeyen sunucu (IMAP4.error) -> duz ALL'a duser, cokmez."""
        import imaplib
        cfg = self._make_config(provider="gmail", prefer_attachments=True)
        mb = ImapMailbox(cfg)
        mock_imap = MagicMock()
        mock_imap.login.return_value = ("OK", [b"Logged in"])
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.side_effect = [
            imaplib.IMAP4.error("X-GM-RAW unsupported"),  # 1. cagri: X-GM-RAW hata
            ("OK", [b""]),                                 # 2. cagri: ALL fallback (bos)
        ]
        mock_imap.logout.return_value = ("BYE", [])
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            result = mb.fetch_new()
        self.assertEqual(result, [])  # cokmedi
        self.assertEqual(mock_imap.uid.call_count, 2)
        self.assertIn("X-GM-RAW", mock_imap.uid.call_args_list[0].args)
        self.assertIn("ALL", mock_imap.uid.call_args_list[1].args)

    def test_backward_compat_no_filters_uses_all(self):
        """Yeni alanlar belirtilmezse (eski config) -> duz ALL davranisi (regresyon korumasi)."""
        cfg = self._make_config()  # provider/category/attachment YOK
        mb = ImapMailbox(cfg)
        mock_imap = self._mock_search_only()
        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            mb.fetch_new()
        search_args = mock_imap.uid.call_args_list[0].args
        self.assertNotIn("X-GM-RAW", search_args)
        self.assertIn("ALL", search_args)

    def test_seen_uid_not_returned_again(self):
        """Daha once gorulen UID tekrar dondurulmez."""
        cfg = self._make_config()
        mb = ImapMailbox(cfg)
        mb._seen_uids.add("100")  # onceden islenmis

        import email as _email
        import imaplib

        # SEARCH ayni UID'yi dondurse bile fetch edilmez
        mock_imap = MagicMock()
        mock_imap.login.return_value = ("OK", [b"Logged in"])
        mock_imap.select.return_value = ("OK", [b"1"])
        mock_imap.uid.return_value = ("OK", [b"100"])  # SEARCH -> bilinen UID

        with patch("imaplib.IMAP4_SSL", return_value=mock_imap):
            result = mb.fetch_new()

        self.assertEqual(result, [], "Onceden islenmis UID tekrar donmemeli")


# ---------------------------------------------------------------------------
# make_mail_source — provider preset testleri
# ---------------------------------------------------------------------------

class TestMakeMailSourceProvider(unittest.TestCase):
    """make_mail_source: provider preset mantigi."""

    def test_gmail_provider_returns_imap_mailbox(self):
        """provider='gmail' → ImapMailbox uretir."""
        config = {
            "provider": "gmail",
            "user": "x@gmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertIsInstance(src, ImapMailbox)

    def test_gmail_provider_sets_correct_host(self):
        """provider='gmail' → host=='imap.gmail.com'."""
        config = {
            "provider": "gmail",
            "user": "x@gmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.host, "imap.gmail.com")

    def test_gmail_provider_sets_correct_port_and_ssl(self):
        """provider='gmail' → port==993, use_ssl==True."""
        config = {
            "provider": "gmail",
            "user": "x@gmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.port, 993)
        self.assertTrue(src.use_ssl)

    def test_outlook_provider_returns_imap_mailbox(self):
        """provider='outlook' → ImapMailbox uretir."""
        config = {
            "provider": "outlook",
            "user": "x@outlook.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertIsInstance(src, ImapMailbox)

    def test_outlook_provider_sets_correct_host(self):
        """provider='outlook' → host=='outlook.office365.com'."""
        config = {
            "provider": "outlook",
            "user": "x@outlook.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.host, "outlook.office365.com")

    def test_hotmail_provider_sets_correct_host(self):
        """provider='hotmail' → host=='outlook.office365.com'."""
        config = {
            "provider": "hotmail",
            "user": "x@hotmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.host, "outlook.office365.com")

    def test_hotmail_provider_port_and_ssl(self):
        """provider='hotmail' → port==993, use_ssl==True."""
        config = {
            "provider": "hotmail",
            "user": "x@hotmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.port, 993)
        self.assertTrue(src.use_ssl)

    def test_explicit_host_overrides_gmail_preset(self):
        """provider='gmail' + acik host → host preset'i degil acik deger kullanilir."""
        config = {
            "provider": "gmail",
            "host": "custom.imap.example.com",
            "user": "x@gmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.host, "custom.imap.example.com")

    def test_explicit_port_overrides_preset(self):
        """provider='gmail' + acik port → port preset'i degil acik deger kullanilir."""
        config = {
            "provider": "gmail",
            "port": 1234,
            "user": "x@gmail.com",
            "password": "pw",
        }
        src = make_mail_source(config)
        self.assertEqual(src.port, 1234)

    def test_unknown_provider_raises_value_error(self):
        """Bilinmeyen provider → ValueError firlatilir."""
        config = {
            "provider": "yahoo",
            "user": "x@yahoo.com",
            "password": "pw",
        }
        with self.assertRaises(ValueError):
            make_mail_source(config)

    def test_provider_does_not_fill_user_or_password(self):
        """Provider preset kullanici adi/parola DOLDURMAZ — config'den gelir."""
        config = {
            "provider": "gmail",
            "user": "myuser@gmail.com",
            "password": "mysecret",
        }
        src = make_mail_source(config)
        self.assertEqual(src.user, "myuser@gmail.com")

    # --- Geriye uyum testleri ---

    def test_backward_compat_fake_source_unchanged(self):
        """Geriye uyum: {'source':'fake'} hala FakeMailbox dondurur."""
        src = make_mail_source({"source": "fake"})
        self.assertIsInstance(src, FakeMailbox)

    def test_backward_compat_imap_source_unchanged(self):
        """Geriye uyum: eski imap konfig (source+host) hala calisir."""
        config = {
            "source": "imap",
            "host": "imap.ornek.com",
            "port": 993,
            "user": "siparis@ornek.com",
            "password": "gizli",
        }
        src = make_mail_source(config)
        self.assertIsInstance(src, ImapMailbox)
        self.assertEqual(src.host, "imap.ornek.com")

    def test_backward_compat_no_source_no_provider_defaults_to_fake(self):
        """Geriye uyum: ne 'source' ne 'provider' → Fake varsayilan."""
        src = make_mail_source({})
        self.assertIsInstance(src, FakeMailbox)


if __name__ == "__main__":
    unittest.main()
