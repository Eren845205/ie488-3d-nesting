"""Prompt sablon kayit defteri + lockfile hash kapisi (PLAN_LLM.md L0.4).

Sablon dizin yapisi (prompts/<rol>/):
    meta.json      : {id, version, model_hint, changelog}
    system.md      : sistem talimat sablonu ({{few_shot}}, {{input}}, {{context}} yuvalari)
    schema.json    : cikti JSON semasi
    examples/      : ex01_input.json, ex01_output.json, ...

Lockfile (prompts/lock.json):
    {
      "<sablon_id>": {
        "version": "1.0",
        "content_hash": "<sha256-hex>",
        "last_eval_ref": "results/llm_eval_report_20260613.md"
      }
    }

Hash hesaplama: system.md + tumuyle birlestirilmis examples + schema.json icerikleri
SHA-256'ya verilir (sistematik siralama ile deterministik).

Hash uyusmazligi kurali:
    Yuklenirken lock.json'daki kayitli hash ile hesaplanan hash FARKLI ise
    PromptHashMismatchError firlatilir. Test FAIL.
    Bu mekanizma: "prompt degisti -> versiyon artir + eval kos" disiplinini saglar.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hatalar
# ---------------------------------------------------------------------------


class PromptError(Exception):
    """Temel prompt yukle/doldur hatasi."""


class MissingSlotError(PromptError):
    """Sablonda yer alan bir yuva doldurulamamis."""


class PromptHashMismatchError(PromptError):
    """Sablon icerigi lock.json'daki hash ile uyusmuyor."""


# ---------------------------------------------------------------------------
# Veri yapisi
# ---------------------------------------------------------------------------


class PromptTemplate:
    """Tek bir sablon yuklemesini temsil eder.

    Alanlar (salt okunur):
        id        : sablon kimlik kodu (meta.json'dan)
        version   : sablon versiyonu
        system    : ham sistem talimat metni (yuvalari hala doldurulmamis)
        schema    : JSON Schema dict
        examples  : [(input_dict, output_dict), ...] (dogal sirada)
        content_hash : SHA-256 hex (hesaplanan)
    """

    def __init__(
        self,
        id: str,
        version: str,
        system: str,
        schema: Dict[str, Any],
        examples: List[tuple],
        content_hash: str,
    ) -> None:
        self.id = id
        self.version = version
        self.system = system
        self.schema = schema
        self.examples = examples
        self.content_hash = content_hash

    def render(self, slots: Dict[str, str]) -> str:
        """Sablona yuvalari doldurur.

        Parametreler
        ------------
        slots : {"few_shot": "...", "input": "...", "context": "..."}

        Hatalar
        -------
        MissingSlotError : sistem.md'de {{yuva}} var ama slots'ta yok
        """
        text = self.system
        import re
        found_slots = set(re.findall(r"\{\{(\w+)\}\}", text))
        missing = found_slots - set(slots.keys())
        if missing:
            raise MissingSlotError(
                f"Sablon {self.id!r}: eksik yuvalar {sorted(missing)}. "
                f"Saglanan yuvalar: {sorted(slots.keys())}"
            )
        for key, val in slots.items():
            text = text.replace("{{" + key + "}}", val)
        return text

    def few_shot_text(self) -> str:
        """examples listesinden birlestirilmis few-shot metni olustur."""
        parts = []
        for i, (inp, out) in enumerate(self.examples, start=1):
            parts.append(
                f"## Ornek {i}\n"
                f"### Girdi\n```json\n{json.dumps(inp, ensure_ascii=False, indent=2)}\n```\n"
                f"### Cikti\n```json\n{json.dumps(out, ensure_ascii=False, indent=2)}\n```"
            )
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Kayit defteri
# ---------------------------------------------------------------------------


class PromptRegistry:
    """Prompts dizininden sablon yukleme + lockfile dogrulama.

    Parametreler
    ------------
    prompts_dir  : prompts/ kok dizini
    lock_path    : lock.json dosya yolu (None ise <prompts_dir>/lock.json)
    enforce_lock : True ise hash uyusmazligi PromptHashMismatchError firlatir
    """

    def __init__(
        self,
        prompts_dir: str | Path,
        lock_path: Optional[str | Path] = None,
        enforce_lock: bool = True,
    ) -> None:
        self._root = Path(prompts_dir)
        self._lock_path = Path(lock_path) if lock_path else self._root / "lock.json"
        self._enforce_lock = enforce_lock
        self._lock: Dict[str, Any] = self._load_lock()

    # ------------------------------------------------------------------
    # Yukle
    # ------------------------------------------------------------------

    def load(self, role: str) -> PromptTemplate:
        """Rol icin sablon yukle, hash dogrula ve PromptTemplate dondur."""
        role_dir = self._root / role
        if not role_dir.is_dir():
            raise PromptError(
                f"Sablon dizini bulunamadi: {role_dir}. "
                f"Tanimli roller: {[d.name for d in self._root.iterdir() if d.is_dir()]}"
            )

        meta = self._load_json(role_dir / "meta.json")
        try:
            tpl_id = meta["id"]
            tpl_version = meta["version"]
        except KeyError as exc:
            raise PromptError(
                f"{role_dir / 'meta.json'}: zorunlu alan eksik — {exc}."
            ) from exc
        system = (role_dir / "system.md").read_text(encoding="utf-8")
        schema = self._load_json(role_dir / "schema.json")
        examples = self._load_examples(role_dir / "examples")

        content_hash = _compute_hash(system, examples, schema)
        tpl = PromptTemplate(
            id=tpl_id,
            version=tpl_version,
            system=system,
            schema=schema,
            examples=examples,
            content_hash=content_hash,
        )

        if self._enforce_lock:
            self._check_lock(tpl)

        return tpl

    # ------------------------------------------------------------------
    # Lockfile
    # ------------------------------------------------------------------

    def _load_lock(self) -> Dict[str, Any]:
        if not self._lock_path.exists():
            return {}
        return self._load_json(self._lock_path)

    def _check_lock(self, tpl: PromptTemplate) -> None:
        """Lockfile'daki hash ile hesaplanan hash'i karsilastirir."""
        if tpl.id not in self._lock:
            logger.warning(
                "Sablon %r lock.json'da kayitli degil — atlananiyor.", tpl.id
            )
            return
        recorded_hash = self._lock[tpl.id].get("content_hash", "")
        if not recorded_hash:
            raise PromptHashMismatchError(
                f"Sablon {tpl.id!r} icin lock.json'da content_hash bos veya eksik. "
                "update_lock() cagrilmadan enforce_lock kullanilamaz."
            )
        if recorded_hash != tpl.content_hash:
            raise PromptHashMismatchError(
                f"Sablon {tpl.id!r} icerigi degisti. "
                f"Kayitli hash: {recorded_hash!r}, hesaplanan: {tpl.content_hash!r}. "
                "Versiyonu artirin ve 'scripts/llm_eval.py' ile yeniden degerlendirin."
            )

    def update_lock(self, tpl: PromptTemplate, eval_ref: str = "") -> None:
        """Lock dosyasini gunceller (yeni sablon veya versiyon artisi sonrasi)."""
        self._lock[tpl.id] = {
            "version": tpl.version,
            "content_hash": tpl.content_hash,
            "last_eval_ref": eval_ref,
        }
        self._lock_path.write_text(
            json.dumps(self._lock, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Yardimci
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise PromptError(f"Dosya bulunamadi: {path}")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _load_examples(examples_dir: Path) -> List[tuple]:
        """examples/ dizininden cift halinde yukler: exNN_input + exNN_output."""
        if not examples_dir.is_dir():
            return []
        pairs: Dict[str, Dict] = {}
        for f in sorted(examples_dir.iterdir()):
            if not f.suffix == ".json":
                continue
            name = f.stem  # "ex01_input" / "ex01_output"
            if "_input" in name:
                key = name.replace("_input", "")
                pairs.setdefault(key, {})["input"] = json.loads(f.read_text(encoding="utf-8"))
            elif "_output" in name:
                key = name.replace("_output", "")
                pairs.setdefault(key, {})["output"] = json.loads(f.read_text(encoding="utf-8"))
        result = []
        for key in sorted(pairs.keys()):
            pair = pairs[key]
            if "input" in pair and "output" in pair:
                result.append((pair["input"], pair["output"]))
        return result


# ---------------------------------------------------------------------------
# Hash hesaplama
# ---------------------------------------------------------------------------


def _compute_hash(
    system: str,
    examples: List[tuple],
    schema: Dict[str, Any],
) -> str:
    """system.md + examples + schema birlesik SHA-256 (deterministik)."""
    h = hashlib.sha256()
    h.update(system.encode("utf-8"))
    for inp, out in examples:
        h.update(json.dumps(inp, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        h.update(json.dumps(out, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    h.update(json.dumps(schema, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()
