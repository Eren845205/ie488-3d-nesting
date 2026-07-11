"""runtime/quantity_text_parser.py — Mail govdesinden parca-adet eslemesi.

Hocanin gercek maili su formatta gelir (her satir bir parca):

    Merhabalar Hocam,

    Plan1

    ENG-500053_L-Bracket 22 adet
    811793-1 20 adet
    TAPER-GAUGE-1 10 adet
    ...
    baseplate_v2 1 adet

    Iyi calismalar,
    Saygilarimla.

Ikinci gercek format (Deneme4 maili, 2026-07-03 canli yakalandi):

    ASY-0176446 - 62
    02_T00-K179 Dugme Cift Fonksiyonlu -26
    ...

Desteklenen satir kaliplari:
    <parca_adi> <sayi> adet          (klasik — "adet" kelimesi zorunlu)
    <parca_adi> - <sayi>[ adet|pcs]  (tire ayracli — tire ONCESI bosluk SART;
                                      boylece "811793-1", "2026-07-03",
                                      telefon no gibi tireli metinler adet
                                      sayilmaz)
Parca adi = ZIP icindeki <ad>.stl dosyasinin uzantisiz adi (toleransli
eslestirme icin bkz. match_quantities_to_stls).
Selamlama / baslik / imza satirlari (adet icermeyen) ATLANIR.

Tasarim: DETERMINISTIK birincil yol (regex). Bu format cok duzenli oldugundan
LLM gerekmez -- LLM yalniz format bozulursa fallback olarak dusunulur (ayri
katman; bu modul saf deterministik + yan etkisiz). Determinizm: ayni metin ->
ayni dict.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Satir: "<ad> <sayi> adet"  — ad bosluk icerebilir (non-greedy), sayi tam,
# "adet" kelimesi zorunlu (TR siparis dili). Sonrasi serbest (nokta vs).
_QTY_LINE = re.compile(r"^(?P<ad>.+?)\s+(?P<adet>\d+)\s*adet\b", re.IGNORECASE)

# Satir: "<ad> - <sayi>" — Deneme4 gercek formati. Kurallar:
#   * Ayrac tire/en-dash/em-dash veya iki-nokta; ONCESINDE bosluk SART
#     ("ASY-0176446-1" icindeki tireler ad parcasidir, "2026-07-03" tarih,
#     "0212-1234567" telefon — hicbiri bosluk+tire tasimaz -> eslesmez).
#   * Ayrac SONRASI bosluk opsiyonel ("Fonksiyonlu -26" gercek mailde gecti).
#   * Sayi satiri BITIRMELI (opsiyonel "adet"/"pcs" soneki haric) — "250,24 mm"
#     gibi olcu metinleri eslesmez.
#   * Non-greedy ad + $ ancoru: addaki tireler atlanip SON gecerli
#     "bosluk+ayrac+sayi+son" bolunmesi bulunur.
_QTY_DASH_LINE = re.compile(
    r"^(?P<ad>.+?)\s+[-–—:]\s*(?P<adet>\d+)\s*(?:adet|pcs|pc|ad\.)?\s*\.?\s*$",
    re.IGNORECASE,
)

# Beyan edilen toplam: "588 parça için ..." / "Toplam 42 parca" — mail
# govdesindeki toplam-parca beyani. Cross-check (checksum) kaynagi:
# parse edilen adetlerin toplamiyla karsilastirilir; tutarsizlik = celiski.
# (?<!\w): kelimeye YAPISIK rakam beyan sayilmaz — "Deneme5 parcalari" /
# "Plan2 parça" gibi urun adlarindaki rakamlar sahte beyan uretiyordu
# (K-45 E2E kenar durumu, 2026-07-12; sahte beyan -> sahte quantity_conflict
# -> gercek siparis gereksiz operator kuyruguna duserdi).
_DECLARED_TOTAL = re.compile(r"(?<!\w)(\d+)\s*par[cç]a", re.IGNORECASE)

# Fix-1 (CRITICAL): mail govdesinde "<ad> 999999999 adet" gibi sinirsiz bir
# sayi pipeline'i OOM'a dusurebilirdi. bkz. src/llm/roles/parser.py MAX_QTY
# (ayni deger, ayni gerekce).
MAX_QTY = 5000


def parse_quantities(text: str) -> Dict[str, int]:
    """Mail govdesinden {parca_adi: adet} eslemesi cikar.

    Args:
        text: Mail govdesi (duz metin).

    Returns:
        Ekleme sirasini koruyan dict {parca_adi: adet}. Adet iceren satir yoksa
        bos dict. Ayni ad birden cok satirda gecerse adetler TOPLANIR (ayni
        parca iki satirda boluunmus olabilir).
    """
    result: Dict[str, int] = {}
    for line in text.splitlines():
        stripped = line.strip()
        # Tire-ayracli kalip ONCE denenir: "Ad - 26 adet" satirinda klasik
        # kalip adi "Ad -" diye yanlis keserdi; tire kalibi ikisini de dogru
        # boler. Klasik "braket 22 adet" satirinda ayrac yoktur -> tire kalibi
        # eslesmez, klasik kalip devralir (regresyon yok).
        m = _QTY_DASH_LINE.match(stripped) or _QTY_LINE.match(stripped)
        if not m:
            continue
        ad = m.group("ad").strip()
        adet = int(m.group("adet"))
        if not ad or adet <= 0:
            continue
        if adet > MAX_QTY:
            logger.warning(
                "quantity_text_parser: '%s' adeti asiri buyuk (%d, izin verilen "
                "ust sinir %d) — clamp'lendi.",
                ad, adet, MAX_QTY,
            )
            adet = MAX_QTY
        result[ad] = result.get(ad, 0) + adet
    return result


def parse_declared_total(text: str) -> Optional[int]:
    """Mail govdesindeki beyan edilen toplam parca sayisini cikar.

    "588 parça için imalat yüksekliği ..." gibi bir beyan varsa 588 doner;
    yoksa None. Ilk eslesme alinir (siparis mailinde tek beyan olur).

    Bu deger CHECKSUM olarak kullanilir: parse edilen adetlerin toplami
    beyanla tutuyorsa esleme dogrulugu matematiksel olarak teyit edilmis
    sayilir (insansiz otomatik isleme icin guven kaynagi).
    """
    m = _DECLARED_TOTAL.search(text or "")
    if not m:
        return None
    val = int(m.group(1))
    return val if val > 0 else None


# ---------------------------------------------------------------------------
# Toleransli STL-adet eslestirme
# ---------------------------------------------------------------------------

# TR karakter katlama — once cevir, sonra casefold (İ.casefold() 'i'+combining
# dot urettigi icin sira onemli).
_TR_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")

# Sonek toleransi: mail adi ile dosya adi arasindaki kabul edilebilir artik —
# "-25pcs", "_25", " 25 adet" gibi ADET IPUCU sonekleri. Serbest metin degil:
# yalniz ayrac+sayi(+adet-kelimesi) kabul edilir ki "Dugme" ile
# "Dugme Kilidi" gibi FARKLI parcalar eslesmesin.
_SUFFIX_TOLERANCE = re.compile(r"^[\s\-_]*\d+\s*(?:pcs|pc|adet|ad)?\.?$", re.IGNORECASE)


def _norm_name(name: str) -> str:
    """Eslestirme icin ad normalizasyonu (gorunur adi DEGISTIRMEZ).

    Buyuk/kucuk katlanir, TR karakterler ASCII'ye indirgenir, .stl uzantisi
    dusurulur, alt cizgi bosluga cevrilip bosluklar teklenir. Tireler KORUNUR
    (parca numarasi kimligidir: "ASY-0176446-1" != "ASY-0176446 1").
    """
    s = str(name).translate(_TR_FOLD).casefold()
    if s.endswith(".stl"):
        s = s[:-4]
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_quantities_to_stls(
    quantities: Dict[str, int],
    stl_names: List[str],
) -> Tuple[Dict[str, int], List[str], List[str]]:
    """Mail'deki adet anahtarlarini ZIP'teki GERCEK STL adlarina esle.

    Iki asama (deterministik, siralama-bagimsiz sonuc):
      1. NORMALIZE birebir eslesme (case/TR-karakter/alt-cizgi toleransi).
      2. SONEK toleransi: dosya adi mail adinin uzantisi (veya tersi) ve artik
         yalniz adet-ipucu ise ("Dugme Cift Fonksiyonlu" ~ "Dugme Cift
         Fonksiyonlu-25pcs"). Yalniz TEK aday varsa eslenir — birden cok aday
         = belirsizlik = eslenmez (yanlis parcaya adet yazmaktansa insana sor).

    Onceki birebir eslesmeler sonek asamasinda "sahiplenilmis" sayilir; boylece
    "ASY-0176446" beyani "ASY-0176446-1" dosyasini CALMAZ (ikisi ayri parca,
    ikisi de birebir eslesir).

    Returns:
        (matched, unmatched_qty_keys, unmatched_stl_names)
        matched: {gercek_stl_adi: adet} — anahtarlar stl_names'ten birebir.
    """
    stl_by_norm: Dict[str, List[str]] = {}
    for nm in stl_names:
        stl_by_norm.setdefault(_norm_name(nm), []).append(nm)

    matched: Dict[str, int] = {}
    claimed: set = set()
    unmatched_keys: List[str] = []

    # Asama 1 — normalize birebir
    suffix_stage: List[Tuple[str, int]] = []
    for key, qty in quantities.items():
        cands = stl_by_norm.get(_norm_name(key), [])
        free = [c for c in cands if c not in claimed]
        if len(free) == 1:
            matched[free[0]] = matched.get(free[0], 0) + qty
            claimed.add(free[0])
        elif len(free) > 1:
            # Ayni normalize ada coklu dosya — belirsiz, insana sor
            unmatched_keys.append(key)
        else:
            suffix_stage.append((key, qty))

    # Asama 2 — sonek toleransi (yalniz sahiplenilmemis dosyalar)
    for key, qty in suffix_stage:
        nk = _norm_name(key)
        cands = []
        for nm in stl_names:
            if nm in claimed:
                continue
            ns = _norm_name(nm)
            longer, shorter = (ns, nk) if len(ns) >= len(nk) else (nk, ns)
            if longer.startswith(shorter) and _SUFFIX_TOLERANCE.match(longer[len(shorter):]):
                cands.append(nm)
        if len(cands) == 1:
            matched[cands[0]] = matched.get(cands[0], 0) + qty
            claimed.add(cands[0])
        else:
            unmatched_keys.append(key)

    unmatched_stls = [nm for nm in stl_names if nm not in claimed]
    return matched, unmatched_keys, unmatched_stls
