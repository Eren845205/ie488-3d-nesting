"""tests/test_webapp_health.py -- /health demo-saglik kontrolu testleri.

Demo oncesi "LLM hazir mi" kapisi:
  - LLM kapali  -> 200 + llm=disabled
  - LLM aktif + probe ok   -> 200 + llm=ok
  - LLM aktif + probe fail  -> 503 + llm=fail
  - probe desteklenmeyen saglayici -> 200 + llm=ok
"""

from __future__ import annotations

import json

from src.webapp.app import create_app


class _HealthyProvider:
    def health_check(self, timeout_s: float = 5.0):
        return (True, "Hazir: test-model yuklu.")

    def complete(self, req):  # roller init edebilsin diye var; /health cagirmaz
        raise NotImplementedError


class _UnhealthyProvider:
    def health_check(self, timeout_s: float = 5.0):
        return (False, "Servise ERISILEMIYOR: ollama serve ile baslatin.")

    def complete(self, req):
        raise NotImplementedError


class _NoProbeProvider:
    """health_check metodu olmayan saglayici (eski/sahte)."""

    def complete(self, req):
        raise NotImplementedError


def _client(**kwargs):
    app = create_app(testing=True, **kwargs)
    return app.test_client()


class TestHealthRoute:
    def test_llm_disabled_returns_200_disabled(self):
        c = _client(llm_enabled=False)
        r = c.get("/health")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body["web"] == "ok"
        assert body["llm"] == "disabled"
        assert body["llm_active"] is False

    def test_healthy_provider_returns_200_ok(self):
        c = _client(llm_provider_override=_HealthyProvider())
        r = c.get("/health")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body["llm"] == "ok"
        assert "Hazir" in body["detail"]

    def test_unhealthy_provider_returns_503_fail(self):
        c = _client(llm_provider_override=_UnhealthyProvider())
        r = c.get("/health")
        assert r.status_code == 503
        body = json.loads(r.data)
        assert body["llm"] == "fail"
        assert "ERISILEMIYOR" in body["detail"]

    def test_provider_without_probe_returns_200_ok(self):
        c = _client(llm_provider_override=_NoProbeProvider())
        r = c.get("/health")
        assert r.status_code == 200
        body = json.loads(r.data)
        assert body["llm"] == "ok"
