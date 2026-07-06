# -*- coding: utf-8 -*-
"""nfv_legal_teshis.py — EVAL-1 kok-neden teshisi: NFV plan1 clearance 0.083 + 81 kilit NEDEN?

Sorular (olc-once; fix'ten ONCE mekanizma):
  S1: 0.083mm nereden? margin=1 @pitch~1.0 -> ~1mm beklenirdi. Bas suphed:
      fine_settle (K-17 post-pass, used_pitch/4'te yeniden oturtma) margin'i
      yeniden uygulamadan parcalari birbirine YANASTIRIYOR olabilir.
      Test: fine_settle=True vs False, ayni seed — clearance farki mekanizmayi soyler.
  S2: 81 kilit clearance'in SONUCU mu? margin=2 (kaba ~2mm bosluk) probu:
      bosluk acilinca kilit sayisi duserse kilit = sikisik-temas artefakti
      (F2-v2 buyuk isine gerek kalmayabilir; clearance kablosu yeter).
  S3: kilit ANATOMISI: hangi tipler kilitli, kac grup, en buyuk grup?
      + clearance worst-pair hangi iki parca?

Kosum: python -m scripts.nfv_legal_teshis   (~5-8 dk; plan1 x3 solve)
URETIME DOKUNMAZ. SAF ASCII stdout.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.nfv_solve import solve_nfv  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from scripts.eval_gate import _load_instance  # noqa: E402

LOG = Path(__file__).parent / "nfv_legal_teshis.log"
SEED = 42
SET = "plan1"

CONFIGS = [
    ("settleON_m1", dict(margin=1, fine_settle=True)),   # EVAL-1 repro
    ("settleOFF_m1", dict(margin=1, fine_settle=False)),  # S1: settle mekanizmasi
    ("settleON_m2", dict(margin=2, fine_settle=True)),   # S2: bosluk->kilit iliskisi
]


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    t_all = time.perf_counter()
    log("=" * 78)
    log(f"NFV LEGAL TESHISI — {SET} (EVAL-1 kok-neden)  seed={SEED}")
    log("=" * 78)
    inst = _load_instance(SET)
    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plaka {pw:.1f}x{pd:.1f}  toplam parca {n_total}")

    for ad, kw in CONFIGS:
        t = time.perf_counter()
        log("")
        log("-" * 78)
        log(f"KONFIG {ad}: {kw}")
        r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, seed=SEED,
                      quality="fast", **kw)
        pitch = float(r.fine_pitch)
        n_placed = int(getattr(r, "n_placed", len(r.placements)))
        meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch)
        rep = min_clearance(meshes)
        acc = check_placements(r.placements, r.fine_voxel_parts)
        log(f"  yukseklik={float(r.height_mm):.1f}mm  yerlesen={n_placed}/{n_total}  "
            f"pitch={pitch:.3f}  ({time.perf_counter() - t:.0f}s)")
        log(f"  min_clearance={rep.min_mm:.3f}mm  (cift sayisi={rep.n_pairs_checked})")
        if rep.worst_pair is not None:
            i, j = rep.worst_pair
            log(f"    worst-pair: [{r.placements[i].name[:34]}] <-> "
                f"[{r.placements[j].name[:34]}]")
        log(f"  kilit={acc.n_locked}/{acc.n_parts}  grup sayisi={len(acc.locked_groups)}")
        if acc.locked_groups:
            grup_boy = sorted((len(g) for g in acc.locked_groups), reverse=True)
            log(f"    grup boylari: {grup_boy[:10]}{'...' if len(grup_boy) > 10 else ''}")
            adlar = Counter()
            ad_by_id = {p.part_id: p.name for p in r.placements}
            for g in acc.locked_groups:
                for pid in g:
                    adlar[ad_by_id.get(pid, str(pid))[:34]] += 1
            log("    kilitli tipler:")
            for t_ad, c in adlar.most_common(8):
                log(f"      x{c:>3}  {t_ad}")

    log("")
    log("YORUM ANAHTARI:")
    log("  settleOFF m1 clearance >> settleON m1  -> S1 DOGRU: fine_settle bosluk yiyor")
    log("  settleOFF m1 clearance ~0.08 de        -> margin kablosu NFV'de kirik (baska yer)")
    log("  m2 kilit << m1 kilit                   -> S2 DOGRU: kilit sikisik-temas artefakti;")
    log("                                            clearance fix'i kilitleri de cozebilir")
    log("  m2 kilit ~ m1 kilit                    -> kilit geometrik/decode kaynakli -> F2-v2 sart")
    log(f"TOPLAM {(time.perf_counter() - t_all) / 60:.1f} dk")


if __name__ == "__main__":
    main()
