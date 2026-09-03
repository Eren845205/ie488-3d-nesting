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


def test_adet_gir_sifir_sonucta_pending_korunur(client, app, monkeypatch):
    """R1 #1 (CRITICAL): nesting sonuc uretemezse bekleyen kayit + STL'ler
    SILINMEZ; operator ?hata=nesting ile bilgilendirilir, gecmise hata duser."""
    import scripts.demo_pipeline as dp

    store = _seed(app, order_id="ZIP-TESTF1")

    def _fail(scenario):
        return {"nesting_results": {"B001": {"height_mm": 0.0,
                                             "note": "Tuner hatasi: voxel bos"}},
                "ranked_orders": [], "batches": [1], "pricing_results": {},
                "elapsed_sec": 1.0}

    monkeypatch.setattr(dp, "run_pipeline", _fail)
    resp = client.post(
        "/adet-gir/ZIP-TESTF1",
        data={"qty_braket": "2", "qty_kapak": "3"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "hata=nesting" in resp.headers.get("Location", "")
    # Bekleyen kayit KORUNDU (veri imhasi yok — yeniden denenebilir)
    assert store.get("ZIP-TESTF1") is not None
    # Gecmise hata kaydi dustu (gorunurluk)
    kayitlar = app.config["OTONOM_GECMIS"].liste()
    assert kayitlar
    assert kayitlar[0]["durum"] == "hata"
    assert kayitlar[0]["kaynak"] == "manuel"
    assert "Tuner hatasi" in kayitlar[0]["hata_ozeti"]


def test_adet_gir_basarida_gecmise_yazar(client, app):
    """R1 #5: basarili adet-girisi de denetim izine (gecmis) duser."""
    _seed(app, order_id="ZIP-TESTOK")
    client.post("/adet-gir/ZIP-TESTOK",
                data={"qty_braket": "2", "qty_kapak": "3"})
    kayitlar = app.config["OTONOM_GECMIS"].liste()
    assert any(k["kaynak"] == "manuel" and k["durum"] == "bitti"
               for k in kayitlar)


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


# ---------------------------------------------------------------------------
# Guvenlik: path traversal (FIX 1) — ham order_id ile disari yazim engellenir.
# ---------------------------------------------------------------------------

def test_adet_gir_path_traversal_disari_yazamaz(client, app, tmp_path=None):
    """store.get() _safe_id ile 'ZIP-TEST01'e cozulur (Windows'ta basename()
    backslash'i ayirir) ama ham order_id backslash icerir; sanitize edilmis
    deger route'a geri donmezse _persist_dir proje kokunun disina (data/evil)
    tasar. Fix sonrasi: dizin yalniz data/mail_stl altinda olusmali, disariya
    HICBIR dosya yazilmamali."""
    from src.webapp.app import _ROOT

    _seed(app, order_id="ZIP-TEST01")
    evil_dir = _ROOT / "data" / "evil"
    assert not evil_dir.exists(), "test oncesi kalinti data/evil olmamali"

    malicious = "..\\..\\..\\evil\\ZIP-TEST01"
    try:
        resp = client.post(f"/adet-gir/{malicious}", data={"qty_braket": "2", "qty_kapak": "1"})
        assert resp.status_code == 302
        assert not evil_dir.exists(), (
            "path traversal: dosyalar data/mail_stl DISINA yazildi (data/evil)"
        )
    finally:
        import shutil
        if evil_dir.exists():
            shutil.rmtree(evil_dir, ignore_errors=True)


def test_adet_gir_auto_family_routing_bayragi_true(client, app, monkeypatch):
    """F5 asama-2 rollout (2026-07-05): adet-gir yolu da auto_family_routing
    True gecirmeli (poller/manuel/otonom ile tutarli — fiilen hep auto)."""
    import scripts.demo_pipeline as dp

    seen = {}

    def _capture(scenario):
        seen["scenario"] = scenario
        return {"nesting_results": {"B001": {"height_mm": 42.0}},
                "ranked_orders": [], "batches": [1], "pricing_results": {}}

    monkeypatch.setattr(dp, "run_pipeline", _capture)
    _seen = _seed(app, order_id="ZIP-TESTAFR")
    resp = client.post(
        "/adet-gir/ZIP-TESTAFR",
        data={"qty_braket": "2", "qty_kapak": "3"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert seen["scenario"].get("auto_family_routing") is True


def test_adet_gir_path_traversal_mail_stl_icinde_kalir(client, app):
    """Zararsiz/normal order_id icin dizin gercekten data/mail_stl altinda
    olusturulmaya devam eder (regresyon: fix normal akisi kirmasin)."""
    from src.webapp.app import _ROOT

    _seed(app, order_id="ZIP-TEST01")
    persist_dir = _ROOT / "data" / "mail_stl" / "adetgir_ZIP-TEST01"
    try:
        resp = client.post("/adet-gir/ZIP-TEST01", data={"qty_braket": "2", "qty_kapak": "1"})
        assert resp.status_code == 302
        assert "/sonuc" in resp.headers.get("Location", "")
        assert persist_dir.exists()
        assert persist_dir.resolve().is_relative_to((_ROOT / "data" / "mail_stl").resolve())
    finally:
        import shutil
        if persist_dir.exists():
            shutil.rmtree(persist_dir, ignore_errors=True)
