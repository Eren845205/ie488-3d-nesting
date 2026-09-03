# -*- coding: utf-8 -*-
"""k22_kuyruk_yerlesim.py — K-22 adayi: KUYRUK-HEDEFLI yeniden-yerlesim (probe).

F4-A bulgusu: K-19 v2 282.0mm layout'unda tavani YALNIZ 9 adet ASY-0176446
kuruyor (son 30mm); 230mm ustu ~bos. HIPOTEZ: o kuyruk parcalari sokulup
herkes yerlesikken yeniden drop edilirse (uretimle AYNI _best_position kurali,
n=8 genis poz seti) tavan legal olarak asagi iner.

Yontem:
  1) k19v2 pickle -> @0.5/n=4-prefix'li grid'lerle TAM replay (KAPI: 282.0
     birebir; f4a kanitina dayanir, n=8 prefix-stable oldugundan idx'ler ayni).
  2) Dongu (strict iyilesme surdukce, max 4 tur): kuyruk = tepesi
     (max - 30mm) ustunde kalan parcalar -> cikar -> kalanlarla bin'i yeniden
     kur -> kuyrugu hacim-azalan sirayla dblf._best_position(range(8)) ile
     yeniden yerlestir.
  3) Legallik: accessibility.check_placements -> kilit sayisi (0 sart).
Karar: yeni yukseklik < 282.0 VE kilit=0 -> K-22 GO sinyali (uretime baglama
ayri is); aksi halde NO-GO. Sonuc -> YONTEM_HARITASI K-22 kunyesi.

Kosum: python -m scripts.k22_kuyruk_yerlesim   (~3-5 dk; rapor-only)
SAF ASCII cikti (cp1254 guvenli). Uretime DOKUNMAZ.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from src.nesting3d.bin3d import Bin3D, Placement3D  # noqa: E402
from src.nesting3d.dblf import _best_position  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "k22_kuyruk.log"
PITCH = 0.5
BAND_MM = 30.0
MAX_ROUNDS = 4


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _top_mm(g: np.ndarray, z: int) -> float:
    zs = np.flatnonzero(g.any(axis=(0, 1)))
    return (z + int(zs[-1]) + 1) * PITCH


def _rebuild(pw: float, pd: float, entries) -> Bin3D:
    """entries: [(part, oi, x, y, z)] — verilen yerlesimi aynen oynat."""
    b = Bin3D(pw, pd, PITCH, z_clearance=1)  # coarse_to_fine fine yolu birebir
    for part, oi, x, y, z in entries:
        b.place(part, oi, x, y, z)
    return b


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("K-22 KUYRUK-HEDEFLI YENIDEN-YERLESIM PROBU — K-19 v2 282.0mm tabani")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]
    exp_h = float(data["height_mm"])

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    pw = float(res.instance.container.width_mm)
    pd = float(res.instance.container.depth_mm)

    t = time.perf_counter()
    # n=8 genis poz denenir; deneme4 kabuklarinda 4..7 pozlardan biri @0.5'te
    # trimesh slice'i dusurebiliyor ("unable to recover polygon", 1. kosu) ->
    # guvenli geri-dusus n=4 (F4-A kaniti; yeniden-yerlesim serbestligi zaten
    # agirlikla SIRA degisiminden gelir, ek pozlar ikincil).
    try:
        parts = to_voxel_parts(res.instance, PITCH, n_orientations=8)
        n_used = 8
    except ValueError as exc:
        log(f"  [uyari] n=8 voxelize dustu ({exc}) -> n=4 geri-dusus")
        parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
        n_used = 4
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n={n_used}: {len(parts)} parca "
        f"({time.perf_counter() - t:.0f}s)")

    # Calisan yerlesim durumu: id -> (part, oi, x, y, z)
    state = {}
    for p in pls:
        state[p.part_id] = (lookup[p.part_id], p.orientation_idx, p.x, p.y, p.z)

    # --- KAPI: tam replay 282.0 birebir mi? (idx 0-3, n=8 prefix'inde ayni) ---
    b = _rebuild(pw, pd, state.values())
    got = b.max_height_mm()
    log(f"KAPI: tam replay = {got:.1f}mm (beklenen {exp_h})")
    if abs(got - exp_h) > 1e-6:
        log("KAPI GECEMEDI — analiz iptal.")
        sys.exit(1)

    cur_h = got
    for rnd in range(1, MAX_ROUNDS + 1):
        cut = cur_h - BAND_MM
        tail_ids = [pid for pid, (part, oi, x, y, z) in state.items()
                    if _top_mm(part.orientations[oi].grid, z) > cut]
        log("")
        log(f"TUR {rnd}: yukseklik {cur_h:.1f} | kuyruk (tepe > {cut:.1f}mm) = "
            f"{len(tail_ids)} parca: {sorted(tail_ids)[:12]}")
        if not tail_ids or len(tail_ids) > 60:
            log("  kuyruk bos veya cok genis (mekanizma disi) -> dur.")
            break

        others = [v for pid, v in state.items() if pid not in set(tail_ids)]
        b = _rebuild(pw, pd, others)
        log(f"  taban ({len(others)} parca) yuksekligi: {b.max_height_mm():.1f}mm")

        # hacim-azalan sirayla yeniden yerlestir (DBLF kurali, n=8 tum pozlar)
        tail_parts = sorted((lookup[pid] for pid in tail_ids),
                            key=lambda vp: -vp.volume_voxels)
        for part in tail_parts:
            old_oi, old_z = state[part.id][1], state[part.id][4]
            old_top = _top_mm(part.orientations[old_oi].grid, old_z)
            best = _best_position(b, part, range(len(part.orientations)))
            assert best is not None, f"{part.id} sigmadi (beklenmez)"
            _, z, y, x, oi = best
            b.place(part, oi, x, y, z)
            state[part.id] = (part, oi, x, y, z)
            new_top = _top_mm(part.orientations[oi].grid, z)
            log(f"  {part.id}: tepe {old_top:.1f} -> {new_top:.1f}mm "
                f"(oi {old_oi}->{oi})")

        new_h = b.max_height_mm()
        log(f"  TUR {rnd} sonucu: {cur_h:.1f} -> {new_h:.1f}mm")
        if new_h >= cur_h - 1e-9:
            log("  strict iyilesme yok -> dur.")
            # iyilesme yoksa onceki state'i korumaya gerek yok: yeniden-drop
            # ayni/daha yuksek tepeyi verdiyse yukseklik zaten degismedi.
            cur_h = min(cur_h, new_h)
            break
        cur_h = new_h

    # --- Legallik denetimi (tum 588, guncel state) -----------------------------
    final_pls = [Placement3D(part_id=pid, name=part.name, x=x, y=y, z=z,
                             orientation_idx=oi)
                 for pid, (part, oi, x, y, z) in state.items()]
    ta = time.perf_counter()
    rep = check_placements(final_pls, lookup)
    log("")
    log(f"ERISILEBILIRLIK ({time.perf_counter() - ta:.1f}s): "
        f"kilitli={rep.n_locked}/{rep.n_parts}")

    if cur_h < exp_h - 1e-9 and rep.n_locked == 0:
        out = _ROOT / "data" / "mail_stl" / "k22_kuyruk_layout.pkl"
        with out.open("wb") as fh:
            pickle.dump({"placements": final_pls, "pitch_mm": PITCH,
                         "height_mm": cur_h}, fh)
        log(f"yerlesim kaydedildi: {out.name}")
        log(f"HUKUM: K-22 GO SINYALI — {exp_h:.1f} -> {cur_h:.1f}mm "
            f"(-{exp_h - cur_h:.1f}mm, %{100 * (exp_h - cur_h) / exp_h:.1f}) ve 0 kilit.")
    elif cur_h < exp_h - 1e-9:
        log(f"HUKUM: iyilesme VAR ({cur_h:.1f}) ama {rep.n_locked} kilit -> ILLEGAL, NO-GO.")
    else:
        log("HUKUM: NO-GO — kuyruk yeniden-yerlesimi tavani indirmedi "
            "(9 ASY zaten en iyi yerinde; tavan yapisal).")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
