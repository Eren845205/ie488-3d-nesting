"""test_llm_assistant.py — src/llm/roles/assistant.py testleri (PLAN_LLM.md L3).

Kapsam:
  - Basarili topraklanmis yanit: FakeProvider -> VALID AssistantResult
  - Alinti zorunlulugu: ret=false + alintilar bos -> INVALID
  - Baglam-disi soru reddi: ret=true -> AssistantResult.data["ret"]==True
  - Sayi-topraklama UYARI (blok degil): ungrounded_numbers dolu ama status!=INVALID
  - Conversation gecmisi: add/to_history_text
  - LLM bozuk JSON -> fallback

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
from src.llm.roles.assistant import AssistantRole, AssistantResult, Conversation, ConversationTurn
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
        role="assistant",
        provider="fake",
        model="fake-model",
        temperature=0.1,
        max_tokens=512,
        schema_retry=2,
    )


def _make_context() -> GroundedContext:
    docs = [
        SourceDoc(
            id="yerlesim#B001",
            tip="yerlesim",
            icerik="Yukseklik: 180.0 mm\nDoluluk: 72.3%\nCozucu: DBLF (seed=42)",
            uretici="nesting3d.dblf",
        ),
        SourceDoc(
            id="fiyat#B001",
            tip="fiyat",
            icerik="Nihai fiyat: 1250.50 USD\nKural: hacim_kademesi",
            uretici="pricing.engine",
        ),
    ]
    return GroundedContext(is_id="test-job", kaynaklar=docs)


def _valid_answer_json(cevap: str = "B001 yuksekligi 180.0 mm.") -> str:
    return json.dumps({
        "cevap_md": cevap,
        "alintilar": [{"kaynak_id": "yerlesim#B001", "konum": "Yukseklik: 180.0 mm"}],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)


def _rejection_json(neden: str = "Bu bilgi baglamda yok.") -> str:
    return json.dumps({
        "cevap_md": "Bu bilgi elimdeki sistem ciktilarinda yok.",
        "alintilar": [],
        "onerilen_aksiyonlar": [],
        "ret": True,
        "ret_nedeni": neden,
    }, ensure_ascii=False)


def _no_citation_json() -> str:
    """ret=False ama alintilar bos — alinti zorunlulugu ihlali."""
    return json.dumps({
        "cevap_md": "Cevap metni.",
        "alintilar": [],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Test 1: Basarili topraklanmis yanit
# ---------------------------------------------------------------------------


def test_assistant_valid_answer(tmp_path):
    """FakeProvider gecerli alintili JSON dondurur -> VALID AssistantResult."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): [_valid_answer_json()]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask(soru="B001 partisinin yuksekligi nedir?", context=_make_context())

    assert result.status == ValidationStatus.VALID
    assert result.data is not None
    assert result.data["ret"] is False
    assert len(result.data["alintilar"]) > 0
    assert result.fallback is None
    assert result.audit_ref != ""


# ---------------------------------------------------------------------------
# Test 2: Alinti zorunlulugu (ret=False ama alintilar bos -> INVALID)
# ---------------------------------------------------------------------------


def test_assistant_no_citation_invalid(tmp_path):
    """ret=False + alintilar bos -> INVALID (alinti zorunlulugu)."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): [_no_citation_json()]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask(soru="Bir soru.", context=_make_context())

    assert result.status == ValidationStatus.INVALID
    assert result.fallback is not None
    assert "alinti" in result.fallback.errors[0].lower() or "alintilar" in result.fallback.errors[0].lower()


# ---------------------------------------------------------------------------
# Test 3: Baglam-disi soru reddi
# ---------------------------------------------------------------------------


def test_assistant_out_of_context_rejection(tmp_path):
    """Baglam-disi soru -> ret=True, status=VALID (sema gecerliyse)."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={
            ("assistant-v1", "_any_"): [_rejection_json("Bitcoin hakkinda bilgi yok.")]
        }
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask(soru="Bitcoin fiyati nedir?", context=_make_context())

    assert result.status == ValidationStatus.VALID
    assert result.data is not None
    assert result.data["ret"] is True
    assert result.data["ret_nedeni"] is not None
    # ret=True -> sohbete eklenmemeli
    assert len(role.conversation.turns) == 0


# ---------------------------------------------------------------------------
# Test 4: Sayi-topraklama UYARI (blok degil)
# ---------------------------------------------------------------------------


def test_assistant_number_flag_warning(tmp_path):
    """LLM ciktisinda baglamsiz sayi -> number_flag=True ama status hala VALID."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # 9999.99 baglamda YOK — uyari olmali, blok degil
    cevap_with_bad_number = "B001 partisinin fiyati 9999.99 USD. Yukseklik 180.0 mm."
    answer_json = json.dumps({
        "cevap_md": cevap_with_bad_number,
        "alintilar": [{"kaynak_id": "yerlesim#B001", "konum": "Yukseklik: 180.0 mm"}],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): [answer_json]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask(soru="Fiyat nedir?", context=_make_context())

    assert result.status == ValidationStatus.VALID, "Asistanda sayi-topraklama BLOK degil — status VALID olmali"
    assert result.number_flag is True
    assert len(result.ungrounded_numbers) > 0


# ---------------------------------------------------------------------------
# Test 5: Conversation gecmisi
# ---------------------------------------------------------------------------


def test_conversation_add_and_history(tmp_path):
    """Basarili yanit -> conversation'a eklenir; ret=True -> eklenmez."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={
            ("assistant-v1", "_any_"): [
                _valid_answer_json("Yukseklik 180.0 mm."),
                _rejection_json("Konu disi."),
            ]
        }
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )

    # 1. gecerli soru -> eklenmeli
    role.ask("Yukseklik?", _make_context())
    assert len(role.conversation.turns) == 1

    # 2. ret soru -> eklenmemeli
    role.ask("Bitcoin?", _make_context())
    assert len(role.conversation.turns) == 1  # hala 1


def test_conversation_max_turns():
    """max_turns asiminda en eski sildir."""
    conv = Conversation(max_turns=3)
    for i in range(5):
        conv.add(soru=f"S{i}", cevap_md=f"C{i}")
    assert len(conv.turns) == 3
    assert conv.turns[0].soru == "S2"
    assert conv.turns[-1].soru == "S4"


def test_conversation_to_history_text_empty():
    """Bos conversation bos metin dondurur."""
    conv = Conversation()
    assert conv.to_history_text() == ""


def test_conversation_to_history_text_nonempty():
    """Dolu conversation gecmis metni olusturur."""
    conv = Conversation()
    conv.add("Soru1", "Cevap1")
    text = conv.to_history_text()
    assert "Soru1" in text
    assert "Cevap1" in text


# ---------------------------------------------------------------------------
# Test 6: LLM bozuk JSON -> fallback
# ---------------------------------------------------------------------------


def test_assistant_invalid_json_fallback(tmp_path):
    """LLM bozuk metin dondururse -> INVALID + fallback."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): ["bozuk", "yine bozuk", "hala bozuk"]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask("Herhangi bir soru?", _make_context())

    assert result.status == ValidationStatus.INVALID
    assert result.fallback is not None
    assert result.data is None


# ---------------------------------------------------------------------------
# Test 7: AssistantResult ozellikleri
# ---------------------------------------------------------------------------


def test_assistant_result_properties(tmp_path):
    """AssistantResult proxy ozellikleri dogru calisir."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): [_valid_answer_json()]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask("Test sorusu", _make_context())

    assert isinstance(result, AssistantResult)
    assert result.status == ValidationStatus.VALID
    assert isinstance(result.audit_ref, str) and result.audit_ref != ""
    assert result.number_flag is False  # 180.0 baglamda var
    assert result.unknown_citation_ids == []


# ---------------------------------------------------------------------------
# Test 8: Normalizasyon — alintilar[].kaynak_id dict ise id string'e indirgenir
# ---------------------------------------------------------------------------


def test_assistant_normalization_dict_kaynak_id_accepted(tmp_path):
    """Model alintilar'da kaynak_id yerine dict kopyalarsa normalizasyon id string'e ceker -> VALID."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # Kucuk model halusinasyonu: kaynak_id string yerine tam kaynak nesnesi
    hallucinated_json = json.dumps({
        "cevap_md": "B001 yuksekligi 180.0 mm.",
        "alintilar": [
            {
                "kaynak_id": {"id": "yerlesim#B001", "tip": "yerlesim", "icerik": "Yukseklik: 180.0 mm"},
                "konum": "Yukseklik: 180.0 mm",
            }
        ],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={("assistant-v1", "_any_"): [hallucinated_json]}
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask("B001 yuksekligi nedir?", _make_context())

    # Normalizasyon sayesinde schema gecmeli
    assert result.status == ValidationStatus.VALID, (
        f"Normalizasyon sonrasi VALID beklendi, aldi: {result.status}. "
        f"Fallback: {result.fallback}"
    )
    assert result.data is not None
    # kaynak_id string'e indirgenmeli
    alintilar = result.data.get("alintilar", [])
    assert len(alintilar) == 1
    assert alintilar[0]["kaynak_id"] == "yerlesim#B001"


def test_assistant_normalization_idless_kaynak_id_stays_invalid(tmp_path):
    """kaynak_id id'siz dict ise normalizasyon dokunmaz -> schema hatasi surmeli."""
    registry = _make_registry()
    audit = _make_audit(tmp_path)
    role_cfg = _make_role_cfg()

    # id anahtari olmayan dict kaynak_id — normalizasyon yapmamali
    idless_json = json.dumps({
        "cevap_md": "Test yanit.",
        "alintilar": [
            {
                "kaynak_id": {"tip": "yerlesim", "icerik": "yok"},  # id yok
                "konum": "bir yer",
            }
        ],
        "onerilen_aksiyonlar": [],
        "ret": False,
        "ret_nedeni": None,
    }, ensure_ascii=False)

    provider = FakeProvider(
        fixture_map={
            ("assistant-v1", "_any_"): [idless_json, idless_json, idless_json]
        }
    )

    role = AssistantRole(
        provider=provider, registry=registry, audit=audit, role_cfg=role_cfg
    )
    result = role.ask("Test sorusu.", _make_context())

    # id'siz dict schema'yi gecemiyor — INVALID olmali
    assert result.status == ValidationStatus.INVALID, (
        "id'siz dict normalizasyon sonrasi hala gecersiz olmali"
    )
