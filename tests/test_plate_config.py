"""tests/test_plate_config.py — Plaka konfig cozumu + /plaka-ayar rotalari.

resolve_plate: configs/plate.local.json > env PLATE_* > (None,None,None).
Manuel sabit plaka girisi ile otomatik plaka arasinda gecisi dogrular.
"""
from __future__ import annotations

import json

import pytest

from src.runtime.plate_config import (
    resolve_plate, plate_cfg_path, resolve_clearance, DEFAULT_CLEARANCE_MM,
)


# ---------------------------------------------------------------------------
# Birim: resolve_plate oncelik zinciri
# ---------------------------------------------------------------------------

def test_hicbir_kaynak_yok_none(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_W_MM", raising=False)
    monkeypatch.delenv("PLATE_D_MM", raising=False)
    monkeypatch.delenv("PLATE_H_MM", raising=False)
    assert resolve_plate(tmp_path) == (None, None, None)


def test_config_dosyasi_okunur(tmp_path):
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"width_mm": 335.0, "depth_mm": 300.0, "height_mm": 250.0}),
        encoding="utf-8",
    )
    assert resolve_plate(tmp_path) == (335.0, 300.0, 250.0)


def test_env_fallback(tmp_path, monkeypatch):
    # config dosyasi yok -> env kullanilir
    monkeypatch.setenv("PLATE_W_MM", "250")
    monkeypatch.setenv("PLATE_D_MM", "200")
    monkeypatch.delenv("PLATE_H_MM", raising=False)
    assert resolve_plate(tmp_path) == (250.0, 200.0, None)


def test_config_env_uzerinde_oncelikli(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATE_W_MM", "999")
    monkeypatch.setenv("PLATE_D_MM", "999")
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"width_mm": 335.0, "depth_mm": 300.0}), encoding="utf-8"
    )
    w, d, _h = resolve_plate(tmp_path)
    assert (w, d) == (335.0, 300.0)  # config kazandi


def test_gecersiz_deger_none(tmp_path, monkeypatch):
    monkeypatch.delenv("PLATE_W_MM", raising=False)
    monkeypatch.delenv("PLATE_D_MM", raising=False)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"width_mm": -5, "depth_mm": "abc"}), encoding="utf-8"
    )
    # gecersiz w/d -> config gecersiz, env de yok -> None
    assert resolve_plate(tmp_path) == (None, None, None)


# ---------------------------------------------------------------------------
# Birim: resolve_clearance oncelik zinciri (WEB_MIN_CLEARANCE_MM kod-sabiti
# tasima, 2026-07-25)
# ---------------------------------------------------------------------------

def test_clearance_hicbir_kaynak_yok_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NESTING_CLEARANCE_MM", raising=False)
    assert resolve_clearance(tmp_path) == DEFAULT_CLEARANCE_MM == 2.0


def test_clearance_config_alani_okunur(tmp_path, monkeypatch):
    monkeypatch.delenv("NESTING_CLEARANCE_MM", raising=False)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"min_clearance_mm": 3.5}), encoding="utf-8"
    )
    assert resolve_clearance(tmp_path) == 3.5


def test_clearance_env_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("NESTING_CLEARANCE_MM", "1.5")
    assert resolve_clearance(tmp_path) == 1.5


def test_clearance_config_env_uzerinde_oncelikli(tmp_path, monkeypatch):
    monkeypatch.setenv("NESTING_CLEARANCE_MM", "9")
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"min_clearance_mm": 3.5}), encoding="utf-8"
    )
    assert resolve_clearance(tmp_path) == 3.5  # config kazandi


def test_clearance_gecersiz_deger_default(tmp_path, monkeypatch):
    monkeypatch.delenv("NESTING_CLEARANCE_MM", raising=False)
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"min_clearance_mm": -1}), encoding="utf-8"
    )
    assert resolve_clearance(tmp_path) == DEFAULT_CLEARANCE_MM


def test_clearance_diger_plaka_alanlariyla_birlikte_var_olabilir(tmp_path):
    """min_clearance_mm, width_mm/depth_mm gibi diger alanlarla ayni dosyada
    yasayabilir — birbirini etkilemez (mevcut plate.local.json semantigi
    genisletilir, degistirilmez)."""
    cfg_dir = tmp_path / "configs"
    cfg_dir.mkdir()
    (cfg_dir / "plate.local.json").write_text(
        json.dumps({"width_mm": 335.0, "depth_mm": 300.0,
                     "min_clearance_mm": 2.5}), encoding="utf-8"
    )
    assert resolve_plate(tmp_path) == (335.0, 300.0, None)
    assert resolve_clearance(tmp_path) == 2.5


# ---------------------------------------------------------------------------
# Rota: GET /plaka-ayar
# ---------------------------------------------------------------------------

@pytest.fixture
def plate_root(tmp_path):
    """Izole plaka koku: /plaka-ayar rotalari gercek configs/ yerine tmp'ye
    yazar-okur (2026-07-16 bulgusu: eski test gercek dosyaya yazip finally'de
    geri yukluyordu — paralel/xdist kosuda yaris riski; artik hic dokunmaz)."""
    (tmp_path / "configs").mkdir()
    return tmp_path


@pytest.fixture
def client(plate_root):
    from src.webapp.app import create_app
    app = create_app(testing=True, llm_provider_override=None,
                     llm_enabled=False, plate_root=str(plate_root))
    return app.test_client()


def test_plaka_ayar_get_200(client):
    r = client.get("/plaka-ayar")
    assert r.status_code == 200
    assert "Plaka" in r.get_data(as_text=True)


def test_plaka_ayar_post_kaydet_ve_temizle(client, plate_root):
    """POST sabit plaka yazar; otomatik=1 ile geri alir — IZOLE tmp kokte."""
    p = plate_root / "configs" / "plate.local.json"

    r = client.post("/plaka-ayar", data={"width_mm": "335", "depth_mm": "300"})
    assert r.status_code in (302, 200)
    assert p.exists()
    assert resolve_plate(plate_root)[:2] == (335.0, 300.0)

    # otomatik=1 -> dosya silinir -> None
    r2 = client.post("/plaka-ayar", data={"otomatik": "1"})
    assert r2.status_code in (302, 200)
    assert not p.exists()


def test_plaka_ayar_post_form_disi_alanlari_korur(client, plate_root):
    """MERGE fix (2026-08-04): POST formda olmayan sozlesme alanlarini
    (no_go_soft, min_clearance_mm) SILMEZ — eski davranis config'i sifirdan
    yazip K-56g soft-nogo sozlesmesini sessizce ucuruyordu."""
    p = plate_root / "configs" / "plate.local.json"
    p.write_text(json.dumps({
        "width_mm": 335.0, "depth_mm": 335.0,
        "no_go": [[152.5, 0.2], [185.5, 45.0]],
        "no_go_soft": [[152.5, 0.2], [185.5, 33.0]],
        "min_clearance_mm": 2.0,
    }), encoding="utf-8")

    r = client.post("/plaka-ayar", data={
        "width_mm": "335", "depth_mm": "335",
        "ng_x1": "152.5", "ng_y1": "0.2", "ng_x2": "185.5", "ng_y2": "45",
    })
    assert r.status_code in (302, 200)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["no_go_soft"] == [[152.5, 0.2], [185.5, 33.0]]
    assert data["min_clearance_mm"] == 2.0
    assert data["no_go"] == [[152.5, 0.2], [185.5, 45.0]]
    assert (data["width_mm"], data["depth_mm"]) == (335.0, 335.0)


def test_plaka_ayar_otomatik_form_disi_alanlarla_dosya_yasar(client, plate_root):
    """otomatik=1: form alanlari (plaka + no_go) kalkar ama form-disi alanlar
    varsa dosya SILINMEZ, onlarla yasar."""
    p = plate_root / "configs" / "plate.local.json"
    p.write_text(json.dumps({
        "width_mm": 335.0, "depth_mm": 335.0,
        "no_go": [[152.5, 0.2], [185.5, 45.0]],
        "no_go_soft": [[152.5, 0.2], [185.5, 33.0]],
    }), encoding="utf-8")

    r = client.post("/plaka-ayar", data={"otomatik": "1"})
    assert r.status_code in (302, 200)
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"no_go_soft": [[152.5, 0.2], [185.5, 33.0]]}
    assert resolve_plate(plate_root) == (None, None, None)


def test_plaka_ayar_no_go_formdan_silinebilir_soft_kalir(client, plate_root):
    """Formda no-go alanlari bos gonderilirse no_go anahtar KALKAR (form o
    anahtarin sahibi) ama no_go_soft'a dokunulmaz."""
    p = plate_root / "configs" / "plate.local.json"
    p.write_text(json.dumps({
        "width_mm": 335.0, "depth_mm": 335.0,
        "no_go": [[152.5, 0.2], [185.5, 45.0]],
        "no_go_soft": [[152.5, 0.2], [185.5, 33.0]],
    }), encoding="utf-8")

    r = client.post("/plaka-ayar", data={"width_mm": "335", "depth_mm": "335"})
    assert r.status_code in (302, 200)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "no_go" not in data
    assert data["no_go_soft"] == [[152.5, 0.2], [185.5, 33.0]]


def test_plaka_ayar_bozuk_config_ustune_yazilir(client, plate_root):
    """Mevcut dosya bozuk JSON ise merge sessizce bos-dict'ten devam eder —
    POST yine gecerli config yazar (regresyon: exception 500 dondurmesin)."""
    p = plate_root / "configs" / "plate.local.json"
    p.write_text("{bozuk json", encoding="utf-8")
    r = client.post("/plaka-ayar", data={"width_mm": "335", "depth_mm": "300"})
    assert r.status_code in (302, 200)
    assert resolve_plate(plate_root)[:2] == (335.0, 300.0)


def test_plaka_ayar_gercek_dosyaya_dokunmaz(client, plate_root, tmp_path):
    """Regresyon kapisi: POST akisi proje kokundeki gercek configs/
    plate.local.json'un mtime/iceriğini DEGISTIRMEZ (izolasyon kaniti)."""
    from pathlib import Path
    gercek = Path(__file__).resolve().parents[1] / "configs" / "plate.local.json"
    once = (gercek.read_bytes(), gercek.stat().st_mtime_ns) if gercek.exists() else None
    client.post("/plaka-ayar", data={"width_mm": "111", "depth_mm": "222"})
    client.post("/plaka-ayar", data={"otomatik": "1"})
    sonra = (gercek.read_bytes(), gercek.stat().st_mtime_ns) if gercek.exists() else None
    assert once == sonra
