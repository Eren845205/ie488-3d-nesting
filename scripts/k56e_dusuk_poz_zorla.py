# -*- coding: utf-8 -*-
"""k56e_dusuk_poz_zorla.py — K-56e: dusuk-poz ZORLAMA teshisi (SA miyopi testi).

Baglam: K-56d v2 raw-no-go 170.69 (soft 171.70'ten -1.0) — x8-x14 pozlari
(plaka z 80-110mm) MENUDE ama SA hep ~x28 dengesine kiliteniyor. Oysa
111-parca serbest tabani ~101mm (K-56d v1 yan-olcumu) -> teorik kompozit
~101-140 bandi. SORU: 170.7 gercek optimum mu, yoksa greedy/SA eğik-poz
miyopisi mi (meta-ders 12)? TEST: menuden yuksek acilari CIKAR — SA alcak
poza MECBUR kalsin; cikan sayi kompozisyonun gercek maliyetini olcer.
  B_dar  = yalniz x8..x14 (7 poz; plaka z 80-110)
  B_orta = yalniz x8..x20 (13 poz; plaka z 80-137)
Yorum: B_dar < 170.7 -> miyopi KANITLI (dekod/coklu-baslangic isi acilir);
B_dar >= 170.7 -> denge gercek optimum, kalan yol duz-poz/kuantizasyon.

Sozlesme: K-56d v2 ile AYNI (kapi=SOFT yamasi, cozucu=ERODE raw semantigi).
Kosum: python -m scripts.detach_run k56e_dusuk_poz_zorla   (D:\\ie488'den)
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
from scripts.k56_plan1_uretim_tilt import CLEAR_MM, HEDEF_AD, SEED, _uretim_fine_pitch

LOG = Path(__file__).parent / "k56e_dusuk_poz_zorla.log"
OUT = _ROOT / "results" / "k56e_dusuk_poz_zorla.json"
NOGO_SOFT = ((152.5, 0.2), (185.5, 33.0))
REF = {"raw_v2": 170.68857421875, "soft": 171.70457763671877,
       "k37": 129.0, "manuel": 110.41, "taban111": 101.17}


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _ozet(r):
    return (f"legal={r['legal_height_mm']}  h={r['height_mm']}"
            f"  clear={r['min_clearance_mm']}  kilit={r['n_locked']}"
            f"  sure={r['duration_s']}s  invalid={r['invalid_reason']}")


def _rots(a1, a2):
    return [trimesh.transformations.rotation_matrix(np.deg2rad(a), [1, 0, 0])
            for a in range(a1, a2 + 1)]


def main():
    LOG.write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    log("K-56e DUSUK-POZ ZORLAMA (SA miyopi testi; K-56d v2 sozlesmesi)")
    log(f"ref: {REF}")

    inst = eg._load_instance("plan1")
    fine_pitch, _w = _uretim_fine_pitch(inst)
    margin, _zc = clearance_to_voxels(CLEAR_MM, fine_pitch)
    margin, _c = cap_margin_to_plate(
        margin, fine_pitch, inst, eg.PLATE_STD[0], eg.PLATE_STD[1])
    m_mm = margin * fine_pitch
    (x1, y1), (x2, y2) = NOGO_SOFT
    eg.NOGO_STD = ((x1 + m_mm, y1 + m_mm), (x2 - m_mm, max(y1, y2 - m_mm)))
    _orig = ap.predict_nfv_benefit

    def _pnb_soft(inst_, *a, **kw):
        kw["no_go_bounds"] = NOGO_SOFT
        return _orig(inst_, *a, **kw)

    ap.predict_nfv_benefit = _pnb_soft
    log(f"cozucu bounds={eg.NOGO_STD}")

    p0 = [p for p in inst.parts if HEDEF_AD in str(p.name).lower()][0]
    sonuc = {}
    for ad, (a1, a2) in [("dar_x8_x14", (8, 14)), ("orta_x8_x20", (8, 20))]:
        rots = _rots(a1, a2)
        log(f"[{ad}] evaluate_set(plan1, {len(rots)} poz x{a1}..x{a2})...")
        try:
            r = eg.evaluate_set("plan1", SEED,
                                extra_rot_overrides={p0.name: rots})
            log(f"[{ad}] SONUC: {_ozet(r)}")
            sonuc[ad] = r
        except Exception as e:
            sonuc[ad] = {"exception": f"{type(e).__name__}: {e}"}
            log(f"[{ad}] EXCEPTION: {type(e).__name__}: {e}")

    ap.predict_nfv_benefit = _orig
    ozet = {k: (v.get("legal_height_mm") if isinstance(v, dict) else None)
            for k, v in sonuc.items()}
    log(f"KIYAS: serbest-menu 170.69 | zorlama {ozet}"
        f" | K-37 {REF['k37']} | manuel {REF['manuel']}")
    OUT.write_text(json.dumps({
        "sonuc": sonuc, "ref": REF, "nogo_erode": eg.NOGO_STD,
        "toplam_sure_dk": round((time.perf_counter() - t0) / 60, 1),
    }, indent=2, default=str), encoding="utf-8")
    log(f"toplam sure: {(time.perf_counter() - t0) / 60:.1f} dk")
    log("BITTI")


if __name__ == "__main__":
    main()
