"""scripts/llm_canli_test.py — Gercek Ollama ile canli smoke testi.

Kullanim:
    python scripts/llm_canli_test.py

Bu script:
1. http://localhost:11434/v1 Ollama ucuna baglanir (llama3:latest).
2. Ornek bir pipeline sonucuyla ReportRole'u cagirir (yonetici ozeti).
3. Ornek bir soruyla AssistantRole'u cagirir (topraklanmis yanit).
4. Her iki sonucu basar; Turkce kalite degerlendirmesi icin yorum satirlari eklenir.

KISIT: En fazla 3 deneme yapilir (retry dahil). Ollama kapali veya modeli yoksa
acik hata mesaji basilir, program cikmaz — exit code 1 ile biter.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import time


def _header(title: str) -> None:
    sep = "=" * 70
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)


def _build_demo_context():
    """Demo pipeline sonucundan GroundedContext olustur."""
    from src.llm.grounding import GroundedContext, SourceDoc

    kaynaklar = [
        SourceDoc(
            id="pipeline#ozet",
            tip="termin",
            icerik=(
                "Siparis sayisi: 5\n"
                "Parti sayisi: 3\n"
                "Uyari sayisi: 0\n"
                "Toplam ciro: 600.0 USD"
            ),
            uretici="demo_pipeline",
        ),
        SourceDoc(
            id="yerlesim#B001",
            tip="yerlesim",
            icerik=(
                "Yukseklik: 60.0 mm\n"
                "Doluluk: 40.7%\n"
                "Yerlestirilen parca: 6\n"
                "Cozucu: DBLF"
            ),
            uretici="nesting3d.dblf",
        ),
        SourceDoc(
            id="yerlesim#B002",
            tip="yerlesim",
            icerik=(
                "Yukseklik: 60.0 mm\n"
                "Doluluk: 39.9%\n"
                "Yerlestirilen parca: 2\n"
                "Cozucu: DBLF"
            ),
            uretici="nesting3d.dblf",
        ),
        SourceDoc(
            id="yerlesim#B003",
            tip="yerlesim",
            icerik=(
                "Yukseklik: 30.0 mm\n"
                "Doluluk: 39.2%\n"
                "Yerlestirilen parca: 2\n"
                "Cozucu: DBLF"
            ),
            uretici="nesting3d.dblf",
        ),
        SourceDoc(
            id="fiyat#B001",
            tip="fiyat",
            icerik="Nihai fiyat: 200.00 USD",
            uretici="pricing.engine",
        ),
        SourceDoc(
            id="fiyat#B002",
            tip="fiyat",
            icerik="Nihai fiyat: 200.00 USD",
            uretici="pricing.engine",
        ),
        SourceDoc(
            id="fiyat#B003",
            tip="fiyat",
            icerik="Nihai fiyat: 200.00 USD",
            uretici="pricing.engine",
        ),
    ]

    return GroundedContext(is_id="canli-smoke", kaynaklar=kaynaklar)


def run_report_smoke(report_role, context) -> bool:
    """Rapor ozeti canli testi. True = basarili."""
    from src.llm.roles.report import ReportInput
    from src.llm.structured import ValidationStatus

    _header("L1 RAPOR YAZICI — Canli Ollama Testi")

    report_input = ReportInput(
        is_id="canli-smoke",
        n_orders=5,
        n_batches=3,
        n_warnings=0,
        total_revenue_usd=600.0,
        context=context,
    )

    print("Istek gonderiliyor (llama3:latest)...")
    t0 = time.monotonic()
    result = report_role.run(report_input)
    elapsed = time.monotonic() - t0

    print(f"Sure: {elapsed:.2f}s | Status: {result.status.value}")

    if result.grounding_blocked:
        print("[UYARI] Sayi-topraklama BLOK — ozet reddedildi.")
        print(f"  Topraklanamayan sayilar: {result.grounding_detail}")
        return False

    if result.status == ValidationStatus.INVALID or result.fallback:
        print("[HATA] LLM gecerli yanit uretemedi.")
        if result.fallback:
            print(f"  Ham metin: {result.fallback.raw_text[:200]}")
            print(f"  Hatalar: {result.fallback.errors}")
        return False

    data = result.data or {}
    print("\n--- Baslik ---")
    print(data.get("baslik", "(yok)"))
    print("\n--- Yonetici Ozeti (govde_md) ---")
    print(data.get("govde_md", "(yok)"))
    print("\n--- Kullanilan Kaynaklar ---")
    print(data.get("kullanilan_kaynaklar", []))
    print("\n--- Turkce Kalite Degerlendirmesi ---")
    govde = data.get("govde_md", "")
    if len(govde) > 50:
        print("  Metin yeterli uzunlukta.")
    else:
        print("  [BAYRAK] Metin cok kisa — model zayif uretim yapti.")
    # Sayilar var mi?
    import re
    numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", govde)
    if numbers:
        print(f"  Sayisal referanslar: {numbers}")
    else:
        print("  [BAYRAK] Metinde sayi referansi yok — model soyut kaldi.")

    return True


def run_assistant_smoke(assistant_role, context) -> bool:
    """Asistan canli testi. True = basarili."""
    from src.llm.structured import ValidationStatus

    _header("L3 ASISTAN — Canli Ollama Testi")

    soru = "B001 partisinin nesting yuksekligi kac mm?"

    print(f"Soru: '{soru}'")
    print("Yanit bekleniyor...")
    t0 = time.monotonic()
    result = assistant_role.ask(soru=soru, context=context)
    elapsed = time.monotonic() - t0

    print(f"Sure: {elapsed:.2f}s | Status: {result.status.value}")

    if result.status == ValidationStatus.INVALID or result.fallback:
        print("[HATA] LLM gecerli yanit uretemedi.")
        if result.fallback:
            print(f"  Ham metin: {result.fallback.raw_text[:200]}")
        return False

    data = result.data or {}
    print("\n--- Cevap ---")
    print(data.get("cevap_md", "(yok)"))
    print("\n--- Alintilar ---")
    for a in data.get("alintilar", []):
        print(f"  [{a.get('kaynak_id')}] {a.get('konum')}")
    if data.get("ret"):
        print("\n[Baglam-disi ret] Neden:", data.get("ret_nedeni"))
    if result.number_flag:
        print(f"\n[UYARI] Sayi-topraklama bayragi: {result.ungrounded_numbers}")

    print("\n--- Turkce Kalite Degerlendirmesi ---")
    cevap = data.get("cevap_md", "")
    if len(cevap) > 20:
        print("  Cevap yeterli uzunlukta.")
    else:
        print("  [BAYRAK] Cevap cok kisa — llama3 Turkce uretiminde zorlaniyor olabilir.")
    if "mm" in cevap or "60" in cevap:
        print("  Sayisal referans mevcut (60.0 mm).")
    else:
        print("  [BAYRAK] Beklenen '60.0 mm' referansi bulunamadi.")

    return True


def main() -> int:
    """Ana fonksiyon. 0=basarili, 1=hata."""

    _header("LLM CANLI SMOKE TESTI — Ollama llama3:latest")
    print(f"Hedef: http://localhost:11434/v1")

    try:
        from src.llm.config import LLMConfig
        from src.llm.audit import AuditLogger
        from src.llm.prompts import PromptRegistry
        from src.llm.roles.report import ReportRole
        from src.llm.roles.assistant import AssistantRole, Conversation
        from src.llm.providers.openai_compat import OpenAICompatProvider

        cfg_path = _ROOT / "configs" / "llm.local.json"
        if not cfg_path.exists():
            print(f"[HATA] {cfg_path} bulunamadi.")
            return 1

        cfg = LLMConfig.from_file(str(cfg_path))
        cfg.validate()
        print(f"Konfig yuklendi: {cfg_path.name}")

        audit = AuditLogger(
            log_dir=str(_ROOT / cfg.audit.log_dir),
            payload_log_dir=str(_ROOT / cfg.audit.payload_log_dir),
            payload_logging="none",
        )

        registry = PromptRegistry(
            prompts_dir=str(_ROOT / "prompts"),
            enforce_lock=True,
        )

        prov_cfg = cfg.provider_for_role("report")
        provider = OpenAICompatProvider(
            base_url=prov_cfg.base_url or "http://localhost:11434",
            model=cfg.role("report").model,
            timeout_s=prov_cfg.timeout_s,
        )
        print(f"Saglayici: {prov_cfg.base_url} | Model: {cfg.role('report').model}")

        report_role = ReportRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("report"),
        )

        assistant_role = AssistantRole(
            provider=provider,
            registry=registry,
            audit=audit,
            role_cfg=cfg.roles.get("assistant"),
            conversation=Conversation(),
        )

    except ImportError as exc:
        print(f"[HATA] Import hatasi: {exc}")
        return 1
    except Exception as exc:
        print(f"[HATA] Baslangic hatasi: {exc}")
        return 1

    context = _build_demo_context()
    success_count = 0
    total = 2

    try:
        if run_report_smoke(report_role, context):
            success_count += 1
        else:
            print("[BASARISIZ] Rapor testi basarisiz.")
    except Exception as exc:
        print(f"[HATA] Rapor testi exception: {exc}")

    try:
        if run_assistant_smoke(assistant_role, context):
            success_count += 1
        else:
            print("[BASARISIZ] Asistan testi basarisiz.")
    except Exception as exc:
        print(f"[HATA] Asistan testi exception: {exc}")

    _header(f"OZET: {success_count}/{total} test basarili")

    if success_count < total:
        print("\nNOT: llama3 Turkce uretiminde orta duzey performans gosterir.")
        print("Model degistirmek icin: configs/llm.local.json -> 'model' satirini guncelle.")
        print("Onerilen: mistral:7b, qwen2:7b, gemma2:9b")

    return 0 if success_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
