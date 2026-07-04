# -*- coding: utf-8 -*-
"""k22b_legal_insert.py — K-22b: 9-ASY icin TAM-3D LEGAL-INSERT teshisi (probe).

K-22 dersi: drop kurali ("ustu tamamen acik yer") ceplere geri giremiyor —
ama LEGALLIK bundan zayif bir sart: "bir sokum SIRASI var" (F2 denetimi).
Ustunu orten parcalar once sokulebiliyorsa muhurlu gorunen cep LEGALDIR.

Yontem (F2-v2'nin 9-parcalik mini hali):
  1) K-19 v2 layout'undan kuyruk (9 ASY, tepe>252) cikar; kalan 579'un TAM-3D
     isgal grid'i kurulur (drop/heightmap DEGIL — gercek voxel doluluk).
  2) Her ASY icin (4 poz) fftconvolve ile CAKISMASIZ tum konumlar taranir
     (kademeli z-dilim, alcaktan yukari); en alcak tepe (z_top, z, y, x, oi)
     secilir, isgale islenir (sirali 9 insert).
  3) 588'lik butunde accessibility.check_placements -> kilit sayisi.
Karar: yeni yukseklik < 282 VE kilit=0 -> LEGAL ONARIM PASI bulundu (K-23'e
gerek kalmayabilir); cep yok/kilitli -> geometri doymus, yol K-23 (sira).

NOT (probe varsayimi): yatay temas payi uretimle ayni (margin=0); dikeyde
uretim z_clearance=1 (0.5mm) ister, insert 0'a izin verir — GO cikarsa
baglamada 1 hucre pay eklenir (sonuc en fazla 0.5mm/parca kotulesir).

Kosum: python -m scripts.k22b_legal_insert   (~10-25 dk; rapor-only)
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
from scipy.signal import fftconvolve  # noqa: E402

from src.nesting3d.bin3d import Placement3D  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "k22b_legal_insert.log"
PITCH = 0.5
BAND_MM = 30.0


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _top_mm(g: np.ndarray, z: int) -> float:
    zs = np.flatnonzero(g.any(axis=(0, 1)))
    return (z + int(zs[-1]) + 1) * PITCH


def _lowest_feasible(occ: np.ndarray, grid: np.ndarray):
    """Kademeli z-dilimle en alcak cakismasiz origin (z, y, x) veya None.

    fftconvolve('valid') slab uzerinde: C[x,y,z] ~ 0 => tamamen bos yuva.
    float32 (bellek yari; sayimlar kucuk, 0.5 esigi guvenli).
    """
    fh = grid.shape[2]
    nz = occ.shape[2]
    kern = grid[::-1, ::-1, ::-1].astype(np.float32)
    z_cap = fh + 40
    while True:
        z_lim = min(nz, z_cap)
        C = fftconvolve(occ[:, :, :z_lim].astype(np.float32), kern, mode="valid")
        free = C < 0.5
        z_any = free.any(axis=(0, 1))
        if z_any.any():
            z = int(np.argmax(z_any))
            sl = free[:, :, z]
            y = int(np.argmax(sl.any(axis=0)))
            x = int(np.argmax(sl[:, y]))
            return z, y, x
        if z_lim >= nz:
            return None
        z_cap *= 2


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("K-22b LEGAL-INSERT TESHISI — 9 ASY icin tam-3D cakismasiz cep aramasi")
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
    nx, ny = int(pw // PITCH), int(pd // PITCH)

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)  # K-22: n=4 saglam
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n=4: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    # kuyruk / taban ayrimi (F4-A/K-22 ile ayni tanim)
    tail, base = [], []
    for p in pls:
        g = lookup[p.part_id].orientations[p.orientation_idx].grid
        (tail if _top_mm(g, p.z) > exp_h - BAND_MM else base).append(p)
    log(f"kuyruk={len(tail)} parca ({sorted(set(p.name for p in tail))}), "
        f"taban={len(base)}")

    # 579'un TAM-3D isgal grid'i (bool) — KAPI: toplam voxel tutarliligi
    nz = 0
    for p in pls:
        g = lookup[p.part_id].orientations[p.orientation_idx].grid
        nz = max(nz, p.z + g.shape[2])
    occ = np.zeros((nx, ny, nz), dtype=bool)
    dup = 0
    for p in base:
        g = lookup[p.part_id].orientations[p.orientation_idx].grid
        gx, gy, gz = g.shape
        sub = occ[p.x:p.x + gx, p.y:p.y + gy, p.z:p.z + gz]
        dup += int((sub & g).sum())
        sub |= g
    base_top = int(np.flatnonzero(occ.any(axis=(0, 1)))[-1]) + 1
    log(f"KAPI: taban cifte-dolu={dup} (0 olmali) | taban tepe={base_top * PITCH:.1f}mm")
    if dup:
        log("KAPI GECEMEDI — replay tutarsiz, iptal.")
        sys.exit(1)

    # sirali 9 insert: her seferinde en alcak cakismasiz yuva
    new_state = []
    worst_top = 0.0
    for p in sorted(tail, key=lambda q: q.part_id):
        part = lookup[p.part_id]
        best = None  # (z_top, z, y, x, oi)
        for oi, orient in enumerate(part.orientations):
            g = orient.grid
            if g.shape[0] > nx or g.shape[1] > ny:
                continue
            t0 = time.perf_counter()
            hit = _lowest_feasible(occ, g)
            if hit is None:
                continue
            z, y, x = hit
            cand = (z + g.shape[2], z, y, x, oi)
            if best is None or cand < best:
                best = cand
        if best is None:
            log(f"  {p.part_id}: HICBIR pozda cakismasiz yuva YOK (grid ici)")
            worst_top = float("inf")
            break
        zt, z, y, x, oi = best
        g = part.orientations[oi].grid
        occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]] |= g
        new_state.append(Placement3D(part_id=p.part_id, name=p.name,
                                     x=x, y=y, z=z, orientation_idx=oi))
        old_g = part.orientations[p.orientation_idx].grid
        old_top = _top_mm(old_g, p.z)
        new_top = _top_mm(g, z)
        worst_top = max(worst_top, new_top)
        log(f"  {p.part_id}: tepe {old_top:.1f} -> {new_top:.1f}mm "
            f"(oi {p.orientation_idx}->{oi}, z {p.z}->{z})  "
            f"[{time.perf_counter() - t0:.0f}s]")

    if worst_top == float("inf"):
        log("")
        log("HUKUM: CEP YOK — geometri doymus; yol K-23 (sira deneyi).")
        log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")
        return

    new_h = max(base_top * PITCH, worst_top)
    log("")
    log(f"insert sonrasi yukseklik: {new_h:.1f}mm (K-19 282.0 | taban "
        f"{base_top * PITCH:.1f} | Magics 250.24)")

    # LEGALLIK: 588 butununde sokum-sirasi denetimi
    final_pls = base + new_state
    ta = time.perf_counter()
    rep = check_placements(final_pls, lookup)
    log(f"ERISILEBILIRLIK ({time.perf_counter() - ta:.1f}s): "
        f"kilitli={rep.n_locked}/{rep.n_parts}")
    if rep.locked_groups:
        uye = sorted(rep.locked_groups[0])[:10]
        log(f"  ilk kilit grubu ornek uyeler: {uye}")

    if new_h < exp_h - 1e-9 and rep.n_locked == 0:
        out = _ROOT / "data" / "mail_stl" / "k22b_insert_layout.pkl"
        with out.open("wb") as fh:
            pickle.dump({"placements": final_pls, "pitch_mm": PITCH,
                         "height_mm": new_h}, fh)
        log(f"yerlesim kaydedildi: {out.name}")
        log(f"HUKUM: LEGAL ONARIM PASI BULUNDU — {exp_h:.1f} -> {new_h:.1f}mm "
            f"(-{exp_h - new_h:.1f}mm) ve 0 kilit. K-23'e gerek kalmayabilir.")
    elif new_h < exp_h - 1e-9:
        log(f"HUKUM: cep var ({new_h:.1f}) ama {rep.n_locked} kilit -> ILLEGAL; "
            "yol K-23 veya kilit-farkindali insert.")
    else:
        log("HUKUM: CEP YOK/yetersiz — insert tavani indiremedi; geometri "
            "doymus, yol K-23 (sira deneyi).")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
