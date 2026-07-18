# -*- coding: utf-8 -*-
"""k57d_voxelize_pay_teshis.py — K-57d ON-TESHISI (A4 olc-once): voxelize'in
eval-kapisi set surelerindeki PAYI.

Soru: kalici voxel onbellegi (STL-hash+pitch+poz-seti anahtarli) kapiyi ne
kadar hizlandirir? Cevap icin once voxelize'in izole suresi olculur ve k51e
munhasir-kosu toplamlarina (p1 356 / p2 1188 / p3 1640 / d4 2095s) oranlanir.
Pay kucukse (<~%15) K-57d dusuk-oncelik/NO-GO; buyukse tasarima gecilir.

Uretim rotasi parametreleri birebir (eval_gate zinciri):
  heightmap : suggest_pitch + suggest_coarse_pitch; to_voxel_parts n4,
              margin = clearance_to_voxels(2.0, pitch) + K-54 cap
  NFV       : kalite recetesi PITCH=clearance=2.0 (K-38); fast->n8,
              max->AX24 (_quality_max_decision); _voxelize_nfv margin=1 +
              clearance z-dilation
NOT: NFV fine_settle'in used_pitch/4 RE-voxelize'i ve FFT grid hazirliklari
bu olcumun DISINDA (ayri kalemler; rapor notunda). Kosum:
python -m scripts.detach_run k57d_voxelize_pay_teshis   SAF ASCII.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

LOG = Path(__file__).parent / "k57d_voxelize_pay_teshis.log"
OUT = _ROOT / "results" / "k57d_voxelize_pay.json"
K51E = {"plan1": 356.0, "plan2": 1188.0, "plan3": 1640.0, "deneme4": 2095.0}
CLEAR_MM = 2.0


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    from scripts.eval_gate import NOGO_STD, _load_instance
    from src.nesting3d.adaptive_params import predict_nfv_benefit
    from src.nesting3d.selection.mode_model_io import (
        MODE_MODEL_PATH, load_mode_model)
    from src.nesting3d.coarse_to_fine import (
        cap_margin_to_plate, clearance_to_voxels, suggest_coarse_pitch)
    from src.nesting3d.instances.format import to_voxel_parts
    from src.nesting3d.instances.pitch import suggest_pitch
    from src.nesting3d import nfv_solve as nfv

    log("K-57d ON-TESHIS: voxelize payi (uretim rotasi parametreleriyle)")
    _mm = load_mode_model(_ROOT / MODE_MODEL_PATH)
    rapor = {}
    for ad in ("plan1", "plan2", "plan3", "deneme4"):
        log(f"--- {ad} ---")
        inst = _load_instance(ad)
        pw = float(inst.container.width_mm)
        pd = float(inst.container.depth_mm)
        dec = predict_nfv_benefit(inst, family_routing=True, mode_model=_mm,
                                  rot_sokum=True, no_go_bounds=NOGO_STD)
        mode = getattr(dec, "mode", "heightmap")
        kayit = {"mode": mode, "k51e_s": K51E[ad]}
        if mode == "nfv":
            quality = getattr(dec, "nfv_quality", "fast")
            pitch = CLEAR_MM  # K-38 kalite recetesi: pitch = clearance
            allowed = None
            if quality == "max":
                caps = nfv.probe_capabilities()
                allowed, detail = nfv._quality_max_decision(caps.ram_bytes)
                n_or = (len(allowed) if allowed is not None
                        else nfv.NFV_DEFAULT_ORIENTATIONS)
                log(f"  NFV quality=max ({detail}) n={n_or}")
            else:
                n_or = nfv.NFV_DEFAULT_ORIENTATIONS
                log(f"  NFV quality=fast n={n_or}")
            t = time.perf_counter()
            parts, used_pitch = nfv._voxelize_nfv(
                inst, pitch, pitch, n_or, 1,
                allowed_orientations=allowed, clearance_mm=CLEAR_MM)
            dt = time.perf_counter() - t
            kayit.update({"quality": quality, "pitch": used_pitch,
                          "n_or": n_or, "voxelize_s": round(dt, 1),
                          "n_parts": len(parts)})
            log(f"  voxelize @p{used_pitch} n{n_or}: {dt:.1f}s"
                f"  ({len(parts)} parca)")
        else:
            wall = bool(getattr(dec, "wall_aware", False))
            fine = suggest_pitch(inst, wall_aware=wall)
            coarse = suggest_coarse_pitch(inst, fine)
            sureler = {}
            for etiket, p in (("coarse", coarse), ("fine", fine)):
                m, _zc = clearance_to_voxels(CLEAR_MM, p)
                m, _ = cap_margin_to_plate(m, p, inst, pw, pd)
                t = time.perf_counter()
                parts = to_voxel_parts(inst, p, n_orientations=4, margin=m)
                sureler[etiket] = round(time.perf_counter() - t, 1)
                log(f"  {etiket} voxelize @p{p:.3f} m{m}: "
                    f"{sureler[etiket]}s ({len(parts)} parca)")
            dt = sum(sureler.values())
            kayit.update({"pitch_fine": fine, "pitch_coarse": coarse,
                          "voxelize_s": round(dt, 1), "detay": sureler})
        pay = kayit["voxelize_s"] / K51E[ad] * 100.0
        kayit["pay_pct"] = round(pay, 1)
        log(f"  PAY: {kayit['voxelize_s']}s / {K51E[ad]:.0f}s = %{pay:.1f}")
        rapor[ad] = kayit

    toplam_vox = sum(r["voxelize_s"] for r in rapor.values())
    toplam_k51e = sum(K51E.values())
    log(f"TOPLAM: voxelize {toplam_vox:.0f}s / kapi {toplam_k51e:.0f}s"
        f" = %{toplam_vox / toplam_k51e * 100:.1f}")
    log("NOT: NFV fine_settle pitch/4 re-voxelize + FFT grid hazirligi ve"
        " r11/rot denetim sureleri BU OLCUMUN DISINDA (ayri kalemler).")
    OUT.write_text(json.dumps(rapor, indent=2), encoding="utf-8")
    log(f"JSON: {OUT}")
    log("BITTI")


if __name__ == "__main__":
    main()
