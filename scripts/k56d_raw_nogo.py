# -*- coding: utf-8 -*-
"""k56d_raw_nogo.py — K-56d: RAW-no-go semantigi olcumu (soft + margin'siz sinir).

Baglam: K-56c soft no-go GO (202.2 -> 171.70) ama Eren "daha iyi olmali".
Kalan tespit edilen fren: clearance margin'i (2 vox ~2.03mm/yan) no-go
SINIRINA da uygulaniyor — oysa clearance kurali PARCA-PARCA ayrilabilirlik
icindir; no-go bir bolge kisitidir (K-37'nin 129.0'u raw semantikle dogdu;
hoca cevap 9 ornegi bizzat duz plakanin giriseydi). ESDEGER NUMARA: no-go
dikdortgenini margin_mm kadar ERODE edip ayni boru hattina vermek = "dilate
parca erode-no-go'ya girmesin" == "raw parca soft-no-go'ya girmesin" —
SIFIR solver degisikligi. Parca-parca clearance DEGISMEZ (margin gridlerde).

Beklenti: soft'ta 302.0mm olan "otede" limiti ~304.03'e cikar -> x8-x10
acilir (plaka z 80-90mm); duz poz pitch-kuantizasyon nedeniyle muhtemelen
hala olu (log'a islenir). SERH: hoca "no-go sinirina temas" netligi henuz
sorulmadi — sonuc serhli-on-olcum statusunde.

Kollar (seed 42, eval v2, yalniz NOGO farkli):
  A_raw = evaluate_set dogal routing (K-56b kablosu erode-bounds'la kendi
          havuzunu kurar — K-56c'de dogal==acik bit-ozdes cikmisti)
  B_raw = acik @1 menu x1..x50 (dusuk ucta @5'in atladigi x8/x9 dahil)

Referanslar: soft 171.70 · hard 202.18 · K-37 serhli 129.0 · manuel 110.41.
Kosum: python -m scripts.detach_run k56d_raw_nogo    (D:\\ie488'den)
Cikti: scripts/k56d_raw_nogo.log + results/k56d_raw_nogo.json
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
from src.nesting3d.coarse_to_fine import cap_margin_to_plate, clearance_to_voxels
from src.nesting3d.voxelize import voxelize_part
from scripts.k56_plan1_uretim_tilt import CLEAR_MM, HEDEF_AD, SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k56d_raw_nogo.log"
OUT = _ROOT / "results" / "k56d_raw_nogo.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))   # K-56c tabani (Eren onayli)
ACILAR = range(1, 51)                        # @1 — dusuk ucu tam tara
REF_SOFT = 171.70457763671877
REF_HARD = 202.18468017578127
REF_K37 = 129.0
MANUEL = 110.41


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
    log("K-56d RAW-NO-GO SEMANTIGI ON-OLCUMU (soft + erode; SERHLI)")

    inst = eg._load_instance("plan1")
    fine_pitch, wall = _uretim_fine_pitch(inst)
    margin, _zc = clearance_to_voxels(CLEAR_MM, fine_pitch)
    margin, _capped = cap_margin_to_plate(
        margin, fine_pitch, inst, eg.PLATE_STD[0], eg.PLATE_STD[1])
    m_mm = margin * fine_pitch
    (x1, y1), (x2, y2) = NOGO_SOFT
    NOGO_RAW = ((x1 + m_mm, y1 + m_mm), (x2 - m_mm, max(y1, y2 - m_mm)))
    log(f"pitch={fine_pitch} margin={margin} vox ({m_mm:.3f}mm/yan)")
    log(f"nogo SOFT={NOGO_SOFT} -> ERODE(raw-esdegeri)={NOGO_RAW}")
    log(f"ref: soft {REF_SOFT:.2f} / hard {REF_HARD:.2f} / K-37 {REF_K37}"
        f" / manuel {MANUEL}")

    # ---- SOZLESME YAMASI ----
    eg.NOGO_STD = NOGO_RAW

    # ---- A_raw: dogal routing ----
    log("[A_raw] evaluate_set(plan1) — raw-no-go, dogal routing...")
    try:
        res_a = eg.evaluate_set("plan1", SEED)
        log(f"[A_raw] SONUC: {_ozet(res_a)}")
    except Exception as e:
        res_a = {"exception": f"{type(e).__name__}: {e}"}
        log(f"[A_raw] EXCEPTION: {type(e).__name__}: {e}")

    # ---- tarama (erode filtre) ----
    p0 = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()][0]
    mesh = trimesh.load(p0.stl_path, force="mesh")
    mesh.apply_translation(-mesh.bounds[0])
    nx, ny = (int(eg.PLATE_STD[0] // fine_pitch),
              int(eg.PLATE_STD[1] // fine_pitch))

    vp4 = voxelize_part(p0.name, mesh, fine_pitch, n_orientations=4,
                        margin=margin, method="slice")
    z_esik_vox = 10 ** 9
    for i, o in enumerate(vp4.orientations):
        fx, fy = o.grid.shape[0] * fine_pitch, o.grid.shape[1] * fine_pitch
        yerl = _yerlesebilir(fx, fy, NOGO_RAW)
        log(f"  n4 poz{i}: fp={o.grid.shape[0]}x{o.grid.shape[1]}"
            f" z={o.grid.shape[2]}  raw-yerlesebilir={yerl}"
            + ("  <-- DUZ POZ" if o.grid.shape[2] < 60 else ""))
        if yerl and o.grid.shape[2] < z_esik_vox:
            z_esik_vox = o.grid.shape[2]
    log(f"z-esigi = {z_esik_vox} vox ({z_esik_vox * fine_pitch:.1f}mm)")

    log("raw-filtreli tarama (x1..x50 @1):")
    rots, tablo = [], []
    for ang in ACILAR:
        R = trimesh.transformations.rotation_matrix(
            np.deg2rad(ang), [1, 0, 0])
        vp = voxelize_part(p0.name, mesh, fine_pitch, rot_matrices=[R],
                           method="slice", margin=margin)
        g = vp.orientations[0].grid
        fx, fy = g.shape[0] * fine_pitch, g.shape[1] * fine_pitch
        sigar = g.shape[0] <= nx and g.shape[1] <= ny
        yerl = _yerlesebilir(fx, fy, NOGO_RAW)
        kisa = g.shape[2] < z_esik_vox
        al = sigar and yerl and kisa
        durum = ("ALINDI" if al else
                 ("sigmiyor" if not sigar else
                  ("no-go-engelli" if not yerl else "uzun")))
        tablo.append({"poz": f"x{ang}", "fp": [g.shape[0], g.shape[1]],
                      "z": g.shape[2], "durum": durum})
        log(f"    x{ang:>2}: fp={g.shape[0]}x{g.shape[1]}"
            f" z={g.shape[2]} (~{g.shape[2] * fine_pitch:.1f}mm)  {durum}")
        if al:
            rots.append(R)
    log(f"kabul: {len(rots)} poz")

    # ---- B_raw ----
    res_b = None
    if rots:
        log(f"[B_raw] evaluate_set(plan1, extra_rot_overrides={len(rots)}"
            f" poz)...")
        try:
            res_b = eg.evaluate_set("plan1", SEED,
                                    extra_rot_overrides={p0.name: rots})
            log(f"[B_raw] SONUC: {_ozet(res_b)}")
        except Exception as e:
            res_b = {"exception": f"{type(e).__name__}: {e}"}
            log(f"[B_raw] EXCEPTION: {type(e).__name__}: {e}")

    a_l = res_a.get("legal_height_mm") if isinstance(res_a, dict) else None
    b_l = res_b.get("legal_height_mm") if isinstance(res_b, dict) else None
    log(f"KIYAS: hard {REF_HARD:.1f} -> soft {REF_SOFT:.1f} -> raw"
        f" A={a_l} B={b_l} | K-37 {REF_K37} | manuel {MANUEL}")
    OUT.write_text(json.dumps({
        "nogo_soft": NOGO_SOFT, "nogo_erode": NOGO_RAW,
        "margin_mm_yan": m_mm, "a_raw": res_a, "b_raw": res_b,
        "pozlar": tablo, "fine_pitch": fine_pitch, "margin": margin,
        "z_esik_vox": z_esik_vox, "kabul": len(rots),
        "ref": {"soft": REF_SOFT, "hard": REF_HARD, "k37": REF_K37,
                "manuel": MANUEL},
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"JSON: {OUT}")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
