# -*- coding: utf-8 -*-
"""plan2_nfv_nogo.py — PLAN2 NFV @335+NOGO probu (2026-07-09: 'plan2'de cok
fark var' — kule teshisi plato gosterdi, tek-parca tilt cozumu yok; ic-ice
potansiyeli olculuyor. plan3'te ayni prob -%18.5 vermisti).

NFV quality=max + no-go + 1 saat butce (plan2 @0.5 pitch RAM/sure belirsiz —
butce asilirsa kismi sonuc isaretlenir). Ardindan legal metrik + 5-yon sokum.
Kiyas: zincir n24 = 646 / Magics 492.39.

Makine bos -> beklemesiz. Kosum: python -m scripts.detach_run plan2_nfv_nogo
SAF ASCII. NOT: _bes_yon LOKAL kopya (log-paylasimi zehirlenmesi dersi —
baska modulun log'una YAZILMAZ).
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import trimesh
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import legal_of
from scripts.demo_pipeline import WEB_MIN_CLEARANCE_MM
from scripts.ax24_kuyruk_335 import _load          # plan2 yukleyici (log'suz)
from scripts.ayrilabilirlik_probu import _sirali_sokum, _yonlu, YONLER

LOG = Path(__file__).parent / "plan2_nfv_nogo.log"
PLATE = (335.0, 335.0)
NOGO = ((152.5, 0.2), (185.5, 45.0))


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _bes_yon(r, etiket):
    t = time.perf_counter()
    sahneler = {yon: [] for yon in YONLER}
    for pl in r.placements:
        grid = r.fine_voxel_parts[pl.part_id].orientations[pl.orientation_idx].grid
        for yon in YONLER:
            sahneler[yon].append(_yonlu(pl.part_id, grid, pl.x, pl.y, pl.z, yon))
    cikan, kalan = _sirali_sokum(sahneler)
    yon_sayim = {}
    for _pid, yon in cikan:
        yon_sayim[yon] = yon_sayim.get(yon, 0) + 1
    log(f"[{etiket}] 5-YON sokum: kilit={len(kalan)}/{len(r.placements)}"
        f"  yon-dagilimi={yon_sayim}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    return len(kalan)


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN2 NFV @335+NOGO — ic-ice potansiyel probu (zincir 646 / Magics 492.39)")
    inst = _load("plan2", PLATE)
    n_total = sum(int(p.qty) for p in inst.parts)
    t = time.perf_counter()
    # Ilk deneme MemoryError verdi (FFT 1.76GB @0.5 pitch — H-11 duvari).
    # Kademeli dusus: max -> fast(seri, n8). Ikisi de olmazsa NO-GO kaydi +
    # BITTI (zincir kilitlenmesin — plan2_sq bekliyor).
    r = None
    for etiket, kw in (("max", dict(quality="max")),
                       ("fast_serial", dict(quality="fast", force="serial"))):
        try:
            r = solve_nfv(
                inst, plate_w_mm=PLATE[0], plate_d_mm=PLATE[1],
                seed=42, clearance_mm=WEB_MIN_CLEARANCE_MM,
                no_go_bounds=NOGO, time_budget_sec=3600, **kw)
            log(f"[nfv_nogo] strateji={etiket} BASARILI")
            break
        except MemoryError as e:
            log(f"[nfv_nogo] {etiket}: MemoryError — {e}")
        except Exception as e:
            log(f"[nfv_nogo] {etiket}: {type(e).__name__} — {e}")
    if r is None:
        log("HUKUM-VERISI: plan2 NFV @0.5 BELLEK DUVARI (H-11 tekrari) — "
            "KESIN NO-GO bu makinede; YONTEM_HARITASI'na islenecek")
        log("BITTI")
        return
    log(f"[nfv_nogo] sure={(time.perf_counter() - t) / 60:.1f} dk"
        f"  strateji={getattr(r, 'strategy', '?')}")
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"[nfv_nogo] h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit_+Z={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}")
    kilit5 = _bes_yon(r, "nfv_nogo")
    h = float(r.height_mm)
    log(f"HUKUM-VERISI: plan2 NFV+nogo={h:.1f} (zincir 646; Magics 492.39 ->"
        f" +%{(h / 492.39 - 1) * 100:.1f})  kilit +Z={acc.n_locked} / 5-yon={kilit5}")
    out = _ROOT / "results" / f"plan2_nfv_nogo335_{h:.1f}mm.stl"
    trimesh.util.concatenate(meshes).export(out)
    log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
