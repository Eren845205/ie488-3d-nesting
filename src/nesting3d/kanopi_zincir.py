# -*- coding: utf-8 -*-
"""kanopi_zincir.py — K-62 v13b recetesinin GENELLESTIRILMIS kablosu.

Mekanizma zinciri (plan1 kesfi 2026-08-04, YONTEM K-62 v9..v14; manuel
110.41 desenine yaklasma):
  1. TETIK (geometrik, veri-adi YOK — A11): duz footprint alani buyuk
     (alan_oran >= esik) + delikli (doluluk < esik) + no-go-fizibil poz
     tasiyan parca = "kanopi adayi".
  2. 3D-PIN: aday, z adaylarinda cozucu occupancy'sine gercek voxelleriyle
     on-yuklenir (solve_nfv pin_3d=True) — kuleler deliklerden yukselir,
     istif kanopi ALTINDAKI gercek bosluga gider.
  3. KULE-ONCELIGI: pinli cozumde kanopi-tepesini asan tipler rutbe-0
     oncelige alinir (decode sira mudahalesi, oncelik_adlari).
  4. (opsiyonel) GREEDY RUTBE-1: asan-aday tipler tek tek rutbe-1'e
     denenir; iyilestiren tutulur (v13b deseni).

TEK-TARAFLI SOZLESME: zincir, referans (pinsiz) cozumden ASLA kotu sonuc
dondurmez — tum adaylar arasindan tam-yerlesimli en dusuk yukseklik secilir;
tetik yoksa referans AYNEN doner. Default'ta hicbir uretim yolu bu modulu
cagirmaz -> bit-ozdeslik yapisal (A11).

A2 notu: zincir yuksekligi optimize eder; legalite (clearance/kilit) olcumu
cagiranin sorumlulugundadir (eval kapisi / uretim R11 sarmali).
"""
from __future__ import annotations

import gc
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Geometrik tetik esikleri (K-62 on-teshis + v9 olcumleri; plan1'de
# baseplate_v2 alan_oran 0.44 / doluluk 0.475 ile atesler, kati plakalar
# doluluk ~1.0 ile elenir).
ALAN_ORAN_ESIK = 0.35
DOLULUK_ESIK = 0.6
# z adaylari: referans yuksekliginin oranlari (v12 mikro: plan1 platosu
# z 64-69mm ~ ref 138'in 0.46-0.50'si; bant genis tutulur).
Z_ORANLARI = (0.50, 0.45, 0.55)


def kanopi_adayi(
    inst,
    plate_w_mm: float,
    plate_d_mm: float,
    no_go_bounds,
    *,
    alan_oran_esik: float = ALAN_ORAN_ESIK,
    doluluk_esik: float = DOLULUK_ESIK,
    pitch: float = 0.5,
    method: str = "slice",
) -> Optional[Dict[str, Any]]:
    """Geometrik kanopi tetigi: buyuk-duz-delikli-fizibil parca ara.

    no_go_bounds None -> None (tetik hic atesleyemez; bit-ozdeslik).
    Donen dict: part / mesh / fiz (duz_poz_nogo_fizibilite ciktisi) /
    alan_oran. Ilk uygun aday doner (alan_oran buyukten kucuge).
    """
    if no_go_bounds is None:
        return None
    import trimesh

    from src.nesting3d.kanopi import duz_poz_nogo_fizibilite

    adaylar = []
    for p in inst.parts:
        yol = getattr(p, "stl_path", None)
        if not yol:
            continue
        try:
            mesh = trimesh.load(yol, force="mesh")
        except Exception as e:
            logger.warning("kanopi_adayi: %s mesh yuklenemedi (%s)", p.name, e)
            continue
        ext = sorted(float(x) for x in mesh.extents)[::-1]
        alan_oran = (ext[0] * ext[1]) / (plate_w_mm * plate_d_mm)
        if alan_oran >= alan_oran_esik:
            adaylar.append((alan_oran, p, mesh))
    for alan_oran, p, mesh in sorted(adaylar, key=lambda t: -t[0]):
        fiz = duz_poz_nogo_fizibilite(mesh, plate_w_mm, plate_d_mm,
                                      no_go_bounds, pitch=pitch,
                                      method=method)
        if fiz is None or not fiz["pozlar"]:
            continue
        if fiz["doluluk"] >= doluluk_esik:
            continue
        return {"part": p, "mesh": mesh, "fiz": fiz,
                "alan_oran": round(alan_oran, 4)}
    return None


def kanopi_pin(aday: Dict[str, Any], z_mm: float,
               poz_idx: int = 0) -> Dict[str, Any]:
    """Aday + z'den solve_nfv pinned_placements girdisi uret."""
    import trimesh.transformations as tt

    from src.nesting3d.kanopi import duz_rot_matrisleri

    poz = aday["fiz"]["pozlar"][poz_idx]
    rot = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])),
                              [0.0, 0.0, 1.0])
           @ duz_rot_matrisleri(aday["mesh"])[0])
    return {"ad": aday["part"].name, "x_mm": float(poz["dx_mm"]),
            "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
            "rot": rot.tolist()}


def asan_tipler(res, kanopi_ad: str, kanopi_ust_mm: float) -> Dict[str, float]:
    """Cozum-gudumlu oncelik kumesi: tepesi kanopi-ustunu asan tipler.

    Donen dict: parca adi -> max tepe (mm). Kanopi'nin kendisi haric.
    (k62_v10 _silo_tipleri'nin src karsiligi; A11 kablo geregi.)
    """
    pt = float(res.fine_pitch)
    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    asanlar: Dict[str, float] = {}
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        ad = getattr(vp, "name", str(pl.part_id))
        if ad == kanopi_ad:
            continue
        ust = (pl.z + o.grid.shape[2]) * pt
        if ust > kanopi_ust_mm + pt:
            asanlar[ad] = max(asanlar.get(ad, 0.0), ust)
    return asanlar


def _tam(res, n_total: int) -> bool:
    return res is not None and int(res.n_placed) == n_total


def _daha_iyi(r, n_iyi: int, h_iyi: float, eps: float = 0.01) -> bool:
    """Lexicographic kıyas: ÖNCE yerleşen parça sayısı (çok = iyi), SONRA
    yükseklik (düşük = iyi). Kapı-1 dersi (2026-08-05): pinsiz referans tam
    yerleşemeyebilir (bbox kapısı kanopi parçayı dışarıda bırakır — K-62 kök
    sebebi); zincirin asıl değeri tam-yerleşimi MÜMKÜN kılması olabilir."""
    n, h = int(r.n_placed), float(r.height_mm)
    return n > n_iyi or (n == n_iyi and h < h_iyi - eps)


def kanopi_zinciri_coz(
    inst,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    no_go_bounds=None,
    clearance_mm: float = 2.0,
    seed: int = 42,
    quality: str = "fast",
    fine_pitch: Optional[float] = None,
    z_adaylari_mm: Optional[Sequence[float]] = None,
    greedy_r1: bool = False,
    max_greedy: int = 6,
    ref_res=None,
    solve_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """K-62 zincirini kos: (en_iyi_result, telemetri) doner.

    Tek-tarafli: en_iyi her zaman denenen TAM-yerlesimli adaylarin en
    dusugu; tetik/aday yoksa referans cozum AYNEN doner (tel.tetik=False).
    ref_res verilirse referans cozum yeniden kosulmaz (maliyet paylasimi).
    """
    from src.nesting3d.nfv_solve import solve_nfv

    sk = dict(solve_kwargs or {})
    sk.setdefault("fine_pitch", fine_pitch)
    ortak = dict(plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
                 seed=seed, quality=quality, clearance_mm=clearance_mm,
                 no_go_bounds=no_go_bounds, **sk)
    n_total = sum(int(p.qty) for p in inst.parts)
    tel: Dict[str, Any] = {"tetik": False, "adimlar": []}

    ref = ref_res if ref_res is not None else solve_nfv(inst, **ortak)
    h_ref = float(ref.height_mm)
    tel["adimlar"].append({"adim": "ref", "h": h_ref,
                           "n": int(ref.n_placed)})

    aday = kanopi_adayi(inst, plate_w_mm, plate_d_mm, no_go_bounds)
    if aday is None:
        return ref, tel
    # DIKKAT: ref tam yerleşememiş olsa da zincir DENENİR (kapı-1 dersi:
    # pinsiz çözüm kanopi parçayı yerleştiremeyebilir; pin bunu açar).

    tel["tetik"] = True
    tel["aday"] = {"ad": aday["part"].name, "alan_oran": aday["alan_oran"],
                   "doluluk": aday["fiz"]["doluluk"],
                   "kalinlik_mm": aday["fiz"]["duz_kalinlik_mm"]}
    kalinlik = float(aday["fiz"]["duz_kalinlik_mm"])
    zler = (list(z_adaylari_mm) if z_adaylari_mm
            else [round(o * h_ref, 1) for o in Z_ORANLARI])

    en_iyi, n_iyi, h_iyi, etiket = ref, int(ref.n_placed), h_ref, "ref"

    # --- adim 2: 3D pin z-adaylari ------------------------------------
    pin_iyi = None
    z_iyi = None
    for z in zler:
        if z <= 0 or z + kalinlik >= h_ref:
            continue
        r = solve_nfv(inst, pinned_placements=[kanopi_pin(aday, z)],
                      pin_3d=True, **ortak)
        h = float(r.height_mm)
        tel["adimlar"].append({"adim": f"pin z={z}", "h": h,
                               "n": int(r.n_placed)})
        if pin_iyi is None or _daha_iyi(r, int(pin_iyi.n_placed),
                                        float(pin_iyi.height_mm)):
            if pin_iyi is not None and pin_iyi is not en_iyi:
                del pin_iyi
            pin_iyi, z_iyi = r, z
        elif r is not en_iyi:
            del r
        gc.collect()
    if pin_iyi is None:
        tel["etiket"] = etiket
        return en_iyi, tel
    if _daha_iyi(pin_iyi, n_iyi, h_iyi):
        en_iyi = pin_iyi
        n_iyi, h_iyi = int(pin_iyi.n_placed), float(pin_iyi.height_mm)
        etiket = "pin"
    tel["z_secilen"] = z_iyi

    # --- adim 3: kule-onceligi (rutbe-0) -------------------------------
    kz2 = float(z_iyi) + kalinlik
    asan = asan_tipler(pin_iyi, aday["part"].name, kz2)
    tel["asan_tipler"] = {k: round(v, 1) for k, v in asan.items()}
    if not asan:
        tel["etiket"] = etiket
        return en_iyi, tel
    rutbeler = {ad: 0 for ad in asan}
    pin_arg = dict(pinned_placements=[kanopi_pin(aday, z_iyi)], pin_3d=True)

    def _coz(rt):
        return solve_nfv(inst, oncelik_adlari=dict(rt), **pin_arg, **ortak)

    r0 = _coz(rutbeler)
    h0 = float(r0.height_mm)
    tel["adimlar"].append({"adim": "oncelik r0", "h": h0,
                           "n": int(r0.n_placed),
                           "rutbeler": dict(rutbeler)})
    if _daha_iyi(r0, n_iyi, h_iyi):
        if en_iyi is not ref and en_iyi is not pin_iyi:
            del en_iyi
            gc.collect()
        en_iyi, n_iyi, h_iyi, etiket = r0, int(r0.n_placed), h0, "oncelik"
    else:
        del r0
        gc.collect()
        tel["etiket"] = etiket
        return en_iyi, tel

    # --- adim 4 (opsiyonel): greedy rutbe-1 ----------------------------
    # (uretim kablosu icin bkz. kanopi_zinciri_uretim asagida)
    if greedy_r1:
        havuz = [ad for ad, _u in sorted(
            asan_tipler(en_iyi, aday["part"].name, kz2).items(),
            key=lambda kv: -kv[1]) if ad not in rutbeler]
        denendi: set = set()
        n = 0
        while havuz and n < max_greedy:
            ad = havuz.pop(0)
            if ad in denendi or ad in rutbeler:
                continue
            denendi.add(ad)
            n += 1
            adayr = dict(rutbeler)
            adayr[ad] = 1
            r = _coz(adayr)
            h = float(r.height_mm)
            tut = _daha_iyi(r, n_iyi, h_iyi)
            tel["adimlar"].append({"adim": f"greedy +{ad}@r1", "h": h,
                                   "karar": "TUT" if tut else "GERI-AL"})
            if tut:
                rutbeler = adayr
                if en_iyi is not ref and en_iyi is not pin_iyi:
                    del en_iyi
                en_iyi, etiket = r, "greedy"
                n_iyi, h_iyi = int(r.n_placed), h
                for a2, _u in sorted(
                        asan_tipler(r, aday["part"].name, kz2).items(),
                        key=lambda kv: -kv[1]):
                    if (a2 not in denendi and a2 not in rutbeler
                            and a2 not in havuz):
                        havuz.append(a2)
            else:
                del r
            gc.collect()
        tel["rutbeler"] = dict(rutbeler)

    tel["etiket"] = etiket
    return en_iyi, tel


# --------------------------------------------------------------------------
# URETIM KABLOSU (K-62 v18, Eren karari 2026-08-15): zincir + A2 legalite +
# GERI-DUSUS. k62_kapi v3 saha deseninin src karsiligi (plan1 otomatik
# 129.00 LEGAL kaniti fix'li motorla; YONTEM §3 K-62 KAPI + v17).
#
# SOZLESME (tek-tarafli, A2-kapili):
#   - Tetik yoksa ref AYNEN doner (A2 olcumu bile kosulmaz — sifir maliyet).
#   - Zincir kazanani ancak TAM A2 legalite (clearance + 5-yon kilit veya
#     rot-sokum-planli) VE ref'ten lexicographic iyi (n_placed, sonra
#     yukseklik) ise kabul edilir.
#   - Kazanan A2 gecemezse geri-dusus adaylari (oncelik-r0 -> yalniz-pin)
#     sirayla tam-A2 ile denenir (kapi-v2 dersi: 132.60 clearance 1.961
#     INVALID -> maskelenmez, dusulur).
#   - Hicbiri gecemezse ref AYNEN doner. Ref'in legalitesi burada YENIDEN
#     olculmez (kalite yolu kendi guard/rot mekanizmasiyla gelir).
#   - ref_height_mm: ref'in EFEKTIF yuksekligi (R11 dz uygulanmissa o) —
#     kiyas bununla yapilir ki kazanan ilani R11'li ref'e haksizlik etmesin.
# --------------------------------------------------------------------------

def _a2_olc_meshes(res, n_total: int, clearance_mm: float,
                   rot_butce_s: float) -> Dict[str, Any]:
    """Tam A2 legalite olcumu: clearance + 5-yon kilit (+ rot-sokum).

    k62_kapi.a2_olc'un src karsiligi. Olcum hatasi legal=False sayilir
    (konservatif taraf, A2)."""
    from src.nesting3d.clearance import min_clearance
    from src.nesting3d.continuous_settle import (kilit_5yon_meshes,
                                                 kilit_rot_meshes)
    from src.nesting3d.export_stl import placed_meshes

    cl_mm = None
    kilit5 = rot_kilit = rot_cert = None
    sokum_planli = False
    try:
        meshes = list(placed_meshes(list(res.placements),
                                    res.fine_voxel_parts,
                                    float(res.fine_pitch)))
        cl_mm = float(min_clearance(meshes).min_mm)
        kilit5 = kilit_5yon_meshes(meshes)
        if kilit5 and kilit5 > 0:
            rapor = kilit_rot_meshes(meshes, sure_butcesi_s=rot_butce_s)
            rot_kilit = int(rapor.n_locked)
            rot_cert = len(getattr(rapor, "certificates", {}) or {})
            sokum_planli = (rot_kilit == 0)
    except Exception:
        logger.exception("kanopi uretim: A2 olcum hatasi (legal=False)")
    yer_ok = int(res.n_placed) == n_total
    cl_ok = cl_mm is not None and cl_mm >= float(clearance_mm)
    kilit_ok = (kilit5 == 0) or sokum_planli
    return {"min_clearance_mm": cl_mm, "kilit_5yon": kilit5,
            "rot_kilit": rot_kilit, "rot_cert": rot_cert,
            "sokum_planli": sokum_planli,
            "legal": yer_ok and cl_ok and kilit_ok}


def kanopi_zinciri_uretim(
    inst,
    *,
    plate_w_mm: float,
    plate_d_mm: float,
    no_go_bounds=None,
    clearance_mm: float = 2.0,
    seed: int = 42,
    quality: str = "fast",
    fine_pitch: Optional[float] = None,
    ref_res=None,
    ref_height_mm: Optional[float] = None,
    greedy_r1: bool = True,
    max_greedy: int = 6,
    rot_butce_s: float = 1200.0,
    _a2=None,
    _solve=None,
) -> Tuple[Any, Dict[str, Any]]:
    """Uretim kablosu: (final_result, telemetri) doner — bkz. blok yorumu.

    ref_res ZORUNLU (kalite yolunun secili sonucu); n_total ondan degil
    inst'ten okunur (ref eksik-yerlesimli olabilir — kapi-1 dersi).
    _a2/_solve test enjeksiyonu (A9: imzalar gercekle ayni).
    """
    import time as _time

    t0 = _time.perf_counter()
    n_total = (sum(int(p.qty) for p in inst.parts) if inst is not None
               else int(ref_res.n_placed))
    ref_eff_h = (float(ref_height_mm) if ref_height_mm is not None
                 else float(ref_res.height_mm))
    tel: Dict[str, Any] = {"tetik": False, "secilen": "ref",
                           "ref_height_mm": float(ref_res.height_mm),
                           "ref_eff_height_mm": ref_eff_h}

    aday = kanopi_adayi(inst, plate_w_mm, plate_d_mm, no_go_bounds)
    if aday is None:
        tel["sure_s"] = round(_time.perf_counter() - t0, 1)
        return ref_res, tel
    tel["tetik"] = True

    kazanan, ztel = kanopi_zinciri_coz(
        inst, plate_w_mm=plate_w_mm, plate_d_mm=plate_d_mm,
        no_go_bounds=no_go_bounds, clearance_mm=clearance_mm, seed=seed,
        quality=quality, fine_pitch=fine_pitch, greedy_r1=greedy_r1,
        max_greedy=max_greedy, ref_res=ref_res)
    tel["zincir"] = ztel
    if kazanan is ref_res or ztel.get("etiket") == "ref":
        tel["sure_s"] = round(_time.perf_counter() - t0, 1)
        return ref_res, tel  # zincir kazanamadi — A2 maliyeti odenmez

    a2 = _a2 or (lambda r: _a2_olc_meshes(r, n_total, clearance_mm,
                                          rot_butce_s))

    def _kabul(r, a2r):
        return a2r["legal"] and _daha_iyi(r, int(ref_res.n_placed), ref_eff_h)

    a2_k = a2(kazanan)
    tel["a2"] = a2_k
    if _kabul(kazanan, a2_k):
        tel["secilen"] = "kanopi"
        tel["etiket"] = ztel.get("etiket")
        tel["kazanc_mm"] = round(ref_eff_h - float(kazanan.height_mm), 2)
        tel["sure_s"] = round(_time.perf_counter() - t0, 1)
        return kazanan, tel

    # --- GERI-DUSUS (kapi-v3 deseni): oncelik-r0 -> yalniz-pin -----------
    tel["geri_dusus"] = []
    z = ztel.get("z_secilen")
    if z is not None:
        solve = _solve
        if solve is None:
            from src.nesting3d.nfv_solve import solve_nfv as solve
        etiket_kazanan = ztel.get("etiket")
        r0_rutbe = {ad: 0 for ad in (ztel.get("asan_tipler") or {})}
        adaylar = []
        if (etiket_kazanan == "greedy" and r0_rutbe
                and ztel.get("rutbeler") != r0_rutbe):
            adaylar.append(("oncelik-r0", r0_rutbe))
        if etiket_kazanan != "pin":
            adaylar.append(("yalniz-pin", None))
        try:
            _pin = [kanopi_pin(aday, z)]
        except Exception:
            logger.exception("kanopi uretim: geri-dusus pin kurulamadi")
            _pin, adaylar = None, []
        for gd_etiket, rutbe in adaylar:
            try:
                r_gd = solve(inst, plate_w_mm=plate_w_mm,
                             plate_d_mm=plate_d_mm, fine_pitch=fine_pitch,
                             seed=seed, quality=quality,
                             clearance_mm=clearance_mm,
                             no_go_bounds=no_go_bounds,
                             pinned_placements=_pin,
                             pin_3d=True, oncelik_adlari=rutbe)
            except Exception:
                logger.exception("kanopi uretim: geri-dusus solve hatasi"
                                 " (%s)", gd_etiket)
                continue
            a2_gd = a2(r_gd)
            tel["geri_dusus"].append(
                {"etiket": gd_etiket, "height_mm": float(r_gd.height_mm),
                 "n_placed": int(r_gd.n_placed), **a2_gd})
            if _kabul(r_gd, a2_gd):
                tel["secilen"] = "kanopi"
                tel["etiket"] = f"geri-dusus:{gd_etiket}"
                tel["a2"] = a2_gd
                tel["kazanc_mm"] = round(ref_eff_h - float(r_gd.height_mm), 2)
                tel["sure_s"] = round(_time.perf_counter() - t0, 1)
                return r_gd, tel
            del r_gd
            gc.collect()

    tel["sure_s"] = round(_time.perf_counter() - t0, 1)
    return ref_res, tel  # tek-tarafli: legal+iyi aday yok -> ref AYNEN
