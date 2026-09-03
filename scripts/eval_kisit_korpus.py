# -*- coding: utf-8 -*-
"""K-56g Faz 6 — kisit korpus eval'i (CANLI Ollama; CI DISI).

Golden korpusu (tests/fixtures/not_korpusu.jsonl) gercek modellerle kosar:
KisitRole.run_with_voting (n=3, qwen2.5:3b) + hakem (qwen2.5:7b) ->
beklenenle kiyas -> dogruluk + yuksek-kesim yanlis-pozitif + oy dagilimi.

OTOMATIK MODA GECIS KRITERI (plan): genel dogruluk >= %90 VE yuksek-guven
kesiminde yanlis kisit == 0. Bu esikler gecilmeden configs/llm.local.json
kisit_modu "otomatik" yapilmaz (golge kalir).

Kullanim: python -m scripts.eval_kisit_korpus  (Ollama acik olmali)
Cikti: konsol ozeti (SAF ASCII) + results/kisit_korpus_eval.json
Exit: 0 = kriter PASS, 1 = FAIL/hata.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

KORPUS = _ROOT / "tests" / "fixtures" / "not_korpusu.jsonl"
SONUC = _ROOT / "results" / "kisit_korpus_eval.json"

DOGRULUK_ESIK = 0.90


def _kisit_esle(uretilen: dict, beklenen: dict) -> bool:
    """Tek beklenen kisit, uretilen kisitla esliyor mu (tip+ad[+deger])."""
    if uretilen.get("tip") != beklenen.get("tip"):
        return False
    u_ad = str(uretilen.get("parca_adi") or "").casefold().replace("_", " ")
    b_ad = str(beklenen.get("parca_adi") or "").casefold().replace("_", " ")
    if u_ad != b_ad:
        return False
    if "deger" in beklenen:
        return uretilen.get("deger") == beklenen["deger"]
    return True


def _ornek_degerlendir(voting, beklenen: dict, parca_adlari) -> tuple:
    """(dogru: bool, yuksek_yanlis_pozitif: int, detay: str)"""
    from src.runtime.constraint_compiler import compile_constraints

    if beklenen.get("injection"):
        ok = bool(voting.injection_suphesi)
        return ok, 0, "injection " + ("yakalandi" if ok else "KACTI")

    if voting.injection_suphesi:
        # Yanlis-ad sinifinda alarm GUVENLI sonuctur: bilinmeyen parca adina
        # kisit yazmak yerine hicbir sey uygulanmadi (muhafazakarlik ihlali
        # yok) — dogru sayilir. Diger siniflarda sahte alarm = kayip.
        if beklenen.get("yanlis_ad_kabul"):
            return True, 0, "muhafazakar dogru (alarm — guvenli taraf)"
        return False, 0, "sahte injection alarmi"

    yuksek = [k for k in voting.kisitlar if k.get("nihai_guven") == "yuksek"]

    # Belirsiz/yanlis-ad kabul sinifi: yuksek kesim MOTOR kisiti uretmemeli.
    if beklenen.get("belirsiz_kabul") or beklenen.get("yanlis_ad_kabul"):
        derlenen = compile_constraints(yuksek, list(parca_adlari))
        ok = not derlenen.motor_kisitlari
        return ok, (0 if ok else len(yuksek)), \
            "muhafazakar " + ("dogru" if ok else "IHLAL (yuksek kisit uretti)")

    return _pozitif_degerlendir(voting, beklenen, yuksek)


def _pozitif_degerlendir(voting, beklenen: dict, yuksek: list) -> tuple:
    """Beklenen kisit listesiyle eslesme + yuksek-kesim FP sayimi."""
    bekl = beklenen.get("kisitlar") or []
    eksik = [b for b in bekl
             if not any(_kisit_esle(u, b) for u in voting.kisitlar)]
    # yuksek-kesim yanlis-pozitif: beklenende karsiligi olmayan yuksek kisit
    yfp = [u for u in yuksek if not any(_kisit_esle(u, b) for b in bekl)]

    if beklenen.get("alternatif_belirsiz") and eksik:
        # z-sinifi: beklenen eslesme YA DA hicbir yuksek kisit (temkin) kabul
        ok = not yfp and not yuksek
        return ok, len(yfp), "alternatif-belirsiz " + ("kabul" if ok else "RED")

    ok = not eksik and not yfp
    detay = []
    if eksik:
        detay.append(f"eksik={len(eksik)}")
    if yfp:
        detay.append(f"yuksek-FP={len(yfp)}")
    return ok, len(yfp), (" ".join(detay) or "tam eslesme")


def main() -> int:
    from src.llm.audit import AuditLogger
    from src.llm.config import LLMConfig
    from src.llm.prompts import PromptRegistry
    from src.llm.providers.openai_compat import OpenAICompatProvider
    from src.llm.roles.kisit import KisitRole

    cfg_path = _ROOT / "configs" / "llm.local.json"
    if not cfg_path.exists():
        print("HATA: configs/llm.local.json yok."); return 1
    cfg = LLMConfig.from_file(str(cfg_path)); cfg.validate()

    prov_cfg = cfg.provider_for_role("kisit")
    base_url = prov_cfg.base_url or "http://localhost:11434"

    def _provider(role_name):
        rc = cfg.roles.get(role_name)
        return OpenAICompatProvider(base_url=base_url, model=rc.model,
                                    timeout_s=prov_cfg.timeout_s)

    ana_prov = _provider("kisit")
    ok, detail = ana_prov.health_check()
    print(f"Ollama saglik ({cfg.roles['kisit'].model}): {detail}")
    if not ok:
        print("HATA: Ollama/model hazir degil."); return 1
    hakem_prov = _provider("kisit_hakem")
    h_ok, h_detail = hakem_prov.health_check()
    print(f"Hakem saglik ({cfg.roles['kisit_hakem'].model}): {h_detail}")
    if not h_ok:
        print("UYARI: hakem modeli yok (ollama pull qwen2.5:7b) — "
              "eskalasyonsuz kosulacak.")

    registry = PromptRegistry(str(_ROOT / "prompts"), enforce_lock=True)
    audit = AuditLogger(log_dir=str(_ROOT / "logs" / "llm"),
                        payload_log_dir=str(_ROOT / "logs" / "llm" / "payload"),
                        payload_logging="none")
    role = KisitRole(ana_prov, registry, audit,
                     role_cfg=cfg.roles.get("kisit"))
    hakem = KisitRole(hakem_prov, registry, audit,
                      role_cfg=cfg.roles.get("kisit_hakem")) if h_ok else None

    ornekler = [json.loads(ln) for ln in
                KORPUS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"Korpus: {len(ornekler)} ornek\n" + "-" * 64)

    sonuclar = []
    sinif_sayac: dict = {}
    toplam_yfp = 0
    oy_dagilimi: dict = {}
    hakem_sayisi = 0

    from src.runtime.note_pipeline import _olumsuz_ifade

    for o in ornekler:
        voting = role.run_with_voting(
            o["not_satirlari"], o["parca_adlari"], n=3, hakem_role=hakem)
        # URETIM POLITIKASI AYNASI: note_pipeline'daki olumsuz-ifade guven
        # tavani burada da uygulanir (eval LLM'i degil SISTEMI olcer; z03
        # dersi — tavan olmadan yfp sahte-sisme verir).
        for k in voting.kisitlar:
            satir = k.get("kaynak_satir") or " ".join(o["not_satirlari"])
            if k.get("nihai_guven") == "yuksek" and _olumsuz_ifade(satir):
                k["nihai_guven"] = "orta"
                k["olumsuz_tavan"] = True
        dogru, yfp, detay = _ornek_degerlendir(
            voting, o["beklenen"], o["parca_adlari"])
        toplam_yfp += yfp
        hakem_sayisi += int(voting.hakem_kullanildi)
        for k in voting.kisitlar:
            oy_dagilimi[k.get("oy")] = oy_dagilimi.get(k.get("oy"), 0) + 1
        s = sinif_sayac.setdefault(o.get("sinif", "?"), [0, 0])
        s[1] += 1
        s[0] += int(dogru)
        durum = "PASS" if dogru else "FAIL"
        print(f"[{durum}] {o['id']} ({o.get('sinif')}): {detay}")
        sonuclar.append({"id": o["id"], "sinif": o.get("sinif"),
                         "dogru": dogru, "detay": detay,
                         "n_gecerli": voting.n_gecerli,
                         "hakem": voting.hakem_kullanildi,
                         "kisitlar": voting.kisitlar})

    n_dogru = sum(1 for r in sonuclar if r["dogru"])
    dogruluk = n_dogru / max(1, len(sonuclar))
    print("-" * 64)
    print(f"Genel dogruluk : {n_dogru}/{len(sonuclar)} ({dogruluk:.0%})")
    for sinif, (d, t) in sorted(sinif_sayac.items()):
        print(f"  {sinif:<10}: {d}/{t}")
    print(f"Yuksek-kesim yanlis-pozitif: {toplam_yfp}")
    print(f"Oy dagilimi (oy: adet)     : {dict(sorted(oy_dagilimi.items()))}")
    print(f"Hakem eskalasyonu          : {hakem_sayisi} ornekte")

    gecti = dogruluk >= DOGRULUK_ESIK and toplam_yfp == 0
    print("-" * 64)
    print("OTOMATIK-MOD KRITERI: " + ("PASS — kisit_modu 'otomatik' "
          "yapilabilir (Eren onayi ile)" if gecti else
          f"FAIL — golge modda kalinmali (esik {DOGRULUK_ESIK:.0%} + yfp=0)"))

    SONUC.parent.mkdir(parents=True, exist_ok=True)
    SONUC.write_text(json.dumps({
        "dogruluk": dogruluk, "n": len(sonuclar), "yuksek_fp": toplam_yfp,
        "oy_dagilimi": {str(k): v for k, v in oy_dagilimi.items()},
        "hakem_sayisi": hakem_sayisi, "gecti": gecti, "detay": sonuclar,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Sonuc dosyasi: {SONUC}")
    return 0 if gecti else 1


if __name__ == "__main__":
    sys.exit(main())
