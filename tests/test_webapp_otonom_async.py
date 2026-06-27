"""test_webapp_otonom_async.py — Asenkron /otonom (baslat + durum) TDD.

Senkron /otonom AYNEN korunur (test_webapp_otonom.py); bu dosya asenkron yolu
test eder: POST /otonom/baslat -> job_id (202), GET /otonom/durum/<id> -> CANLI
ilerleme, is bitince sonuc senkron yol ile AYNI (FakeMailbox + FakeProvider).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Senkron testlerin FakeProvider kurulumunu yeniden kullan (DRY)
from tests.test_webapp_otonom import _make_full_fake_provider


@pytest.fixture
def app_with_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_provider_override=_make_full_fake_provider())


@pytest.fixture
def client_llm(app_with_llm):
    return app_with_llm.test_client()


@pytest.fixture
def app_no_llm():
    from src.webapp.app import create_app
    return create_app(testing=True, llm_enabled=False)


@pytest.fixture
def client_no_llm(app_no_llm):
    return app_no_llm.test_client()


def _poll_until_done(client, job_id, timeout_s=30.0):
    """Durum 'calisiyor' olmaktan cikana kadar yokla; son snapshot'i don."""
    deadline = time.time() + timeout_s
    snap = None
    while time.time() < deadline:
        resp = client.get(f"/otonom/durum/{job_id}")
        assert resp.status_code == 200
        snap = resp.get_json()
        if snap["durum"] != "calisiyor":
            return snap
        time.sleep(0.25)
    return snap


class TestBaslatRota:
    def test_baslat_rota_var(self, client_no_llm):
        """/otonom/baslat rotasi var olmali (asla 404)."""
        resp = client_no_llm.post("/otonom/baslat", content_type="application/json")
        assert resp.status_code != 404

    def test_baslat_llm_yoksa_503(self, client_no_llm):
        resp = client_no_llm.post("/otonom/baslat", content_type="application/json")
        assert resp.status_code == 503

    def test_baslat_llm_varsa_202_ve_job_id(self, client_llm):
        resp = client_llm.post("/otonom/baslat", json={})
        assert resp.status_code == 202, f"Beklenen 202, gelen {resp.status_code}: {resp.data[:200]}"
        data = resp.get_json()
        assert data.get("job_id")
        assert data.get("durum") == "calisiyor"


class TestDurumRota:
    def test_durum_bilinmeyen_job_404(self, client_llm):
        resp = client_llm.get("/otonom/durum/yokboyle")
        assert resp.status_code == 404

    def test_durum_snapshot_alanlari(self, client_llm):
        jid = client_llm.post("/otonom/baslat", json={}).get_json()["job_id"]
        snap = client_llm.get(f"/otonom/durum/{jid}").get_json()
        for key in ("durum", "asamalar", "job_id"):
            assert key in snap


class TestAsenkronTamamlanma:
    def test_is_tamamlanir_durum_bitti(self, client_llm):
        jid = client_llm.post("/otonom/baslat", json={}).get_json()["job_id"]
        snap = _poll_until_done(client_llm, jid)
        assert snap is not None
        assert snap["durum"] == "bitti", f"durum={snap['durum']} hata={snap.get('hata')}"

    def test_asenkron_sonuc_senkronla_ayni_asamalar(self, client_llm, app_with_llm):
        # Asenkron yol
        jid = client_llm.post("/otonom/baslat", json={}).get_json()["job_id"]
        snap = _poll_until_done(client_llm, jid)
        async_asama_adlari = [a.get("ad") for a in snap["sonuc"]["asamalar"]]

        # Senkron yol (ayni app/fake kurulum) — ayni asama dizisi beklenir
        sync = client_llm.post("/otonom", json={}).get_json()
        sync_asama_adlari = [a.get("ad") for a in sync["asamalar"]]

        assert async_asama_adlari == sync_asama_adlari

    def test_asenkron_canli_ilerleme_asamalar_birikir(self, client_llm):
        """Is biterken sonuc 'asamalar' EN AZ 4 asama icermeli (mail/parse/nesting/fiyat)."""
        jid = client_llm.post("/otonom/baslat", json={}).get_json()["job_id"]
        snap = _poll_until_done(client_llm, jid)
        assert len(snap["sonuc"]["asamalar"]) >= 4
