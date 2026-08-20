# -*- coding: utf-8 -*-
"""k66_d_kafes_dekod.py — K-66-d PROTOTIP: kitlesel ozdes-parca KAFES dekodu.

Mekanizma (K-66-a/b teshis bulgusundan): plaka-asan cubuklar DIK kolon
kafesine dizilir; aralarindaki kanallara yuksek-adet KITLE parcasi
periyodik katmanlarla (kafes) PINLENIR; kalan parcalar NFV'ye birakilir
(pin_3d=True: pin alti/ustu serbest). Hedef: cubuk-ustu yigilma bandini
(516 anatomisindeki ~116mm) cubuk-arasi hacme indirmek.

TETIK GEOMETRIK (A11, veri-adsiz): (1) plaka-asan parca sinifi = iki
buyuk boyutuyla yatayda plakaya sigmayan parca; (2) kitle sinifi =
en yuksek adetli model (adet payi >= M66_KITLE_PAY, default 0.5).

Kaynaklar:
  M66_MODE=stl (default): M66_STL_DIR'deki STL'ler; adet dosya-adindaki
    ilk tamsayidan (uretim 'adet' konvansiyonu). Default dir:
    D:\\ie488\\results\\fsm610_stl_persist (fsm610 SINIF ORNEGI — kod
    veri-adi tasimiyor, dizin env ile degisir).
  M66_MODE=synthetic: mass_plate_rod_mix(seed=M66_SEED_INST) — dagilimsal
    adim ayni harness'la kosulur (k59 deseni icin taban).
Ayarlar: M66_PLATE (335) / M66_CLEAR (2.0) / M66_QUALITY (fast|max) /
  M66_PLAN_ONLY=1 (yalniz plan hesabi, cozum yok) / M66_SEED (42).

SERH (A11): tek-sinif ON-OLCUM prototipi; kazanc ilani degildir. Kablo
karari ancak dagilimsal (synthetic mod, cok-seed) + dev-set sifir-dokunus
kanitiyla. Kosum: D:\\ie488'den python -m scripts.detach_run
k66_d_kafes_dekod (K-57a munhasir). SAF ASCII stdout.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k66_d_kafes_dekod.log"
OUT = _ROOT / "results" / "k66_d_kafes_dekod.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Saf yardimcilar (test edilebilir)
# ---------------------------------------------------------------------------

def adet_parse(stem: str) -> int:
    """Dosya-adindaki ILK tamsayi = adet ('520 adet', '27adet_'); yoksa 1."""
    m = re.search(r"(\d+)", stem)
    return int(m.group(1)) if m else 1


def asan_mi(dims: Tuple[float, float, float], plate_w: float,
            plate_d: float, clear: float) -> bool:
    """Yatay iki yerlesimde de iki buyuk boyut plakaya sigmiyor mu?"""
    d0, d1, d2 = sorted(dims)
    a, b = d1 + clear, d2 + clear
    W, D = max(plate_w, plate_d), min(plate_w, plate_d)
    return not (b <= W and a <= D)


def eksen_rot_bul(mesh_extents: Tuple[float, float, float],
                  hedef: Tuple[float, float, float],
                  tol: float = 0.75) -> Optional[List[List[float]]]:
    """24 eksen-hizali rotasyondan, mesh extentlerini hedefe esleyen ILK
    matris (4x4 liste). Bulunamazsa None."""
    import numpy as np
    import trimesh.transformations as tt

    eksenler = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
    gorulen = set()
    matrisler = []
    for ax1 in eksenler:
        for k1 in range(4):
            m1 = tt.rotation_matrix(math.pi / 2 * k1, ax1)
            for ax2 in eksenler:
                for k2 in range(4):
                    m = tt.rotation_matrix(math.pi / 2 * k2, ax2) @ m1
                    anahtar = tuple(np.round(m[:3, :3].flatten()).astype(int))
                    if anahtar in gorulen:
                        continue
                    gorulen.add(anahtar)
                    matrisler.append(m)
    e = np.asarray(mesh_extents, dtype=float)
    h = np.asarray(hedef, dtype=float)
    for m in matrisler:
        r = np.abs(m[:3, :3]) @ e
        if np.all(np.abs(r - h) <= tol):
            return m.tolist()
    return None


def kafes_plani(rod_dims: Tuple[float, float, float], n_rod: int,
                kitle_dims: Tuple[float, float, float], n_kitle: int,
                plate_w: float, plate_d: float, clear: float) -> Dict:
    """Jenerik kafes plani: cubuk satirlari + arada kitle kanallari.

    Cubuk: footprint = iki kucuk boyut (buyugu x'e), yukseklik = en buyuk.
    Kitle: 3 yatis oryantasyonu x kanal-katsayisi m (1..4) taranir; hedef
    cubuk-yuksekligi altina EN COK kitle parcasi sigdirmak.
    Donen plan: rod satir y'leri + kitle hucre yerlesimleri (mm) + kapasite.
    """
    r0, r1, r2 = sorted(rod_dims)
    k0, k1_, k2_ = sorted(kitle_dims)
    oryantasyonlar = [
        ((k2_, k1_, k0), "duz"),   # en ince boyut yukari
        ((k2_, k0, k1_), "yan"),
        ((k1_, k0, k2_), "dik"),
    ]
    en_iyi = None
    for rod_w, rod_d in ((r0, r1), (r1, r0)):  # footprint yonelimi taranir
        rods_x = int((plate_w + clear) // (rod_w + clear))
        if rods_x <= 0:
            continue
        n_rows = math.ceil(n_rod / rods_x)
        for (cw, cd, ch), oad in oryantasyonlar:
            if cw + clear > plate_w:
                continue
            katman = int((r2 + clear) // (ch + clear))
            if katman <= 0:
                continue
            cols_x = int((plate_w + clear) // (cw + clear))
            if cols_x <= 0:
                continue
            for m in range(1, 5):
                ch_d = m * (cd + clear)
                n_ch = n_rows + 1
                d_gerek = (n_rows * (rod_d + clear)) + n_ch * (ch_d + clear)
                if d_gerek > plate_d + clear:
                    continue
                kap = cols_x * m * katman * n_ch
                aday = {"uygun": True, "oryantasyon": oad, "m": m,
                        "cell": [cw, cd, ch], "cols_x": cols_x,
                        "katman": katman, "n_ch": n_ch,
                        "kapasite": min(kap, n_kitle),
                        "d_kullanim": round(d_gerek, 1),
                        "rod": {"w": rod_w, "d": rod_d, "h": r2,
                                "rows_x": rods_x, "n_rows": n_rows}}
                if en_iyi is None or aday["kapasite"] > en_iyi["kapasite"]:
                    en_iyi = aday
    if en_iyi is None:
        return {"uygun": False,
                "sebep": "hicbir oryantasyon/kanal kombinasyonu sigmadi"}
    return en_iyi


def pin_listesi(plan: Dict, rod_pinler: List[Tuple[str, object]],
                kitle_ad: str, kitle_rot, clear: float) -> List[Dict]:
    """Plani mm-koordinatli pin listesine coz (alt-sol kose semantigi).

    rod_pinler: [(ad, rot), ...] — HER cubuk kopyasi icin bir giris (coklu
    asan-model destegi: slotlar sirayla model-model tuketilir; slot boyutu
    plan['rod'] = modellerin maksimumu, kucuk model buyuk slota sigar).
    """
    pins = []
    rod = plan["rod"]
    cw, cd, ch = plan["cell"]
    m = plan["m"]
    ch_d = m * (cd + clear)
    # y-yerlesimi: [kanal, rod-satiri, kanal, rod-satiri, ..., kanal]
    y = 0.0
    bolgeler = []  # ("kanal"|"rod", y_basi)
    for i in range(rod["n_rows"]):
        bolgeler.append(("kanal", y))
        y += ch_d + clear
        bolgeler.append(("rod", y))
        y += rod["d"] + clear
    bolgeler.append(("kanal", y))

    rod_kuyruk = list(rod_pinler)
    kitle_sayac = plan["kapasite"]
    for tur, yb in bolgeler:
        if tur == "rod":
            for j in range(rod["rows_x"]):
                if not rod_kuyruk:
                    break
                ad, rrot = rod_kuyruk.pop(0)
                pins.append({"ad": ad, "x_mm": j * (rod["w"] + clear),
                             "y_mm": yb, "z_mm": 0.0, "rot": rrot})
        else:
            for kat in range(plan["katman"]):
                for satir in range(m):
                    for j in range(plan["cols_x"]):
                        if kitle_sayac <= 0:
                            break
                        pins.append({"ad": kitle_ad,
                                     "x_mm": j * (cw + clear),
                                     "y_mm": yb + satir * (cd + clear),
                                     "z_mm": kat * (ch + clear),
                                     "rot": kitle_rot})
                        kitle_sayac -= 1
    return pins


# ---------------------------------------------------------------------------
# Kosu
# ---------------------------------------------------------------------------

def _instance_kur(mode: str, plate: float):
    from src.nesting3d.instances.stl_order_loader import (
        build_instance_from_order)
    if mode == "synthetic":
        from src.nesting3d.instances.format import ContainerSpec
        from src.nesting3d.instances.synthetic import mass_plate_rod_mix
        seed_i = int(os.environ.get("M66_SEED_INST", "0"))
        cnt = ContainerSpec(width_mm=plate, depth_mm=plate, height_mm=None)
        inst = mass_plate_rod_mix(container=cnt, seed=seed_i,
                                  qty_per_plate=int(
                                      os.environ.get("M66_QTY", "120")))
        return inst, None
    stl_dir = Path(os.environ.get(
        "M66_STL_DIR", r"D:\ie488\results\fsm610_stl_persist"))
    stl_map = {f.stem: f.read_bytes() for f in sorted(stl_dir.glob("*.stl"))}
    if not stl_map:
        raise SystemExit(f"HATA: {stl_dir} icinde STL yok")
    qty = {stem: adet_parse(stem) for stem in stl_map}
    res = build_instance_from_order(
        stl_map, qty, persist_dir=_ROOT / "data" / "mail_stl" / "gen_k66d",
        container_w_mm=plate, container_d_mm=plate)
    return res.instance, qty


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    mode = os.environ.get("M66_MODE", "stl")
    plate = float(os.environ.get("M66_PLATE", "335"))
    clear = float(os.environ.get("M66_CLEAR", "2.0"))
    quality = os.environ.get("M66_QUALITY", "fast")
    kitle_pay = float(os.environ.get("M66_KITLE_PAY", "0.5"))
    seed = int(os.environ.get("M66_SEED", "42"))
    plan_only = os.environ.get("M66_PLAN_ONLY") == "1"

    log("K-66-d KAFES DEKOD PROTOTIPI (A11 serhli on-olcum)")
    log(f"mode={mode} plate={plate} clear={clear} quality={quality}"
        f" seed={seed} plan_only={plan_only}")

    inst, _ = _instance_kur(mode, plate)

    # Model envanteri (ad -> dims, qty) — instance PartSpec'lerinden
    modeller: Dict[str, Dict] = {}
    for p in inst.parts:
        mm = modeller.setdefault(p.name, {"qty": 0, "dims": (
            float(p.width_mm), float(p.depth_mm), float(p.height_mm))})
        mm["qty"] += int(p.qty)
    n_total = sum(m["qty"] for m in modeller.values())
    log(f"modeller: " + ", ".join(
        f"{ad}({m['qty']}x {m['dims'][0]:.0f}/{m['dims'][1]:.0f}/"
        f"{m['dims'][2]:.0f})" for ad, m in modeller.items()))

    # Siniflandirma (GEOMETRIK)
    asanlar = {ad: m for ad, m in modeller.items()
               if asan_mi(m["dims"], plate, plate, clear)}
    # Kitle tanimi (2026-08-20 duzeltme): mekanizma TEK modele degil TEKRARLI
    # kitleye bakar — tekrar-modelleri (adet >= max(20, %5)) TOPLAMI esikle
    # kiyaslanir; kafes EN YUKSEK adetli modele kurulur (digerleri NFV'ye).
    tekrar_esigi = max(20, int(0.05 * n_total))
    tekrarlar = {ad: m for ad, m in modeller.items()
                 if m["qty"] >= tekrar_esigi and ad not in asanlar}
    tekrar_toplam = sum(m["qty"] for m in tekrarlar.values())
    if not tekrarlar or tekrar_toplam < kitle_pay * n_total:
        log(f"TETIK YOK: tekrar-kitle payi {tekrar_toplam}/{n_total} < "
            f"{kitle_pay} — kafes dekodu uygulanmaz (sifir-dokunus)")
        return 0
    kitle_ad = max(tekrarlar, key=lambda a: tekrarlar[a]["qty"])
    log(f"tekrar-kitle: {sorted(tekrarlar)} toplam={tekrar_toplam}"
        f" (esik {tekrar_esigi}); kafes modeli={kitle_ad}")
    if kitle_ad in asanlar:
        log("TETIK YOK: kitle modeli plaka-asan — desen disi")
        return 0
    if not asanlar:
        log("NOT: plaka-asan yok; kafes yalniz-kitle modunda ANLAMSIZ "
            "(duz kafes zaten heightmap isi) — cikiliyor")
        return 0
    n_rod = sum(m["qty"] for m in asanlar.values())
    # Slot boyutu = asan modellerin eksen-bazli MAKSIMUMU (kucuk model
    # buyuk slota sigar; pinler model-model tuketilir — coklu-model destegi)
    slot = tuple(max(sorted(m["dims"])[i] for m in asanlar.values())
                 for i in range(3))
    if len(asanlar) > 1:
        log(f"NOT: {len(asanlar)} asan model; slot={tuple(round(s,1) for s in slot)}")

    plan = kafes_plani(slot, n_rod,
                       modeller[kitle_ad]["dims"],
                       modeller[kitle_ad]["qty"], plate, plate, clear)
    if not plan.get("uygun"):
        log(f"PLAN KURULMADI: {plan.get('sebep')}")
        return 1
    log(f"PLAN: rod_slot={tuple(round(s,1) for s in slot)} n={n_rod} rows_x={plan['rod']['rows_x']} "
        f"n_rows={plan['rod']['n_rows']} h={plan['rod']['h']:.1f} | "
        f"kitle={kitle_ad} oryant={plan['oryantasyon']} m={plan['m']} "
        f"katman={plan['katman']} kapasite={plan['kapasite']}/"
        f"{modeller[kitle_ad]['qty']} | D-kullanim={plan['d_kullanim']}")
    ust_kalan = modeller[kitle_ad]["qty"] - plan["kapasite"]
    log(f"NFV'ye kalan: kitle {ust_kalan} + diger modeller "
        f"{n_total - n_rod - modeller[kitle_ad]['qty']}")

    if plan_only:
        log("PLAN_ONLY=1 — cozum atlandi")
        return 0

    # Rotasyon matrisleri (mesh extent -> hedef)
    import trimesh
    hedef_adlar = set(asanlar) | {kitle_ad}
    ornek = {}
    for p in inst.parts:
        if p.name in hedef_adlar and p.name not in ornek:
            if getattr(p, "stl_path", None):
                ornek[p.name] = tuple(
                    trimesh.load(str(p.stl_path), force="mesh").extents)
            else:
                ornek[p.name] = (float(p.width_mm), float(p.depth_mm),
                                 float(p.height_mm))
    rod = plan["rod"]
    # Slot yonelimi: plan.rod.w slotun kucuk mu buyuk mu boyutu? Her modelin
    # kendi sorted-dims'i ayni yonelimle hedeflenir (dar-x veya genis-x).
    dar_x = abs(rod["w"] - slot[0]) < abs(rod["w"] - slot[1])
    rod_pinler: List[Tuple[str, object]] = []
    for ad in sorted(asanlar):
        m0, m1, m2 = sorted(asanlar[ad]["dims"])
        hedef = (m0, m1, m2) if dar_x else (m1, m0, m2)
        rrot = eksen_rot_bul(ornek[ad], hedef)
        if rrot is None:
            log(f"HATA: rotasyon bulunamadi (asan model {ad})")
            return 1
        rod_pinler.extend([(ad, rrot)] * asanlar[ad]["qty"])
    kitle_rot = eksen_rot_bul(ornek[kitle_ad], tuple(plan["cell"]))
    if kitle_rot is None:
        log("HATA: rotasyon bulunamadi (kitle)")
        return 1

    pins = pin_listesi(plan, rod_pinler, kitle_ad, kitle_rot, clear)
    log(f"pin sayisi: {len(pins)} (rod {n_rod} + kitle {plan['kapasite']})")

    from src.nesting3d.nfv_solve import solve_nfv
    from scripts.k62_v17_ripup import a2_olc
    t1 = time.perf_counter()
    res = solve_nfv(inst, plate_w_mm=plate, plate_d_mm=plate,
                    seed=seed, quality=quality, clearance_mm=clear,
                    pinned_placements=pins, pin_3d=True)
    h = float(res.height_mm)
    n_placed = int(res.n_placed)
    log(f"[SONUC] h={h:.2f} n={n_placed}/{n_total} "
        f"sure={(time.perf_counter() - t1)/60:.1f}dk "
        f"pitch={float(res.coarse_pitch):.2f}")

    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[A2] clearance={a2['min_clearance_mm']} "
            f"kilit5={a2['kilit_5yon']} rot={a2.get('rot_kilit')} "
            f"-> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[A2] OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {"olcum": "k66_d_kafes_dekod", "mode": mode,
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-sinif on-olcum PROTOTIPI; kazanc ilani "
                    "degildir; kablo = dagilimsal + sifir-dokunus sonrasi"),
           "ayarlar": {"plate": plate, "clear": clear, "quality": quality,
                       "seed": seed},
           "plan": plan, "n_pins": len(pins),
           "sonuc": {"height_mm": h, "n_placed": n_placed,
                     "n_total": n_total, "a2": a2},
           "sure_s": round(time.perf_counter() - t0, 1)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")
    log(f"BITTI  sure={(time.perf_counter() - t0)/60:.1f}dk")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
