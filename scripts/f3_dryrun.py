# -*- coding: utf-8 -*-
"""f3_dryrun.py — K-19 cidar-duyarli pitch KURU-KOSU (classify + pitch tablosu).

OPT-IN, HIZLI (solve YOK): 6 gercek-veri setini yukler, her biri icin
family/guven + onerilen pitch (normal vs cidar-duyarli) tablosu basar. Amac:
uretime baglama (F3) oncesi KAPI dogrulamasi — hangi setler cidar dalini
TETIKLER (kabuk ailesi + guven>=esik), hangileri TETIKLEMEZ, gorulebilsin.

    python scripts/f3_dryrun.py

Cikti SAF ASCII (Windows cp1254 stdout guvenli). Solve/nesting yapilmaz;
yalniz build_instance_from_order (wall_mm=2V/A doldurur) + classify + pitch.
Adet (qty) bilinmiyorsa her parca qty=1 alinir (family oylamasi icin yeterli
yaklasim; pitch qty'den bagimsiz — min ozellik uzerinden turer).

NOT: STL yukleme trimesh ile yapilir (watertight olcum) -> set basina birkac
saniye. run_pipeline / solve CAGRILMAZ (131 dk'lik olcum bu script'te YOK).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.instances.family import classify_prelim  # noqa: E402
from src.nesting3d.instances.pitch import (  # noqa: E402
    WALL_AWARE_CONF_THRESHOLD,
    min_feature_mm,
    suggest_nfv_pitch,
    suggest_pitch,
    wall_feature_mm,
)
from src.nesting3d.instances.stl_order_loader import (  # noqa: E402
    build_instance_from_order,
)

# Set adi -> STL klasoru. gen_* klasorleri her setin STL'lerini tutar.
_MAIL = _ROOT / "data" / "mail_stl"
DATASETS = {
    "plan1": _MAIL / "gen_plan1",
    "plan2": _MAIL / "gen_plan2",
    "plan3": _MAIL / "gen_plan3",
    "numune": _MAIL / "feat_numune",
    "boxy": _MAIL / "gen_boxy",
    "deneme4": _MAIL / "gen_deneme4",
}

# Kuru-kosu icin nominal plaka (NFV plaka-orani/H-11 kosulu icin). Gercek plaka
# siparisten turer; burada sabit nominal yeter (yalniz tetik gozlemi).
_PLATE_W = 335.0
_PLATE_D = 250.0
_RAM = 6 * 1024 ** 3  # bu makine ~6GB; H-11 plaka-boyut kosulunu gercekci tutar


def _load_instance(stl_dir: Path):
    """Klasordeki STL'leri qty=1 ile NestingInstance'a yukle (wall_mm doldurulur)."""
    stl_map = {}
    quantities = {}
    for stl in sorted(stl_dir.glob("*.stl")):
        stl_map[stl.stem] = stl.read_bytes()
        quantities[stl.stem] = 1
    if not stl_map:
        return None
    return build_instance_from_order(stl_map=stl_map, quantities=quantities).instance


def _row(name: str, inst) -> str:
    fam, conf = classify_prelim(inst)
    bbox_mf = min_feature_mm(inst)
    wall_mf = wall_feature_mm(inst)
    p_norm = suggest_pitch(inst)
    p_wall = suggest_pitch(inst, wall_aware=True)
    nfv_norm, _, _ = suggest_nfv_pitch(
        inst, plate_w_mm=_PLATE_W, plate_d_mm=_PLATE_D, ram_bytes=_RAM)
    nfv_wall, _, nfv_reason = suggest_nfv_pitch(
        inst, plate_w_mm=_PLATE_W, plate_d_mm=_PLATE_D, ram_bytes=_RAM,
        wall_aware=True)
    triggers = fam in ("thin_shell", "tube") and conf >= WALL_AWARE_CONF_THRESHOLD
    n_wall = sum(1 for p in inst.parts if p.wall_mm is not None)
    return (
        "%-9s %-11s %5.2f  n=%-3d wall=%-3d  bbox=%7.2f wall=%6.2f  "
        "hm[%6.3f->%6.3f]  nfv[%6.3f->%6.3f]  %s"
        % (name, fam, conf, len(inst.parts), n_wall, bbox_mf, wall_mf,
           p_norm, p_wall, nfv_norm, nfv_wall,
           "TETIKLER" if triggers else "-")
    )


def main() -> int:
    print("K-19 F3 KURU-KOSU -- cidar-duyarli pitch tetik tablosu")
    print("esik (WALL_AWARE_CONF_THRESHOLD) = %.2f" % WALL_AWARE_CONF_THRESHOLD)
    print("plaka nominal = %.0f x %.0f  RAM = %.0fGB" % (_PLATE_W, _PLATE_D, _RAM / 1e9))
    print("-" * 118)
    print("%-9s %-11s %5s  %-11s %-22s  %-22s  %-22s  %s"
          % ("set", "family", "conf", "n/wall", "min_feature(mm)",
             "heightmap pitch", "nfv pitch", "tetik"))
    print("-" * 118)
    for name, stl_dir in DATASETS.items():
        if not stl_dir.exists():
            print("%-9s (klasor yok: %s)" % (name, stl_dir))
            continue
        try:
            inst = _load_instance(stl_dir)
            if inst is None or not inst.parts:
                print("%-9s (STL bulunamadi)" % name)
                continue
            print(_row(name, inst))
        except Exception as exc:  # noqa: BLE001
            print("%-9s HATA: %s: %s" % (name, type(exc).__name__, exc))
    print("-" * 118)
    print("Beklenen: deneme4 TETIKLER (kabuk, guven>=esik); plan2/plan3/boxy/plan1 -.")
    print("hm[normal->cidar], nfv[normal->cidar]: cidar dali ince pitch verir mi?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
