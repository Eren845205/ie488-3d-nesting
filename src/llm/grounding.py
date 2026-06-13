"""Topraklama cekirde gi — PLAN_LLM.md L0.8.

SourceDoc  : tek bir kaynak belge (deterministik motor ciktisi).
GroundedContext : bir is icin toplanmis kaynaklar.
Adapterler:
    from_solve_result()    -> SolveResult'ten SourceDoc
    from_pricing_result()  -> PricingResult'ten SourceDoc'lar (breakdown satirlari)
    from_schedule_report() -> cizelgeleme raporu -> SourceDoc

Sayi-topraklama dogrulayicisi:
    LLM ciktisindaki sayisal degerler atif yapilan SourceDoc iceriklerinde gecmeli.
    Normalize karsilastirma: 181.5 ~ 181,5 ~ "181.5 mm"
    Rapor rolunde: BLOK (ihlal -> INVALID)
    Asistan rolunde: UYARI + bayrak
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# SourceDoc
# ---------------------------------------------------------------------------


@dataclass
class SourceDoc:
    """Tek bir deterministik kaynak belge.

    Alanlar
    -------
    id       : benzersiz kaynak kimlik kodu (orn. "yerlesim#bin1", "fiyat#r1")
    tip      : kaynak tipi: "yerlesim" | "fiyat" | "termin" | "telemetri" | "siparis_notu"
    icerik   : kaynak metni (deterministik motor ciktisi; markdown tablo vs.)
    uretici  : icerik hangi modul/fonksiyondan geldi (orn. "nesting3d.sa3d")
    versiyon : kaynak datanin versiyonu (opsiyonel)
    """

    id: str
    tip: str
    icerik: str
    uretici: str
    versiyon: str = ""

    VALID_TYPES = frozenset(
        {"yerlesim", "fiyat", "termin", "telemetri", "siparis_notu"}
    )

    def validate(self) -> None:
        if not self.id:
            raise ValueError("SourceDoc: id bos olamaz.")
        if self.tip not in self.VALID_TYPES:
            raise ValueError(
                f"SourceDoc: gecersiz tip {self.tip!r}. "
                f"Gecerli tipler: {sorted(self.VALID_TYPES)}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tip": self.tip,
            "icerik": self.icerik,
            "uretici": self.uretici,
            "versiyon": self.versiyon,
        }


# ---------------------------------------------------------------------------
# GroundedContext
# ---------------------------------------------------------------------------


@dataclass
class GroundedContext:
    """Bir LLM cagrisi icin toplanmis kaynaklar.

    Alanlar
    -------
    is_id           : ilgili is kimlik kodu
    kaynaklar       : SourceDoc listesi
    olusturma_zamani: ISO timestamp
    """

    is_id: str
    kaynaklar: List[SourceDoc] = field(default_factory=list)
    olusturma_zamani: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def kaynak_by_id(self, source_id: str) -> Optional[SourceDoc]:
        """Kimlik kodu ile kaynak bul."""
        for k in self.kaynaklar:
            if k.id == source_id:
                return k
        return None

    def kaynak_ids(self) -> List[str]:
        return [k.id for k in self.kaynaklar]

    def to_context_text(self) -> str:
        """LLM prompt icin okunabilir kaynak metni olustur."""
        parts = []
        for doc in self.kaynaklar:
            parts.append(f"### [{doc.id}] ({doc.tip})\n{doc.icerik}")
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Adapterler
# ---------------------------------------------------------------------------


def from_solve_result(solve_result: Any) -> SourceDoc:
    """SolveResult (nesting3d) -> SourceDoc.

    SolveResult'ten beklenen alanlar (duck-typing):
        .bin_id veya id — bin kimlik kodu
        .height_mm      — yukseklik (float)
        .utilization    — doluluk orani (0-1)
        .placements     — Placement3D listesi (part_id, name, x, y, z, orientation_idx)
        .solver_name    — cozucu adi
        .seed           — seed degeri (opsiyonel)
    """
    bin_id = getattr(solve_result, "bin_id", None) or getattr(solve_result, "id", "bin")
    height = getattr(solve_result, "height_mm", 0.0)
    util = getattr(solve_result, "utilization", 0.0)
    solver = getattr(solve_result, "solver_name", "")
    seed = getattr(solve_result, "seed", None)
    placements = getattr(solve_result, "placements", [])

    rows = []
    for p in placements:
        part_id = getattr(p, "part_id", "")
        name = getattr(p, "name", "")
        x = getattr(p, "x", 0)
        y = getattr(p, "y", 0)
        z = getattr(p, "z", 0)
        ori = getattr(p, "orientation_idx", 0)
        rows.append(f"| {part_id} | {name} | {x} | {y} | {z} | {ori} |")

    table_header = "| part_id | name | x | y | z | orientation |\n|---|---|---|---|---|---|"
    table = table_header + "\n" + "\n".join(rows) if rows else "(yerlesim yok)"

    icerik = (
        f"Yukseklik: {height} mm\n"
        f"Doluluk: {util:.1%}\n"
        f"Cozucu: {solver}"
        + (f" (seed={seed})" if seed is not None else "")
        + f"\n\n{table}"
    )

    return SourceDoc(
        id=f"yerlesim#{bin_id}",
        tip="yerlesim",
        icerik=icerik,
        uretici=solver or "nesting3d",
    )


def from_pricing_result(pricing_result: Any) -> List[SourceDoc]:
    """PricingResult (pricing.engine) -> [SourceDoc] (breakdown satirlari).

    PricingResult'ten beklenen alanlar:
        .total_price    — nihai fiyat
        .breakdown      — BreakdownLine listesi
        .rule_set_name  — kural seti adi
        .rule_set_version
    """
    total = getattr(pricing_result, "total_price", 0.0)
    breakdown = getattr(pricing_result, "breakdown", [])
    rs_name = getattr(pricing_result, "rule_set_name", "")
    rs_version = getattr(pricing_result, "rule_set_version", "")

    docs: List[SourceDoc] = []
    for line in breakdown:
        rule_id = getattr(line, "rule_id", "")
        rule_type = getattr(line, "rule_type", "")
        rule_desc = getattr(line, "rule_description", "")
        input_field = getattr(line, "input_field", None)
        input_value = getattr(line, "input_value", None)
        intermediate = getattr(line, "intermediate_value", 0.0)
        subtotal = getattr(line, "subtotal_after", 0.0)
        note = getattr(line, "note", "")

        field_str = f"{input_field}={input_value}" if input_field else "-"
        icerik = (
            f"Kural: {rule_id} ({rule_type})\n"
            f"Aciklama: {rule_desc}\n"
            f"Girdi: {field_str}\n"
            f"Ara deger: {intermediate:.4f}\n"
            f"Toplam sonra: {subtotal:.4f}\n"
            f"Not: {note}\n"
            f"Nihai toplam: {total}"
        )

        docs.append(
            SourceDoc(
                id=f"fiyat#{rule_id}",
                tip="fiyat",
                icerik=icerik,
                uretici="pricing.engine",
                versiyon=rs_version,
            )
        )
    return docs


def from_schedule_report(schedule_report: Any) -> SourceDoc:
    """Cizelgeleme raporu -> SourceDoc.

    schedule_report'tan beklenen: .markdown veya .warnings listesi.
    """
    markdown = getattr(schedule_report, "markdown", None)
    if markdown is None:
        # dict gibi davranabilir
        if isinstance(schedule_report, dict):
            markdown = schedule_report.get("markdown", str(schedule_report))
        else:
            markdown = str(schedule_report)

    warnings = getattr(schedule_report, "warnings", [])
    warnings_text = ""
    if warnings:
        lines = []
        for w in warnings:
            oid = getattr(w, "order_id", str(w))
            delay = getattr(w, "delay_days", "")
            lines.append(f"- {oid}: {delay} gun gecikme")
        warnings_text = "\nUyarilar:\n" + "\n".join(lines)

    return SourceDoc(
        id="termin#cizelge",
        tip="termin",
        icerik=markdown + warnings_text,
        uretici="scheduling.report",
    )


# ---------------------------------------------------------------------------
# Sayi-topraklama dogrulayicisi
# ---------------------------------------------------------------------------


def _normalize_number(s: str) -> str:
    """181,5 -> 181.5; bogaz ve birim kaldir."""
    s = s.replace(",", ".")
    s = re.sub(r"[^\d.]", "", s)
    return s


def extract_numbers_from_text(text: str) -> List[str]:
    """Metindeki sayisal degerleri cikart (tam ve kesirli)."""
    raw = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
    return [_normalize_number(r) for r in raw if _normalize_number(r)]


@dataclass
class NumberGroundingResult:
    """Sayi-topraklama dogrulama sonucu."""

    grounded: List[str]    # atif kaynaklarinda bulunan sayilar
    ungrounded: List[str]  # bulunamayan sayilar
    is_clean: bool         # ungrounded bos mu?


def verify_number_grounding(
    text: str,
    cited_sources: List[SourceDoc],
) -> NumberGroundingResult:
    """Metindeki sayilarin atif yapilan kaynaklarda gecip gecmedigini kontrol eder.

    Normalize karsilastirma: 181.5 == "181.5 mm" == "181,5".
    """
    text_numbers = extract_numbers_from_text(text)
    if not text_numbers:
        return NumberGroundingResult(grounded=[], ungrounded=[], is_clean=True)

    source_numbers: set = set()
    for doc in cited_sources:
        source_numbers.update(extract_numbers_from_text(doc.icerik))

    def _to_float(s: str) -> Optional[float]:
        try:
            return float(s)
        except (ValueError, TypeError):
            return None

    # Float-deger esitligi: "72" == "72.0", "181.5" == "181.50"
    source_floats: set = set()
    source_str_fallback: set = set()
    for s in source_numbers:
        f = _to_float(s)
        if f is not None:
            source_floats.add(f)
        else:
            source_str_fallback.add(s)

    grounded = []
    ungrounded = []
    for num in text_numbers:
        f = _to_float(num)
        if f is not None:
            matched = f in source_floats
        else:
            matched = num in source_str_fallback
        if matched:
            grounded.append(num)
        else:
            ungrounded.append(num)

    return NumberGroundingResult(
        grounded=grounded,
        ungrounded=ungrounded,
        is_clean=len(ungrounded) == 0,
    )
