# -*- coding: utf-8 -*-
"""k56d_raw_nogo_v2.py — K-56d v2: RAW-no-go olcumu, KAPI-HIZALI.

v1 dersi (2026-07-19, results/k56d_raw_nogo.json): NOGO erode'u ADIM -1
tilt-zorunlu kapisini sondurdu — raw-rect testi duz pozu "sigar" sandi
(302.0 <= 304.03) ve plan1 NFV'ye yonlendi (K-40 sert no-go yolu):
A_raw INVALID 111/112 @ h=101.17 (baseplate NFV'de yerlesemedi; YAN-BULGU:
kalan 111 parcanin taban yuksekligi ~101mm — manuel 110.41 erisilebilir
gorunuyor). 2026-07-09 "filtre dersi"nin sozlesme-katmani tekrari: kapi
raw-dikdortgen konusuyor, cozucu dilate-voksel konusuyor.

v2 TASARIM KISITI (uretim kablosuna da gececek): raw semantik benimsenirse
ADIM -1 kapisi ERODE-EDILMEMIS (soft) bounds'la karar vermeli — kapinin
"duz sigar mi" sorusu cozucunun GERCEKTEN yerlestirebilecegiyle hizali
kalmali. Uygulama: adaptive_params.predict_nfv_benefit sarilir (no_go_bounds
= SOFT zorlanir) -> kapi tilt-zorunlu kalir; eg.NOGO_STD = ERODE -> cozucu
maskesi + hedefli-tilt havuzu raw semantikle calisir.

Kollar: A = dogal routing (kapi-yamali) · B = acik @1 menu (x8..x50).
Referans: soft 171.70 · hard 202.18 · K-37 129.0 · manuel 110.41 ·
111-parca taban ~101.2 (v1 yan-bulgusu).
Kosum: python -m scripts.detach_run k56d_raw_nogo_v2    (D:\\ie488'den)
SAF ASCII stdout (cp1254).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

import scripts.eval_gate as eg
import src.nesting3d.adaptive_params as ap
from src.nesting3d.coarse_to_fine import cap_margin_to_plate, clearance_to_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k56_plan1_uretim_tilt import CLEAR_MM, HEDEF_AD, SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k56d_raw_nogo_v2.log"
OUT = _ROOT / "results" / "k56d_raw_nogo_v2.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))
ACILAR = range(1, 51)
REF = {"soft": 171.70457763671877, "hard": 202.18468017578127,
       "k37": 129.0, "manuel": 110.41, "taban111": 101.17}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _yerlesebilir(fp_x_mm, fp_y_mm, nogo):
    pw, pd = eg.PLATE_STD
    (ng_x1, ng_y1), (ng_x2, ng_y2) = nogo
    solda = fp_x_mm <= ng_x1 and fp_y_mm <= pd
    sagda = fp_x_mm <= (pw - ng_x2) and fp_y_mm <= pd
    otede = fp_y_mm <= (pd - ng_y2) and fp_x_mm <= pw
    return bool(solda or sagda or otede)


def _ozet(r):
    return (f"legal={r['legal_height_mm']}  h={r['height_mm']}"
            f"  clear={r['min_clearance_mm']}  kilit={r['n_locked']}"
            f"  sure={r['duration_s']}s  invalid={r['invalid_reason']}")


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56d v2 RAW-NO-GO (KAPI-HIZALI: kapi=SOFT, cozucu=ERODE; SERHLI)")

    inst = eg._load_instance("plan1")
    fine_pitch, wall = _uretim_fine_pitch(inst)
    margin, _zc = clearance_to_voxels(CLEAR_MM, fine_pitch)
    margin, _capped = cap_margin_to_plate(
        margin, fine_pitch, inst, eg.PLATE_STD[0], eg.PLATE_STD[1])
    m_mm = margin * fine_pitch
    (x1, y1), (x2, y2) = NOGO_SOFT
    NOGO_RAW = ((x1 + m_mm, y1 + m_mm), (x2 - m_mm, max(y1, y2 - m_mm)))
    log(f"pitch={fine_pitch} margin={margin} vox ({m_mm:.3f}mm/yan)")
    log(f"kapi bounds=SOFT {NOGO_SOFT} | cozucu bounds=ERODE {NOGO_RAW}")
    log(f"ref: {REF}")

    # ---- YAMALAR ----
    eg.NOGO_STD = NOGO_RAW                      # cozucu maskesi + tilt havuzu
    _orig_pnb = ap.predict_nfv_benefit

    def _pnb_kapi_soft(inst_, *a, **kw):        # kapi karari SOFT'la
        kw["no_go_bounds"] = NOGO_SOFT
        return _orig_pnb(inst_, *a, **kw)

    ap.predict_nfv_benefit = _pnb_kapi_soft

    # ---- A: dogal routing ----
    log("[A] evaluate_set(plan1) — kapi-yamali dogal routing...")
    try:
        res_a = eg.evaluate_set("plan1", SEED)
        log(f"[A] SONUC: {_ozet(res_a)}")
    except Exception as e:
        res_a = {"exception": f"{type(e).__name__}: {e}"}
        log(f"[A] EXCEPTION: {type(e).__name__}: {e}")

    # ---- tarama (erode filtre) ----
    p0 = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()][0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])
    nx, ny = (int(eg.PLATE_STD[0] // fine_pitch),
              int(eg.PLATE_STD[1] // fine_pitch))
    vp4 = voxelize_part(p0.name, mesh, fine_pitch, n_orientations=4,
                        margin=margin, method="slice")
    z_esik_vox = 10 ** 9
    for o in vp4.orientations:
        fx, fy = o.grid.shape[0] * fine_pitch, o.grid.shape[1] * fine_pitch
        if _yerlesebilir(fx, fy, NOGO_RAW) and o.grid.shape[2] < z_esik_vox:
            z_esik_vox = o.grid.shape[2]
    log(f"z-esigi = {z_esik_vox} vox")

    rots, tablo = [], []
    for ang in ACILAR:
        R = trimesh.transformations.rotation_matrix(
            np.deg2rad(ang), [1, 0, 0])
        vp = voxelize_part(p0.name, mesh, fine_pitch, rot_matrices=[R],
                           method="slice", margin=margin)
        g = vp.orientations[0].grid
        fx, fy = g.shape[0] * fine_pitch, g.shape[1] * fine_pitch
        al = (g.shape[0] <= nx and g.shape[1] <= ny
              and _yerlesebilir(fx, fy, NOGO_RAW)
              and g.shape[2] < z_esik_vox)
        tablo.append({"poz": f"x{ang}", "fp": [g.shape[0], g.shape[1]],
                      "z": g.shape[2], "al": al})
        if al:
            rots.append(R)
    kabul_acilar = [t["poz"] for t in tablo if t["al"]]
    log(f"kabul: {len(rots)} poz ({kabul_acilar[0]}..{kabul_acilar[-1]})"
        if rots else "kabul: 0")

    # ---- B: acik menu ----
    res_b = None
    if rots:
        log(f"[B] evaluate_set(plan1, extra_rot_overrides={len(rots)} poz)...")
        try:
            res_b = eg.evaluate_set("plan1", SEED,
                                    extra_rot_overrides={p0.name: rots})
            log(f"[B] SONUC: {_ozet(res_b)}")
        except Exception as e:
            res_b = {"exception": f"{type(e).__name__}: {e}"}
            log(f"[B] EXCEPTION: {type(e).__name__}: {e}")

    ap.predict_nfv_benefit = _orig_pnb
    a_l = res_a.get("legal_height_mm") if isinstance(res_a, dict) else None
    b_l = res_b.get("legal_height_mm") if isinstance(res_b, dict) else None
    log(f"KIYAS: hard {REF['hard']:.1f} -> soft {REF['soft']:.1f} -> raw"
        f" A={a_l} B={b_l} | K-37 {REF['k37']} | manuel {REF['manuel']}")
    OUT.write_text(json.dumps({
        "nogo_soft": NOGO_SOFT, "nogo_erode": NOGO_RAW,
        "a": res_a, "b": res_b, "pozlar": tablo,
        "fine_pitch": fine_pitch, "margin": margin, "kabul": len(rots),
        "ref": REF,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
