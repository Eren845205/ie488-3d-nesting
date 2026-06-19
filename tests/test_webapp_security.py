"""tests/test_webapp_security.py — Uygulama geneli CSRF + admin oturum testleri.

NOT: Bu testler testing=False ile kurar (CSRF/auth yalniz uretim modunda aktif;
testing=True'da mevcut testleri kirmamak icin atlanir). llm_enabled=False —
deterministik uclar (mail-ayar, oncelik, run) yeterli.
"""

import pytest

from src.webapp.app import create_app


def _client(monkeypatch, admin=None):
    if admin is None:
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_PASSWORD", admin)
    app = create_app(testing=False, llm_enabled=False)
    return app.test_client()


def _csrf(client, path="/"):
    """Oturum cookie'sini kur ve CSRF token'ini dondur."""
    client.get(path)
    with client.session_transaction() as s:
        return s["_csrf"]


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

def test_csrf_tokensiz_post_reddedilir(monkeypatch):
    c = _client(monkeypatch)
    r = c.post("/mail-ayar", data={"provider": "fake"})
    assert r.status_code == 403


def test_csrf_yanlis_token_reddedilir(monkeypatch):
    c = _client(monkeypatch)
    _csrf(c)
    r = c.post("/mail-ayar", data={"provider": "fake", "_csrf": "yanlis-token"})
    assert r.status_code == 403


def test_csrf_dogru_token_form_gecer(monkeypatch):
    # /mail-ayar/test yazmaz (gercek configs'i kirletmez); form-field _csrf yolu
    c = _client(monkeypatch)
    tok = _csrf(c, "/mail-ayar")
    r = c.post("/mail-ayar/test", data={"provider": "fake", "_csrf": tok})
    assert r.status_code == 200


def test_csrf_header_ile_gecer(monkeypatch):
    c = _client(monkeypatch)
    tok = _csrf(c, "/mail-ayar")
    r = c.post("/mail-ayar/test", data={"provider": "fake"},
               headers={"X-CSRF-Token": tok})
    assert r.status_code == 200


def test_health_csrf_disinda(monkeypatch):
    c = _client(monkeypatch, admin="gizli")
    assert c.get("/health").status_code == 200  # auth+csrf muaf


# ---------------------------------------------------------------------------
# Admin oturum
# ---------------------------------------------------------------------------

def test_admin_bossa_login_devre_disi(monkeypatch):
    c = _client(monkeypatch)  # ADMIN_PASSWORD yok
    assert c.get("/oncelik").status_code == 200  # serbest


def test_admin_set_ise_korumali_get_giris_yonlendirir(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    r = c.get("/oncelik")
    assert r.status_code == 302
    assert "/giris" in r.headers["Location"]


def test_admin_set_ise_korumali_post_401(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    tok = _csrf(c, "/giris")
    # CSRF dogru ama oturum yok -> 401 (auth, csrf'ten once). Yazmayan uc.
    r = c.post("/mail-ayar/test", data={"provider": "fake", "_csrf": tok})
    assert r.status_code == 401


def test_login_dogru_parola_erisim_acar(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    tok = _csrf(c, "/giris")
    r = c.post("/giris", data={"password": "gizli123", "_csrf": tok})
    assert r.status_code == 302
    assert c.get("/oncelik").status_code == 200  # artik erisilebilir


def test_login_yanlis_parola_reddedilir(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    tok = _csrf(c, "/giris")
    r = c.post("/giris", data={"password": "yanlis", "_csrf": tok})
    assert "yanl" in r.get_data(as_text=True).lower()
    assert c.get("/oncelik").status_code == 302  # hala kapali


def test_cikis_oturumu_kapatir(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    tok = _csrf(c, "/giris")
    c.post("/giris", data={"password": "gizli123", "_csrf": tok})
    assert c.get("/oncelik").status_code == 200
    c.get("/cikis")
    assert c.get("/oncelik").status_code == 302  # tekrar kapali


def test_turkce_unicode_parola_kabul(monkeypatch):
    # compare_digest str non-ASCII'de TypeError verir; bytes karsilastirma sart
    c = _client(monkeypatch, admin="Şifrем-çığ-123")
    tok = _csrf(c, "/giris")
    r = c.post("/giris", data={"password": "Şifrем-çığ-123", "_csrf": tok})
    assert r.status_code == 302
    assert c.get("/oncelik").status_code == 200


def test_acik_yonlendirme_korumasi(monkeypatch):
    c = _client(monkeypatch, admin="gizli123")
    tok = _csrf(c, "/giris")
    # next=//evil.com gibi disa yonlendirme engellenmeli
    r = c.post("/giris?next=//evil.com", data={"password": "gizli123", "_csrf": tok})
    assert r.status_code == 302
    assert "evil.com" not in r.headers["Location"]
