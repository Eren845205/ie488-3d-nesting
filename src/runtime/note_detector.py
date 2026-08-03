"""runtime/note_detector.py — Kapi-0: deterministik siparis-notu tespiti.

Siparis mailindeki serbest-metin PARCA NOTLARINI ("konumu degismeyecek",
"dik uretilecek" gibi) LLM'siz, saf-deterministik kurallarla tespit eder.
Bu modul LLM hattinin TEK kapisidir: buradan aday cikmayan siparis icin
LLM'e HIC gidilmez (yapisal garanti — notsuz siparis bit-ozdes yol).

Tasarim (K-56g not->kisit hatti, Faz 1):
  * LLM IMPORTU YOK — bu dosya asla model cagirmaz.
  * Satir siniflandirma sirasi:
      1. Adet satiri mi? (quantity_text_parser regex'leri — parser'a
         DOKUNULMAZ, yalniz import edilir). Klasik "X 22 adet" satirinin
         KUYRUGUNDA kisit anahtar-kelimesi varsa kuyruk not adayidir.
      2. Sert eleme: e-posta/URL/tarih/telefon satiri, tek-token baslik,
         beyan-toplami satiri ("588 parca icin ...").
      3. Pozitif kapi: kisit sozlugu regex'i (TR-fold). Eslesen satir
         "not adayi"dir.
      4. Yumusak eleme: selamlama/imza kaliplari (pozitif kapidan SONRA —
         "Hocam bu parca dik uretilecek" satirini selamlama yutmasin).
      5. Kalan = "bilinmeyen satir": LLM'e GITMEZ, yalniz sayaci tutulur
         (Kapi-0 recall kaybinin gorunur izi; golge donemde sozluk buyur).
  * Injection-yuzey tavanlari: satir basi MAX_SATIR_KR karakter, siparis
    basi MAX_ADAY aday (asan kirpilir + bayrak).

Cikti sozlesmesi:
    {"adaylar": [{"satir", "satir_no", "kaynak", "parca_adaylari"}, ...],
     "bilinmeyen_satir": int, "kirpildi": bool}
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from src.runtime.quantity_text_parser import (
    _DECLARED_TOTAL,
    _QTY_DASH_LINE,
    _QTY_LINE,
    _TR_FOLD,
    _norm_name,
)

# Injection-yuzey tavanlari (K-56g Faz 1): LLM'e akan metin miktari sinirli.
MAX_SATIR_KR = 300
MAX_ADAY = 10

# Kisit sozlugu (pozitif kapi). TR-fold + casefold SONRASI metne uygulanir;
# koklerle eslesir (degism- -> degismeyecek/degismesin; ureti- ->
# uretilecek/uretilmeli/uretim). \b'li kisa kelimeler yanlis-pozitife karsi
# sinirli ("dik" != "dikkat"/"degildir"; "acil" != "acilacak"). Sozluk bilerek
# GENIS-KAPSAM degildir: kapiyi gecemeyen not "bilinmeyen satir" sayacina
# duser ve golge donemde sozluk buyutulur (yapisal LLM-kapatma garantisinin
# bilincli bedeli).
#
# 2026-08-03 genislemesi (hoca gercek ornekleri — kupon maili + 5-ornek
# taramasi): "uretil" -> "ureti" (isim hali de girer); gruplama/parti
# (tek sefer/parti/plaka, ayni plaka/tabla, birlikte, bolun-), oncelik
# (oncelik, \bacil\b, basil-), makine-ekseni (recoater, gaz akis, transvers)
# kokleri eklendi. kisit_modu="kapali"/"golge" iken davranis garantisi
# degismez (note_pipeline yapisal siniri); genisleme yalnizca aday sayisini
# etkiler (MAX_ADAY tavani gecerli).
_KISIT_SOZLUK = re.compile(
    r"\bdik\b|\bdikey\b|\byatay\b|\bduz\b|yatir|dondur|cevir|rotasyon|"
    r"oryantasyon|\baci\b|acis|acili|konum|pozisyon|yerles|sabit|degism|"
    r"oynat|dokunma|ureti|\bkenar\b|\bkose\b|"
    r"oncelik|\bacil\b|basil|tek sefer|tek parti|tek plaka|ayni plaka|"
    r"ayni tabla|birlikte|bolun|recoater|gaz akis|transvers"
)

# Sert eleme kaliplari (kisit tasiyamayacak yapisal satirlar).
_EPOSTA = re.compile(r"[\w.+-]+@[\w-]+\.\w")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_TARIH = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
_TELEFON = re.compile(r"(?:\+?\d[\d\s-]{8,}\d)")

# Yumusak eleme: selamlama/imza/kapanis. Pozitif kapidan SONRA denenir.
# "rica" bilerek YOK ("dik uretilmesini rica ederim" gercek nottur).
_SELAM_IMZA = re.compile(
    r"merhaba|selam|sayin\b|\bsn\.|\bhocam\b|iyi calismalar|iyi gunler|"
    r"saygilar|saygiyla|tesekkur|kolay gelsin|iyi aksamlar|gorusmek uzere"
)

# DETERMINISTIK injection filtresi (eval v1.1 dersi: i01/i02 LLM'den kacti —
# bilinen kaliplar LLM'e GUVENILMEZ, Kapi-0'da kesilir; LLM yalnizca yeni/
# bilinmeyen kaliplara son savunmadir). Eslesen satir ADAY OLMAZ (kisit
# sozlugu tetiklese bile) ve tarama injection_kapi0 bayragini kaldirir.
#
# TEK KAYNAK (H7, 2026-07-25): bu kalip note->kisit hatti DISINDA da kullanilir
# (src/runtime/mail_ingest.py serbest-metin LLM-parse yolunun ONU) — kopya-
# yapistir cift bakim yasak, `has_injection_pattern()` uzerinden import edilir.
_INJECTION_KALIP = re.compile(
    r"yok say|talimatlari? (iptal|unut|bosver)|kurallari? (iptal|unut|kaldir)|"
    r"ignore (all|previous|above|prior)|disregard|"
    r"\bsystem\s*:|\bsistem\s*:|\boverride\b|\bprompt\b|injection_suphesi"
)


def has_injection_pattern(text: str) -> bool:
    """Serbest metinde deterministik injection kalibi var mi? (TR-fold + casefold).

    Ortak kapi (H7): note_detector'in Kapi-0 injection filtresiyle AYNI
    kalip/oncelik. mail_ingest.py serbest-metin LLM-parse yolunun onunde
    de kullanilir — boylece bilinen injection denemeleri LLM'e hic gitmeden
    (satir bazinda degil, tum metin uzerinde) yakalanir.
    """
    return bool(_INJECTION_KALIP.search(_fold(text or "")))


def _fold(s: str) -> str:
    """TR karakter katlama + casefold (parser _TR_FOLD ile ayni tablo)."""
    return s.translate(_TR_FOLD).casefold()


def _parca_adaylari(satir: str, stl_norms: Dict[str, str]) -> List[str]:
    """Satirda gecen bilinen STL adlari (normalize substring; en cok 5)."""
    hits: List[str] = []
    n_satir = _norm_name(satir)
    for orig, norm in stl_norms.items():
        if norm and norm in n_satir:
            hits.append(orig)
            if len(hits) >= 5:
                break
    return hits


def extract_note_candidates(
    body: str,
    txt_text: str = "",
    stl_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Mail govdesi + .txt ekinden deterministik not adaylarini cikar.

    Args:
        body: Mail govdesi (duz metin, bos olabilir).
        txt_text: Adet-listesi .txt ekinin metni (yoksa bos).
        stl_names: ZIP'teki STL adlari (parca_adaylari eslemesi icin).

    Returns:
        {"adaylar": [...], "bilinmeyen_satir": int, "kirpildi": bool}
        Aday ogesi: {"satir", "satir_no", "kaynak", "parca_adaylari"}.
        Not adayi yoksa adaylar=[] doner — cagiran taraf bu durumda order
        dict'ine ALAN KOYMAZ (bit-ozdes sozlesme).
    """
    stl_norms = {nm: _norm_name(nm) for nm in (stl_names or [])}
    adaylar: List[Dict[str, Any]] = []
    bilinmeyen = 0
    kirpildi = False
    injection_kapi0 = False

    for kaynak, text in (("govde", body or ""), ("txt", txt_text or "")):
        for satir_no, raw in enumerate(text.splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            satir = stripped[:MAX_SATIR_KR]
            if len(stripped) > MAX_SATIR_KR:
                kirpildi = True
            folded = _fold(satir)

            # 0) DETERMINISTIK injection filtresi — EN ONCE (kisit sozlugu
            #    tetiklese bile bu satir LLM'e ASLA gitmez; bayrak kalkar,
            #    note_pipeline hicbir kisiti uygulamaz + operator isareti).
            if _INJECTION_KALIP.search(folded):
                injection_kapi0 = True
                continue

            # 1) Adet satiri: parser regex'leri (ayni oncelik sirasi).
            #    _QTY_DASH_LINE $-ancorlu (kuyruk olamaz); _QTY_LINE'in
            #    "adet" sonrasi kuyrugu kisit sozlugunden gecirilir.
            m_dash = _QTY_DASH_LINE.match(satir)
            m_qty = None if m_dash else _QTY_LINE.match(satir)
            if m_dash:
                continue  # saf adet satiri
            if m_qty:
                kuyruk = satir[m_qty.end():].strip(" .,;-")
                if kuyruk and _KISIT_SOZLUK.search(_fold(kuyruk)):
                    adaylar.append({
                        "satir": satir, "satir_no": satir_no,
                        "kaynak": "adet_satiri_kuyrugu",
                        "parca_adaylari": _parca_adaylari(satir, stl_norms),
                    })
                continue

            # 2) Sert eleme: yapisal satirlar kisit tasimaz.
            if (_EPOSTA.search(satir) or _URL.search(satir)
                    or _TARIH.search(satir) or _TELEFON.search(satir)):
                continue
            if _DECLARED_TOTAL.search(satir) and \
                    not _KISIT_SOZLUK.search(folded):
                continue  # beyan-toplami satiri ("588 parca icin ...")
            if " " not in satir and not _KISIT_SOZLUK.search(folded):
                continue  # tek-token baslik ("Plan1")

            # 3) Pozitif kapi — LLM'i acan TEK anahtar.
            if _KISIT_SOZLUK.search(folded):
                adaylar.append({
                    "satir": satir, "satir_no": satir_no, "kaynak": kaynak,
                    "parca_adaylari": _parca_adaylari(satir, stl_norms),
                })
                continue

            # 4) Yumusak eleme: selamlama/imza (pozitif kapidan sonra).
            if _SELAM_IMZA.search(folded):
                continue

            # 5) Bilinmeyen satir: LLM'e gitmez, sayaci tutulur.
            bilinmeyen += 1

    if len(adaylar) > MAX_ADAY:
        adaylar = adaylar[:MAX_ADAY]
        kirpildi = True

    return {"adaylar": adaylar, "bilinmeyen_satir": bilinmeyen,
            "kirpildi": kirpildi, "injection_kapi0": injection_kapi0}
