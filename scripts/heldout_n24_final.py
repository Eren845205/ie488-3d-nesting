# -*- coding: utf-8 -*-
"""heldout_n24_final.py — n24 KABLOLAMA KARARININ HELD-OUT FINAL DOGRULAMASI
(kullanici karari 2026-07-09: 'overfit riski var, genellemeyi TEST ETMELIYIZ').

ANAYASA uyumu:
  A3 — held-out bakisi registry'ye tarihle loglanir (_log_heldout_bakis);
       bu bir FINAL dogrulamadir (n24 karari dev-setlerde 4/4 teyitli, tuning
       degil). Iki kol (n8/n24) TEK kararin A/B'sidir.
  A5 — dagilim: dev 4/4 + held-out bu kosu; sonuc ne olursa rapora girer.
  A7 — sonuc YONTEM_HARITASI'na islenecek (GO da NO-GO da).

Kosul: boxy'nin KENDI kayitli konfigurasyonu (uretim zinciri, auto-plaka,
clearance 1.0) — n_orientations disinda hicbir sey degistirilmez.

RAM zinciri: plan2_sq.log son satiri BITTI olana kadar bekler.
Kosum: python -m scripts.detach_run heldout_n24_final   SAF ASCII.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import (_load_instance, _run_champion,
                               _log_heldout_bakis, legal_of)

LOG = Path(__file__).parent / "heldout_n24_final.log"
BEKLE = Path(__file__).parent / "plan2_sq.log"


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _olc(r, n_total, etiket):
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"[{etiket}] h={float(r.height_mm):.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}"
        f"  yerlesen={r.n_placed}/{n_total}")
    return legal


def main():
    LOG.write_text("", encoding="utf-8")
    log("HELD-OUT FINAL: boxy n8 vs n24 (n24 kablolama karari; ANAYASA A3 kayitli)")
    tur = 0
    while True:
        satirlar = ([s.strip() for s in
                     BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                     if s.strip()] if BEKLE.exists() else [])
        if satirlar and satirlar[-1] == "BITTI":
            break
        if tur % 10 == 0:
            log(f"plan2 sikistirma bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("zincir hazir — held-out final basliyor")

    _log_heldout_bakis(["boxy"], "n24 kablolama FINAL A/B dogrulamasi "
                       "(dev 4/4 teyit sonrasi; kullanici karari 2026-07-09)")
    inst = _load_instance("boxy")
    n_total = sum(int(p.qty) for p in inst.parts)
    sonuc = {}
    for n in (8, 24):
        t = time.perf_counter()
        r = _run_champion("boxy", inst, seed=42, n_orientations=n)
        log(f"[boxy_n{n}] sure={(time.perf_counter() - t) / 60:.1f} dk")
        sonuc[n] = _olc(r, n_total, f"boxy_n{n}")

    if sonuc.get(8) is not None and sonuc.get(24) is not None:
        d = sonuc[24] - sonuc[8]
        pct = (sonuc[24] / sonuc[8] - 1) * 100
        hukum = ("n24 HELD-OUT'TA DA KAZANIYOR -> kablolama TEYIT" if d < 0 else
                 ("NOTR (kuantizasyon bandi)" if abs(pct) < 1.0 else
                  "n24 held-out'ta KAYBEDIYOR -> kablolama DUR, teshis gerek"))
        log(f"HUKUM: n8={sonuc[8]:.1f} -> n24={sonuc[24]:.1f}"
            f" ({d:+.1f}mm, %{pct:+.1f})  {hukum}")
    else:
        log("HUKUM: en az bir kol INVALID — karar verilemez, teshis gerek")
    log("BITTI")


if __name__ == "__main__":
    main()
