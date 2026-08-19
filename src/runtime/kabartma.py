# -*- coding: utf-8 -*-
"""runtime/kabartma.py — parca ustu kabartma/gomu yazi okuma (KANAL-3 MVP).

Hoca S4 (2026-08-03) kisit kanali 3: parca STL'i uzerinde kabartma label
("XY" = XY duzleminde/yatay uretim). Fizibilite kaniti 2026-08-15 (a2):
alt yuzeye 0.4mm gomulu "XY-1" + "P3-ALTM-26-001" — geometrik cikarim +
qwen2.5vl:3b okumasi birebir dogru.

Boru hatti (hepsi opt-in cagri; uretim yolu default CAGIRMAZ):
  1. GEOMETRIK KAPI: buyuk duz dis yuzeye 0.1-1.5mm ofsetli kucuk-alanli
     yatay ucgen katmani ara (yazi tabani). Yoksa None — VL cagrisi YOK.
  2. RENDER: katman ucgenlerini 2B dolgulu ciz (alt yuzeydeyse AYNA duzelt).
  3. OKUMA: yerel vision-LLM (Ollama) goruntuden metni cikarir.
  4. NOT ADAYI: metin durus-kalibi (XY/XZ/YZ) tasiyorsa anlamlandirilmis
     not satiri uret -> mevcut not->kisit hattina (kisit-onay) akar;
     kaynak="parca_label" (UI etiketi: "parca ustu kabartma").

A2/A11: okuma hicbir kisiti DOGRUDAN uygulamaz — yalniz not adayi uretir;
karar operatorde (kisit_modu golge + /kisit-onay onayi).
"""
from __future__ import annotations

import io
import json
import logging
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

VL_MODEL = "qwen2.5vl:3b"
VL_URL = "http://localhost:11434/api/generate"
VL_PROMPT = ("Bu goruntude muhendislik parcasina kazinmis yazilar var. "
             "SADECE gordugun yazilari aynen listele, baska aciklama yazma.")

# yazi katmani ofset bandi (mm): dis yuzeyden bu kadar iceride/disarida
OFSET_MIN_MM = 0.1
OFSET_MAX_MM = 1.5
# yazi katmani alani, parca izdusum alaninin en fazla bu orani olabilir
ALAN_ORAN_TAVAN = 0.2

_DURUS_KALIBI = re.compile(r"\b([XYZ])[\s\-]?([XYZ])\b")

# Turkce buyuk-harf aksan katlamasi (echo filtresi normalize adimi)
_TR_KATLAMA = str.maketrans("ÇĞİÖŞÜ", "CGIOSU")


def kabartma_acik(root=None) -> bool:
    """Mail-ingest oto-taramasi acik mi? configs/llm.local.json
    "kabartma_okuma" (Eren karari 2026-08-15: true). Eksik/hata = False
    (bit-ozdes eski davranis — rollout guvenligi)."""
    try:
        p = Path(root or _ROOT) / "configs" / "llm.local.json"
        return bool(json.loads(p.read_text(encoding="utf-8"))
                    .get("kabartma_okuma", False))
    except Exception:
        return False


def kabartma_goruntusu(mesh, pitch_px: float = 0.1
                       ) -> Optional[Tuple[Any, str]]:
    """Geometrik kapi + render: (PIL.Image, yuz) veya None.

    yuz: "alt" (ayna duzeltilmis) | "ust". None = kabartma katmani yok
    (VL cagrisi yapilmamali — sifir maliyet).
    """
    try:
        m = mesh.copy()
        m.apply_translation(-m.bounds[0])
        tris = m.triangles
        zall = tris[:, :, 2]
        z1 = float(m.bounds[1][2])
        # yatay ucgenler: uc kose z'si esit (tol 0.02)
        yatay = (zall.max(axis=1) - zall.min(axis=1)) < 0.02
        if not yatay.any():
            return None
        seviyeler = np.round(zall[yatay][:, 0], 2)
        adaylar = []
        for L in np.unique(seviyeler):
            alt_of, ust_of = float(L), float(z1 - L)
            if OFSET_MIN_MM <= alt_of <= OFSET_MAX_MM:
                adaylar.append((float(L), "alt"))
            elif OFSET_MIN_MM <= ust_of <= OFSET_MAX_MM:
                adaylar.append((float(L), "ust"))
        if not adaylar:
            return None
        # en genis aday katmani sec (alan orani tavanla sinirli)
        (x1, y1) = m.bounds[1][0], m.bounds[1][1]
        iz_alan = float(x1 * y1) or 1.0
        en_iyi = None
        for L, yuz in adaylar:
            sec = yatay & np.all(np.abs(zall - L) < 0.05, axis=1)
            t = tris[sec]
            if len(t) == 0:
                continue
            # ucgen alanlari (2B izdusum)
            a = t[:, 1, :2] - t[:, 0, :2]
            b = t[:, 2, :2] - t[:, 0, :2]
            alan = float(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum()) / 2
            if alan <= 0 or alan / iz_alan > ALAN_ORAN_TAVAN:
                continue
            if en_iyi is None or alan > en_iyi[2]:
                en_iyi = (t, yuz, alan)
        if en_iyi is None:
            return None
        t04, yuz, _ = en_iyi

        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PIL import Image

        fig, ax = plt.subplots(figsize=(12, 4.5), dpi=160)
        for t in t04:
            ax.fill(t[:, 0], t[:, 1], color="black", lw=0.2)
        ax.set_aspect("equal")
        ax.axis("off")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        im = Image.open(buf).convert("L")
        if yuz == "alt":  # alttan gomu yazi ustten AYNA gorunur
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
        return im, yuz
    except Exception:
        logger.exception("kabartma_goruntusu: cikarilamadi")
        return None


def kabartma_metni(im, *, model: str = VL_MODEL, base_url: str = VL_URL,
                   timeout_s: float = 240.0) -> Optional[str]:
    """Goruntuyu yerel vision-LLM'e okut; metin veya None (hata/kapali)."""
    try:
        import base64

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        req = urllib.request.Request(
            base_url,
            data=json.dumps({"model": model, "prompt": VL_PROMPT,
                             "images": [base64.b64encode(
                                 buf.getvalue()).decode()],
                             "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=timeout_s).read())
        metin = (r.get("response") or "").strip()
        return metin or None
    except Exception as exc:
        logger.warning("kabartma_metni: VL okumasi yapilamadi (%s)", exc)
        return None


def _vl_satir_supheli(sat: str) -> bool:
    """VL prompt-echo / halusinasyon satiri mi?

    2026-08-16 plan1 canli bulgusu: qwen2.5vl etiketsiz parcada prompt
    talimatini geri basiyor ("SADECE GORDUGUN YAZILARI AYNEN LISTELLE" x8)
    veya prompt kelimelerinden uyduruyor ("Muhendislik | Parca | Kazinmis").
    Genel kural (veri-adi yok): satirin kelimelerinin >=%60'i prompt kelime
    kumesindeyse echo sayilir. Gercek etiketler (XY-1, P3-ALTM-26-001)
    prompt'ta gecmedigi icin filtreden etkilenmez.
    """
    def _norm(metin: str):
        # Turkce aksan katlamasi: VL echo'su aksanli varyant uretebiliyor
        # ("GORDUGUN" -> "GORUNGUN"/"GORDUGUN", "LISTELE" -> "LISTELEMEK").
        m = metin.upper().translate(_TR_KATLAMA)
        return [k for k in re.sub(r"[^A-Z0-9\-]+", " ", m).split()
                if len(k) > 1]

    prompt_k = set(_norm(VL_PROMPT))
    imzalar = {p for p in prompt_k if len(p) >= 4}
    kelimeler = _norm(sat)
    if not kelimeler:
        return True  # yalniz noktalama/rakam-siralamasi — bilgi tasimiyor

    def _promptta(k: str) -> bool:
        if k in prompt_k:
            return True
        # govde eslesmesi: "PARCA" ~ "PARCASINA", "LISTELENEN" ~ "LISTELE"
        # (Turkce ek almis/kok haline donmus echo kelimeleri)
        return any(len(k) >= 4
                   and (p.startswith(k) or k.startswith(p))
                   for p in imzalar)

    # Kural 1: satirda >=2 FARKLI prompt-imza kelimesi geciyorsa echo
    # (uzun parafraz halusinasyonlari: "Iste listelenen yazilardan baska
    # bir aciklama yapmadan..." gibi satirlarda oran dusuk kalabiliyor).
    n_imza = sum(1 for k in set(kelimeler) if _promptta(k))
    if n_imza >= 2:
        return True
    # Kural 2: kisa satirlarda kelimelerin cogu prompt'tan geliyorsa echo.
    oran = sum(1 for k in kelimeler if _promptta(k)) / len(kelimeler)
    return oran >= 0.6


def _durus_cumlesi(metin: str, parca_adi: str) -> Optional[str]:
    """VL metninden durus-etiketi kalibini anlamlandirilmis nota cevir."""
    for sat in metin.splitlines():
        m = _DURUS_KALIBI.search(sat.upper())
        if m and m.group(1) != m.group(2):
            duzlem = m.group(1) + m.group(2)
            yatay = " (yatay)" if duzlem in ("XY", "YX") else ""
            return (f"{parca_adi} parcasi {duzlem} duzleminde{yatay} "
                    f"uretilecek — parca ustu kabartma etiketi: "
                    f"'{sat.strip()}'")
    return None


def kabartma_not_adaylari(stl_map: Dict[str, bytes],
                          *, _goruntu=None, _oku=None
                          ) -> List[Dict[str, Any]]:
    """STL haritasindan parca-label not adaylari uret (opt-in cagri).

    Donen adaylar note_detector semasiyla ayni: satir / kaynak /
    parca_adaylari. Kabartmasiz parca = sifir maliyet (geometrik kapi).
    _goruntu/_oku test enjeksiyonu (A9: imzalar gercekle ayni).
    """
    import trimesh

    goruntu = _goruntu or kabartma_goruntusu
    oku = _oku or kabartma_metni
    adaylar: List[Dict[str, Any]] = []
    for ad, veri in stl_map.items():
        try:
            mesh = trimesh.load(io.BytesIO(veri), file_type="stl",
                                force="mesh")
        except Exception:
            logger.warning("kabartma: %s yuklenemedi", ad)
            continue
        g = goruntu(mesh)
        if g is None:
            continue
        im, yuz = g
        metin = oku(im)
        if not metin:
            continue
        # prompt-echo / halusinasyon satirlarini ele (2026-08-16 bulgusu);
        # hicbir gercek satir kalmadiysa parca etiketsiz sayilir.
        satirlar = [s.strip() for s in metin.splitlines() if s.strip()]
        satirlar = [s for s in satirlar if not _vl_satir_supheli(s)]
        # VL loop artefakti: AYNI satir >=3 kez tekrarliyorsa ("Muhendislik
        # projesi" x10 canli bulgusu) o satir uydurmadir — elenir; kalanlar
        # sira korunarak tekillestirilir.
        _sayim: Dict[str, int] = {}
        for s in satirlar:
            _sayim[s.upper()] = _sayim.get(s.upper(), 0) + 1
        _gorulen = set()
        satirlar = [s for s in satirlar
                    if _sayim[s.upper()] < 3
                    and s.upper() not in _gorulen
                    and not _gorulen.add(s.upper())]
        # Asiri-liste artefakti: gercek kabartma etiketi 1-3 kisa koddur
        # (a2 kaniti: "XY-1" + "P3-ALTM-26-001"); >4 farkli "etiket" =
        # serbest halusinasyon listesi — tumu supheli.
        if len(satirlar) > 4:
            logger.info("kabartma: %s VL ciktisi %d satirlik liste — "
                        "halusinasyon sayildi, not adayi uretilmedi",
                        ad, len(satirlar))
            continue
        if not satirlar:
            logger.info("kabartma: %s VL ciktisi prompt-echo/supheli — "
                        "not adayi uretilmedi", ad)
            continue
        metin = "\n".join(satirlar)
        temiz = " | ".join(satirlar)
        satir = (_durus_cumlesi(metin, ad)
                 or f"{ad} parca ustu kabartma etiketi: '{temiz}'")
        stl_ad = (str(ad) if str(ad).lower().endswith(".stl")
                  else f"{ad}.stl")
        adaylar.append({"satir": satir, "satir_no": None,
                        "kaynak": "parca_label",
                        "parca_adaylari": [stl_ad],
                        "ham_metin": temiz, "yuz": yuz})
    return adaylar
