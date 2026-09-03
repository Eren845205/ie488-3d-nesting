"""Testler: src/llm/prompts.py — PLAN_LLM.md L0.4.

Kapsanan:
  - Sablon yukle (tmp_path fixture ile)
  - Yuva doldurma: dogru sonuc
  - Yuva doldurma: eksik yuva -> MissingSlotError
  - Hash deterministik (ayni icerik -> ayni hash)
  - Hash farklilastirma (icerik degisirse -> farkli hash)
  - Lockfile kontrolu: eslesme -> gecer
  - Lockfile kontrolu: uyusmazlik -> PromptHashMismatchError
  - Lockfile yoksa uyari (hata yok — yeni sablon)
  - update_lock() lockfile'i gunceller
  - examples/ dizinden cift yukleme
  - few_shot_text() ornekleri birlestiriyor
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.llm.prompts import (
    MissingSlotError,
    PromptHashMismatchError,
    PromptRegistry,
    PromptTemplate,
    _compute_hash,
)


# ---------------------------------------------------------------------------
# Yardimci: minimal sablon dizini olustur
# ---------------------------------------------------------------------------


def _make_template_dir(
    tmp_path: Path,
    role: str = "test_role",
    system_content: str = "sistem {{few_shot}} {{input}}",
    schema: dict = None,
    examples: list = None,
    meta: dict = None,
) -> Path:
    role_dir = tmp_path / "prompts" / role
    role_dir.mkdir(parents=True)

    _meta = meta or {"id": f"{role}-v1", "version": "1.0", "model_hint": "test"}
    (role_dir / "meta.json").write_text(json.dumps(_meta), encoding="utf-8")
    (role_dir / "system.md").write_text(system_content, encoding="utf-8")
    (role_dir / "schema.json").write_text(
        json.dumps(schema or {"type": "object"}), encoding="utf-8"
    )

    if examples:
        ex_dir = role_dir / "examples"
        ex_dir.mkdir()
        for i, (inp, out) in enumerate(examples, start=1):
            prefix = f"ex{i:02d}"
            (ex_dir / f"{prefix}_input.json").write_text(
                json.dumps(inp), encoding="utf-8"
            )
            (ex_dir / f"{prefix}_output.json").write_text(
                json.dumps(out), encoding="utf-8"
            )

    return role_dir


def _make_registry(tmp_path: Path, enforce_lock: bool = False) -> PromptRegistry:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    return PromptRegistry(prompts_dir, enforce_lock=enforce_lock)


# ---------------------------------------------------------------------------
# Sablon yukle
# ---------------------------------------------------------------------------


def test_load_template(tmp_path):
    _make_template_dir(tmp_path, "my_role", system_content="Sistem {{few_shot}} {{input}}")
    registry = _make_registry(tmp_path)
    tpl = registry.load("my_role")
    assert tpl.id == "my_role-v1"
    assert tpl.version == "1.0"
    assert "{{few_shot}}" in tpl.system


def test_load_missing_role_raises(tmp_path):
    registry = _make_registry(tmp_path)
    with pytest.raises(Exception, match="bulunamadi"):
        registry.load("nonexistent")


# ---------------------------------------------------------------------------
# Yuva doldurma
# ---------------------------------------------------------------------------


def test_render_fills_slots(tmp_path):
    _make_template_dir(tmp_path, "r1", system_content="Giris: {{input}} Ornek: {{few_shot}}")
    registry = _make_registry(tmp_path)
    tpl = registry.load("r1")
    rendered = tpl.render({"input": "TEST_INPUT", "few_shot": "ORNEKLER"})
    assert "TEST_INPUT" in rendered
    assert "ORNEKLER" in rendered
    assert "{{" not in rendered


def test_render_missing_slot_raises(tmp_path):
    _make_template_dir(tmp_path, "r2", system_content="{{input}} {{context}}")
    registry = _make_registry(tmp_path)
    tpl = registry.load("r2")
    with pytest.raises(MissingSlotError, match="context"):
        tpl.render({"input": "var"})
        # context eksik -> hata


def test_render_extra_slots_ignored(tmp_path):
    """Sablonda olmayan extra slot verilmesi hata vermez."""
    _make_template_dir(tmp_path, "r3", system_content="{{input}}")
    registry = _make_registry(tmp_path)
    tpl = registry.load("r3")
    rendered = tpl.render({"input": "x", "extra": "y"})
    assert rendered == "x"


# ---------------------------------------------------------------------------
# Hash deterministik
# ---------------------------------------------------------------------------


def test_hash_deterministic(tmp_path):
    _make_template_dir(tmp_path, "h1")
    reg = _make_registry(tmp_path)
    tpl1 = reg.load("h1")
    tpl2 = reg.load("h1")
    assert tpl1.content_hash == tpl2.content_hash


def test_hash_changes_with_system_content(tmp_path):
    _make_template_dir(tmp_path, "hA", system_content="ilk icerik {{input}}")
    regA = _make_registry(tmp_path)
    tplA = regA.load("hA")

    # sistem.md icerigini degistir
    (tmp_path / "prompts" / "hA" / "system.md").write_text(
        "degisen icerik {{input}}", encoding="utf-8"
    )
    regB = _make_registry(tmp_path)
    tplB = regB.load("hA")

    assert tplA.content_hash != tplB.content_hash


def test_hash_changes_with_examples(tmp_path):
    _make_template_dir(
        tmp_path, "hEx",
        examples=[
            ({"a": 1}, {"b": 2}),
        ]
    )
    reg1 = _make_registry(tmp_path)
    tpl1 = reg1.load("hEx")

    # ornek ekle
    ex_dir = tmp_path / "prompts" / "hEx" / "examples"
    (ex_dir / "ex02_input.json").write_text(json.dumps({"c": 3}), encoding="utf-8")
    (ex_dir / "ex02_output.json").write_text(json.dumps({"d": 4}), encoding="utf-8")

    reg2 = _make_registry(tmp_path)
    tpl2 = reg2.load("hEx")
    assert tpl1.content_hash != tpl2.content_hash


# ---------------------------------------------------------------------------
# Lockfile kontrolu
# ---------------------------------------------------------------------------


def test_lock_match_passes(tmp_path):
    _make_template_dir(tmp_path, "locked_role")
    reg_no_lock = _make_registry(tmp_path, enforce_lock=False)
    tpl = reg_no_lock.load("locked_role")

    # Lock yaz
    lock_path = tmp_path / "prompts" / "lock.json"
    lock_path.write_text(
        json.dumps({
            tpl.id: {
                "version": tpl.version,
                "content_hash": tpl.content_hash,
                "last_eval_ref": "",
            }
        }),
        encoding="utf-8",
    )

    reg_with_lock = PromptRegistry(
        tmp_path / "prompts", lock_path=lock_path, enforce_lock=True
    )
    loaded = reg_with_lock.load("locked_role")
    assert loaded.content_hash == tpl.content_hash


def test_lock_mismatch_raises(tmp_path):
    _make_template_dir(tmp_path, "mismatch_role")
    reg = _make_registry(tmp_path, enforce_lock=False)
    tpl = reg.load("mismatch_role")

    # Kasitli yanlis hash yaz
    lock_path = tmp_path / "prompts" / "lock.json"
    lock_path.write_text(
        json.dumps({
            tpl.id: {
                "version": tpl.version,
                "content_hash": "aaaaaa_yanlis_hash",
                "last_eval_ref": "",
            }
        }),
        encoding="utf-8",
    )

    reg_with_lock = PromptRegistry(
        tmp_path / "prompts", lock_path=lock_path, enforce_lock=True
    )
    with pytest.raises(PromptHashMismatchError, match="Versiyonu"):
        reg_with_lock.load("mismatch_role")


def test_lock_missing_entry_logs_warning_not_error(tmp_path, caplog):
    """Lockfile var ama sablon kaydedilmemisse uyari verir, hata vermez."""
    _make_template_dir(tmp_path, "new_role")
    lock_path = tmp_path / "prompts" / "lock.json"
    lock_path.write_text(json.dumps({}), encoding="utf-8")

    reg = PromptRegistry(
        tmp_path / "prompts", lock_path=lock_path, enforce_lock=True
    )
    import logging
    with caplog.at_level(logging.WARNING, logger="src.llm.prompts"):
        tpl = reg.load("new_role")
    assert tpl.id == "new_role-v1"


# ---------------------------------------------------------------------------
# update_lock
# ---------------------------------------------------------------------------


def test_update_lock_writes_correct_entry(tmp_path):
    _make_template_dir(tmp_path, "update_role")
    reg = _make_registry(tmp_path, enforce_lock=False)
    tpl = reg.load("update_role")

    reg.update_lock(tpl, eval_ref="results/eval_20260613.md")

    lock_path = tmp_path / "prompts" / "lock.json"
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    entry = data[tpl.id]
    assert entry["content_hash"] == tpl.content_hash
    assert entry["version"] == tpl.version
    assert entry["last_eval_ref"] == "results/eval_20260613.md"


# ---------------------------------------------------------------------------
# examples/ dizini
# ---------------------------------------------------------------------------


def test_examples_loaded_in_order(tmp_path):
    examples = [
        ({"mail": "birinci"}, {"parcalar": []}),
        ({"mail": "ikinci"}, {"parcalar": [{"ad": "A"}]}),
    ]
    _make_template_dir(tmp_path, "ex_role", examples=examples)
    reg = _make_registry(tmp_path)
    tpl = reg.load("ex_role")
    assert len(tpl.examples) == 2
    assert tpl.examples[0][0]["mail"] == "birinci"
    assert tpl.examples[1][0]["mail"] == "ikinci"


def test_examples_dir_missing_returns_empty(tmp_path):
    _make_template_dir(tmp_path, "no_ex_role")
    reg = _make_registry(tmp_path)
    tpl = reg.load("no_ex_role")
    assert tpl.examples == []


# ---------------------------------------------------------------------------
# few_shot_text
# ---------------------------------------------------------------------------


def test_few_shot_text_contains_examples(tmp_path):
    examples = [({"q": "soru"}, {"a": "cevap"})]
    _make_template_dir(tmp_path, "fs_role", examples=examples)
    reg = _make_registry(tmp_path)
    tpl = reg.load("fs_role")
    fs = tpl.few_shot_text()
    assert "soru" in fs
    assert "cevap" in fs
    assert "Ornek 1" in fs


def test_few_shot_text_empty_when_no_examples(tmp_path):
    _make_template_dir(tmp_path, "empty_role")
    reg = _make_registry(tmp_path)
    tpl = reg.load("empty_role")
    fs = tpl.few_shot_text()
    assert fs == ""


# ---------------------------------------------------------------------------
# C1: bos hash + enforce_lock=True -> PromptHashMismatchError
# ---------------------------------------------------------------------------


def test_empty_hash_with_enforce_lock_raises(tmp_path):
    """lock.json'da content_hash bos iken enforce_lock=True -> PromptHashMismatchError."""
    _make_template_dir(tmp_path, "empty_hash_role")
    reg_no_lock = _make_registry(tmp_path, enforce_lock=False)
    tpl = reg_no_lock.load("empty_hash_role")

    # Bos hash ile lock kaydi yaz
    lock_path = tmp_path / "prompts" / "lock.json"
    lock_path.write_text(
        json.dumps({
            tpl.id: {
                "version": tpl.version,
                "content_hash": "",
                "last_eval_ref": "",
            }
        }),
        encoding="utf-8",
    )

    reg_with_lock = PromptRegistry(
        tmp_path / "prompts", lock_path=lock_path, enforce_lock=True
    )
    with pytest.raises(PromptHashMismatchError, match="update_lock"):
        reg_with_lock.load("empty_hash_role")


# ---------------------------------------------------------------------------
# L1: meta.json eksik alan -> PromptError (KeyError degil)
# ---------------------------------------------------------------------------


def test_missing_meta_field_raises_prompt_error(tmp_path):
    """meta.json'da id veya version eksikse KeyError degil PromptError firlatilmali."""
    from src.llm.prompts import PromptError

    # id alani olmayan meta.json ile sablon olustur
    role_dir = tmp_path / "prompts" / "no_id_role"
    role_dir.mkdir(parents=True)
    (role_dir / "meta.json").write_text(
        json.dumps({"version": "1.0"}), encoding="utf-8"
    )
    (role_dir / "system.md").write_text("sistem {{input}}", encoding="utf-8")
    (role_dir / "schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )

    reg = _make_registry(tmp_path, enforce_lock=False)
    with pytest.raises(PromptError, match="meta.json"):
        reg.load("no_id_role")
