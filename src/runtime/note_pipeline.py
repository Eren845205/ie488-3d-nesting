"""runtime/note_pipeline.py — not->kisit hattinin orkestrasyonu (K-56g Faz 5).

Tek giris noktasi: analyze_order_notes(order, ...) -> order.

YAPISAL GARANTI (Eren serti #1): fonksiyonun ILK kosulu not adaylarini
kontrol eder — `not_adaylari` bos/yokken LLM objesine HIC dokunulmaz ve
order dict'i AYNEN doner (notsuz siparis bit-ozdes yol). Ayrica mode
"kapali" (default) iken notlu siparis bile analiz edilmez (rollout anahtari).

Mod semantigi (configs/llm.local.json "kisit_modu"):
  kapali   : hat kapali — order AYNEN doner (default; A11 rollout disiplini).
  golge    : analiz kosulur, sonuc YALNIZ order["not_analizi"]'na yazilir;
             motor_kisitlari ASLA eklenmez (kiyas/gozlem donemi).
  otomatik : analiz + nihai_guven=="yuksek" VE derlenen kisitlar
             order["motor_kisitlari"]'na yazilir (uygulama); digerleri
             operator isareti olarak not_analizi'nda kalir.

Karar politikasi (plan Faz 4): dusuk/orta guvenli veya derlenemeyen kisit
UYGULANMAZ — muhafazakarlik burada "motora yanlis-pozitif kisit sokmamak"
demektir (kisitsiz nesting musteri istegini en fazla karsilamamis olur,
asla ihlal etmez). Her karar not_analizi'nda gorunur (sessiz uygulama yok).

Hata guvenligi: analiz herhangi bir sebeple patlarsa order DEGISMEDEN doner
(yalniz not_analizi.hata alani) — LLM hatti uretim hattini asla dusuremez.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.runtime.quantity_text_parser import _TR_FOLD

logger = logging.getLogger(__name__)

# Uretim heightmap yolunun aktif poz seti (demo_pipeline scenario default
# n_orientations=4 — c2f cagrisi default n=4 ile kosar). Compiler kesisim
# kontrolu bu kesite gore yapilir.
URETIM_N_ORIENTATIONS = 4

# OLUMSUZ-IFADE GUVEN TAVANI (eval v1.1 z03 dersi — Turkce olumsuzluk eki
# tuzagi): "yatay YATMASIN" notunu 3b model 3/3 oy + yuksek guvenle TERS
# yonde kilitledi (yatay), oybirligi yuzunden hakem de devreye girmedi.
# Yapisal savunma: kisitin kaynak satirinda olumsuzluk kalibi varsa nihai
# guven ASLA "yuksek" olamaz -> otomatik modda uygulanmaz, operatore duser.
# (Yanlis-pozitif tavan uygulamasi zararsizdir: yalniz onay istetir.)
_OLUMSUZ_KALIP = re.compile(
    r"(?:ma|me)(?:sin|yin)\b|(?:ma|me)yacak|(?:ma|me)yecek|"
    r"\bdegil\b|\byasak|\bolmaz\b|\bolmasin\b"
)


def _olumsuz_ifade(metin: str) -> bool:
    return bool(_OLUMSUZ_KALIP.search(
        str(metin or "").translate(_TR_FOLD).casefold()))


def analyze_order_notes(
    order: Optional[Dict[str, Any]],
    kisit_role: Any,
    hakem_role: Any = None,
    *,
    mode: str = "kapali",
    n_orientations: int = URETIM_N_ORIENTATIONS,
) -> Optional[Dict[str, Any]]:
    """Siparis notlarini analiz et; karar politikasina gore order'i isaretle.

    order dict'i YERINDE zenginlestirilir ve dondurulur (cagiran tarafta
    atama gerektirmez ama okunabilirlik icin `order = analyze...` onerilir).
    """
    # --- YAPISAL KAPI: notsuz siparis / kapali mod -> LLM'e sifir dokunus ---
    if not order or not order.get("not_adaylari"):
        return order
    if mode not in ("golge", "otomatik"):
        return order
    if kisit_role is None:
        return order  # LLM aktif degil (Ollama kapali) — deterministik yol

    try:
        return _analyze(order, kisit_role, hakem_role, mode=mode,
                        n_orientations=n_orientations)
    except Exception as exc:  # LLM hatti uretimi ASLA dusurmez
        logger.warning("note_pipeline: analiz hatasi (%s) — order degismeden "
                       "devam.", exc, exc_info=True)
        order["not_analizi"] = {"mode": mode, "hata": str(exc)}
        return order


def _analyze(
    order: Dict[str, Any],
    kisit_role: Any,
    hakem_role: Any,
    *,
    mode: str,
    n_orientations: int,
) -> Dict[str, Any]:
    from src.runtime.constraint_compiler import compile_constraints

    adaylar = order["not_adaylari"]
    not_satirlari = [a.get("satir", "") for a in adaylar if a.get("satir")]
    parca_adlari: List[str] = (
        [p.get("name") for p in order.get("parts", []) if p.get("name")]
        or list(order.get("stl_names") or [])
    )

    # Kapi-0 deterministik injection tespiti (note_detector): bilinen kalip
    # yakalandiysa LLM'e HIC gidilmez — analiz "injection" olarak kapanir.
    if order.get("not_injection_kapi0"):
        order["not_analizi"] = {
            "mode": mode, "n_ornekleme": 0, "n_gecerli": 0,
            "hakem_kullanildi": False, "injection_suphesi": True,
            "injection_kaynak": "kapi0_deterministik",
            "kisitlar": [], "uygulanan": None,
            "operator_isaretleri": [
                "injection kalibi (deterministik Kapi-0) — not analizi "
                "YAPILMADI, hicbir kisit uygulanmadi; mail elle incelenmeli"],
        }
        return order

    voting = kisit_role.run_with_voting(
        not_satirlari, parca_adlari, n=3, hakem_role=hakem_role)

    cont = order.get("container") or {}
    plate_w, plate_d = cont.get("width_mm"), cont.get("depth_mm")

    analiz: Dict[str, Any] = {
        "mode": mode,
        "n_ornekleme": voting.n_ornekleme,
        "n_gecerli": voting.n_gecerli,
        "hakem_kullanildi": voting.hakem_kullanildi,
        "injection_suphesi": voting.injection_suphesi,
        "kisitlar": [],
        "operator_isaretleri": [],
        "uygulanan": None,
    }
    if order.get("not_bilinmeyen_satir"):
        analiz["bilinmeyen_satir"] = order["not_bilinmeyen_satir"]

    if voting.injection_suphesi:
        analiz["operator_isaretleri"].append(
            "injection suphesi: not analizi sonuclari KULLANILMADI — "
            "operator mail'i incelemeli")
        order["not_analizi"] = analiz
        return order
    if voting.n_gecerli == 0:
        analiz["operator_isaretleri"].append(
            "LLM gecerli kisit ciktisi uretemedi — notlar operator "
            "incelemesi bekliyor")
        order["not_analizi"] = analiz
        return order

    # OLUMSUZ-IFADE TAVANI (z03 dersi): kaynak satirda olumsuzluk varsa
    # nihai guven en fazla "orta" — yon tersine cevrilmis olabilir; karar
    # operatore. Kaynak satir yoksa TUM not satirlarina bakilir (temkin).
    for k in voting.kisitlar:
        satir = k.get("kaynak_satir") or " ".join(not_satirlari)
        if k.get("nihai_guven") == "yuksek" and _olumsuz_ifade(satir):
            k["nihai_guven"] = "orta"
            k["olumsuz_tavan"] = True
            analiz["operator_isaretleri"].append(
                f"olumsuz ifade tavani [{k.get('tip')}] "
                f"parca={k.get('parca_adi') or '?'}: satirda olumsuzluk "
                "kalibi var — yon/anlam tersine cevrilmis olabilir, "
                "otomatik uygulanmadi")

    # Tum kisitlari derle (rapor gorunurlugu); uygulama alt kumesi ayri.
    tumu = compile_constraints(
        voting.kisitlar, parca_adlari,
        plate_w_mm=plate_w, plate_d_mm=plate_d,
        n_orientations=n_orientations)
    durum_by_id = {id(d["kisit"]): d for d in tumu.durumlar}
    for k in voting.kisitlar:
        d = durum_by_id.get(id(k), {})
        analiz["kisitlar"].append({
            **{a: k.get(a) for a in ("tip", "parca_adi", "deger", "guven",
                                     "gerekce", "kaynak_satir", "oy",
                                     "hakem", "nihai_guven")},
            "derleme": d.get("durum", "uygulanmadi"),
            "derleme_sebep": d.get("sebep"),
        })
    analiz["operator_isaretleri"].extend(tumu.operator_isaretleri)
    for k in voting.kisitlar:
        if k.get("nihai_guven") != "yuksek":
            analiz["operator_isaretleri"].append(
                f"dusuk/orta guvenli kisit uygulanmadi "
                f"[{k.get('tip')}] parca={k.get('parca_adi') or '?'} "
                f"(oy={k.get('oy')}, hakem={k.get('hakem')}) — operator "
                "onayi: /kisit-onay")

    if mode == "otomatik":
        # Yalniz YUKSEK guvenli kisitlar derlenip uygulanir.
        yuksek = [k for k in voting.kisitlar
                  if k.get("nihai_guven") == "yuksek"]
        uygulanacak = compile_constraints(
            yuksek, parca_adlari,
            plate_w_mm=plate_w, plate_d_mm=plate_d,
            n_orientations=n_orientations)
        if uygulanacak.motor_kisitlari:
            order["motor_kisitlari"] = uygulanacak.motor_kisitlari
            analiz["uygulanan"] = uygulanacak.motor_kisitlari
            logger.info(
                "note_pipeline: %d yuksek-guvenli kisit UYGULANDI "
                "(order=%s).", len(yuksek), order.get("order_id"))

    order["not_analizi"] = analiz
    return order
