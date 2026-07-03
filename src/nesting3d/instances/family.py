"""family.py — F1 aile taksonomisi (kural-tabanli parca/instance siniflandirma).

Bir NestingInstance (veya PartSpec listesi) icin geometrik aile etiketi uretir.
Cekirdek satilabilirlik ilkesi: DUSUK GUVENDE "unknown" don — bilinmeyeni
bilinmeyen olarak etiketle, kati parca gibi davranarak yanlis karar verme.

Aileler
-------
- thin_shell : ince cidarli, kompakt kabuk (yarim-kure/can; dusuk true_fill).
- tube       : ince cidarli, uzun/boru benzeri (dusuk true_fill + yuksek uzama).
- thin_plate : cok yassi kati levha (min/mak kenar orani cok kucuk).
- long_rod   : uzun-ince kati cubuk (yuksek uzama + ince kesit).
- solid_bulk : tikiz/kup benzeri kati blok.
- mixed_scale: tek geometrik aile baskin degil ama buyuk olcek dagilimi var.
- unknown    : yeterli guven yok / olculemeyen geometri.

Iki katman
----------
- classify_prelim(instance|parts)         -> (family, confidence)
      bbox + loader verisi (wall_mm/true_fill) ile on-siniflandirma.
- classify_confirmed(prelim, voxel_fill)   -> (family, confidence)
      voxel-sonrasi gercek doluluk ile prelim'i rafine eden SAF fonksiyon
      (cozucuye baglanmaz).
- classify_family(instance|parts)          -> (family, confidence)
      birincil giris; classify_prelim'in takma adi.

Tum fonksiyonlar deterministiktir (seed bagimsiz, yalnizca geometriye bagli).
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional, Tuple, Union

from src.nesting3d.instances.format import NestingInstance, PartSpec

_EPS = 1e-9

# Aile isimleri (sabit sozluk)
THIN_SHELL = "thin_shell"
TUBE = "tube"
THIN_PLATE = "thin_plate"
LONG_ROD = "long_rod"
SOLID_BULK = "solid_bulk"
MIXED_SCALE = "mixed_scale"
UNKNOWN = "unknown"

FAMILY_NAMES: Tuple[str, ...] = (
    THIN_SHELL, TUBE, THIN_PLATE, LONG_ROD, SOLID_BULK, MIXED_SCALE, UNKNOWN,
)

# Esikler (birimsiz oranlar) — deterministik, geometriden turer.
_FLAT_PLATE = 0.15      # min/mak kenar < bu -> yassi levha
_FLAT_ROD = 0.25        # cubukta ince-kesit kapisi (min/mak)
_ELONG_ROD = 5.0        # mak/orta > bu -> cubuk uzamasi
_ELONG_TUBE = 3.0       # hollow + mak/orta > bu -> boru (aksi kompakt kabuk)
_FILL_HOLLOW = 0.5      # true_fill < bu -> shell/hollow adayi
_CUBE_FLAT = 0.30       # min/mak > bu -> tikiz (kup benzeri) kati
_DOM_FRAC = 0.60        # instance baskin aile esigi
_MIXED_VOL_RATIO = 30.0  # mixed_scale icin bbox-hacim yayilma esigi


# ---------------------------------------------------------------------------
# Parca gorunumu (normalize edilmis giris)
# ---------------------------------------------------------------------------

class _PartView(NamedTuple):
    mn: float
    mid: float
    mx: float
    wall_mm: Optional[float]
    true_fill: Optional[float]
    measured: bool  # solidligi biliyor muyuz? (box-source VEYA olculmus stl)


def _part_view(part: PartSpec) -> _PartView:
    """PartSpec -> normalize gorunum.

    box-source: kati kabul edilir (true_fill None ise 1.0), solidlik BILINIR.
    stl-source: true_fill dolu ise olculmus; None ise olculememis (belirsiz).
    """
    w = part.width_mm or 0.0
    d = part.depth_mm or 0.0
    h = part.height_mm or 0.0
    mn, mid, mx = sorted([w, d, h])

    tf = part.true_fill
    if part.source == "box":
        measured = True
        if tf is None:
            tf = 1.0  # kati kutu (tanim geregi dolu)
    else:  # stl
        measured = tf is not None

    return _PartView(mn=mn, mid=mid, mx=mx, wall_mm=part.wall_mm,
                     true_fill=tf, measured=measured)


def _fill_conf(true_fill: Optional[float], base: float = 0.70) -> float:
    """Doluluktan shell/tube guveni: bosluk arttikca guven artar."""
    if true_fill is None:
        return base
    # true_fill 0.5'e yaklastikca base, 0'a yaklastikca ~0.95.
    margin = max(0.0, _FILL_HOLLOW - true_fill) / _FILL_HOLLOW  # 0..1
    return min(0.95, base + 0.25 * margin)


# ---------------------------------------------------------------------------
# Parca-seviyesi siniflandirma
# ---------------------------------------------------------------------------

def _classify_view(v: _PartView) -> Tuple[str, float]:
    """Tek parca gorunumu -> (family, confidence)."""
    if v.mx <= _EPS:
        return UNKNOWN, 0.0

    flat = v.mn / (v.mx + _EPS)          # 0..1 (kucuk = yassi)
    elong = v.mx / (v.mid + _EPS)        # >=1 (buyuk = uzun)

    hollow = (v.wall_mm is not None) or (
        v.true_fill is not None and v.true_fill < _FILL_HOLLOW
    )

    # 1) Hollow ise: kabuk mu boru mu? (shape kararindan ONCE gelir)
    if hollow:
        conf = _fill_conf(v.true_fill)
        if elong > _ELONG_TUBE:
            return TUBE, conf
        return THIN_SHELL, conf

    # Sekil-kesin aileler (hollowluktan bagimsiz gecerli)
    is_rod = elong > _ELONG_ROD and flat < _FLAT_ROD
    is_plate = flat < _FLAT_PLATE and not is_rod

    # 2) Olculememis stl: yalnizca sekil-kesin aileler; aksi unknown.
    if not v.measured:
        if is_rod:
            return LONG_ROD, 0.55
        if is_plate:
            return THIN_PLATE, 0.55
        return UNKNOWN, 0.30

    # 3) Olculmus/bilinen kati.
    if is_rod:
        conf = min(0.95, 0.60 + 0.05 * min(elong / _ELONG_ROD, 4.0))
        return LONG_ROD, conf
    if is_plate:
        conf = 0.90 if flat < 0.08 else 0.75
        return THIN_PLATE, conf
    if flat > _CUBE_FLAT:
        conf = 0.85 if flat > 0.5 else 0.65
        return SOLID_BULK, conf
    # ara yassilik (0.15..0.30) kati: zayif tikiz
    return SOLID_BULK, 0.50


# ---------------------------------------------------------------------------
# Instance-seviyesi toplulastirma
# ---------------------------------------------------------------------------

def _iter_parts(obj: Union[NestingInstance, List[PartSpec]]) -> List[PartSpec]:
    if isinstance(obj, NestingInstance):
        return list(obj.parts)
    if hasattr(obj, "parts"):
        return list(obj.parts)  # duck-type NestingInstance
    return list(obj)


def _bbox_vol(v: _PartView) -> float:
    return v.mn * v.mid * v.mx


def classify_prelim(
    obj: Union[NestingInstance, List[PartSpec]],
) -> Tuple[str, float]:
    """On-siniflandirma (bbox + loader verisi). -> (family, confidence)."""
    parts = _iter_parts(obj)
    if not parts:
        return UNKNOWN, 0.0

    # qty-agirlikli oy + guven toplami
    votes: dict = {}
    conf_sum: dict = {}
    total_qty = 0
    vols: List[float] = []
    for p in parts:
        v = _part_view(p)
        fam, conf = _classify_view(v)
        qty = max(int(p.qty), 0)
        if qty == 0:
            continue
        votes[fam] = votes.get(fam, 0) + qty
        conf_sum[fam] = conf_sum.get(fam, 0.0) + conf * qty
        total_qty += qty
        bv = _bbox_vol(v)
        if bv > 0:
            vols.append(bv)

    if total_qty == 0:
        return UNKNOWN, 0.0

    # Baskin aile (esitlikte deterministik: sabit oncelik sirasi)
    def _key(item):
        fam, q = item
        return (q, -FAMILY_NAMES.index(fam))
    dominant, dom_qty = max(votes.items(), key=_key)
    frac = dom_qty / total_qty
    dom_mean_conf = conf_sum[dominant] / dom_qty

    if dominant != UNKNOWN and frac >= _DOM_FRAC:
        return dominant, round(min(0.99, frac * dom_mean_conf), 4)

    # Net geometrik cogunluk yok — olcek dagilimina bak
    vol_ratio = (max(vols) / (min(vols) + _EPS)) if vols else 1.0
    if vol_ratio > _MIXED_VOL_RATIO:
        conf = round(min(0.70, 0.40 + 0.30 * (1.0 - frac)), 4)
        return MIXED_SCALE, conf

    # Zayif cogunluk: bilinmeyeni bilinmeyen olarak etiketle
    if dominant == UNKNOWN:
        return UNKNOWN, round(frac, 4)
    return UNKNOWN, round(min(0.49, frac), 4)


# Birincil giris — classify_prelim takma adi.
def classify_family(
    obj: Union[NestingInstance, List[PartSpec]],
) -> Tuple[str, float]:
    """Instance/parca listesi -> (family, confidence).  classify_prelim'e esdeger."""
    return classify_prelim(obj)


def classify_confirmed(
    prelim: Tuple[str, float],
    voxel_fill: Optional[float],
) -> Tuple[str, float]:
    """Prelim'i voxel-sonrasi gercek doluluk ile rafine et (SAF fonksiyon).

    voxel_fill: [0,1] gercek voxel doluluk orani (occupied / bbox_voxels).
                None ise prelim aynen dondurulur (teyit verisi yok).

    Kurallar:
      - Gercekten bos (voxel_fill < 0.5): kati/bilinmeyen tahmin -> thin_shell'e
        yukselt; shell/tube tahmini teyit edilir (guven artar).
      - Gercekten dolu (voxel_fill >= 0.7): shell/tube tahmini yanlisti ->
        solid_bulk'a dusur; diger tahminler teyit edilir.
      - Ara doluluk: prelim korunur.
    """
    fam, conf = prelim
    if voxel_fill is None:
        return prelim

    if voxel_fill < 0.5:  # gercekten hollow
        if fam in (SOLID_BULK, UNKNOWN):
            return THIN_SHELL, max(conf, 0.60)
        if fam in (THIN_SHELL, TUBE):
            return fam, min(0.98, conf + 0.15)
        return fam, conf  # thin_plate/long_rod sekil-kesin, dokunma

    if voxel_fill >= 0.7:  # gercekten dolu
        if fam in (THIN_SHELL, TUBE):
            return SOLID_BULK, max(conf * 0.8, 0.50)
        return fam, min(0.98, conf + 0.10)

    return prelim
