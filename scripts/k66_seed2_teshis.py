# -*- coding: utf-8 -*-
"""k66_seed2_teshis.py — K-66-d dagilimsal kapidaki seed2 clearance teshisi.

BULGU (results/k66_dagilim_smoke.json, 2026-08-20 @pitch2.0): seed2 kafes
clearance 1.642 < 2.0 (pinsiz ayni seed 2.104 LEGAL). Diger 11 seed >= 2.01.
SUPHE (RESUME): kafes-pin x settle etkilesimi.

Bu script A4 ucuz-teshis adimidir: seed2 kafes cozumunu smoke ile AYNI
parametrelerle (pitch/quality/seed) yeniden uretir ve clearance esigi
altindaki TUM cift kimliklerini dokerr:
  - cift tipi: PIN-PIN / PIN-SERBEST / SERBEST-SERBEST
  - parca adlari, yerlesim (mm), eksen-bazli AABB bosluklari
  - en yakin nokta ciftinin koordinati (ihlalin uzaydaki yeri)
Pin kimligi: pinler res.placements listesinin SONUNA eklenir
(nfv_solve.py K-62 v8 adim c) -> son n_pins indeks = pin.

Kosum: D:\\ie488'den python -m scripts.detach_run k66_seed2_teshis
Env: K66T_SEED_INST (2) / K66T_PITCH (2.0) / K66T_QTY (120) /
     K66T_QUALITY (fast) / K66T_ESIK (2.05)
SAF ASCII stdout. A11: teshis adimi — mekanizma/kablo karari degil.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k66_seed2_teshis.log"
OUT = _ROOT / "results" / "k66_seed2_teshis.json"
ONEDRIVE = Path(r"C:\Users\erenk\OneDrive\Masaüstü\IE 488 Project")
PLATE = 335.0
CLEAR = 2.0


def log(m: str = "") -> None:
    print(m, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(m + "\n")
    except OSError:
        pass


def _kafes_coz_pinli(inst, pitch, quality, seed):
    """k66_dagilim_smoke._kafes_coz kopyasi + pin listesi de doner."""
    import trimesh
    from src.nesting3d.nfv_solve import solve_nfv
    from scripts.k66_d_kafes_dekod import (
        eksen_rot_bul, kafes_plani, pin_listesi)
    from scripts.k66_dagilim_smoke import _siniflandir
    modeller, asanlar, tekrarlar, n_total, tetik = _siniflandir(inst)
    if not tetik:
        raise SystemExit("TETIK YOK — beklenmedik (smoke 12/12 tetiklemisti)")
    kitle_ad = max(tekrarlar, key=lambda a: tekrarlar[a]["qty"])
    n_rod = sum(m["qty"] for m in asanlar.values())
    slot = tuple(max(sorted(m["dims"])[i] for m in asanlar.values())
                 for i in range(3))
    plan = kafes_plani(slot, n_rod, modeller[kitle_ad]["dims"],
                       modeller[kitle_ad]["qty"], PLATE, PLATE, CLEAR,
                       pitch=pitch)
    if not plan.get("uygun"):
        raise SystemExit(f"plan kurulamadi: {plan.get('sebep')}")
    ornek = {}
    for p in inst.parts:
        if p.name in (set(asanlar) | {kitle_ad}) and p.name not in ornek:
            if getattr(p, "stl_path", None):
                ornek[p.name] = tuple(
                    trimesh.load(str(p.stl_path), force="mesh").extents)
            else:
                ornek[p.name] = (float(p.width_mm), float(p.depth_mm),
                                 float(p.height_mm))
    rod = plan["rod"]
    dar_x = abs(rod["w"] - slot[0]) < abs(rod["w"] - slot[1])
    rod_pinler = []
    for ad in sorted(asanlar):
        m0, m1, m2 = sorted(asanlar[ad]["dims"])
        hedef = (m0, m1, m2) if dar_x else (m1, m0, m2)
        rrot = eksen_rot_bul(ornek[ad], hedef)
        if rrot is None:
            raise SystemExit(f"rot bulunamadi: {ad}")
        rod_pinler.extend([(ad, rrot)] * asanlar[ad]["qty"])
    kitle_rot = eksen_rot_bul(ornek[kitle_ad], tuple(plan["cell"]))
    if kitle_rot is None:
        raise SystemExit("rot bulunamadi: kitle")
    pins = pin_listesi(plan, rod_pinler, kitle_ad, kitle_rot, CLEAR)
    res = solve_nfv(inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
                    fine_pitch=pitch, seed=seed, quality=quality,
                    clearance_mm=CLEAR, pinned_placements=pins, pin_3d=True)
    return res, pins, plan, n_total


def _cift_taramasi(meshes, esik, samples=3000, tree_seed=0):
    """min_clearance ile ayni ornekleme; esik altindaki TUM ciftler."""
    from scipy.spatial import cKDTree
    import trimesh
    n = len(meshes)
    bounds = [m.bounds for m in meshes]
    smp = [None] * n
    trees = [None] * n

    def _get(i):
        if smp[i] is None:
            pts, _f = trimesh.sample.sample_surface(
                meshes[i], samples, seed=tree_seed + i)
            smp[i] = np.asarray(pts)
            trees[i] = cKDTree(smp[i])
        return smp[i], trees[i]

    ihlaller = []
    best = np.inf
    best_pair = None
    for i in range(n):
        for j in range(i + 1, n):
            gap = np.maximum(
                bounds[i][0] - bounds[j][1],
                bounds[j][0] - bounds[i][1]).max()
            if gap > esik:
                continue
            pts_i, _ = _get(i)
            _, tj = _get(j)
            d, idx = tj.query(pts_i, k=1, workers=-1)
            k = int(np.argmin(d))
            pair_min = float(d[k])
            if pair_min < best:
                best, best_pair = pair_min, (i, j)
            if pair_min < esik:
                pi = pts_i[k]
                pj = _get(j)[0][int(idx[k])]
                ihlaller.append((pair_min, i, j,
                                 [round(float(v), 2) for v in pi],
                                 [round(float(v), 2) for v in pj]))
    ihlaller.sort()
    return best, best_pair, ihlaller


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    t0 = time.time()
    seed_inst = int(os.environ.get("K66T_SEED_INST", "2"))
    pitch = float(os.environ.get("K66T_PITCH", "2.0"))
    qty = int(os.environ.get("K66T_QTY", "120"))
    quality = os.environ.get("K66T_QUALITY", "fast")
    esik = float(os.environ.get("K66T_ESIK", "2.05"))
    log("K-66 SEED2 CLEARANCE TESHISI (A4 ucuz-teshis)")
    log(f"seed_inst={seed_inst} pitch={pitch} qty={qty} quality={quality}"
        f" esik={esik} plate={PLATE} clear={CLEAR}")

    from src.nesting3d.instances.format import ContainerSpec
    from src.nesting3d.instances.synthetic import mass_plate_rod_mix
    from src.nesting3d.export_stl import placed_meshes

    cnt = ContainerSpec(width_mm=PLATE, depth_mm=PLATE, height_mm=None)
    inst = mass_plate_rod_mix(container=cnt, seed=seed_inst,
                              qty_per_plate=qty)
    res, pins, plan, n_total = _kafes_coz_pinli(inst, pitch, quality, 42)
    pls = list(res.placements)
    n_pins = len(pins)
    rp = float(res.fine_pitch)
    log(f"[cozum] h={float(res.height_mm):.2f} n={int(res.n_placed)}/"
        f"{n_total} rapor_pitch={rp} n_pins={n_pins}"
        f" (pin= son {n_pins} indeks)")
    log(f"[plan] oryant={plan['oryantasyon']} m={plan['m']} "
        f"katman={plan['katman']} kapasite={plan['kapasite']} "
        f"adim={plan['adim']}")

    meshes = placed_meshes(pls, res.fine_voxel_parts, rp)
    log(f"[tarama] {len(meshes)} mesh, esik {esik}mm alti tum ciftler...")
    best, best_pair, ihlaller = _cift_taramasi(meshes, esik)
    log(f"[global] min={best:.3f} worst_pair={best_pair}")

    def _kimlik(i):
        pl = pls[i]
        pin_idx = i - (len(pls) - n_pins)
        b = meshes[i].bounds
        d = {"idx": i, "ad": pl.name,
             "tip": "PIN" if pin_idx >= 0 else "SERBEST",
             "vox": [int(pl.x), int(pl.y), int(pl.z)],
             "mm": [round(pl.x * rp, 1), round(pl.y * rp, 1),
                    round(pl.z * rp, 1)],
             "bbox_min": [round(float(v), 2) for v in b[0]],
             "bbox_max": [round(float(v), 2) for v in b[1]]}
        if pin_idx >= 0:
            sp = pins[pin_idx]
            d["pin_spec"] = {"ad": sp["ad"], "x_mm": sp["x_mm"],
                             "y_mm": sp["y_mm"], "z_mm": sp["z_mm"]}
        return d

    kayit = []
    for pair_min, i, j, pi, pj in ihlaller:
        ki, kj = _kimlik(i), _kimlik(j)
        tip = "-".join(sorted([ki["tip"], kj["tip"]]))
        # eksen-bazli AABB bosluklari (negatif = o eksende ortusuyor)
        bi = meshes[i].bounds
        bj = meshes[j].bounds
        eksen = [round(float(max(bi[0][a] - bj[1][a], bj[0][a] - bi[1][a])), 3)
                 for a in range(3)]
        kayit.append({"min_mm": round(pair_min, 3), "tip": tip,
                      "eksen_gap": eksen, "nokta_i": pi, "nokta_j": pj,
                      "i": ki, "j": kj})
        log(f"  {pair_min:6.3f}mm  {tip:17s} {ki['ad']}@{ki['mm']}"
            f"({ki['tip']}) <-> {kj['ad']}@{kj['mm']}({kj['tip']})"
            f"  eksen_gap={eksen}")
    if not kayit:
        log("  esik altinda cift yok (?) — smoke 1.642 uyusmazligi arastir")

    tipler = {}
    for k in kayit:
        tipler[k["tip"]] = tipler.get(k["tip"], 0) + 1
    log(f"[ozet] ihlal ciftleri tip dagilimi: {tipler}")

    doc = {"olcum": "k66_seed2_teshis", "tarih": str(date.today()),
           "ayarlar": {"seed_inst": seed_inst, "pitch": pitch, "qty": qty,
                       "quality": quality, "esik": esik},
           "cozum": {"h": float(res.height_mm), "n": int(res.n_placed),
                     "n_total": n_total, "rapor_pitch": rp,
                     "n_pins": n_pins},
           "global_min": round(float(best), 3),
           "ihlaller": kayit, "tip_dagilimi": tipler,
           "sure_s": round(time.time() - t0, 1),
           "a11_not": "teshis adimi; mekanizma karari degil"}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                   encoding="utf-8")
    try:
        ek = ONEDRIVE / "results" / OUT.name
        if ONEDRIVE.exists() and ek.resolve() != OUT.resolve():
            ek.write_text(json.dumps(doc, indent=2, ensure_ascii=True),
                          encoding="utf-8")
    except Exception as e:
        log(f"uyari: OneDrive kopyasi yazilamadi ({e})")
    log(f"KAYIT: {OUT}")
    log(f"BITTI  sure={(time.time() - t0)/60:.1f}dk")
    return 0


if __name__ == "__main__":
    sys.exit(main())
