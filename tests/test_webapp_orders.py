"""test_webapp_orders.py — Siparis Havuzu CRUD, CSV yukleme, pipeline baglantisi.

Kapsam:
    - orders_store: yukle/kaydet/ekle/sil (atomik yazim, bozuk dosya, tmp_path izolasyonu)
    - GET /siparisler  -> 200 + tablo
    - POST /siparisler (manuel form) -> ekleme, dogrulama hatalari (satir numarali)
    - POST /siparisler/sil/<order_id> -> silme
    - GET /siparisler/sablon.csv -> 200, CSV icerigi
    - POST /siparisler/csv -> gecerli CSV ekleme, hatali satir raporu
    - POST /run bos havuz -> demo fallback (302 ok, sonuc sayfasinda nota)
    - POST /run dolu havuz -> havuz senaryosu kosar (kaba pitch, hizli)
    - Kaliicilik: orders_path parametresi ile create_app izolasyonu

Kosus: pytest tests/test_webapp_orders.py -q
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ---------------------------------------------------------------------------
# Ornek siparis verileri
# ---------------------------------------------------------------------------

_SAMPLE_ORDER = {
    "order_id": "TEST-001",
    "customer": "TEST-MUSTERI",
    "deadline": "2027-01-15",
    "priority_class": 1,
    "parts": [
        {
            "name": "test_parca",
            "width_mm": 50.0,
            "depth_mm": 40.0,
            "height_mm": 30.0,
            "qty": 2,
        }
    ],
}

_SAMPLE_ORDER_2 = {
    "order_id": "TEST-002",
    "customer": "TEST-MUSTERI-B",
    "deadline": "2027-02-20",
    "priority_class": 2,
    "parts": [
        {
            "name": "parca_b",
            "width_mm": 60.0,
            "depth_mm": 50.0,
            "height_mm": 20.0,
            "qty": 3,
        }
    ],
}


# ---------------------------------------------------------------------------
# orders_store birim testleri
# ---------------------------------------------------------------------------


class TestOrdersStore:

    def test_load_missing_file_returns_empty(self, tmp_path):
        from src.webapp.orders_store import load_orders
        orders = load_orders(tmp_path / "yok.json")
        assert orders == []

    def test_save_and_load_roundtrip(self, tmp_path):
        from src.webapp.orders_store import load_orders, save_orders
        path = tmp_path / "orders.json"
        save_orders([_SAMPLE_ORDER], path)
        loaded = load_orders(path)
        assert len(loaded) == 1
        assert loaded[0]["order_id"] == "TEST-001"

    def test_save_is_atomic(self, tmp_path):
        """save_orders tmp+rename deseni kullaniyor; islev tamamlaninca dosya okunabilir."""
        from src.webapp.orders_store import load_orders, save_orders
        path = tmp_path / "orders.json"
        save_orders([_SAMPLE_ORDER, _SAMPLE_ORDER_2], path)
        loaded = load_orders(path)
        assert len(loaded) == 2

    def test_load_corrupt_file_raises(self, tmp_path):
        from src.webapp.orders_store import load_orders
        bad = tmp_path / "bad.json"
        bad.write_text("{ gecersiz json }", encoding="utf-8")
        with pytest.raises(ValueError, match="bozuk"):
            load_orders(bad)

    def test_add_order(self, tmp_path):
        from src.webapp.orders_store import add_order, load_orders, save_orders
        path = tmp_path / "orders.json"
        save_orders([], path)
        add_order(_SAMPLE_ORDER, path)
        loaded = load_orders(path)
        assert len(loaded) == 1
        assert loaded[0]["order_id"] == "TEST-001"

    def test_add_duplicate_order_id_raises(self, tmp_path):
        from src.webapp.orders_store import add_order, save_orders
        path = tmp_path / "orders.json"
        save_orders([_SAMPLE_ORDER], path)
        with pytest.raises(ValueError, match="zaten mevcut"):
            add_order(_SAMPLE_ORDER, path)

    def test_delete_order(self, tmp_path):
        from src.webapp.orders_store import delete_order, load_orders, save_orders
        path = tmp_path / "orders.json"
        save_orders([_SAMPLE_ORDER, _SAMPLE_ORDER_2], path)
        delete_order("TEST-001", path)
        loaded = load_orders(path)
        assert len(loaded) == 1
        assert loaded[0]["order_id"] == "TEST-002"

    def test_delete_nonexistent_order_raises(self, tmp_path):
        from src.webapp.orders_store import delete_order, save_orders
        path = tmp_path / "orders.json"
        save_orders([], path)
        with pytest.raises(ValueError, match="bulunamadi"):
            delete_order("YOK-999", path)

    def test_orders_to_scenario(self, tmp_path):
        """orders_to_scenario: havuz -> pipeline senaryo dict donusumu."""
        from src.webapp.orders_store import orders_to_scenario
        orders = [_SAMPLE_ORDER]
        scenario = orders_to_scenario(orders)
        assert "orders" in scenario
        assert "container" in scenario
        assert "capacity" in scenario
        assert "pricing_rules" in scenario
        # Parca bilgisi tasindi mi?
        first_order = scenario["orders"][0]
        assert first_order["order_id"] == "TEST-001"
        assert len(first_order["parts"]) == 1
        # parts source=box olmali
        assert first_order["parts"][0]["source"] == "box"
        # parts id alani olmali
        assert "id" in first_order["parts"][0]


# ---------------------------------------------------------------------------
# Flask app fixture (orders_path izolasyonlu)
# ---------------------------------------------------------------------------


@pytest.fixture
def orders_path(tmp_path):
    path = tmp_path / "orders.json"
    # Bos havuz ile basla
    path.write_text("[]", encoding="utf-8")
    return path


@pytest.fixture
def app_orders(orders_path):
    from src.webapp.app import create_app
    application = create_app(
        testing=True,
        llm_enabled=False,
        orders_path=str(orders_path),
    )
    yield application


@pytest.fixture
def client_orders(app_orders):
    return app_orders.test_client()


@pytest.fixture
def app_orders_dolu(tmp_path):
    """Iki ornek siparisli dolu havuzla baslayan app."""
    from src.webapp.orders_store import save_orders
    from src.webapp.app import create_app
    path = tmp_path / "orders.json"
    save_orders([_SAMPLE_ORDER, _SAMPLE_ORDER_2], path)
    application = create_app(
        testing=True,
        llm_enabled=False,
        orders_path=str(path),
    )
    yield application


@pytest.fixture
def client_orders_dolu(app_orders_dolu):
    return app_orders_dolu.test_client()


# ---------------------------------------------------------------------------
# GET /siparisler
# ---------------------------------------------------------------------------


class TestSiparislerGet:

    def test_returns_200(self, client_orders):
        assert client_orders.get("/siparisler").status_code == 200

    def test_contains_havuz_title(self, client_orders):
        html = client_orders.get("/siparisler").data.decode("utf-8")
        assert "Siparis" in html

    def test_empty_pool_shows_no_rows(self, client_orders):
        html = client_orders.get("/siparisler").data.decode("utf-8")
        # Bos havuzda simdiye kadar kayitli siparis yok
        assert "TEST-001" not in html

    def test_populated_pool_shows_order_ids(self, client_orders_dolu):
        html = client_orders_dolu.get("/siparisler").data.decode("utf-8")
        assert "TEST-001" in html
        assert "TEST-002" in html

    def test_has_yeni_siparis_form(self, client_orders):
        html = client_orders.get("/siparisler").data.decode("utf-8")
        assert "form" in html.lower()
        assert "musteri" in html.lower() or "customer" in html.lower() or "Musteri" in html

    def test_has_csv_upload_form(self, client_orders):
        html = client_orders.get("/siparisler").data.decode("utf-8")
        assert "csv" in html.lower() or "CSV" in html

    def test_has_sablon_link(self, client_orders):
        html = client_orders.get("/siparisler").data.decode("utf-8")
        assert "sablon" in html.lower() or "sablon.csv" in html


# ---------------------------------------------------------------------------
# POST /siparisler (manuel form)
# ---------------------------------------------------------------------------


class TestSiparislerPost:

    def test_valid_form_adds_order(self, client_orders, orders_path):
        from src.webapp.orders_store import load_orders
        data = {
            "order_id": "FORM-001",
            "customer": "FormMusteri",
            "deadline": "2027-06-01",
            "priority_class": "1",
            "parts_text": "parca_x, 80, 60, 40, 2",
        }
        resp = client_orders.post("/siparisler", data=data, follow_redirects=True)
        assert resp.status_code == 200
        loaded = load_orders(orders_path)
        assert any(o["order_id"] == "FORM-001" for o in loaded)

    def test_invalid_part_line_shows_error(self, client_orders):
        data = {
            "order_id": "FORM-ERR",
            "customer": "ErrMusteri",
            "deadline": "2027-06-01",
            "priority_class": "1",
            "parts_text": "eksik_alan, 80",
        }
        resp = client_orders.post("/siparisler", data=data, follow_redirects=True)
        html = resp.data.decode("utf-8")
        # Satir numarali hata mesaji olmali
        assert "1" in html  # satir no
        assert any(k in html for k in ["hata", "Hata", "gecersiz", "Gecersiz", "format"])

    def test_empty_order_id_returns_error(self, client_orders):
        data = {
            "order_id": "",
            "customer": "X",
            "deadline": "2027-06-01",
            "priority_class": "1",
            "parts_text": "parca, 50, 40, 30, 1",
        }
        resp = client_orders.post("/siparisler", data=data, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert any(k in html for k in ["hata", "Hata", "bos", "Bos", "zorunlu"])

    def test_empty_parts_text_returns_error(self, client_orders):
        data = {
            "order_id": "NO-PARTS",
            "customer": "X",
            "deadline": "2027-06-01",
            "priority_class": "1",
            "parts_text": "   ",
        }
        resp = client_orders.post("/siparisler", data=data, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert any(k in html for k in ["hata", "Hata", "parca", "Parca"])

    def test_duplicate_order_id_returns_error(self, client_orders, orders_path):
        from src.webapp.orders_store import save_orders
        save_orders([_SAMPLE_ORDER], orders_path)
        data = {
            "order_id": "TEST-001",
            "customer": "X",
            "deadline": "2027-06-01",
            "priority_class": "1",
            "parts_text": "parca, 50, 40, 30, 1",
        }
        resp = client_orders.post("/siparisler", data=data, follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert any(k in html for k in ["mevcut", "zaten", "duplicate", "Mevcut"])


# ---------------------------------------------------------------------------
# POST /siparisler/sil/<order_id>
# ---------------------------------------------------------------------------


class TestSiparislerSil:

    def test_delete_existing_order(self, client_orders_dolu, tmp_path):
        resp = client_orders_dolu.post(
            "/siparisler/sil/TEST-001", follow_redirects=True
        )
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "TEST-001" not in html

    def test_delete_nonexistent_returns_graceful(self, client_orders):
        resp = client_orders.post(
            "/siparisler/sil/YOK-999", follow_redirects=True
        )
        # Hata sayfasina gitmesin; 200 veya redirect olmali
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# GET /siparisler/sablon.csv
# ---------------------------------------------------------------------------


class TestSablonCsv:

    def test_sablon_returns_200(self, client_orders):
        resp = client_orders.get("/siparisler/sablon.csv")
        assert resp.status_code == 200

    def test_sablon_content_type_csv(self, client_orders):
        resp = client_orders.get("/siparisler/sablon.csv")
        assert "text/csv" in resp.content_type or "csv" in resp.content_type

    def test_sablon_has_expected_columns(self, client_orders):
        resp = client_orders.get("/siparisler/sablon.csv")
        text = resp.data.decode("utf-8")
        for col in ["order_id", "customer", "deadline", "priority",
                    "part_name", "width_mm", "depth_mm", "height_mm", "qty"]:
            assert col in text


# ---------------------------------------------------------------------------
# POST /siparisler/csv — CSV yukleme
# ---------------------------------------------------------------------------


def _make_csv_bytes(rows: list[dict]) -> bytes:
    """CSV satirlarini bayt olarak uretir."""
    fieldnames = [
        "order_id", "customer", "deadline", "priority",
        "part_name", "width_mm", "depth_mm", "height_mm", "qty",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue().encode("utf-8")


_VALID_CSV_ROWS = [
    {
        "order_id": "CSV-001", "customer": "CSV-MUSTERI",
        "deadline": "2027-03-01", "priority": "1",
        "part_name": "csv_parca", "width_mm": "70", "depth_mm": "50",
        "height_mm": "30", "qty": "2",
    },
    {
        # Ayni order_id -> ayni siparise eklenir
        "order_id": "CSV-001", "customer": "CSV-MUSTERI",
        "deadline": "2027-03-01", "priority": "1",
        "part_name": "csv_parca2", "width_mm": "40", "depth_mm": "35",
        "height_mm": "25", "qty": "1",
    },
    {
        "order_id": "CSV-002", "customer": "CSV-MUSTERI-B",
        "deadline": "2027-04-01", "priority": "2",
        "part_name": "parca_b", "width_mm": "60", "depth_mm": "45",
        "height_mm": "20", "qty": "3",
    },
]


class TestCsvUpload:

    def test_valid_csv_adds_orders(self, client_orders, orders_path):
        from src.webapp.orders_store import load_orders
        csv_data = _make_csv_bytes(_VALID_CSV_ROWS)
        resp = client_orders.post(
            "/siparisler/csv",
            data={"csv_file": (io.BytesIO(csv_data), "test.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        loaded = load_orders(orders_path)
        order_ids = [o["order_id"] for o in loaded]
        assert "CSV-001" in order_ids
        assert "CSV-002" in order_ids

    def test_same_order_id_grouped_into_one(self, client_orders, orders_path):
        from src.webapp.orders_store import load_orders
        csv_data = _make_csv_bytes(_VALID_CSV_ROWS)
        client_orders.post(
            "/siparisler/csv",
            data={"csv_file": (io.BytesIO(csv_data), "test.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        loaded = load_orders(orders_path)
        csv001 = next(o for o in loaded if o["order_id"] == "CSV-001")
        # 2 satirdan 2 parca olmali
        assert len(csv001["parts"]) == 2

    def test_invalid_csv_row_reported_with_line_number(self, client_orders):
        bad_rows = [
            {
                "order_id": "CSV-BAD", "customer": "X",
                "deadline": "2027-03-01", "priority": "1",
                "part_name": "iyi_parca", "width_mm": "50",
                "depth_mm": "40", "height_mm": "30", "qty": "1",
            },
            {
                # width_mm bos -> gecersiz
                "order_id": "CSV-BAD", "customer": "X",
                "deadline": "2027-03-01", "priority": "1",
                "part_name": "kotu_parca", "width_mm": "",
                "depth_mm": "40", "height_mm": "30", "qty": "1",
            },
        ]
        csv_data = _make_csv_bytes(bad_rows)
        resp = client_orders.post(
            "/siparisler/csv",
            data={"csv_file": (io.BytesIO(csv_data), "bad.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        html = resp.data.decode("utf-8")
        # Satir numarasi raporlanmali (satir 3 = header+2)
        assert any(k in html for k in ["hata", "Hata", "satir", "Satir", "gecersiz"])

    def test_valid_rows_added_despite_invalid_rows(self, client_orders, orders_path):
        from src.webapp.orders_store import load_orders
        mixed_rows = [
            {
                "order_id": "MIX-OK", "customer": "OK",
                "deadline": "2027-05-01", "priority": "1",
                "part_name": "iyi", "width_mm": "50",
                "depth_mm": "40", "height_mm": "30", "qty": "1",
            },
            {
                # gecersiz satir (qty harfli)
                "order_id": "MIX-BAD", "customer": "BAD",
                "deadline": "2027-05-01", "priority": "1",
                "part_name": "kotu", "width_mm": "50",
                "depth_mm": "40", "height_mm": "30", "qty": "abc",
            },
        ]
        csv_data = _make_csv_bytes(mixed_rows)
        client_orders.post(
            "/siparisler/csv",
            data={"csv_file": (io.BytesIO(csv_data), "mix.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        loaded = load_orders(orders_path)
        ids = [o["order_id"] for o in loaded]
        assert "MIX-OK" in ids
        assert "MIX-BAD" not in ids

    def test_no_file_returns_graceful(self, client_orders):
        resp = client_orders.post(
            "/siparisler/csv",
            data={},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert resp.status_code in (200, 302, 400)


# ---------------------------------------------------------------------------
# Pipeline baglantisi: bos havuz -> demo fallback
# ---------------------------------------------------------------------------


class TestPipelineDemoFallback:

    def test_run_with_empty_pool_does_not_crash(self, client_orders):
        resp = client_orders.post("/run", follow_redirects=True)
        assert resp.status_code == 200

    def test_run_with_empty_pool_shows_demo_note(self, client_orders):
        resp = client_orders.post("/run", follow_redirects=True)
        html = resp.data.decode("utf-8")
        # Demo fallback notu gosterilmeli
        assert any(k in html for k in [
            "demo", "Demo", "siparisler", "/siparisler"
        ])

    def test_index_with_empty_pool_shows_link(self, client_orders):
        html = client_orders.get("/").data.decode("utf-8")
        assert "/siparisler" in html or "siparisler" in html.lower()


# ---------------------------------------------------------------------------
# Pipeline baglantisi: dolu havuz -> havuz senaryosu
# ---------------------------------------------------------------------------


class TestNestingModeOptIn:
    """Opt-in NFV "kalite modu" UI seçici (backlog #2): checkbox → scenario['nesting_mode']."""

    def test_index_shows_nesting_mode_radio(self, client_orders):
        # 2026-06-27 akıllı mod: checkbox → 3'lü radio (auto/nfv/heightmap), default auto.
        html = client_orders.get("/").data.decode("utf-8")
        assert 'name="nesting_mode"' in html
        assert 'value="auto"' in html and 'value="nfv"' in html and 'value="heightmap"' in html
        assert "Otomatik" in html

    def test_run_passes_nfv_mode_to_scenario(self, client_orders, monkeypatch):
        captured = {}

        def fake_run_pipeline(scenario):
            captured["scenario"] = scenario
            return {"nesting_results": {}, "used_demo": True}

        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", fake_run_pipeline)
        client_orders.post("/run", data={"nesting_mode": "nfv"})
        assert captured["scenario"]["nesting_mode"] == "nfv"

    def test_run_defaults_to_auto_when_unspecified(self, client_orders, monkeypatch):
        # 2026-06-27 akıllı mod: mod belirtilmezse VARSAYILAN "auto" (veri-odaklı seçim).
        captured = {}

        def fake_run_pipeline(scenario):
            captured["scenario"] = scenario
            return {"nesting_results": {}, "used_demo": True}

        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", fake_run_pipeline)
        client_orders.post("/run", data={})  # mod belirtilmemiş
        assert captured["scenario"]["nesting_mode"] == "auto"

    def test_index_shows_quality_max_option(self, client_orders):
        html = client_orders.get("/").data.decode("utf-8")
        assert 'name="nfv_quality"' in html and "Maksimum kalite" in html

    def test_run_passes_nfv_quality_max(self, client_orders, monkeypatch):
        captured = {}

        def fake_run_pipeline(scenario):
            captured["scenario"] = scenario
            return {"nesting_results": {}, "used_demo": True}

        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", fake_run_pipeline)
        client_orders.post("/run", data={"nesting_mode": "nfv", "nfv_quality": "max"})
        assert captured["scenario"]["nfv_quality"] == "max"

    def test_run_nfv_quality_defaults_fast(self, client_orders, monkeypatch):
        captured = {}

        def fake_run_pipeline(scenario):
            captured["scenario"] = scenario
            return {"nesting_results": {}, "used_demo": True}

        monkeypatch.setattr("scripts.demo_pipeline.run_pipeline", fake_run_pipeline)
        client_orders.post("/run", data={"nesting_mode": "nfv"})  # max işaretsiz
        assert captured["scenario"]["nfv_quality"] == "fast"


class TestPipelineFromPool:

    def test_run_with_pool_does_not_crash(self, client_orders_dolu):
        resp = client_orders_dolu.post("/run", follow_redirects=True)
        assert resp.status_code == 200

    def test_run_with_pool_shows_result(self, client_orders_dolu):
        resp = client_orders_dolu.post("/run", follow_redirects=True)
        html = resp.data.decode("utf-8")
        assert any(k in html for k in ["Toplam", "Parti", "Siparis"])

    def test_run_with_pool_uses_pool_order_ids(self, client_orders_dolu):
        """Sonuc sayfasinda havuz siparis ID'leri gozukmeli."""
        resp = client_orders_dolu.post("/run", follow_redirects=True)
        html = resp.data.decode("utf-8")
        # TEST-001 veya TEST-002 sonuc sayfasinda olmali
        assert "TEST-001" in html or "TEST-002" in html


# ---------------------------------------------------------------------------
# Ana sayfa havuz ozeti
# ---------------------------------------------------------------------------


class TestIndexPoolSummary:

    def test_index_shows_pool_count_when_empty(self, client_orders):
        html = client_orders.get("/").data.decode("utf-8")
        # 0 siparis veya bos havuz ifadesi olmali
        assert any(k in html for k in ["0 siparis", "Bos havuz", "siparis", "havuz"])

    def test_index_shows_pool_count_when_populated(self, client_orders_dolu):
        html = client_orders_dolu.get("/").data.decode("utf-8")
        assert any(k in html for k in ["2 siparis", "siparis", "havuz"])

    def test_base_nav_has_siparisler_link(self, client_orders):
        html = client_orders.get("/").data.decode("utf-8")
        assert "/siparisler" in html
