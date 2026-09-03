"""runtime/constraint_compiler.py — sembolik kisit -> motor parametresi (K-56g Faz 3).

LLM'in urettigi SEMBOLIK kisitlari ({"yon": "dik"}) deterministik olarak
motor parametrelerine cevirir ve dogrular. LLM bu katmani ASLA atlayamaz:
motor_kisitlari alanina yazilan her deger buradan cikar.

Politika sinirlari:
  * Bu modul KARAR VERMEZ (guven esigi / uygula-uygulama note_pipeline'in
    isi); yalniz "cevrilebilir mi, gecerli mi" sorusunu yanitlar.
  * HOCA TEYIDI (2026-07-22, HOCA_CEVAPLARI S2): "konumu degismeyecek"
    ibaresi KONUM degil DURUS ACISI kilididir ("yatay imal edilmesi talep
    edilmekte; herhangi bir yukseklikte veya X-Y koordinatinda olabilir").
    Bu yuzden: (a) orientation_lock yeni "durus_koru" degeri alir (STL'in
    geldigi durus korunur = R.ez=+ez pozlari; Rz duzlem-ici donus serbest
    cunku durus acisini degistirmez); (b) pinned_orientation ARTIK DERLENIR
    (ayni durus_koru kumesine — semantik hoca-teyitli); (c) pinned_position
    GOLGEDE kalir (gercek X-Y sabitleme ihtiyaci hicbir vakada dogrulanmadi).
  * Yon -> poz indeksi tablosu 28-pozluk master setten GEOMETRIK turetilir
    (A11: veri-adi/elle-sabit yok): dik/durus_koru = parcanin kendi +Z
    ekseni yukari kalan pozlar; yatay = +Z ekseni plakaya paralel dusen
    pozlar. Egik pozlar (8..11) hicbir kumeye girmez.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from src.runtime.quantity_text_parser import match_quantities_to_stls

logger = logging.getLogger(__name__)

_YON_DEGERLERI = ("dik", "yatay", "durus_koru")


@lru_cache(maxsize=1)
def yon_poz_tablosu() -> Dict[str, Tuple[int, ...]]:
    """28-poz master setten geometrik yon->indeks tablosu (deterministik).

    dik        : R @ ez = +ez (parca modellendigi gibi ayakta; ters [-ez]
                 BILEREK haric — 'dik uretilecek' emrinin muhafazakar yorumu).
    yatay      : (R @ ez).z ~ 0 (parca yan yatmis).
    durus_koru : STL'in geldigi durus korunur = dik kumesiyle AYNI indeksler
                 (R.ez=+ez; Rz duzlem-ici donus durus acisini degistirmez ->
                 serbest). Hoca S2 2026-07-22: "konumu degismeyecek" = durus
                 kilidi, z/x-y serbest.
    """
    import numpy as np
    from src.nesting3d.voxelize import N_MASTER_POSES, rotation_matrices

    ez = np.array([0.0, 0.0, 1.0, 0.0])
    dik: List[int] = []
    yatay: List[int] = []
    for i, r in enumerate(rotation_matrices(N_MASTER_POSES)):
        vz = float((np.asarray(r) @ ez)[2])
        if vz > 0.99:
            dik.append(i)
        elif abs(vz) < 0.01:
            yatay.append(i)
    return {"dik": tuple(dik), "yatay": tuple(yatay),
            "durus_koru": tuple(dik)}


@dataclass
class CompiledResult:
    """compile_constraints ciktisi.

    motor_kisitlari    : run_pipeline order alanina yazilabilir sozluk —
                         {"orientation_overrides": {ad: [idx,...]},
                          "pinned_placements": [...]}; bos dict = kisit yok.
    operator_isaretleri: insana gosterilecek kisa ASCII mesajlar.
    durumlar           : girdi kisiti basina {"kisit", "durum", "sebep"}
                         (durum: "derlendi" | "uygulanmadi").
    """

    motor_kisitlari: Dict[str, Any] = field(default_factory=dict)
    operator_isaretleri: List[str] = field(default_factory=list)
    durumlar: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def uygulanmayan(self) -> List[Dict[str, Any]]:
        return [d for d in self.durumlar if d["durum"] == "uygulanmadi"]


def _ad_esle(parca_adi: Any, stl_names: List[str]) -> Optional[str]:
    """LLM'in verdigi adi gercek STL adina toleransli esle (tek aday sart).

    match_quantities_to_stls'in normalize + sonek-toleransi birebir yeniden
    kullanilir (dummy adet 1); belirsiz coklu aday = eslenmez (parser ilkesi:
    yanlis parcaya kisit yazmaktansa insana sor).
    """
    if not parca_adi or not stl_names:
        return None
    matched, _unm, _ = match_quantities_to_stls({str(parca_adi): 1}, stl_names)
    if len(matched) == 1:
        return next(iter(matched))
    return None


def compile_constraints(
    kisitlar: List[Dict[str, Any]],
    stl_names: List[str],
    *,
    plate_w_mm: Optional[float] = None,
    plate_d_mm: Optional[float] = None,
    n_orientations: int = 28,
) -> CompiledResult:
    """Sembolik kisit listesini dogrula + motor parametrelerine derle.

    Parametreler
    ------------
    kisitlar       : KisitRole ciktisi ogeleri (oylama alanlari olabilir).
    stl_names      : siparisteki gercek parca adlari.
    plate_w_mm/d   : plaka olculeri (pinned koordinat kontrolu; None = atla).
    n_orientations : aktif poz seti buyuklugu (master sete ilk-n kesiti);
                     yon kumesi bu kesitle KESISMIYORSA derleme hatasi
                     (sessiz genisletme YOK — poz seti buyutme karari
                     cagiranin/urun politikasinin isi).
    """
    res = CompiledResult()
    orient_overrides: Dict[str, Tuple[int, ...]] = {}

    def _dusur(k: Dict[str, Any], sebep: str) -> None:
        res.durumlar.append({"kisit": k, "durum": "uygulanmadi",
                             "sebep": sebep})
        ad = k.get("parca_adi") or "?"
        res.operator_isaretleri.append(
            f"kisit uygulanamadi [{k.get('tip')}] parca={ad}: {sebep}")

    for k in kisitlar or []:
        tip = k.get("tip")
        if tip == "belirsiz" or tip not in (
                "orientation_lock", "pinned_position", "pinned_orientation"):
            _dusur(k, "tip belirsiz/desteklenmiyor — operator karari gerekli")
            continue

        gercek_ad = _ad_esle(k.get("parca_adi"), stl_names)
        if gercek_ad is None:
            _dusur(k, "parca adi siparis listesine tek-aday eslenemedi")
            continue

        if tip == "orientation_lock":
            deger = k.get("deger") or {}
            yon = str(deger.get("yon") or "").strip().lower()
            if yon not in _YON_DEGERLERI:
                _dusur(k, f"gecersiz yon degeri: {yon!r}")
                continue
            izinli = yon_poz_tablosu()[yon]
            aktif = tuple(i for i in izinli if i < int(n_orientations))
            if not aktif:
                _dusur(k, f"yon '{yon}' aktif {n_orientations}-poz setiyle "
                          "kesismiyor (poz seti buyutulmeli)")
                continue
            if gercek_ad in orient_overrides:
                onceki = set(orient_overrides[gercek_ad])
                kesisim = tuple(sorted(onceki & set(aktif)))
                if not kesisim:
                    _dusur(k, "ayni parcada celisen yon kilitleri "
                              "(dik+yatay) — kesisim bos")
                    continue
                aktif = kesisim
            orient_overrides[gercek_ad] = aktif
            res.durumlar.append({"kisit": k, "durum": "derlendi",
                                 "sebep": None})
            continue

        if tip == "pinned_orientation":
            # HOCA S2 TEYIDI (2026-07-22): durus-acisi sabitleme = durus_koru
            # kumesi (z/x-y serbest). Artik GOLGE DEGIL — derlenir.
            aktif = tuple(i for i in yon_poz_tablosu()["durus_koru"]
                          if i < int(n_orientations))
            if not aktif:
                _dusur(k, f"durus_koru kumesi aktif {n_orientations}-poz "
                          "setiyle kesismiyor")
                continue
            if gercek_ad in orient_overrides:
                kesisim = tuple(sorted(
                    set(orient_overrides[gercek_ad]) & set(aktif)))
                if not kesisim:
                    _dusur(k, "ayni parcada celisen kilitler — kesisim bos")
                    continue
                aktif = kesisim
            orient_overrides[gercek_ad] = aktif
            res.durumlar.append({"kisit": k, "durum": "derlendi",
                                 "sebep": None})
            continue

        # pinned_position — GOLGEDE kalir (gercek X-Y sabitleme ihtiyaci
        # hicbir vakada dogrulanmadi; hoca vakasi durus kilidi cikti).
        # Koordinat verildiyse plaka-ici on-kontrol yine yapilir ki operator
        # isareti "gecersiz koordinat" bilgisini simdiden tasisin.
        deger = k.get("deger") or {}
        x, y = deger.get("x_mm"), deger.get("y_mm")
        if (x is not None and y is not None
                and plate_w_mm is not None and plate_d_mm is not None):
            try:
                xf, yf = float(x), float(y)
            except (TypeError, ValueError):
                _dusur(k, "pinned koordinati sayiya cevrilemedi")
                continue
            if not (0.0 <= xf <= float(plate_w_mm)
                    and 0.0 <= yf <= float(plate_d_mm)):
                _dusur(k, f"pinned koordinati plaka disi "
                          f"({xf:.1f},{yf:.1f})")
                continue
        _dusur(k, "pinned_position golge: gercek X-Y sabitleme ihtiyaci "
                  "dogrulanmadi (hoca S2: 'konum' ibaresi durus kilidi "
                  "cikti) — operator karari")

    if orient_overrides:
        res.motor_kisitlari["orientation_overrides"] = {
            ad: list(t) for ad, t in orient_overrides.items()}
    return res
