"""test_llm_teklif.py — src/llm/roles/teklif.py testleri (TDD).

Kapsam:
  - TeklifInput.to_dict() icerigi dogru
  - VALID taslak: FakeProvider gecerli JSON -> VALID TeklifResult, mail_govde_md dolu
  - Bozuk JSON 3x -> INVALID + fallback (dead-end yok: hata rapor edilir)
  - Retry: ilk gecersiz, ikinci gecerli -> attempt_count=2, VALID
  - TestTopraklamaUyari: number_flag=True AMA status VALID + fallback None (BLOK DEGIL)
  - Temiz: aciklamadaki sayilar girdiden -> number_flag=False
  - Prompt-lock: teklif-v1, 3 ornek, enforce_lock=True hash tutar
  - TestReportFarki: ayni girdiden report.run vs teklif.draft FARKLI sema/cikti

TDD: FakeProvider — ag baglantisi YOK.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.llm.audit import AuditLogger
from src.llm.config import RoleConfig
from src.llm.grounding import GroundedContext, SourceDoc
from src.llm.prompts import PromptRegistry
from src.llm.provider import FakeProvider
from src.llm.roles.teklif import TeklifInput, TeklifResult, TeklifRole
from src.llm.structured import ValidationStatus


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
        role="teklif",
        provider="fake",
        model="fake-model",
        temperature=0.0,
        max_tokens=512,
        schema_retry=2,
    )


def _make_context() -> GroundedContext:
    return GroundedContext(
        is_id="test-001",
        kaynaklar=[
            SourceDoc(
                id="fiyat#B001",
                tip="fiyat",
                icerik="Nihai fiyat: 1500.0 USD",
                uretici="pricing.engine",
            )
        ],
    )


def _make_teklif_input(
    musteri_adi: str = "Sayin Test Musterisi",
    parcalar: List[Dict[str, Any]] = None,
    fiyat: float = 1500.0,
    termin: str = "7 is gunu",
) -> TeklifInput:
    if parcalar is None:
        parcalar = [{"ad": "Test Parcasi", "adet": 10}]
    return TeklifInput(
        musteri_adi=musteri_adi,
        parca_ozeti=parcalar,
        toplam_fiyat_usd=fiyat,
        termin_ifadesi=termin,
        context=_make_context(),
    )


def _valid_teklif_json(
    konu: str = "Siparis Teklifiniz",
    mail_govde_md: str = "Sayin Musterimiz, 10 adet Test Parcasi icin teklifimiz 1500.0 USD, termin 7 is gunudur.",
    kullanilan_kaynaklar: List[str] = None,
    topraklama_uyarisi: bool = False,
) -> str:
    return json.dumps(
        {
            "konu": konu,
            "mail_govde_md": mail_govde_md,
            "kullanilan_kaynaklar": kullanilan_kaynaklar or ["teklif#ozet"],
            "topraklama_uyarisi": topraklama_uyarisi,
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# TEST: TeklifInput yapisi
# ---------------------------------------------------------------------------


class TestTeklifInput:
    def test_to_dict_musteri_adi(self):
        inp = _make_teklif_input(musteri_adi="Sayin Ahmet")
        d = inp.to_dict()
        assert d["musteri_adi"] == "Sayin Ahmet"

    def test_to_dict_parcalar(self):
        inp = _make_teklif_input(parcalar=[{"ad": "Flanş", "adet": 5}])
        d = inp.to_dict()
        assert d["parcalar"][0]["ad"] == "Flanş"
        assert d["parcalar"][0]["adet"] == 5

    def test_to_dict_fiyat_ve_termin(self):
        inp = _make_teklif_input(fiyat=999.0, termin="3 is gunu")
        d = inp.to_dict()
        assert d["toplam_fiyat_usd"] == 999.0
        assert d["termin_ifadesi"] == "3 is gunu"

    def test_to_dict_kaynaklarda_teklif_ozet_var(self):
        """to_dict() augmented context'i serializer -> teklif#ozet kaynagi dahil olmali."""
        inp = _make_teklif_input()
        d = inp.to_dict()
        kaynak_ids = [k["id"] for k in d.get("kaynaklar", [])]
        assert "teklif#ozet" in kaynak_ids

    def test_augmented_context_icerir_ozet(self):
        inp = _make_teklif_input(fiyat=1500.0)
        ctx = inp.augmented_context()
        ids = [k.id for k in ctx.kaynaklar]
        assert "teklif#ozet" in ids

    def test_ozet_icerik_fiyat_rakamini_tasir(self):
        inp = _make_teklif_input(fiyat=1500.0)
        ctx = inp.augmented_context()
        ozet_doc = next(k for k in ctx.kaynaklar if k.id == "teklif#ozet")
        assert "1500.0" in ozet_doc.icerik


# ---------------------------------------------------------------------------
# TEST: VALID taslak
# ---------------------------------------------------------------------------


class TestTeklifRoleValid:
    def test_valid_taslak_status(self, tmp_path):
        fake_resp = _valid_teklif_json()
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.status == ValidationStatus.VALID
        assert result.fallback is None

    def test_valid_taslak_mail_govde_md_dolu(self, tmp_path):
        govde = "Sayin Musterimiz, 10 adet Test Parcasi icin teklifimiz 1500.0 USD, termin 7 is gunudur."
        fake_resp = _valid_teklif_json(mail_govde_md=govde)
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.data is not None
        assert "1500.0" in result.data["mail_govde_md"]

    def test_valid_taslak_konu_alani(self, tmp_path):
        fake_resp = _valid_teklif_json(konu="Siparis Teklifiniz — Test Parcasi")
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.data["konu"] == "Siparis Teklifiniz — Test Parcasi"

    def test_valid_audit_ref_dolu(self, tmp_path):
        fake_resp = _valid_teklif_json()
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.audit_ref != ""


# ---------------------------------------------------------------------------
# TEST: Topraklama UYARI modu (BLOK DEGIL)
# ---------------------------------------------------------------------------


class TestTopraklamaUyari:
    def test_number_flag_true_status_valid_kalir(self, tmp_path):
        """BLOK DEGIL kaniti: number_flag=True ama status VALID, fallback None."""
        # 99999.0 teklif#ozet'te YOK -> topraklama uyarisi
        govde = "Sayin Musterimiz, fiyatimiz 99999.0 USD olup termin 7 is gunudur."
        fake_resp = _valid_teklif_json(
            mail_govde_md=govde,
            topraklama_uyarisi=True,
        )
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())

        # BLOK DEGIL kaniti:
        assert result.status == ValidationStatus.VALID, "BLOK modunda OLMAMALI: status VALID kalmali"
        assert result.fallback is None, "BLOK modunda OLMAMALI: fallback None olmali"
        assert result.number_flag is True, "99999.0 baglamda yok -> number_flag=True"
        assert result.data is not None, "Taslak data dolu olmali (dead-end yok)"
        assert "99999.0" in result.data.get("mail_govde_md", "")

    def test_number_flag_true_ungrounded_listesi_dolu(self, tmp_path):
        govde = "Fiyat: 77777.0 USD, termin 7 is gunu."
        fake_resp = _valid_teklif_json(mail_govde_md=govde)
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.number_flag is True
        assert "77777.0" in result.ungrounded_numbers

    def test_temiz_sayi_number_flag_false(self, tmp_path):
        """Sayilar girdiden geliyorsa number_flag=False."""
        govde = "10 adet Test Parcasi icin 1500.0 USD, termin 7 is gunu."
        fake_resp = _valid_teklif_json(
            mail_govde_md=govde,
            topraklama_uyarisi=False,
        )
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input(fiyat=1500.0))
        assert result.status == ValidationStatus.VALID
        assert result.number_flag is False
        assert result.ungrounded_numbers == []


# ---------------------------------------------------------------------------
# TEST: Fallback ve retry
# ---------------------------------------------------------------------------


class TestTeklifFallback:
    def test_bozuk_json_3x_fallback(self, tmp_path):
        """LLM 3 kez gecersiz JSON -> INVALID + fallback."""
        provider = FakeProvider(
            fixture_map={
                ("teklif-v1", "_any_"): [
                    "Bu JSON degil",
                    "Hala gecersiz",
                    "Yine de degil",
                ]
            }
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None
        assert result.fallback.call_ref != ""
        assert result.data is None

    def test_retry_ikinci_yanit_gecerli(self, tmp_path):
        """Ilk yanit bozuk, ikinci gecerli -> VALID, attempt_count=2."""
        gecerli = _valid_teklif_json()
        provider = FakeProvider(
            fixture_map={
                ("teklif-v1", "_any_"): ["gecersiz", gecerli]
            }
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.status == ValidationStatus.VALID
        assert result.role_result.attempt_count == 2

    def test_eksik_zorunlu_alan_fallback(self, tmp_path):
        """konu eksik -> schema INVALID -> fallback."""
        bad_json = json.dumps({
            "mail_govde_md": "Test govde",
            "kullanilan_kaynaklar": [],
        })
        provider = FakeProvider(
            fixture_map={
                ("teklif-v1", "_any_"): [bad_json, bad_json, bad_json]
            }
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.status == ValidationStatus.INVALID
        assert result.fallback is not None


# ---------------------------------------------------------------------------
# TEST: TeklifResult ozellikleri
# ---------------------------------------------------------------------------


class TestTeklifResult:
    def test_status_proxy(self, tmp_path):
        fake_resp = _valid_teklif_json()
        provider = FakeProvider(
            fixture_map={("teklif-v1", "_any_"): [fake_resp]}
        )
        role = TeklifRole(
            provider=provider,
            registry=_make_registry(),
            audit=_make_audit(tmp_path),
            role_cfg=_make_role_cfg(),
        )
        result = role.draft(_make_teklif_input())
        assert result.status == result.role_result.status
        assert result.data == result.role_result.data
        assert result.fallback == result.role_result.fallback
        assert result.audit_ref == result.role_result.audit_ref


# ---------------------------------------------------------------------------
# TEST: Prompt-lock
# ---------------------------------------------------------------------------


class TestTeklifPrompt:
    def test_prompt_lockfile_eslesmesi(self):
        """teklif-v1 hash'i lock.json ile uyusmali (enforce_lock=True)."""
        registry = _make_registry()
        tpl = registry.load("teklif")
        assert tpl.id == "teklif-v1"
        assert tpl.version == "1.0"
        assert len(tpl.examples) == 3

    def test_few_shot_uc_ornek(self):
        registry = _make_registry()
        tpl = registry.load("teklif")
        few_shot_text = tpl.few_shot_text()
        assert "Ornek 1" in few_shot_text
        assert "Ornek 2" in few_shot_text
        assert "Ornek 3" in few_shot_text

    def test_schema_zorunlu_alanlar(self):
        registry = _make_registry()
        tpl = registry.load("teklif")
        required = tpl.schema.get("required", [])
        assert "konu" in required
        assert "mail_govde_md" in required
        assert "kullanilan_kaynaklar" in required

    def test_schema_additional_properties_false(self):
        registry = _make_registry()
        tpl = registry.load("teklif")
        assert tpl.schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# TEST: TestReportFarki — ayni girdiden report.run vs teklif.draft FARKLI sema
# ---------------------------------------------------------------------------


class TestReportFarki:
    """Report ve Teklif rolleri farkli sema kullanmali.

    Ozet-raporu yonetici icindir (govde_md, baslik, eksik_bilgi).
    Teklif taslagi musteri-mail icindir (mail_govde_md, konu).
    """

    def test_teklif_sema_musteri_alanlari(self):
        """Teklif sema: konu + mail_govde_md (rapor ozet alanlari degil)."""
        registry = _make_registry()
        teklif_tpl = registry.load("teklif")
        report_tpl = registry.load("report")

        teklif_required = set(teklif_tpl.schema.get("required", []))
        report_required = set(report_tpl.schema.get("required", []))

        # Teklif: musteri-mail alanlari
        assert "mail_govde_md" in teklif_required
        assert "konu" in teklif_required

        # Rapor: yonetici ozet alanlari
        assert "govde_md" in report_required
        assert "baslik" in report_required

        # Sema kesisimi minimal olmali (ortak: kullanilan_kaynaklar)
        musteri_ozgu = teklif_required - report_required
        assert "mail_govde_md" in musteri_ozgu
        assert "konu" in musteri_ozgu

    def test_teklif_draft_farkli_cikti_report_run(self, tmp_path):
        # Bu test sema ayrimini denetler; LLM davranisini degil — asil guvence sema-kesisim testleridir
        """Ayni FakeProvider ile: teklif.draft() konu+mail_govde_md; report.run() baslik+govde_md dondurur."""
        from src.llm.roles.report import ReportRole, ReportInput

        teklif_fake = _valid_teklif_json(
            konu="Musteri Konu",
            mail_govde_md="Musteri mail govdesi: 1500.0 USD, 7 is gunu.",
        )
        report_fake = json.dumps({
            "baslik": "Yonetici Ozet Baslik",
            "govde_md": "Bu kosuda 3 siparis islendi. Toplam 1500 USD.",
            "kullanilan_kaynaklar": [],
            "eksik_bilgi": [],
        }, ensure_ascii=False)

        provider = FakeProvider(
            fixture_map={
                ("teklif-v1", "_any_"): [teklif_fake],
                ("report-v1", "_any_"): [report_fake],
            }
        )
        registry = _make_registry()
        audit = _make_audit(tmp_path)

        teklif_role = TeklifRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=_make_role_cfg(),
        )
        report_role = ReportRole(
            provider=provider,
            registry=registry,
            audit=audit,
        )

        teklif_result = teklif_role.draft(_make_teklif_input())
        report_input = ReportInput(
            is_id="test-001",
            n_orders=3,
            n_batches=1,
            n_warnings=0,
            total_revenue_usd=1500.0,
            context=_make_context(),
        )
        report_result = report_role.run(report_input)

        # Teklif: musteri alanlari
        assert teklif_result.data is not None
        assert "mail_govde_md" in teklif_result.data
        assert "konu" in teklif_result.data
        # Rapor: yonetici alanlari
        assert report_result.data is not None
        assert "govde_md" in report_result.data
        assert "baslik" in report_result.data

        # Ciktilar birbirinden farkli olmali
        teklif_mail = teklif_result.data.get("mail_govde_md", "")
        report_govde = report_result.data.get("govde_md", "")
        assert teklif_mail != report_govde, "Teklif ve rapor ciktilari ozdes olmamali"
