"""test_llm_watcher.py — src/llm/roles/watcher.py TDD testleri.

Kapsam:
  - WatcherNarrationInput gecerli JSON -> VALID narrate sonucu
  - Bozuk JSON -> fallback (INVALID)
  - Retry: ilk yanit gecersiz, ikinci gecerli -> VALID attempt_count=2
  - Sayi-topraklama UYARI: anlatimda bulguda olmayan sayi -> topraklama_uyarisi=True
  - Graceful: finding listesi bos -> erken donus (LLM cagrisi yok)
  - Lock hash kapisi: watcher-v1 lock.json'da kayitli ve eslesiyor
  - Severity degistirme yasagi: schema'da severity alani YOK

TDD: FakeProvider — ag baglantisi YOK.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider
from src.llm.structured import ValidationStatus
from src.watcher.checks import Finding


# ---------------------------------------------------------------------------
# Yardimcilar
# ---------------------------------------------------------------------------

def _make_registry() -> PromptRegistry:
    root = Path(__file__).resolve().parent.parent
    return PromptRegistry(
        prompts_dir=str(root / "prompts"),
        enforce_lock=True,
    )


def _make_audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(
        log_dir=tmp_path / "logs" / "llm",
        payload_log_dir=tmp_path / "logs" / "payload",
        payload_logging="none",
    )


def _make_role_cfg() -> RoleConfig:
    return RoleConfig(
        role="watcher",
        provider="fake",
        model="fake-model",
        temperature=0.0,
        max_tokens=512,
        schema_retry=2,
    )


def _sample_findings(n: int = 2) -> List[Finding]:
    findings = []
    if n >= 1:
        findings.append(Finding(
            asama="fiyat",
            kod="FIYAT_ORAN_YUKSEK",
            severity="high",
            baslik="Fiyat gecmisine gore yuksek",
            ham_detay="total=250.0, medyan=100.0, oran=2.5",
            metrik={"total": 250.0, "medyan": 100.0, "oran": 2.5},
        ))
    if n >= 2:
        findings.append(Finding(
            asama="nest",
            kod="NEST_DOLULUK_DUSUK",
            severity="med",
            baslik="Doluluk beklenenin altinda",
            ham_detay="density=0.10, beklenen=0.25",
            metrik={"density": 0.10, "beklenen": 0.25},
        ))
    return findings


def _valid_watcher_json(
    anlatim: str = "Fiyat gecmis benzer islerden yaklasik 2.5 kat yuksek — kontrol oneriliyor.",
    kapsanan: List[str] = None,
    topraklama_uyarisi: bool = False,
) -> str:
    return json.dumps({
        "anlatim_md": anlatim,
        "kapsanan_bulgular": kapsanan or ["FIYAT_ORAN_YUKSEK"],
        "topraklama_uyarisi": topraklama_uyarisi,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# TEST: WatcherNarrationInput
# ---------------------------------------------------------------------------

class TestWatcherNarrationInput:

    def test_input_has_findings(self):
        from src.llm.roles.watcher import WatcherNarrationInput
        findings = _sample_findings(1)
        inp = WatcherNarrationInput(findings=findings)
        assert len(inp.findings) == 1
        assert inp.findings[0].kod == "FIYAT_ORAN_YUKSEK"

    def test_input_to_dict(self):
        from src.llm.roles.watcher import WatcherNarrationInput
        findings = _sample_findings(2)
        inp = WatcherNarrationInput(findings=findings)
        d = inp.to_dict()
        assert "bulgular" in d
        assert len(d["bulgular"]) == 2
        # Her bulgu asama, kod, severity, baslik, ham_detay icermeli
        for b in d["bulgular"]:
            assert "asama" in b
            assert "kod" in b
            assert "severity" in b
            assert "baslik" in b
            assert "ham_detay" in b

    def test_input_to_source_doc(self):
        from src.llm.roles.watcher import WatcherNarrationInput
        findings = _sample_findings(1)
        inp = WatcherNarrationInput(findings=findings)
        doc = inp.to_source_doc()
        assert doc.tip == "telemetri"
        # Bulgu kodu, severity ve metrik sayilari icerik'te olmali
        assert "FIYAT_ORAN_YUKSEK" in doc.icerik
        assert "250.0" in doc.icerik


# ---------------------------------------------------------------------------
# TEST: Basarili narrate
# ---------------------------------------------------------------------------

class TestWatcherRoleNarrate:

    def test_valid_narrate(self, tmp_path):
        """FakeProvider gecerli JSON -> VALID narrate sonucu."""
        from src.llm.roles.watcher import WatcherRole

        anlatim = "Fiyat 2.5 kat yuksek — kontrol oneriliyor."
        fake_resp = _valid_watcher_json(anlatim=anlatim, kapsanan=["FIYAT_ORAN_YUKSEK"])
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [fake_resp]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))

        assert result.status == ValidationStatus.VALID
        assert result.fallback is None
        assert result.data is not None
        assert "2.5" in result.data["anlatim_md"]
        assert "FIYAT_ORAN_YUKSEK" in result.data["kapsanan_bulgular"]

    def test_valid_narrate_iki_bulgu(self, tmp_path):
        """Iki bulgu -> ikisi de kapsanan_bulgular'da."""
        from src.llm.roles.watcher import WatcherRole

        fake_resp = _valid_watcher_json(
            anlatim="Fiyat 2.5 kat yuksek ve doluluk 0.10 beklenenin altinda.",
            kapsanan=["FIYAT_ORAN_YUKSEK", "NEST_DOLULUK_DUSUK"],
        )
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [fake_resp]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(2))
        assert result.status == ValidationStatus.VALID
        assert "NEST_DOLULUK_DUSUK" in result.data["kapsanan_bulgular"]


# ---------------------------------------------------------------------------
# TEST: Bos bulgu listesi
# ---------------------------------------------------------------------------

class TestWatcherEmptyFindings:

    def test_bos_bulgular_erken_donus(self, tmp_path):
        """Bos finding listesi -> LLM cagrisi yapilmaz, None/bos donus."""
        from src.llm.roles.watcher import WatcherRole

        call_count = [0]
        class CountingFakeProvider:
            def complete(self, req):
                call_count[0] += 1
                from src.llm.provider import LLMResponse
                return LLMResponse(text=_valid_watcher_json(), model_id="fake")

        role = WatcherRole(
            provider=CountingFakeProvider(),
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate([])
        # LLM cagrisi yapilmamali
        assert call_count[0] == 0
        # Sonuc None veya bos anlatim
        if result is not None:
            assert result.data is None or result.data.get("anlatim_md", "") == ""


# ---------------------------------------------------------------------------
# TEST: Fallback ve retry
# ---------------------------------------------------------------------------

class TestWatcherFallback:

    def test_bozuk_json_fallback(self, tmp_path):
        """LLM gecersiz JSON donduruyor -> INVALID + fallback."""
        from src.llm.roles.watcher import WatcherRole

        provider = FakeProvider(
            fixture_map={
                ("watcher-v1", "_any_"): [
                    "Bu JSON degil",
                    "Hala JSON degil",
                    "Yine de degil",
                ]
            }
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None
        assert result.data is None

    def test_retry_ikinci_yanit_gecerli(self, tmp_path):
        """Ilk yanit bozuk JSON, ikinci gecerli -> VALID, attempt_count=2."""
        from src.llm.roles.watcher import WatcherRole

        gecerli = _valid_watcher_json()
        provider = FakeProvider(
            fixture_map={
                ("watcher-v1", "_any_"): ["gecersiz metin", gecerli]
            }
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.VALID
        assert result.role_result.attempt_count == 2

    def test_eksik_zorunlu_alan_fallback(self, tmp_path):
        """anlatim_md eksik -> schema INVALID -> fallback."""
        from src.llm.roles.watcher import WatcherRole

        bad_json = json.dumps({"kapsanan_bulgular": ["X"]})
        provider = FakeProvider(
            fixture_map={
                ("watcher-v1", "_any_"): [bad_json, bad_json, bad_json]
            }
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None


# ---------------------------------------------------------------------------
# TEST: Sayi-topraklama UYARI
# ---------------------------------------------------------------------------

class TestWatcherTopraklama:

    def test_topraklama_temiz(self, tmp_path):
        """Anlatimda 2.5 -> bulguda mevcut -> topraklama_uyarisi=False."""
        from src.llm.roles.watcher import WatcherRole

        # 2.5 bulgu metriginde var
        anlatim = "Fiyat oran 2.5 kat — kontrol oneriliyor."
        fake_resp = _valid_watcher_json(anlatim=anlatim, topraklama_uyarisi=False)
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [fake_resp]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.VALID
        assert result.number_flag is False

    def test_topraklama_uyari_yabanci_sayi(self, tmp_path):
        """Anlatimda 9999.9 -> bulguda YOK -> number_flag=True."""
        from src.llm.roles.watcher import WatcherRole

        anlatim = "Beklenen tasarruf 9999.9 USD civarinda."
        fake_resp = _valid_watcher_json(anlatim=anlatim, topraklama_uyarisi=True)
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [fake_resp]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.VALID
        # 9999.9 bulgu iceriklerinde yok -> number_flag=True
        assert result.number_flag is True

    def test_topraklama_blok_degil(self, tmp_path):
        """Topraklama uyarisi -> status INVALID olmamali (UYARI modu)."""
        from src.llm.roles.watcher import WatcherRole

        anlatim = "Bilinmeyen deger 77777.0 raporlandi."
        fake_resp = _valid_watcher_json(anlatim=anlatim)
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [fake_resp]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == ValidationStatus.VALID
        assert result.fallback is None


# ---------------------------------------------------------------------------
# TEST: Prompt registry ve lock hash
# ---------------------------------------------------------------------------

class TestWatcherPrompt:

    def test_prompt_lockfile_eslesmesi(self):
        """Watcher sablon hash'i lock.json ile uyusmali."""
        registry = _make_registry()
        tpl = registry.load("watcher")
        assert tpl.id == "watcher-v1"
        assert tpl.version == "1.0"

    def test_few_shot_uc_ornek(self):
        """3 ornek olmali."""
        registry = _make_registry()
        tpl = registry.load("watcher")
        few_shot_text = tpl.few_shot_text()
        assert "Ornek 1" in few_shot_text
        assert "Ornek 2" in few_shot_text
        assert "Ornek 3" in few_shot_text

    def test_schema_zorunlu_alanlar(self):
        """anlatim_md ve kapsanan_bulgular zorunlu; severity YOK."""
        registry = _make_registry()
        tpl = registry.load("watcher")
        required = tpl.schema.get("required", [])
        assert "anlatim_md" in required
        assert "kapsanan_bulgular" in required
        # severity LLM şemasinda OLMAMALI (deterministikten gelir)
        props = tpl.schema.get("properties", {})
        assert "severity" not in props, "severity LLM sema'sinda olmamali"

    def test_schema_additionalProperties_false(self):
        """additionalProperties=false olmali."""
        registry = _make_registry()
        tpl = registry.load("watcher")
        assert tpl.schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# TEST: WatcherResult ozellikleri
# ---------------------------------------------------------------------------

class TestWatcherResult:

    def test_result_proxy_alanlar(self, tmp_path):
        """WatcherResult status/data/fallback/audit_ref proxy'leri calissin."""
        from src.llm.roles.watcher import WatcherRole

        gecerli = _valid_watcher_json()
        provider = FakeProvider(
            fixture_map={("watcher-v1", "_any_"): [gecerli]}
        )
        role = WatcherRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.narrate(_sample_findings(1))
        assert result.status == result.role_result.status
        assert result.data == result.role_result.data
        assert result.fallback == result.role_result.fallback
        assert result.audit_ref == result.role_result.audit_ref
        assert result.audit_ref != ""
