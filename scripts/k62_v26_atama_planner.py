# -*- coding: utf-8 -*-
"""k62_v26_atama_planner.py — K-62 v26: ORTAK ATAMA planlayicisi (zemin+delik+kat).

v24+v25 KOK DERSI: zemin alani SIFIR-TOPLAMLI — pyramid'e zemin vermek
(rutbeyle de elle-pinle de) bobbin/dolgu sinifini delik-sutunlarinda bir ust
kata itiyor. Tek-eksenli mudahaleler 127.20 platosunu kiramadi; zemin+delik+
kat tahsisi ORTAK bir atama problemi.

v26 mekanizmasi:
  faz-A: taban cozum (kanopi pin + uclu rutbe; 129.60 beklenir). Tavan-
         surucu kopyalar COZUM-GUDUMLU secilir: top > T_hedef;
         T_hedef = max(kanopi-tepe, dikili-kule max boyu) + pitch
         (geometrik; veri-adi yok).
  faz-B: surucu kopyalar sokulur; KALAN sahne 3 z-bandina projeksiyonlanir
         (bandZ 0..kz1 / bandD kz1..kz2 / bandU kz2..T_hedef; dilated fp).
         Bantli maske zemin/delik/kat catismasini TEK modelde tutar:
         delik hucresine oturan zemin parcasi kule kolonunu OTOMATIK bloklar
         (v25 sifir-toplam mekanizmasi modelin icinde). Atama aramasi:
         sira varyantlari x rot adaylari x fftconvolve serbest-pozisyon
         haritasi; pozisyon skoru delik-ortusme cezali (v24 dersi: pyramid
         delik-altini kaplamasin) + kose-sikiligi. Kolonlarda L-katli istif
         (adim = gh+1; v10 mekanigi). En iyi plan = (yerlesmeyen az,
         planlanan tavan alcak, delik-isgal az).
  faz-C: kalan-sahne pinleri + plan pinleri -> cozucu (en-alcak parca
         serbest; tam-pin bosluk sorunu) -> v20 tekil-relokasyon post-pass
         -> B2 settle -> A2 olcumu.

v10-silo'dan FARKI: statik greedy raster + tip-sirali tahsis degil;
cozum-gudumlu sokum + bantli ortak-kapasite modeli + arama; ham-pin (v17)
altyapisiyla pinler 1x boslukla oturur; relokasyon post-pass var.

Kosum: python -m scripts.detach_run k62_v26_atama_planner  (D:\\ie488). ASCII.
SERH (A11): tek-set on-olcum; mekanizma script-seviyesi — GO cikarsa kablo
+ dagilimsal (holey_frames) + 4-set kapi ayri is.
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
from scipy import ndimage
from scipy.signal import fftconvolve

import scripts.eval_gate as eg
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv, _nfv_clearance_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k62_v9_pin3d import _kanopi_adayi
from scripts.k62_v17_ripup import _raw_off_voxel, a2_olc
from scripts.k62_v20_relokasyon import _dokum

LOG = Path(__file__).parent / "k62_v26_atama_planner.log"
OUT = _ROOT / "results" / "k62_v26_atama_planner.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8
MAX_RELOK = 8
MAX_SOKUM = 12
REF = {"plato": 127.20, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _sahne_dokumu(res):
    """Placement basina: (ad, xv, yv, zv, grid, top_mm, rot, pin-dict)."""
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
            "top_mm": float(pl.z + o.grid.shape[2] - off) * pt,
            "pin": {"ad": getattr(vp, "name", str(pl.part_id)),
                    "x_mm": float(pl.x + off) * pt,
                    "y_mm": float(pl.y + off) * pt,
                    "z_mm": float(pl.z) * pt,
                    "rot": np.asarray(o.rot_matrix, dtype=float).tolist()}})
    return out


def _band_isgal(mask, item, z0_v, z1_v, nx, ny):
    """item grid'inin [z0_v,z1_v) bandindaki fp'sini mask'a OR'lar."""
    g = item["grid"]
    zlo = max(item["zv"], z0_v) - item["zv"]
    zhi = min(item["zv"] + g.shape[2], z1_v) - item["zv"]
    if zhi <= zlo:
        return
    fp = g[:, :, zlo:zhi].any(axis=2)
    x0, y0 = item["xv"], item["yv"]
    xa, ya = max(0, x0), max(0, y0)
    xb = min(nx, x0 + fp.shape[0])
    yb = min(ny, y0 + fp.shape[1])
    if xb > xa and yb > ya:
        mask[xa:xb, ya:yb] |= fp[xa - x0:xb - x0, ya - y0:yb - y0]


def _serbest_harita(dolu_f4, fp):
    """fp'nin (dilated) hicbir dolu hucreye degmedigi pozisyonlar (valid)."""
    c = fftconvolve(dolu_f4, fp[::-1, ::-1].astype(np.float32), mode="valid")
    return c < 0.5


def _dusuk_katman_rotlar(mesh):
    """Eksenleri Z'ye getiren 3 rot, katman-h artan sirali (v10 mekanigi)."""
    ext = np.asarray(mesh.extents, dtype=float)
    rotlar = []
    for eksen in np.argsort(ext):
        if eksen == 2:
            R = np.eye(4)
        elif eksen == 0:
            R = tt.rotation_matrix(np.pi / 2.0, [0.0, 1.0, 0.0])
        else:
            R = tt.rotation_matrix(np.pi / 2.0, [1.0, 0.0, 0.0])
        rotlar.append(R)
    return rotlar


def _plan_dene(sira, adaylar, bandlar_0, delik_f4, pt, kz1, kz2, t_hedef,
               nx, ny):
    """Tek sira varyanti icin atama planini kur.

    bandlar_0: {"Z","D","U"} bool maskeler (kopyalanir).
    Doner: (pinler, yerlesmeyen, max_top, delik_isgal_hucre, plan_kaydi)
    """
    bz = bandlar_0["Z"].copy()
    bd = bandlar_0["D"].copy()
    bu = bandlar_0["U"].copy()
    pinler, plan, yerlesmeyen = [], [], []
    max_top = 0.0
    delik_isgal = 0
    for kopya in sira:
        ad = kopya["ad"]
        en_iyi = None  # (top_mm, delik_ceza, y, x, rc)
        for rc in adaylar[ad]:
            top_mm = rc["gh"] * pt  # z=0 tek kat (dilated-top, konservatif)
            if top_mm > t_hedef + 1e-6:
                continue
            # kopyanin kapladigi bantlar (bantli ortak-kapasite modeli)
            dolu = bz
            if top_mm > kz1 + 1e-6:
                dolu = dolu | bd
            if top_mm > kz2 + 1e-6:
                dolu = dolu | bu
            srb = _serbest_harita(dolu.astype(np.float32), rc["fp"])
            if not srb.any():
                continue
            # skor: delik-ortusme cezasi (v24 dersi) + kose sikiligi
            ceza = fftconvolve(delik_f4, rc["fp"][::-1, ::-1]
                               .astype(np.float32), mode="valid")
            ceza[~srb] = np.inf
            idx = np.unravel_index(int(np.argmin(
                ceza + 1e-4 * (np.add.outer(
                    np.arange(ceza.shape[0], dtype=np.float32),
                    np.arange(ceza.shape[1], dtype=np.float32))))),
                ceza.shape)
            c_val = float(ceza[idx])
            kayit = (top_mm, c_val, idx[1], idx[0], rc)
            if en_iyi is None or kayit[:2] < en_iyi[:2]:
                en_iyi = kayit
        if en_iyi is None:
            yerlesmeyen.append(ad)
            continue
        top_mm, c_val, yv, xv, rc = en_iyi
        fp = rc["fp"]
        # bantlari guncelle
        bz[xv:xv + fp.shape[0], yv:yv + fp.shape[1]] |= fp
        if top_mm > kz1 + 1e-6:
            bd[xv:xv + fp.shape[0], yv:yv + fp.shape[1]] |= fp
        if top_mm > kz2 + 1e-6:
            bu[xv:xv + fp.shape[0], yv:yv + fp.shape[1]] |= fp
        halo = rc["halo"]
        pinler.append({"ad": ad, "x_mm": (xv + halo) * pt,
                       "y_mm": (yv + halo) * pt, "z_mm": 0.0,
                       "rot": rc["rot"].tolist()})
        plan.append({"ad": ad, "x_mm": round((xv + halo) * pt, 1),
                     "y_mm": round((yv + halo) * pt, 1),
                     "top_mm": round(top_mm, 1),
                     "delik_ceza": round(c_val, 1)})
        max_top = max(max_top, top_mm)
        delik_isgal += int(c_val)
    return pinler, yerlesmeyen, max_top, delik_isgal, plan


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v26: ORTAK ATAMA planlayicisi (zemin+delik+kat)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}")

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

    # T_hedef: kanopi-tepe ile dikili (z~0, top>kz2) kule boylarinin max'i
    kule_max = 0.0
    for it in sahne:
        if it["zv"] * pt < 2 * pt and it["top_mm"] > kz2:
            kule_max = max(kule_max, it["top_mm"])
    t_hedef = max(kz2, kule_max) + pt
    surucular = [it for it in sahne if it["top_mm"] > t_hedef + 1e-6]
    surucular.sort(key=lambda k: -k["top_mm"])
    if len(surucular) > MAX_SOKUM:
        log(f"[A] uyari: {len(surucular)} surucu > {MAX_SOKUM} -> ilk"
            f" {MAX_SOKUM}")
        surucular = surucular[:MAX_SOKUM]
    sur_ids = {id(it) for it in surucular}
    kalan = [it for it in sahne if id(it) not in sur_ids]
    log(f"[A] T_hedef={t_hedef:.1f} (kule_max={kule_max:.1f})"
        f"  surucu={len(surucular)}: "
        + ", ".join(f"{it['ad']}@{it['top_mm']:.0f}" for it in surucular))
    if not surucular:
        log("[A] surucu yok -> plan gereksiz. BITTI")
        return

    # ---- FAZ-B: bantli kapasite modeli + atama aramasi -----------------
    kz1_v = int(round(Z_IYI / pt))
    kz2_v = int(round(kz2 / pt))
    tu_v = int(round(t_hedef / pt)) + 2
    bz = np.zeros((nx, ny), dtype=bool)
    bd = np.zeros((nx, ny), dtype=bool)
    bu = np.zeros((nx, ny), dtype=bool)
    for it in kalan:
        _band_isgal(bz, it, 0, kz1_v, nx, ny)
        _band_isgal(bd, it, kz1_v, kz2_v, nx, ny)
        _band_isgal(bu, it, kz2_v, tu_v, nx, ny)
    ngm = Bin3D.no_go_mask_from_bounds(eg.NOGO_STD, eg.PLATE_STD[0],
                                       eg.PLATE_STD[1], pt)
    if ngm is not None:
        ng = np.asarray(ngm, dtype=bool)[:nx, :ny]
        bz |= ng
        bd |= ng
        bu |= ng
    # delik envanteri (telemetri + ceza haritasi): kanopi bbox'inda bandD bos
    kan_it = next((it for it in sahne if it["ad"] == p0.name), None)
    delik = np.zeros((nx, ny), dtype=bool)
    if kan_it is not None:
        g = kan_it["grid"]
        x0, y0 = kan_it["xv"], kan_it["yv"]
        xb = min(nx, x0 + g.shape[0]); yb = min(ny, y0 + g.shape[1])
        kutu = np.zeros((nx, ny), dtype=bool)
        kutu[max(0, x0):xb, max(0, y0):yb] = True
        delik = kutu & ~bd
        lbl, n_comp = ndimage.label(delik)
        alanlar = np.bincount(lbl.ravel())[1:]
        log(f"[B] delik envanteri: {n_comp} bilesen; alan(hucre)"
            f" ilk10={sorted(alanlar.tolist(), reverse=True)[:10]}")
    delik_f4 = delik.astype(np.float32)
    log(f"[B] band doluluk: Z={bz.mean():.2f} D={bd.mean():.2f}"
        f" U={bu.mean():.2f}")
    for it in sahne:
        it["grid"] = None  # bantlar kuruldu; grid referanslari birakilir

    # rot adaylari (tip basina cache): base-rot + 2 dusuk-katman rotu
    eff_m, z_c = _nfv_clearance_voxels(CLEAR_MM, pt, 1)
    adaylar = {}
    for it in surucular:
        ad = it["ad"]
        if ad in adaylar:
            continue
        ps = next((p for p in inst.parts if p.name == ad), None)
        if ps is None or not getattr(ps, "stl_path", None):
            adaylar[ad] = []
            continue
        m = trimesh.load(ps.stl_path, force="mesh")
        rotlar = [np.asarray(it["pin"]["rot"], dtype=float)]
        rotlar += _dusuk_katman_rotlar(m)[:2]
        rc_list = []
        gorulen = set()
        for R in rotlar:
            anahtar = tuple(np.round(np.asarray(R)[:3, :3].ravel(), 3))
            if anahtar in gorulen:
                continue
            gorulen.add(anahtar)
            vk = voxelize_part(ad, m, pt, rot_matrices=[np.asarray(R)],
                               method="slice", margin=eff_m, z_dilate=z_c)
            g = vk.orientations[0].grid
            gh = g.shape[2]
            if g.shape[0] > nx or g.shape[1] > ny:
                continue
            rc_list.append({"rot": np.asarray(R), "fp": g.any(axis=2),
                            "gh": gh, "halo": eff_m})
        rc_list.sort(key=lambda r: r["gh"])
        adaylar[ad] = rc_list
        log(f"[B] aday {ad}: "
            + " | ".join(f"gh={r['gh']*pt:.1f} fp={r['fp'].shape}"
                         for r in rc_list))

    # sira varyantlari
    varyantlar = [
        ("V1 top-azalan", sorted(surucular, key=lambda k: -k["top_mm"])),
        ("V2 fp-alan-azalan",
         sorted(surucular,
                key=lambda k: -(adaylar[k["ad"]][0]["fp"].sum()
                                if adaylar[k["ad"]] else 0))),
        ("V3 kisitli-once",
         sorted(surucular,
                key=lambda k: (len(adaylar[k["ad"]]),
                               -(adaylar[k["ad"]][0]["fp"].sum()
                                 if adaylar[k["ad"]] else 0)))),
    ]
    bandlar_0 = {"Z": bz, "D": bd, "U": bu}
    en_iyi_plan = None
    plan_kayitlari = []
    for etiket, sira in varyantlar:
        t1 = time.perf_counter()
        pinler, kayip, mtop, disg, plan = _plan_dene(
            sira, adaylar, bandlar_0, delik_f4, pt, Z_IYI, kz2, t_hedef,
            nx, ny)
        skor = (len(kayip), round(mtop, 1), disg)
        plan_kayitlari.append({"varyant": etiket, "yerlesmeyen": kayip,
                               "max_top": round(mtop, 1),
                               "delik_isgal": disg, "plan": plan})
        log(f"[B] {etiket:18s} yerlesen={len(pinler)}/{len(sira)}"
            f" max_top={mtop:.1f} delik_isgal={disg}"
            f" ({time.perf_counter() - t1:.0f}s)")
        if en_iyi_plan is None or skor < en_iyi_plan[0]:
            en_iyi_plan = (skor, etiket, pinler, kayip)
    skor, et_plan, plan_pinleri, kayip = en_iyi_plan
    log(f"[B] KAZANAN: {et_plan} skor={skor}"
        f" ({len(plan_pinleri)} pin, {len(kayip)} havuzda)")
    for pk in plan_kayitlari:
        if pk["varyant"] == et_plan:
            for satir in pk["plan"]:
                log(f"[B]   {satir['ad']:24s} ({satir['x_mm']:6.1f},"
                    f"{satir['y_mm']:6.1f}) top={satir['top_mm']:5.1f}"
                    f" ceza={satir['delik_ceza']}")

    # ---- FAZ-C: planli cozum + relokasyon + settle + A2 ----------------
    kalan_pinler = [it["pin"] for it in kalan]
    # tam-pin bos-havuz sorunu: en-alcak KALAN parcayi serbest birak
    # (plan pinlerine dokunulmaz — plan bozulmasin)
    kalan_pinler.sort(key=lambda q: q["z_mm"])
    serbest = kalan_pinler.pop(0)
    tum = kalan_pinler + plan_pinleri
    log(f"[C] cozum: {len(tum)} pin (+1 serbest: {serbest['ad']},"
        f" {len(kayip)} havuzda)")
    del res
    gc.collect()
    t1 = time.perf_counter()
    res = coz(pinler=tum, pitch=pt)
    h_iyi = float(res.height_mm)
    n1 = int(res.n_placed)
    log(f"[C] h={h_iyi:.2f} n={n1}/{n_total}"
        f" ({(time.perf_counter() - t1)/60:.1f}dk)"
        f"  [plato 127.20 / manuel 110.41]")
    if n1 != n_total:
        log("[C] TAM YERLESMEDI -> plan asamasi INVALID; yine de relokasyon"
            " denenir")

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

    doc = {"olcum": "k62_v26_atama_planner",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": ("A11 tek-set on-olcum; ortak-atama planlayicisi "
                    "script-seviyesi — GO cikarsa kablo + dagilimsal "
                    "(holey_frames) + 4-set kapi ayri is"),
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI},
           "faz_a": {"h": h0, "t_hedef": round(t_hedef, 1),
                     "surucu": [{"ad": it["ad"],
                                 "top": round(it["top_mm"], 1)}
                                for it in surucular]},
           "plan_varyantlari": plan_kayitlari,
           "kazanan_varyant": et_plan,
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
    log(f"OZET: final={h_iyi:.2f} plan={et_plan}")
    log(f"WALL_S={time.perf_counter() - t0:.1f}"
        f"  ({(time.perf_counter() - t0) / 60:.1f} dk)")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
