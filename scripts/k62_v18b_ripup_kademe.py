# -*- coding: utf-8 -*-
"""k62_v18b_ripup_kademe.py — K-62 v18b: kademeli rip-up DUZELTMESI.

v18 faz-B kusuru: hedef = h - pitch, RAW-ust semantigiyle TAM tepeye denk
geliyor (h dilated-tepe; raw ust = h - z_pad) -> "ust <= hedef" tepe parcayi
da PIN sayip sokulen listesini BOS birakti, rip-up hic calismadi. v18b:
hedef, sokulen bulunana dek pitch adimlariyla indirilir (taban manuel-bandi).

Faz-A v18'de olculdu (z=64.8 kazanan, 129.60) -> burada tek nokta.
Sira varyantlari + tek-tarafli kabul + B2 settle + A2 v18 ile ayni.

Kosum: python -m scripts.detach_run k62_v18b_ripup_kademe  (D:\\ie488). ASCII.
Env: K62V18B_MAXKADEME (4). SERH (A11): tek-set on-olcum.
"""
from __future__ import annotations

import gc
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
from scripts.k62_v17_ripup import _pinler_ve_sokulenler, a2_olc

LOG = Path(__file__).parent / "k62_v18b_ripup_kademe.log"
OUT = _ROOT / "results" / "k62_v18b_ripup_kademe.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
SEED = 42
CLEAR_MM = 2.0
Z_IYI = 64.8                                 # v18 faz-A kazanani
MAX_KADEME = int(os.environ.get("K62V18B_MAXKADEME", "4"))
REF = {"v18_faz_a": 129.60, "kapi_otomatik": 129.00, "manuel": 110.41}
UCLU = {"811793-1": 0, "bobbin_2_v2": 0, "bobbin_1_v2": 0}
KULE_TIPLERI = ("811793-1", "bobbin_1_v2", "bobbin_2_v2", "bobbin_3_v2",
                "pyramid_with_doors", "TAPER-GAUGE-1")


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-62 v18b: kademeli rip-up (hedef-dusurme duzeltmeli)")
    log(f"sozlesme: plate={eg.PLATE_STD} nogo={eg.NOGO_STD}"
        f" clearance={CLEAR_MM} seed={SEED} z={Z_IYI}")

    inst = eg._load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    p0, mesh, fiz = _kanopi_adayi(inst)
    poz = fiz["pozlar"][0]
    rot_k = (tt.rotation_matrix(np.deg2rad(float(poz["rot_deg"])), [0, 0, 1])
             @ duz_rot_matrisleri(mesh)[0])

    def coz(z_mm, pinler=None, rutbeler=None, pitch=None, settle=False):
        if pinler is None:
            pinler = [{"ad": p0.name, "x_mm": float(poz["dx_mm"]),
                       "y_mm": float(poz["dy_mm"]), "z_mm": float(z_mm),
                       "rot": rot_k.tolist()}]
        return solve_nfv(inst, plate_w_mm=eg.PLATE_STD[0],
                         plate_d_mm=eg.PLATE_STD[1],
                         fine_pitch=pitch, fine_settle=settle, seed=SEED,
                         quality="fast", clearance_mm=CLEAR_MM,
                         no_go_bounds=eg.NOGO_STD,
                         pinned_placements=pinler, pin_3d=True,
                         oncelik_adlari=(rutbeler or None))

    res = coz(Z_IYI, rutbeler=UCLU)
    h_iyi = float(res.height_mm)
    pt = float(res.coarse_pitch)
    log(f"[taban] h={h_iyi:.2f} n={int(res.n_placed)}/{n_total}"
        f" pitch={pt:.3f}")

    def sira_varyantlari(sokulen):
        boy = {}
        for ad, alt, ust in sokulen:
            boy[ad] = max(boy.get(ad, 0.0), float(ust) - float(alt))
        uzun = sorted(boy, key=lambda a: -boy[a])
        v1 = {a: i for i, a in enumerate(uzun)}
        v2 = {a: i for i, a in enumerate(reversed(uzun))}
        v3 = {a: (0 if a in KULE_TIPLERI else 1) for a in boy}
        return [("V0-default", None), ("V1-uzun", v1),
                ("V2-kisa", v2), ("V3-kule", v3)]

    kademeler = []
    son_kabul = None
    for k in range(1, MAX_KADEME + 1):
        # hedefi sokulen bulunana dek indir (v18 kusurunun duzeltmesi)
        hedef = h_iyi - pt
        pinler, sokulen = _pinler_ve_sokulenler(res, hedef)
        while not sokulen and hedef > REF["manuel"]:
            hedef -= pt
            pinler, sokulen = _pinler_ve_sokulenler(res, hedef)
        if not sokulen:
            log(f"[k{k}] manuel-bandina dek sokulecek yok -> dur")
            break
        tipler = {}
        for ad, _a, _u in sokulen:
            tipler[ad] = tipler.get(ad, 0) + 1
        log(f"[k{k}] hedef={hedef:.1f} pin={len(pinler)}"
            f" sokulen={len(sokulen)} {tipler}")
        kabul_var = False
        for etiket, rutbeler in sira_varyantlari(sokulen):
            t1 = time.perf_counter()
            r = coz(None, pinler=pinler, rutbeler=rutbeler, pitch=pt)
            hr = float(r.height_mm)
            nr = int(r.n_placed)
            kabul = (nr == n_total and hr < h_iyi - 0.01)
            log(f"  {etiket:10s} h={hr:.2f} n={nr}/{n_total}"
                f" ({'KABUL' if kabul else 'gecildi'})"
                f" {(time.perf_counter() - t1)/60:.1f}dk")
            kademeler.append({"kademe": k, "varyant": etiket, "hedef": hedef,
                              "h": hr, "n": nr, "kabul": kabul})
            if kabul:
                del res
                gc.collect()
                res, h_iyi = r, hr
                son_kabul = (pinler, rutbeler)
                kabul_var = True
                break
            del r
            gc.collect()
        if not kabul_var:
            log(f"[k{k}] hicbir varyant iyilestirmedi -> dur")
            break

    log(f"[rip-up] SONUC: h={h_iyi:.2f} (kapi 129.00 / manuel 110.41)")

    # settle'li tekrar (tek-tarafli)
    t1 = time.perf_counter()
    if son_kabul is not None:
        rs = coz(None, pinler=son_kabul[0], rutbeler=son_kabul[1],
                 pitch=pt, settle=True)
    else:
        rs = coz(Z_IYI, rutbeler=UCLU, settle=True)
    hs = float(rs.height_mm)
    ns = int(rs.n_placed)
    log(f"[B2] settle'li tekrar: h={hs:.2f} n={ns}/{n_total}"
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

    doc = {"olcum": "k62_v18b_ripup_kademe",
           "tarih": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "serh": "A11 tek-set on-olcum (fix'li motor)",
           "sozlesme": {"plate": list(eg.PLATE_STD), "nogo": eg.NOGO_STD,
                        "clearance_mm": CLEAR_MM, "seed": SEED,
                        "z_mm": Z_IYI},
           "kademeler": kademeler,
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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write("FATAL:\n" + traceback.format_exc() + "\n")
        raise
