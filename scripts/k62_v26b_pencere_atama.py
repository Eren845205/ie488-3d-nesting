# -*- coding: utf-8 -*-
"""k62_v26b_pencere_atama.py — K-62 v26b: PENCERE-OYMA atamasi (ortak atama, tur 2).

v26 dersi: 3-bantli z=0 modeli yetersiz — zemin bandinin 2D projeksiyonu
%91 dolu (102 dilated fp), planner 0/10 yerlestirdi. Gercek kapasite dikey
istifte; ve plato aritmetigi mekanizmayi veriyor:
  plato 127.2 = kanopi-tepe 105.8 + bobbin_3 kati 21.6
  T_hedef ~117.6 icin kanopi ustunde yalniz gh <= T_hedef - kanopi_tepe
  (~11.8mm) parca durabilir (ince TAPER gecer, bobbin_3/pyramid GECMEZ).

v26b mekanizmasi (zemin sifir-toplamliligini POZITIF kullan):
  faz-A: taban cozum + surucu secimi (v26 ile ayni; cozum-gudumlu).
  faz-B: surucularden ZEMIN-ZORUNLU olanlar (dik gh > kz1/2 — kolon
         paylasamaz, gercek zemin ister; geometrik tetik) icin PENCERE
         OYMA: dilated fp penceresi tum pozisyonlarda skorlanir —
         yasak: kule/yuksek parca (top > kz1) veya no-go ortusmesi;
         ceza: yerinden-edilen parcalarin yeniden-yerlesim maliyeti
         (ince parca [kanopi-ustune sigan] ucuz, kalin pahali) +
         delik-ortusme (v24 dersi) + onceki pencereler. Kazanan pencereye
         pin (z=0); pencereyle ortusen kalan-parcalar UNPIN edilip havuza.
  faz-C: kalan pinler + pencere pinleri; havuz = ince suruculer +
         yerinden-edilenler (BLB istifler; ince olanlar kanopi ustune,
         kisa olanlar deliklere/boşluklara) -> cozucu -> v20 tekil-
         relokasyon post-pass -> B2 settle -> A2.

Kosum: python -m scripts.detach_run k62_v26b_pencere_atama  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum; tetikler geometrik (gh/kz1 orani, top>kz1,
delik-maskesi) — veri-adi yok; GO cikarsa kablo + dagilimsal + kapi ayri is.
"""
from __future__ import annotations

import gc
import json
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
import trimesh.transformations as tt
from scipy.signal import fftconvolve

import scripts.eval_gate as eg
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv, _nfv_clearance_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v17_ripup import _raw_off_voxel, a2_olc
from scripts.k62_v20_relokasyon import _dokum

LOG = Path(__file__).parent / "k62_v26b_pencere_atama.log"
OUT = _ROOT / "results" / "k62_v26b_pencere_atama.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_RELOK = 8
MAX_SOKUM = 12
W_DELIK = 3.0      # delik hucresi kaplama cezasi (hucre basi)
W_KALIN = 25.0     # kalin (kanopi-ustune sigmayan) parca yerinden etme
W_INCE = 4.0       # ince parca yerinden etme
REF = {"plato": 127.20, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _sahne_dokumu(res):
    pt = float(res.fine_pitch)
    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    out = []
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        off = _raw_off_voxel(o, pt)
        out.append({
            "ad": getattr(vp, "name", str(pl.part_id)),
            "xv": int(pl.x), "yv": int(pl.y), "zv": int(pl.z),
            "grid": o.grid,
            "gh_mm": float(o.grid.shape[2]) * pt,
            "top_mm": float(pl.z + o.grid.shape[2] - off) * pt,
            "pin": {"ad": getattr(vp, "name", str(pl.part_id)),
                    "x_mm": float(pl.x + off) * pt,
                    "y_mm": float(pl.y + off) * pt,
                    "z_mm": float(pl.z) * pt,
                    "rot": np.asarray(o.rot_matrix, dtype=float).tolist()}})
    return out


def _fp_plaka(it, nx, ny):
    """Parcanin plaka gridine oturan tam-yukseklik dilated fp'si."""
    fp = it["grid"].any(axis=2)
    m = np.zeros((nx, ny), dtype=bool)
    x0, y0 = it["xv"], it["yv"]
    xa, ya = max(0, x0), max(0, y0)
    xb = min(nx, x0 + fp.shape[0]); yb = min(ny, y0 + fp.shape[1])
    if xb > xa and yb > ya:
        m[xa:xb, ya:yb] = fp[xa - x0:xb - x0, ya - y0:yb - y0]
    return m


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v26b: PENCERE-OYMA atamasi (ortak atama, tur 2)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}"
        f" W=(delik {W_DELIK}, kalin {W_KALIN}, ince {W_INCE})")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh0, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh0)[0])
    kz2 = Z_IYI + float(fiz["duz_kalinlik_mm"])
    kanopi_pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
                  "y_mm": float(poz["dy_mm"]), "z_mm": Z_IYI,
                  "rot": rot_k.tolist()}

    def coz(pinler=None, rutbeler=None, pitch=None, settle=False):
        if pinler is None:
            pinler = [kanopi_pin]
        return solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                         plate_d_mm=eg.PLATE_STD[1],
                         fine_pitch=pitch, fine_settle=settle, seed=SEED,
                         quality="fast", clearance_mm=CLEAR_MM,
                         no_go_bounds=eg.NOGO_STD,
                         pinned_placements=pinler, pin_3d=True,
                         oncelik_adlari=(rutbeler or None))

    # ---- FAZ-A: taban + surucu secimi ----------------------------------
    res = coz(rutbeler=UCLU)
    h0 = float(res.height_mm)
    pt = float(res.coarse_pitch)
    nx, ny = int(eg.PLATE_STD[0] // pt), int(eg.PLATE_STD[1] // pt)
    sahne = _sahne_dokumu(res)
    log(f"[A] taban h={h0:.2f} n={int(res.n_placed)}/{n_total}"
        f" pitch={pt:.3f} kz2={kz2:.1f}")

    kule_max = 0.0
    for it in sahne:
        if it["zv"] < 2 and it["top_mm"] > kz2:
            kule_max = max(kule_max, it["top_mm"])
    t_hedef = max(kz2, kule_max) + pt
    ust_pay = t_hedef - kz2   # kanopi ustune sigan max parca kalinligi
    surucular = [it for it in sahne if it["top_mm"] > t_hedef + 1e-6]
    surucular.sort(key=lambda k: -k["top_mm"])
    if len(surucular) > MAX_SOKUM:
        surucular = surucular[:MAX_SOKUM]
    sur_ids = {id(it) for it in surucular}
    kalan = [it for it in sahne if id(it) not in sur_ids]
    log(f"[A] T_hedef={t_hedef:.1f} (kule_max={kule_max:.1f}"
        f" ust_pay={ust_pay:.1f})  surucu={len(surucular)}: "
        + ", ".join(f"{it['ad']}@{it['top_mm']:.0f}" for it in surucular))
    if not surucular:
        log("[A] surucu yok -> plan gereksiz. BITTI")
        return

    # ---- FAZ-B: pencere-oyma atamasi -----------------------------------
    eff_m, z_c = _nfv_clearance_voxels(CLEAR_MM, pt, 1)
    kz1_v = int(round(Z_IYI / pt))
    kz2_v = int(round(kz2 / pt))

    # zemin-zorunlu suruculer: dik gh > kz1/2 (kolon paylasamaz) VE dik
    # gh <= kz1 (kanopi altina sigar) — geometrik tetik
    pencereli, havuz_sur = [], []
    vox_cache = {}
    for it in surucular:
        ad = it["ad"]
        if ad not in vox_cache:
            ps = next((p for p in inst.parts if p.name == ad), None)
            if ps is None or not getattr(ps, "stl_path", None):
                vox_cache[ad] = None
            else:
                m = trimesh.load(ps.stl_path, force="mesh")
                ext = np.asarray(m.extents, dtype=float)
                eksen = int(np.argmin(ext))
                if eksen == 2:
                    R = np.eye(4)
                elif eksen == 0:
                    R = tt.rotation_matrix(np.pi / 2.0, [0.0, 1.0, 0.0])
                else:
                    R = tt.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0])
                vk = voxelize_part(ad, m, pt, rot_matrices=[R],
                                   method="slice", margin=eff_m,
                                   z_dilate=z_c)
                g = vk.orientations[0].grid
                vox_cache[ad] = {"rot": np.asarray(R), "fp": g.any(axis=2),
                                 "gh_mm": g.shape[2] * pt}
        vc = vox_cache[ad]
        if vc is not None and Z_IYI / 2.0 < vc["gh_mm"] <= Z_IYI:
            pencereli.append(it)
        else:
            havuz_sur.append(it)
    log(f"[B] zemin-zorunlu (pencereli): {len(pencereli)}"
        f" ({', '.join(sorted({it['ad'] for it in pencereli}))})"
        f"  havuz-surucu: {len(havuz_sur)}")

    # kalan-parca fp'leri + siniflar
    ngm = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, eg.PLATE_STD[0],
                                       eg.PLATE_STD[1], pt)
    ng = (np.asarray(ngm, dtype=bool)[:nx, :ny] if ngm is not None
          else np.zeros((nx, ny), dtype=bool))
    kan_it = next((it for it in sahne if it["ad"] == p0.name), None)
    delik = np.zeros((nx, ny), dtype=bool)
    bd = np.zeros((nx, ny), dtype=bool)
    if kan_it is not None:
        g = kan_it["grid"]
        x0, y0 = kan_it["xv"], kan_it["yv"]
        kutu = np.zeros((nx, ny), dtype=bool)
        kutu[max(0, x0):min(nx, x0 + g.shape[0]),
             max(0, y0):min(ny, y0 + g.shape[1])] = True
        bd = _fp_plaka(kan_it, nx, ny)
        delik = kutu & ~bd & ~ng
    delik_f4 = delik.astype(np.float32)

    kalan_fp = []   # (it, fp_plaka, sinif)  sinif: yasak/kalin/ince
    for it in kalan:
        if it is kan_it:
            continue
        m2 = _fp_plaka(it, nx, ny)
        if it["top_mm"] > Z_IYI + 1e-6:
            sinif = "yasak"       # kule / kanopi-bandi parcasi — dokunulmaz
        elif it["gh_mm"] > ust_pay:
            sinif = "kalin"
        else:
            sinif = "ince"
        kalan_fp.append((it, m2, sinif))

    pencere_pinleri, yerinden, plan_kaydi = [], set(), []
    sabit = ng.copy()   # pencere secildikce buyur
    for it in pencereli:
        vc = vox_cache[it["ad"]]
        fp = vc["fp"]
        fw, fd = fp.shape
        if fw > nx or fd > ny:
            plan_kaydi.append({"ad": it["ad"], "durum": "sigmaz"})
            continue
        flip = fp[::-1, ::-1].astype(np.float32)
        yasak = _conv_pos(sabit, flip) > 0.5
        ceza = W_DELIK * _conv_pos(delik_f4, flip)
        for jt, m2, sinif in kalan_fp:
            if id(jt) in yerinden:
                continue
            ort = _conv_pos(m2, flip) > 0.5
            if sinif == "yasak":
                yasak |= ort
            elif sinif == "kalin":
                ceza += W_KALIN * ort
            else:
                ceza += W_INCE * ort
        ceza[yasak] = np.inf
        if not np.isfinite(ceza).any():
            plan_kaydi.append({"ad": it["ad"], "durum": "pencere-yok"})
            continue
        ceza += 1e-4 * np.add.outer(
            np.arange(ceza.shape[0], dtype=np.float32),
            np.arange(ceza.shape[1], dtype=np.float32))
        xv, yv = np.unravel_index(int(np.argmin(ceza)), ceza.shape)
        c_val = float(ceza[xv, yv])
        # pencereyle ortusen kalan-parcalari yerinden et
        pencere = np.zeros((nx, ny), dtype=bool)
        pencere[xv:xv + fw, yv:yv + fd] = fp
        ye_bu = []
        for jt, m2, sinif in kalan_fp:
            if id(jt) in yerinden:
                continue
            if (m2 & pencere).any():
                yerinden.add(id(jt))
                ye_bu.append(f"{jt['ad']}({sinif})")
        sabit |= pencere
        pencere_pinleri.append({"ad": it["ad"],
                                "x_mm": (xv + eff_m) * pt,
                                "y_mm": (yv + eff_m) * pt,
                                "z_mm": 0.0, "rot": vc["rot"].tolist()})
        plan_kaydi.append({"ad": it["ad"],
                           "x_mm": round((xv + eff_m) * pt, 1),
                           "y_mm": round((yv + eff_m) * pt, 1),
                           "ceza": round(c_val, 1),
                           "yerinden": ye_bu})
        log(f"[B] pencere {it['ad']:22s} ({(xv + eff_m) * pt:6.1f},"
            f"{(yv + eff_m) * pt:6.1f}) ceza={c_val:7.1f}"
            f" yerinden={len(ye_bu)}: {', '.join(ye_bu) if ye_bu else '-'}")

    n_ye = len(yerinden)
    log(f"[B] toplam: {len(pencere_pinleri)} pencere pini,"
        f" {n_ye} yerinden-edilen, {len(havuz_sur)} havuz-surucu")

    # ---- FAZ-C: planli cozum + relokasyon + settle + A2 ----------------
    for it in sahne:
        it["grid"] = None
    kalan_pinler = [it["pin"] for it in kalan if id(it) not in yerinden]
    tum = kalan_pinler + pencere_pinleri
    havuz_n = n_ye + len(havuz_sur)
    log(f"[C] cozum: {len(tum)} pin, {havuz_n} havuzda")
    del res
    gc.collect()
    t1 = time.perf_counter()
    res = coz(pinler=tum, pitch=pt)
    h_iyi = float(res.height_mm)
    n1 = int(res.n_placed)
    log(f"[C] h={h_iyi:.2f} n={n1}/{n_total}"
        f" ({(time.perf_counter() - t1)/60:.1f}dk)"
        f"  [plato 127.20 / manuel 110.41]")

    denemeler = []
    denendi = set()
    for d in range(1, MAX_RELOK + 1):
        dokum = _dokum(res)
        dokum.sort(key=lambda k: -k["ust"])
        hedef_p = None
        for p in dokum:
            anahtar = (p["ad"], round(p["x_mm"], 1), round(p["y_mm"], 1),
                       round(p["z_mm"], 1))
            if anahtar not in denendi:
                hedef_p = p
                denendi.add(anahtar)
                break
        if hedef_p is None:
            break
        pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
                   "z_mm": q["z_mm"], "rot": q["rot"]}
                  for q in dokum if q is not hedef_p]
        t1 = time.perf_counter()
        r = coz(pinler=pinler, pitch=pt)
        hr = float(r.height_mm)
        nr = int(r.n_placed)
        kabul = (nr == n_total and hr < h_iyi - 0.01)
        log(f"[R d{d}] {hedef_p['ad']:22s} ust={hedef_p['ust']:6.1f}"
            f" -> h={hr:.2f} n={nr}/{n_total}"
            f" ({'KABUL' if kabul else 'gecildi'})"
            f" {(time.perf_counter() - t1)/60:.1f}dk")
        denemeler.append({"d": d, "ad": hedef_p["ad"], "h": hr,
                          "n": nr, "kabul": kabul})
        if kabul:
            del res
            gc.collect()
            res, h_iyi = r, hr
            denendi.clear()
        else:
            del r
            gc.collect()

    log(f"[R] SONUC: h={h_iyi:.2f} (plato 127.20 / manuel 110.41)")

    dokum = _dokum(res)
    dokum.sort(key=lambda k: k["ust"])
    pinler = [{"ad": q["ad"], "x_mm": q["x_mm"], "y_mm": q["y_mm"],
               "z_mm": q["z_mm"], "rot": q["rot"]}
              for q in dokum[1:]]
    t1 = time.perf_counter()
    rs = coz(pinler=pinler, pitch=pt, settle=True)
    hs = float(rs.height_mm)
    ns = int(rs.n_placed)
    log(f"[B2] settle'li final: h={hs:.2f} n={ns}/{n_total}"
        f" ({(time.perf_counter() - t1)/60:.1f}dk)")
    if ns == n_total and hs < h_iyi - 0.01:
        del res
        gc.collect()
        res, h_iyi = rs, hs
        log(f"[B2] KABUL: h={h_iyi:.2f}")
    else:
        del rs
        gc.collect()
        log("[B2] gecildi")

    a2 = None
    try:
        a2 = a2_olc(res, n_total)
        log(f"[A2] clearance={a2['min_clearance_mm']}"
            f" kilit5={a2['kilit_5yon']} rot={a2['rot_kilit']}"
            f" sokum_planli={a2['sokum_planli']}"
            f" -> {'LEGAL' if a2['legal'] else 'INVALID'}")
    except Exception:
        log(f"[A2] OLCUM HATASI:\n{traceback.format_exc()}")

    doc = {"olcum": "k62_v26b_pencere_atama",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-set on-olcum; pencere-oyma atamasi "
                    "script-seviyesi; tetikler geometrik (gh/kz1, top>kz1, "
                    "delik-maskesi) — GO cikarsa kablo + dagilimsal + kapi"),
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI, "W": [W_DELIK, W_KALIN, W_INCE]},
           "faz_a": {"h": h0, "t_hedef": round(t_hedef, 1),
                     "ust_pay": round(ust_pay, 1),
                     "surucu": [{"ad": it["ad"],
                                 "top": round(it["top_mm"], 1)}
                                for it in surucular]},
           "plan": plan_kaydi,
           "n_yerinden": n_ye,
           "denemeler": denemeler,
           "final": {"height_mm": h_iyi, "a2": a2},
           "referanslar": REF}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    log(f"yazildi: {OUT}")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
            log(f"kopya: {ek}")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")
    log(f"OZET: final={h_iyi:.2f}")
    log(f"WALL_S={time.perf_counter() - t0:.1f}"
        f"  ({(time.perf_counter() - t0) / 60:.1f} dk)")
    log("BITTI")


def _conv_pos(mask, flip_f4):
    """mask (nx,ny) ile flip'lenmis fp'nin valid konvolusyonu (pozisyon haritasi)."""
    return fftconvolve(np.asarray(mask, dtype=np.float32), flip_f4,
                       mode="valid")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
