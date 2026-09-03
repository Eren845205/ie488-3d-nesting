# -*- coding: utf-8 -*-
"""h15b_coarse_profil.py — H-15 DUZELTME PROBU: 104.5 dk'nin GERCEK atifi.

Reviewer H1 bulgusu: demo_pipeline C2F cagrisinda adaptive/fine_angle_window
GECMIYOR -> uretim yolunda ince-aci rafinesi ZATEN kosmuyorm; h15_on_analiz'in
"%92 rafine" atfi CIKARIMDI ve yanlis. Kalan tek buyuk supheli: COARSE asamasi
= tune(coarse_parts, budget=25, TAM MENU) @ suggest_coarse_pitch.

Bu prob OLCER (kosu yok, ekstrapolasyon + tek-gecis zamanlamasi):
  [1] suggest_coarse_pitch(deneme4, fine=0.5) -> gercek coarse pitch
  [2] coarse voxelize suresi (n=4)
  [3] menu konfig sayisi (build_menu) + budget semantigi
  [4] TEK dblf gecisinin suresi @coarse -> tune maliyeti ~ konfig x gecis
      (tuner iterasyonu basina ~1 yerlesim varsayimi — kod dogrulamasi loga)
  [5] fine taban gecis tahmini (h15_on_analiz: ~479s) ile toplam sentez;
      zincir-testi 6270s ile kiyas.

Kosum: python -m scripts.h15b_coarse_profil   (~3-6 dk)  SAF ASCII.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.nesting3d.dblf import dblf  # noqa: E402
from src.nesting3d.coarse_to_fine import suggest_coarse_pitch  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

LOG = Path(__file__).parent / "h15b_coarse_profil.log"
FINE = 0.5
GERCEK_TOPLAM_S = 6270.0
FINE_TABAN_TAHMIN_S = 479.0  # h15_on_analiz olcumu


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("H-15b — coarse asamasi maliyet atifi (deneme4, fine=0.5)")
    log("=" * 78)

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    inst = res.instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)

    cp = suggest_coarse_pitch(inst, FINE)
    log(f"[1] suggest_coarse_pitch = {cp} mm (fine {FINE} x3 hedef, "
        f"min_feature bbox-tabanli tavan)")

    t = time.perf_counter()
    coarse_parts = to_voxel_parts(inst, cp, n_orientations=4)
    t_vox = time.perf_counter() - t
    log(f"[2] coarse voxelize @{cp}: {len(coarse_parts)} parca, {t_vox:.0f}s")

    # [3] menu buyuklugu
    from src.nesting3d.tuner import build_menu
    menu = build_menu()
    log(f"[3] tune menusu: {len(menu)} konfig | demo_pipeline COARSE_BUDGET=25")
    for name in list(menu)[:12]:
        log(f"      - {name}")

    # [4] tek dblf gecisi @coarse
    t = time.perf_counter()
    _, b = dblf(coarse_parts, lambda: Bin3D(pw, pd, cp, z_clearance=1))
    t_pass = time.perf_counter() - t
    log(f"[4] TEK dblf gecisi @coarse: {t_pass:.1f}s (yukseklik "
        f"{b.max_height_mm():.1f}mm)")

    # [5] sentez
    n_cfg = len(menu)
    est_tune_1x = n_cfg * t_pass          # konfig basina 1 gecis (alt sinir)
    est_tune_bud = n_cfg * 25 * t_pass    # konfig basina 25 gecis (ust sinir)
    log("")
    log("[5] SENTEZ (zincir testi toplami 6270s):")
    log(f"    coarse voxelize        ~{t_vox:6.0f}s")
    log(f"    tune ALT sinir (1x)    ~{est_tune_1x:6.0f}s = {n_cfg} konfig x {t_pass:.0f}s")
    log(f"    tune UST sinir (25x)   ~{est_tune_bud:6.0f}s")
    log(f"    fine voxelize (~n=4)   ~   90s (h15 olcumu 28-94s)")
    log(f"    fine taban gecisi      ~{FINE_TABAN_TAHMIN_S:6.0f}s (h15 olcumu)")
    for label, est in (("1x", est_tune_1x), ("25x", est_tune_bud)):
        top = t_vox + est + 90 + FINE_TABAN_TAHMIN_S
        log(f"    TOPLAM ({label} varsayimi) ~{top:6.0f}s (oran "
            f"{top / GERCEK_TOPLAM_S:.2f})")
    log("")
    log("NOT: tuner iterasyon semantigi (budget=25'in kac tam gecise denk"
        " geldigi) instance_tuner kodundan ayrica dogrulanmali — bu prob"
        " alt/ust sinir bracket verir.")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
