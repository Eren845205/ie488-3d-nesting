# -*- coding: utf-8 -*-
"""k62_v15_teshis.py — K-62 v15: 130.80 cozumunun BANT x BOLGE doluluk
anatomisi (A4 olc-once: siradaki dusurme mekanizmasini VERI secsin).

Soru: manuel 110.41'e kalan 20.4mm makas NEREDE?
  (a) kanopi ALTINDA (z < z_pin) bos hacim kaldiysa -> bolge-hedefli
      decode / kanopi-alti yonlendirme kazandirir;
  (b) delik sutunlarinda 110-131 bandinda KULLANILMAYAN delik kapasitesi
      varsa -> kule-parcalarini deliklere yonlendirme kazandirir;
  (c) ikisi de doluysa -> tavan bu sozlesmede yapisal; kazanc ancak
      poz-kalitesi/atama optimizasyonundan (v10-dinamik) gelir.

Yontem: v13b recetesi deterministik cozulur; fine_voxel_parts grid'leri
occupancy'ye toplanir; bantlar [0,z_pin) / kanopi / (kanopi,110) / [110,h)
x bolgeler (kanopi-bbox ici delik-kolonu / malzeme-kolonu / plaka-disi)
doluluk oranlari + 110+ tavan parca listesi cikartilir.

Kosum: python -m scripts.detach_run k62_v15_teshis  (D:\\ie488). SAF ASCII.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh.transformations as tt

import scripts.eval_gate as eg
from src.nesting3d.kanopi import duz_rot_matrisleri
from src.nesting3d.nfv_solve import solve_nfv
from scripts.k62_v9_pin3d import _kanopi_adayi

LOG = Path(__file__).parent / "k62_v15_teshis.log"
OUT = _ROOT / "results" / "k62_v15_teshis.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_MM = float(os.environ.get("K62V15_Z", "67"))
MANUEL_MM = 110.41
RUTBELER = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0,
            "TAPER-GAUGE-1": 1}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v15 TESHIS: 130.80 bant x bolge doluluk anatomisi")
    inst = eg._load_instance("plan1")
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])
    kalinlik = float(fiz["duz_kalinlik_mm"])
    pin = {"ad": p0.name, "x_mm": float(poz["dx_mm"]),
           "y_mm": float(poz["dy_mm"]), "z_mm": Z_MM, "rot": rot_k.tolist()}
    res = solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                    plate_d_mm=eg.PLATE_STD[1],
                    fine_pitch=None, seed=SEED, quality="fast",
                    clearance_mm=CLEAR_MM, no_go_bounds=eg.NOGO_STD,
                    pinned_placements=[pin], pin_3d=True,
                    oncelik_adlari=RUTBELER)
    h = float(res.height_mm)
    pt = float(res.fine_pitch)
    log(f"[cozum] h={h:.2f} n={int(res.n_placed)} pitch={pt}"
        f"  sure={(time.perf_counter() - t0) / 60:.1f}dk")

    # ---- occupancy insa (parca gridlerinden) --------------------------
    W = int(np.ceil(eg.PLATE_STD[0] / pt))
    D = int(np.ceil(eg.PLATE_STD[1] / pt))
    H = int(np.ceil(h / pt)) + 2
    occ = np.zeros((W, D, H), dtype=bool)
    fvp = res.fine_voxel_parts
    vps = fvp if isinstance(fvp, dict) else {v.id: v for v in fvp}
    kanopi_pl = None
    parca_bilgi = []
    for pl in res.placements:
        vp = vps.get(pl.part_id)
        o = (vp.orientations[pl.orientation_idx]
             if vp and pl.orientation_idx < len(vp.orientations) else None)
        if o is None:
            continue
        g = np.asarray(o.grid, dtype=bool)
        x, y, z = int(pl.x), int(pl.y), int(pl.z)
        sx = slice(max(0, x), min(W, x + g.shape[0]))
        sy = slice(max(0, y), min(D, y + g.shape[1]))
        sz = slice(max(0, z), min(H, z + g.shape[2]))
        gg = g[(sx.start - x):(sx.stop - x), (sy.start - y):(sy.stop - y),
               (sz.start - z):(sz.stop - z)]
        occ[sx, sy, sz] |= gg
        ad = getattr(vp, "name", str(pl.part_id))
        parca_bilgi.append({"ad": ad, "alt": z * pt,
                            "ust": (z + g.shape[2]) * pt,
                            "x": x, "y": y,
                            "fx": g.shape[0], "fy": g.shape[1]})
        if ad == p0.name and abs(z * pt - Z_MM) < 3 * pt:
            kanopi_pl = (pl, g)
    if kanopi_pl is None:
        log("FATAL: kanopi placement bulunamadi")
        return

    # ---- bolgeler: kanopi bbox ici delik/malzeme kolonlari ------------
    kpl, kg = kanopi_pl
    kx, ky = int(kpl.x), int(kpl.y)
    kfp = kg.any(axis=2)  # kanopi footprint (malzeme)
    bolge = np.zeros((W, D), dtype=np.int8)  # 0=plaka-disi(kanopi disinda)
    sx = slice(max(0, kx), min(W, kx + kfp.shape[0]))
    sy = slice(max(0, ky), min(D, ky + kfp.shape[1]))
    kk = kfp[(sx.start - kx):(sx.stop - kx), (sy.start - ky):(sy.stop - ky)]
    bolge[sx, sy] = np.where(kk, 1, 2)  # 1=malzeme-kolonu 2=delik-kolonu

    z_pin_v = int(round(Z_MM / pt))
    z_kust_v = int(round((Z_MM + kalinlik) / pt))
    z_man_v = int(round(MANUEL_MM / pt))
    h_v = int(np.ceil(h / pt))
    bantlar = [("alt (0..z_pin)", 0, z_pin_v),
               ("kanopi", z_pin_v, z_kust_v),
               ("orta (kanopi..110)", z_kust_v, z_man_v),
               ("tavan (110..h)", z_man_v, h_v)]
    bolge_adlari = {0: "kanopi-disi", 1: "malzeme-kolonu", 2: "delik-kolonu"}
    tablo = {}
    log("[bant x bolge] doluluk oranlari (dolu voxel / bant-bolge hacmi):")
    for bant_ad, z1, z2 in bantlar:
        if z2 <= z1:
            continue
        satir = {}
        for b, b_ad in bolge_adlari.items():
            maske = bolge == b
            n_kolon = int(maske.sum())
            if n_kolon == 0:
                continue
            dolu = int(occ[:, :, z1:z2][maske].sum())
            hacim = n_kolon * (z2 - z1)
            satir[b_ad] = round(dolu / hacim, 4) if hacim else None
        tablo[bant_ad] = satir
        log(f"  {bant_ad:22s}: " + "  ".join(
            f"{k}={v:.3f}" for k, v in satir.items()))

    # ---- tavan parcalari (ust > 110) ---------------------------------
    tavan = sorted([p for p in parca_bilgi if p["ust"] > MANUEL_MM + pt],
                   key=lambda p: -p["ust"])
    log(f"[tavan] 110+ ustune tasan {len(tavan)} parca:")
    tavan_kayit = []
    for p in tavan[:20]:
        cx, cy = p["x"] + p["fx"] // 2, p["y"] + p["fy"] // 2
        b = bolge_adlari[int(bolge[min(cx, W - 1), min(cy, D - 1)])]
        log(f"  {p['ad']:24s} alt={p['alt']:6.1f} ust={p['ust']:6.1f}"
            f"  bolge={b}")
        tavan_kayit.append({**{k: p[k] for k in ('ad', 'alt', 'ust')},
                            "bolge": b})

    # ---- delik kapasitesi: 110..h bandinda bos delik-kolon hacmi ------
    delik_maske = bolge == 2
    z1, z2 = z_man_v, h_v
    delik_bos = int((~occ[:, :, z1:z2][delik_maske]).sum())
    delik_toplam = int(delik_maske.sum() * (z2 - z1))
    # kanopi-alti bos hacim (0..z_pin, tum bolgeler)
    alt_bos = int((~occ[:, :, 0:z_pin_v]).sum())
    alt_toplam = W * D * z_pin_v
    # tavan bandindaki toplam parca hacmi (tasinacak yuk)
    tavan_yuk = int(occ[:, :, z1:z2].sum())
    log(f"[kapasite] kanopi-alti bos={alt_bos * pt**3 / 1000:.0f}cm3"
        f" ({100 * alt_bos / alt_toplam:.0f}%)"
        f" | 110+ delik-kolon bos={delik_bos * pt**3 / 1000:.0f}cm3"
        f" ({100 * delik_bos / max(1, delik_toplam):.0f}%)"
        f" | 110+ toplam yuk={tavan_yuk * pt**3 / 1000:.0f}cm3")

    doc = {
        "olcum": "k62_v15_teshis", "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cozum": {"h": h, "pitch": pt, "z_pin": Z_MM, "kalinlik": kalinlik},
        "bant_bolge_doluluk": tablo,
        "tavan_parcalari": tavan_kayit,
        "kapasite": {
            "kanopi_alti_bos_cm3": round(alt_bos * pt**3 / 1000, 1),
            "kanopi_alti_bos_oran": round(alt_bos / alt_toplam, 4),
            "delik110_bos_cm3": round(delik_bos * pt**3 / 1000, 1),
            "delik110_bos_oran": (round(delik_bos / delik_toplam, 4)
                                  if delik_toplam else None),
            "tavan_yuk_cm3": round(tavan_yuk * pt**3 / 1000, 1),
        },
    }
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
    log(f"WALL_S={time.perf_counter() - t0:.1f}")
    log("BITTI")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
