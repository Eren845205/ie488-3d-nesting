"""plaka_bolme.py — U1: parti-ici plaka yukseklik fizibilitesi + bolme onerisi.

MIMARI (Eren 2026-08-20, RUNBOOK/YONTEM U1 kaydi): bolme kapisi karar
katmaninin ALTINDADIR —
  1. KESIN hakem = GERCEK-HACIM alt siniri (toplam gercek parca hacmi /
     plaka alani). Hicbir yerlesim bunu delemez (hacim korunumu). YALNIZ
     bu sinir plaka yuksekligini asarsa "bolme ZORUNLU" denir.
  2. bbox-hucre tahmini KANIT DEGILDIR (2026-08-20 dersi: 458,4 sonucu
     496'lik bbox-LB'yi deldi) — yalniz N-onerisi/siralama icin TAHMIN.
  3. Kesin sinir siga diyorsa erken bolme YASAK: asim algoritmanin
     sucudur; once dogru mod (KARAR-6 kalite-once), bolme SON CARE.

Bu modul SAF mantiktir (nesting3d import etmez); pipeline kablosu
rapor-only alan ekler (v1a) — bol-ve-kos entegrasyonu v1b'nin isi.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass
class ParcaOzeti:
    """Bolme hesabi icin gereken asgari parca bilgisi."""
    ad: str
    qty: int
    w_mm: float
    d_mm: float
    h_mm: float
    gercek_hacim_mm3: Optional[float] = None  # None -> bbox hacmi kullanilir


@dataclass
class BolmeKarari:
    lb_kesin_mm: float            # gercek-hacim alt siniri (delinemez)
    lb_tahmin_mm: float           # bbox-hucre tahmini (kanit DEGIL)
    plaka_h_mm: Optional[float]
    bolme_zorunlu: bool           # lb_kesin > plaka_h (hicbir algoritma sigdiramaz)
    oneri_n: int                  # onerilen plaka sayisi (>=1)
    atama: List[List[str]] = field(default_factory=list)  # plaka-basina model adlari
    not_: str = ""


def _bbox_hacim(p: ParcaOzeti) -> float:
    return p.w_mm * p.d_mm * p.h_mm


def gercek_hacim_lb_mm(parcalar: Sequence[ParcaOzeti], plate_w: float,
                       plate_d: float) -> float:
    """KESIN alt sinir: toplam gercek hacim / plaka alani (doluluk %100).

    gercek_hacim verilmeyen parcada bbox hacmi kullanilir — bu LB'yi
    YUKSELTIR (bbox >= gercek) ve 'kesin' vasfini bozar; cagiran taraf
    true_fill tasiyorsa gecmelidir. Konservatif kullanim: bolme-zorunlu
    hukmu yalniz TUM parcalarin gercek hacmi biliniyorsa verilir
    (bolme_karari icinde kontrol edilir).
    """
    toplam = sum((p.gercek_hacim_mm3 if p.gercek_hacim_mm3 is not None
                  else _bbox_hacim(p)) * p.qty for p in parcalar)
    alan = plate_w * plate_d
    return toplam / alan if alan > 0 else float("inf")


def bbox_hucre_tahmin_mm(parcalar: Sequence[ParcaOzeti], plate_w: float,
                         plate_d: float, clear: float) -> float:
    """TAHMIN: (boyut+clearance) hucre hacimleri toplami / plaka alani.

    Eksen-hizali bbox-paketleme icin gerceklik-yakini kestirim; gercek
    geometri (ic-ice/yuvalama) bunu DELEBILIR — kanit olarak KULLANILMAZ.
    """
    toplam = sum((p.w_mm + clear) * (p.d_mm + clear) * (p.h_mm + clear)
                 * p.qty for p in parcalar)
    alan = plate_w * plate_d
    return toplam / alan if alan > 0 else float("inf")


def asan_mi(p: ParcaOzeti, plate_w: float, plate_d: float,
            clear: float) -> bool:
    """Iki buyuk boyutuyla yatayda plakaya sigmayan parca (dik-zorunlu)."""
    d0, d1, d2 = sorted((p.w_mm, p.d_mm, p.h_mm))
    W, D = max(plate_w, plate_d), min(plate_w, plate_d)
    return not (d2 + clear <= W and d1 + clear <= D)


def parca_atama(parcalar: Sequence[ParcaOzeti], n: int, plate_w: float,
                plate_d: float, clear: float) -> List[List[str]]:
    """v1 atama: yukseklik-surucu (asan) sinif ILK plakada toplanir
    (PLAN8 dersi: tek-tip/sinif-ayrimli plan); kalan modeller bbox-hacim
    buyuklugune gore N plakaya acgozlu dengelenir (model butunlugu korunur
    — bir model tek plakada kalir; qty cok buyukse v1b boler)."""
    if n <= 1:
        return [[p.ad for p in parcalar]]
    plakalar: List[List[str]] = [[] for _ in range(n)]
    yukler = [0.0] * n
    asanlar = [p for p in parcalar if asan_mi(p, plate_w, plate_d, clear)]
    digerleri = [p for p in parcalar if not asan_mi(p, plate_w, plate_d, clear)]
    for p in asanlar:
        plakalar[0].append(p.ad)
        yukler[0] += _bbox_hacim(p) * p.qty
    for p in sorted(digerleri, key=lambda q: -_bbox_hacim(q) * q.qty):
        i = min(range(n), key=lambda k: yukler[k])
        plakalar[i].append(p.ad)
        yukler[i] += _bbox_hacim(p) * p.qty
    return [pl for pl in plakalar if pl]


def bolme_karari(parcalar: Sequence[ParcaOzeti], plate_w: float,
                 plate_d: float, plate_h: Optional[float], clear: float,
                 hedef_doluluk: float = 0.85) -> BolmeKarari:
    """LB hakemi + N onerisi (rapor-only karar nesnesi).

    hedef_doluluk: N-onerisinde kullanilan pratik doluluk varsayimi
    (kesin-LB / hedef_doluluk = beklenen pratik yukseklik). Kanit degil.
    """
    lb_kesin = gercek_hacim_lb_mm(parcalar, plate_w, plate_d)
    lb_tahmin = bbox_hucre_tahmin_mm(parcalar, plate_w, plate_d, clear)
    hepsi_gercek = all(p.gercek_hacim_mm3 is not None for p in parcalar)
    if plate_h is None or plate_h <= 0:
        return BolmeKarari(round(lb_kesin, 1), round(lb_tahmin, 1), plate_h,
                           False, 1, [[p.ad for p in parcalar]],
                           "plaka yuksekligi bilinmiyor — kapi devre disi")
    zorunlu = hepsi_gercek and lb_kesin > plate_h
    pratik = lb_kesin / max(hedef_doluluk, 1e-6)
    if zorunlu:
        n = max(2, math.ceil(lb_kesin / (plate_h * hedef_doluluk)))
        not_ = ("BOLME ZORUNLU: gercek-hacim LB plaka yuksekligini asiyor "
                "(hicbir algoritma tek plakaya sigdiramaz)")
    elif pratik > plate_h:
        n = math.ceil(pratik / plate_h)
        not_ = ("bolme ONERILIR (tahmini; kanit degil) — once dogru mod "
                "denenir (KARAR-6), bolme SON CARE")
    else:
        n = 1
        not_ = "tek plaka beklenir"
    atama = parca_atama(parcalar, n, plate_w, plate_d, clear)
    return BolmeKarari(round(lb_kesin, 1), round(lb_tahmin, 1), plate_h,
                       zorunlu, n, atama, not_)


def rapor_alani(karar: BolmeKarari, sonuc_h_mm: Optional[float]) -> Dict:
    """Nesting sonucuna eklenecek additive rapor alani (tek-tarafli)."""
    d = {"lb_kesin_mm": karar.lb_kesin_mm,
         "lb_tahmin_mm": karar.lb_tahmin_mm,
         "plaka_h_mm": karar.plaka_h_mm,
         "bolme_zorunlu": karar.bolme_zorunlu,
         "oneri_n": karar.oneri_n,
         "oneri_atama": karar.atama,
         "not": karar.not_}
    if (sonuc_h_mm is not None and karar.plaka_h_mm
            and sonuc_h_mm > karar.plaka_h_mm):
        d["asim_mm"] = round(sonuc_h_mm - karar.plaka_h_mm, 1)
        if not karar.bolme_zorunlu:
            d["asim_yorumu"] = ("LB sigar diyor — asim ALGORITMA/mod "
                                "secimi sorunu; once kalite-yol (KARAR-6), "
                                "bolme son care")
        else:
            d["asim_yorumu"] = "bolme zorunlu (LB kaniti)"
    return d
