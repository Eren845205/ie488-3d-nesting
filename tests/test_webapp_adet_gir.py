"""tests/test_webapp_adet_gir.py — /adet-gir (eksik-bilgi siparis adet girisi).

Akis: PendingOrderStore'a bekleyen siparis seed -> GET /adet-gir gosterir ->
POST /adet-gir/<id> adetlerle pipeline kosar, kaydi temizler, /sonuc'a yonlendirir.
"""

import io
import zipfile

import pytest

trimesh = pytest.importorskip("trimesh")

from src.webapp.app import create_app


def _stl_bytes(extents=(40, 30, 15)):
    return trimesh.creation.box(extents=extents).export(file_type="stl")


@pytest.fixture
def app():
    return create_app(testing=True, llm_enabled=False)


@pytest.fixture
def client(app):
    return app.test_client()


def _seed(app, order_id="ZIP-TEST01"):
    store = app.config["PENDING_STORE"]
    store.add(
        order_id=order_id,
        customer="FORD",
        sender="uretim@ford.com.tr",
        deadline="2026-07-01",
        priority_class=1,
        konu="Plan siparisi",
        stl_map={"braket": _stl_bytes((40, 30, 15)),
                 "kapak": _stl_bytes((60, 40, 10))},
    )
    return store


# ---------------------------------------------------------------------------

def test_adet_gir_route_exists(client):
    assert client.get("/adet-gir").status_code == 200


def test_adet_gir_bos_liste(client):
    """Bekleyen yokken sayfa 200 + 'bekleyen ... yok' mesaji."""
    html = client.get("/adet-gir").data.decode("utf-8", errors="replace")
    assert "yok" in html.lower()


def test_adet_gir_bekleyeni_listeler(client, app):
    _seed(app)
    html = client.get("/adet-gir").data.decode("utf-8", errors="replace")
    assert "FORD" in html
    assert "braket" in html
    assert "kapak" in html
    # her STL icin adet input alani olmali
    assert 'name="qty_braket"' in html
    assert 'name="qty_kapak"' in html


def test_adet_gir_isle_pipeline_kosar_ve_temizler(client, app):
    store = _seed(app)
    resp = client.post(
        "/adet-gir/ZIP-TEST01",
        data={"qty_braket": "2", "qty_kapak": "3"},
        follow_redirects=False,
    )
    # basari -> /sonuc'a yonlendir
    assert resp.status_code == 302
    assert "/sonuc" in resp.headers.get("Location", "")
    # bekleyen kayit temizlendi
    assert store.get("ZIP-TEST01") is None
    # LAST_RESULT yazildi (pipeline kostu)
    assert app.config["LAST_RESULT"] is not None
    # /sonuc artik 200
    assert client.get("/sonuc").status_code == 200


def test_adet_gir_isle_kismi_adet(client, app):
    """Bir parcaya 0/bos adet -> o parca dahil edilmez, digeri islenir."""
    store = _seed(app)
    resp = client.post(
        "/adet-gir/ZIP-TEST01",
        data={"qty_braket": "5", "qty_kapak": "0"},
    )
    assert resp.status_code == 302
    assert "/sonuc" in resp.headers.get("Location", "")
    assert store.get("ZIP-TEST01") is None


def test_adet_gir_isle_hic_adet_yok_hata(client, app):
    """Hicbir adet girilmezse -> hata=adet_yok ile geri doner, kayit KALIR."""
    store = _seed(app)
    resp = client.post(
        "/adet-gir/ZIP-TEST01",
        data={"qty_braket": "", "qty_kapak": "0"},
    )
    assert resp.status_code == 302
    assert "hata=adet_yok" in resp.headers.get("Location", "")
    assert store.get("ZIP-TEST01") is not None  # islenmediginden durur


def test_adet_gir_isle_bulunamayan_id(client):
    resp = client.post("/adet-gir/YOK-123", data={"qty_x": "1"})
    assert resp.status_code == 302
    assert "hata=bulunamadi" in resp.headers.get("Location", "")
