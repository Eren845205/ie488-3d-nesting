"""tests/test_plate_config.py — Plaka konfig cozumu + /plaka-ayar rotalari.

resolve_plate: configs/plate.local.json > env PLATE_* > (None,None,None).
Manuel sabit plaka girisi ile otomatik plaka arasinda gecisi dogrular.
"""
from __future__ import annotations

import json

import pytest

from src.runtime.plate_config import resolve_plate, plate_cfg_path


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
