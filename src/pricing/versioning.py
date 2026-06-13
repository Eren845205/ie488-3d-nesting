"""Teklif / kural versiyonu iz kaydi — append-only JSONL (PLAN_DEMO1.md 7.4).

DB YOK. Her kayit tek JSON satirina yazilir; log dosyasi append-only'dir.
Teklif kaydinda hangi kural versiyonuyla hesaplandigi bilgisi tutulur;
bu sayede gecmise donuk sorgu mumkundur.

Dosya yapisi (her satir bagimsiz JSON nesnesi)
----------------------------------------------
{"record_type": "quote", "quote_id": "Q-001", "rule_set_version": "1.0",
 "rule_set_name": "...", "total_price": 1234.5, "inputs": {...},
 "breakdown": ["...", "..."], "timestamp": "2026-06-12T..."}

{"record_type": "rule_override", "original_version": "1.0",
 "new_version": "1.1", "rule_id": "r1", "changed_params": {...},
 "reason": "...", "timestamp": "..."}

{"record_type": "quote_override", "quote_id": "Q-001",
 "original_price": 1000.0, "overridden_price": 950.0,
 "reason": "...", "operator": "...", "timestamp": "..."}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.pricing.engine import PricingResult
from src.pricing.overrides import QuoteOverrideRecord, RuleOverrideRecord


# ---------------------------------------------------------------------------
# Yardimci
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# JSONL append
# ---------------------------------------------------------------------------


def _append_record(log_path: str, record: Dict[str, Any]) -> None:
    """Kaydi JSONL dosyasina ekler (append-only)."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Teklif kaydi yazma
# ---------------------------------------------------------------------------


def append_quote_record(
    log_path: str,
    quote_id: str,
    result: PricingResult,
) -> None:
    """Hesap sonucunu iz kaydina yazar.

    Parametreler
    ------------
    log_path : JSONL log dosyasinin yolu (yoksa olusturulur)
    quote_id : Teklifin benzersiz kimligi
    result   : PricingEngine.calculate() donus degeri

    Hata
    ----
    ValueError : ayni quote_id daha once yazilmissa (duplikat yasak)
    """
    if find_quote_record(log_path, quote_id) is not None:
        raise ValueError(f"quote_id zaten mevcut: {quote_id!r}")
    record: Dict[str, Any] = {
        "record_type": "quote",
        "quote_id": quote_id,
        "rule_set_version": result.rule_set_version,
        "rule_set_name": result.rule_set_name,
        "total_price": result.total_price,
        "inputs": result.inputs,
        "breakdown": [str(line) for line in result.breakdown],
        "timestamp": _now_iso(),
    }
    _append_record(log_path, record)


# ---------------------------------------------------------------------------
# Kural override kaydi yazma
# ---------------------------------------------------------------------------


def append_rule_override_record(
    log_path: str,
    record: RuleOverrideRecord,
) -> None:
    """Kural duzeyi override'i iz kaydina yazar."""
    _append_record(
        log_path,
        {
            "record_type": "rule_override",
            "original_version": record.original_rule_set_version,
            "new_version": record.new_rule_set_version,
            "rule_id": record.rule_id,
            "changed_params": record.changed_params,
            "reason": record.reason,
            "timestamp": record.timestamp,
        },
    )


# ---------------------------------------------------------------------------
# Teklif override kaydi yazma
# ---------------------------------------------------------------------------


def append_quote_override_record(
    log_path: str,
    record: QuoteOverrideRecord,
) -> None:
    """Teklif duzeyi override'i iz kaydina yazar."""
    _append_record(
        log_path,
        {
            "record_type": "quote_override",
            "quote_id": record.quote_id,
            "original_price": record.original_price,
            "overridden_price": record.overridden_price,
            "reason": record.reason,
            "operator": record.operator,
            "original_breakdown_summary": record.original_breakdown_summary,
            "timestamp": record.timestamp,
        },
    )


# ---------------------------------------------------------------------------
# Sorgulama
# ---------------------------------------------------------------------------


def read_all_records(log_path: str) -> List[Dict[str, Any]]:
    """JSONL log dosyasindaki tum kayitlari okur."""
    path = Path(log_path)
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def find_quote_record(
    log_path: str,
    quote_id: str,
) -> Optional[Dict[str, Any]]:
    """Belirli bir teklifin ilk kaydini dondurur.

    Bu sayede teklifin HANGI kural versiyonuyla hesaplandigi geri okunabilir.
    """
    for record in read_all_records(log_path):
        if record.get("record_type") == "quote" and record.get("quote_id") == quote_id:
            return record
    return None


def find_rule_set_version_for_quote(
    log_path: str,
    quote_id: str,
) -> Optional[str]:
    """Teklifin hesaplandigi kural seti versiyonunu dondurur.

    Donus: versiyon etiketi str, ya da kayit bulunamazsa None.
    """
    record = find_quote_record(log_path, quote_id)
    if record is None:
        return None
    return record.get("rule_set_version")


def find_quote_overrides(
    log_path: str,
    quote_id: str,
) -> List[Dict[str, Any]]:
    """Belirli teklife ait tum quote_override kayitlarini dondurur."""
    return [
        r
        for r in read_all_records(log_path)
        if r.get("record_type") == "quote_override"
        and r.get("quote_id") == quote_id
    ]
