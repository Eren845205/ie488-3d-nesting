# -*- coding: utf-8 -*-
"""k66_analitik_teshis.py — K-66 (a)+(b) ucuz teshis (A4 olc-once; KOSUSUZ).

(a) ANALITIK KAFES ALT-SINIRI: her modelin bbox'u + 2mm bosluk + 325x325
    kullanilabilir plaka ile eksen-hizali periyodik istif yuksekligi KAGIT
    USTUNDE hesaplanir (basit karisik-oryantasyon serit yerlestirme).
    Amac: fsm610 NFV-max 516,0'in ne kadarinin S1/S2 kiyas-sartlarindan
    BAGIMSIZ olarak gercekten masada oldugunu gostermek.
(b) MEVCUT 516 COZUMUNUN z-DAGILIMI: 127MB sonuc JSON'undaki Placement3D
    string'leri parse edilir (yeni kosu YOK); model-bazli z-taban dagilimi
    cikarilir. Sinirlilik: orientation_idx -> boyut permutasyonu JSON'dan
    cozulemedigi icin parca TEPE yuksekligi kesin degil; yalniz taban-z
    dagilimi ve sacilim raporlanir (teshis amacli yeterli).

Kosum (offline analiz, munhasir-kosu GEREKMEZ):
  python -m scripts.k66_analitik_teshis
SAF ASCII stdout. Cikti: results/k66_analitik_teshis.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k66_analitik_teshis.log"
OUT = _ROOT / "results" / "k66_analitik_teshis.json"
SONUC_JSON = Path(r"D:\ie488\results\fsm610_nfv_max_1787009208.json")
STL_DIR = Path(r"D:\ie488\results\fsm610_stl_persist")
ADETLER = {"27adet": 27, "27adet_": 27, "36 adet": 36, "520 adet": 520}
PLAKA_KULLANILABILIR = 325.0  # 335 - 2x5 kenar (hoca 2026-07-06)
BOSLUK = 2.0
PITCH = 2.0  # sonuc JSON'unun pitch'i (log kaniti)


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def katman_kapasitesi(w: float, d: float, alan: float = PLAKA_KULLANILABILIR,
                      bosluk: float = BOSLUK) -> int:
    """325x325'te (w+2)x(d+2) hucreli karisik-oryantasyon serit sayimi.

    Ana yonelim satirlari + artan seritte 90-derece cevrilmis dolgu.
    Basit ama ALT-SINIR olarak gecerli (daha iyi 2D paketleme yalniz
    sayiyi ARTIRIR -> yukseklik alt-siniri daha da DUSER).
    """
    cw, cd = w + bosluk, d + bosluk
    if cw > alan and cd > alan:
        return 0
    en_iyi = 0
    for a, b in ((cw, cd), (cd, cw)):
        if a > alan:
            continue
        n_sutun = int(alan // a)
        n_satir = int(alan // b)
        ana = n_sutun * n_satir
        # artan serit (alan - n_sutun*a genisliginde) 90-cevrilmis dolgu
        kalan = alan - n_sutun * a
        ek = 0
        if kalan >= b:
            ek = int(kalan // b) * int(alan // a) if False else \
                int(kalan // b) * n_satir  # cevrilmemis dar kolon
        # cevrilmis dolgu da dene
        if kalan >= b:
            ek = max(ek, int(kalan // b) * int(alan // a))
        en_iyi = max(en_iyi, ana + ek)
    return en_iyi


def kafes_yuksekligi(w: float, d: float, h: float, qty: int) -> dict:
    """Uc yatis oryantasyonundan en iyi periyodik istif yuksekligi."""
    en_iyi = None
    for dims, ad in (((w, d, h), "duz"), ((w, h, d), "yan"),
                     ((d, h, w), "dik")):
        taban_w, taban_d, kat_h = dims
        kap = katman_kapasitesi(taban_w, taban_d)
        if kap <= 0:
            continue
        import math
        n_kat = math.ceil(qty / kap)
        yuk = n_kat * (kat_h + BOSLUK) - BOSLUK  # son katin ustunde bosluk yok
        aday = {"oryantasyon": ad, "katman_kapasitesi": kap,
                "n_katman": n_kat, "yukseklik_mm": round(yuk, 1),
                "taban": [taban_w, taban_d], "kat_h": kat_h}
        if en_iyi is None or aday["yukseklik_mm"] < en_iyi["yukseklik_mm"]:
            en_iyi = aday
    return en_iyi or {"yukseklik_mm": None, "not": "hicbir yatis sigmiyor"}


def bolum_a() -> dict:
    import trimesh
    log("=" * 70)
    log("(a) ANALITIK KAFES ALT-SINIRI  (325x325 kullanilabilir, 2mm bosluk)")
    log("=" * 70)
    modeller = {}
    for stl in sorted(STL_DIR.glob("*.stl")):
        ad = stl.stem
        m = trimesh.load(str(stl), force="mesh")
        e = m.extents
        w, d, h = float(e[0]), float(e[1]), float(e[2])
        vol = abs(float(m.volume)) if m.is_watertight else None
        tf = (vol / (w * d * h)) if vol else None
        qty = ADETLER.get(ad, 1)
        kafes = kafes_yuksekligi(w, d, h, qty)
        modeller[ad] = {"bbox": [round(w, 1), round(d, 1), round(h, 1)],
                        "true_fill": round(tf, 3) if tf else None,
                        "qty": qty, "kafes": kafes}
        log(f"{ad:12s} bbox={w:6.1f}x{d:6.1f}x{h:6.1f} tf={tf:.3f} "
            f"qty={qty:3d} -> kafes {kafes.get('oryantasyon')}: "
            f"{kafes.get('katman_kapasitesi')}/katman x "
            f"{kafes.get('n_katman')} katman = "
            f"{kafes.get('yukseklik_mm')}mm")
    # Naif SIRALI toplam (her model ayri blok, ust uste — kaba UST-sinir
    # niteliginde bir plan; ic-ice/yan-yana karistirma yalniz DUSURUR):
    toplam = 0.0
    for ad, mm in modeller.items():
        y = mm["kafes"].get("yukseklik_mm")
        if y:
            toplam += y + BOSLUK
    toplam -= BOSLUK
    log("")
    log(f"NAIF SIRALI-BLOK PLAN TOPLAMI: {toplam:.1f}mm  "
        f"(karistirma/ic-ice YOK — gercek optimum bundan DUSUK)")
    log("NOT: cubuk (95x10x399.6) duz yatista 325'e SIGMAZ; 'dik' modda")
    log("     399.6 tavan yapar; capraz-yatis (325*sqrt2=459.6 > 399.6)")
    log("     MUMKUN ama eksen-hizali kafese girmez — ayri satir olarak")
    log("     raporlanir (rot-serbestisi S1 sorusuyla baglantili).")
    return {"modeller": modeller,
            "naif_sirali_toplam_mm": round(toplam, 1),
            "capraz_yatis_mumkun": True,
            "kullanilabilir_mm": PLAKA_KULLANILABILIR, "bosluk_mm": BOSLUK}


def bolum_b() -> dict:
    log("")
    log("=" * 70)
    log("(b) MEVCUT 516,0 COZUMUNUN z-TABAN DAGILIMI (offline parse)")
    log("=" * 70)
    if not SONUC_JSON.exists():
        log(f"UYARI: {SONUC_JSON} yok — (b) atlandi")
        return {"atlandi": True}
    rx = re.compile(r"Placement3D\(part_id='([^']+)', name='([^']+)', "
                    r"x=(\d+), y=(\d+), z=(\d+), orientation_idx=(\d+)\)")
    dagilim: dict = {}
    n_toplam = 0
    with SONUC_JSON.open("r", encoding="utf-8") as fh:
        icerik = fh.read()  # ~127MB — tek okuma, offline analiz
    for pid, ad, x, y, z, oi in rx.findall(icerik):
        n_toplam += 1
        d = dagilim.setdefault(ad, [])
        d.append(int(z) * PITCH)
    del icerik
    rapor = {}
    for ad, zs in sorted(dagilim.items()):
        zs.sort()
        n = len(zs)
        med = zs[n // 2]
        rapor[ad] = {"n": n, "z_min": zs[0], "z_med": med, "z_max": zs[-1],
                     "z_ust300_pay": round(
                         sum(1 for z in zs if z > 300) / n, 2)}
        log(f"{ad:12s} n={n:3d}  z-taban min/med/max = "
            f"{zs[0]:5.0f}/{med:5.0f}/{zs[-1]:5.0f}  "
            f"z>300 pay={rapor[ad]['z_ust300_pay']:.0%}")
    log(f"toplam placement: {n_toplam}")
    log("SINIRLILIK: orientation_idx->boyut permutasyonu JSON'dan")
    log("cozulemedi; TEPE yukseklikleri kesin degil, yalniz taban-z.")
    return {"model_z_dagilim": rapor, "n_toplam": n_toplam,
            "pitch_mm": PITCH}


def main() -> int:
    t0 = time.time()
    a = bolum_a()
    b = bolum_b()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(
        {"tarih": str(date.today()), "a_analitik": a, "b_z_dagilim": b,
         "kaynak": {"sonuc_json": str(SONUC_JSON), "stl_dir": str(STL_DIR)},
         "a11_not": "ucuz teshis (A4); kazanc/mekanizma ilani degildir"},
        indent=2, ensure_ascii=True), encoding="utf-8")
    log("")
    log(f"KAYIT: {OUT}")
    log(f"BITTI  sure={time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
