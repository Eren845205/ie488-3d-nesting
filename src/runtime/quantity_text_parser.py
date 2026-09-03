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

# Akan-cumle kalibi: "<ad> isimli parçadan <sayi> adet" (2026-08-18 gercek
# musteri maili: "520 adet isimli parçadan 520 adet, 36 adet isimli parçadan
# 36 adet ... yerleştirilmesini istiyorum"). Satir-bazli kaliplardan farki:
#   * TEK cumle icinde virgul/"ve" ile ayrilmis COK kayit tasir;
#   * kayit satir sonuna tasabilir (mail istemcisi kirmasi) -> metin once
#     bosluk-normalize edilip BUTUN halinde taranir;
#   * parca adi "adet" kelimesini ICEREBILIR ("520 adet" adli dosya) — klasik
#     kalip bu yuzden yanlis boler, "isimli parça" ibaresi guvenli caradir.
# Ad grubu virgul/noktali-virgulle sinirlidir (kayitlar birbirine karismaz);
# bas taraftaki baglac/serbest metin artiklari _ISIMLI_AD_ARTIK ile kirpilir
# (kirpilamayan uzun onek match_quantities_to_stls sonek-caps asamasinda
# gercek STL adina oturur).
_QTY_ISIMLI = re.compile(
    r"(?P<ad>[^,;]+?)\s+isimli\s+par[cç]a\w*\s+(?P<adet>\d+)\s*adet\b",
    re.IGNORECASE,
)
_ISIMLI_AD_ARTIK = re.compile(r"^(?:ve|ile|ayr[ıi]ca)\s+", re.IGNORECASE)
_ISIMLI_IBARE = re.compile(r"isimli\s+par[cç]a", re.IGNORECASE)

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

    # Asama-0: akan-cumle "isimli parça" kalibi. Kayit satir ortasindan
    # kirilabilir (mail istemcisi) — ama TUM metni tek satira indirmek
    # onceki satirdaki BAGIMSIZ kaydi ad grubuna yutar. Bu yuzden yalniz
    # ibare-ici kirilmalar birlestirilir: sonraki satir "isimli" ile
    # basliyorsa VEYA onceki satir "isimli"/"isimli parça*" ile bitiyorsa.
    _fold = lambda s: s.translate(_TR_FOLD).casefold()  # noqa: E731
    birlesik: List[str] = []
    for _ln in (text or "").splitlines():
        _ln = _ln.strip()
        if not _ln:
            birlesik.append(_ln)
            continue
        if birlesik and birlesik[-1] and (
                re.match(r"^isimli\b", _fold(_ln))
                or re.search(r"\bisimli(?:\s+parca\w*)?$", _fold(birlesik[-1]))):
            birlesik[-1] = birlesik[-1] + " " + _ln
        else:
            birlesik.append(_ln)
    duz_metin = " ; ".join(re.sub(r"\s+", " ", s) for s in birlesik if s)
    for m in _QTY_ISIMLI.finditer(duz_metin):
        ad = _ISIMLI_AD_ARTIK.sub("", m.group("ad").strip()).strip()
        adet = int(m.group("adet"))
        if not ad or adet <= 0:
            continue
        if adet > MAX_QTY:
            logger.warning(
                "quantity_text_parser: '%s' adeti asiri buyuk (%d, izin verilen "
                "ust sinir %d) — clamp'lendi.", ad, adet, MAX_QTY,
            )
            adet = MAX_QTY
        result[ad] = result.get(ad, 0) + adet

    for line in text.splitlines():
        stripped = line.strip()
        # "isimli parça" ibaresi tasiyan satirlar Asama-0'da islenmistir;
        # satir-bazli kaliplara sokulursa ayni kayit IKI kez sayilir veya
        # yanlis bolunmus sahte ad uretilir -> atla.
        if _ISIMLI_IBARE.search(stripped):
            continue
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


def _ham_name(name: str) -> str:
    """Birebir (Asama-0) eslestirme anahtari: alt cizgi KORUNUR.

    _norm_name alt cizgiyi bosluga cevirdigi icin "kapak" ile "kapak_"
    AYNI normalize ada duser (gercek musteri verisinde iki AYRI parca,
    2026-08-18) — birebir asama bu ayrimi korur: yalniz case/TR-katlama +
    .stl uzantisi dusurme + bosluk tekleme yapilir.
    """
    s = str(name).translate(_TR_FOLD).casefold()
    if s.endswith(".stl"):
        s = s[:-4]
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
    stl_by_ham: Dict[str, List[str]] = {}
    for nm in stl_names:
        stl_by_norm.setdefault(_norm_name(nm), []).append(nm)
        stl_by_ham.setdefault(_ham_name(nm), []).append(nm)

    matched: Dict[str, int] = {}
    claimed: set = set()
    unmatched_keys: List[str] = []

    # Asama 0 — HAM birebir (alt cizgi korunur): "kapak_" beyani yalniz
    # "kapak_.stl"i alir, "kapak.stl"e sizmaz (iki AYRI parca). Bu asama
    # normalize asamadan ONCE kosar ki alt-cizgi katlamasi belirsizlik
    # uretmesin (2026-08-18 gercek musteri verisi dersi).
    norm_stage: List[Tuple[str, int]] = []
    for key, qty in quantities.items():
        cands = stl_by_ham.get(_ham_name(key), [])
        free = [c for c in cands if c not in claimed]
        if len(free) == 1:
            matched[free[0]] = matched.get(free[0], 0) + qty
            claimed.add(free[0])
        else:
            norm_stage.append((key, qty))

    # Asama 1 — normalize birebir
    suffix_stage: List[Tuple[str, int]] = []
    for key, qty in norm_stage:
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
    prefix_stage: List[Tuple[str, int]] = []
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
            prefix_stage.append((key, qty))

    # Asama 3 — onek-artigi toleransi: akan-cumle kaliplarinda ("... sekilde
    # 520 adet isimli parcadan") ad grubunun BASINA serbest metin yapisir;
    # normalize anahtar gercek STL adiyla KELIME SINIRINDA bitiyorsa ve tek
    # serbest aday varsa eslenir. Cok kisa (<3) adlar bu asamaya girmez —
    # "A" gibi bir ad her cumle sonuna yapisip yanlis eslerdi. Birden cok
    # aday ayni anahtar sonunda eslesiyorsa belirsizlik korunur (insana sor).
    for key, qty in prefix_stage:
        nk = _norm_name(key)
        cands = []
        for nm in stl_names:
            if nm in claimed:
                continue
            ns = _norm_name(nm)
            if len(ns) < 3:
                continue
            if nk == ns or nk.endswith(" " + ns):
                cands.append(nm)
        if len(cands) == 1:
            matched[cands[0]] = matched.get(cands[0], 0) + qty
            claimed.add(cands[0])
        else:
            unmatched_keys.append(key)

    unmatched_stls = [nm for nm in stl_names if nm not in claimed]
    return matched, unmatched_keys, unmatched_stls
