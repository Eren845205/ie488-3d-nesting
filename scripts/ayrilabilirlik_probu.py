# -*- coding: utf-8 -*-
"""ayrilabilirlik_probu.py — AYRILABILIRLIK GERCEKCILIK PROBU (Adim-3).

Soru (kullanici 2026-07-07): kilit metrigimiz (+Z duz cekme) hocanin gercek
kriterinden ('ayrilabilirlik' — ic-ice IZINLI) SERT mi? NFV kazanclarini bu
yuzden mi cope atiyoruz?

Olcum: K-21 deneme4 NFV yerlesimi (562.5mm/0.5 pitch, +Z'de 554/588 KILIT) al;
sokulebilirligi 5 DUZ-CIZGI yonuyle yeniden denetle: +Z, +X, -X, +Y, -Y
(sirali sokum: her turda HERHANGI bir yonden cikabilen parca cikar).
NOT: dondurerek cikarma (rotasyon-out) v1'de MODELLENMIYOR — bu prob alt-sinir
verir: '5-yonlu sokumde bile kilit kalan' parcalar rotasyonsuz gercek kilit.

RAM icin ax24_kuyruk_335 BITTI olana kadar bekler.
Kosum: python -m scripts.ayrilabilirlik_probu   SAF ASCII.
"""
from __future__ import annotations
import pickle, sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from src.nesting3d.accessibility import (PlacedVoxels, _column_profiles,
                                         _blocks)
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from scripts.c3_generality import DATASETS

LOG = Path(__file__).parent / "ayrilabilirlik_probu.log"
PKL = _ROOT / "data" / "mail_stl" / "k21_placements_p1_n8.pkl"
BEKLE = Path(__file__).parent / "ax24_kuyruk_335.log"
YONLER = ("+Z", "+X", "-X", "+Y", "-Y")


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def _pv(part_id, grid, x, y, z):
    filled, cmin, cmax = _column_profiles(np.asarray(grid, dtype=bool))
    return PlacedVoxels(str(part_id), int(x), int(y), int(z),
                        filled, cmin.astype(np.int32), cmax.astype(np.int32))


def _yonlu(part_id, grid, x, y, z, yon):
    """Grid+pozisyonu 'yon' cekmesi +Z olacak sekilde donustur."""
    g = np.asarray(grid, dtype=bool)
    gx, gy, _gz = g.shape
    if yon == "+Z":
        return _pv(part_id, g, x, y, z)
    if yon == "+X":
        return _pv(part_id, g.transpose(1, 2, 0), y, z, x)
    if yon == "-X":
        return _pv(part_id, np.flip(g, 0).transpose(1, 2, 0), y, z, -(x + gx))
    if yon == "+Y":
        return _pv(part_id, g.transpose(0, 2, 1), x, z, y)
    if yon == "-Y":
        return _pv(part_id, np.flip(g, 1).transpose(0, 2, 1), x, z, -(y + gy))
    raise ValueError(yon)


def _sirali_sokum(sahneler):
    """sahneler: {yon: [PlacedVoxels...]} (ayni parca sirasi!). Her turda
    HERHANGI bir yonde 0 canli-engeli olan parcalar cikar. Doner:
    (cikan_sira [(pid, yon)], kalan_idx)."""
    n = len(sahneler["+Z"])
    blocks = {}   # (yon, j) -> j'nin o yonde engelledigi i listesi
    sayac = {yon: [0] * n for yon in YONLER}
    for yon in YONLER:
        parts = sahneler[yon]
        for i in range(n):
            for j in range(n):
                if j != i and _blocks(parts[j], parts[i]):
                    blocks.setdefault((yon, j), []).append(i)
                    sayac[yon][i] += 1
    alive = set(range(n))
    cikan = []
    while alive:
        freed = []
        for i in alive:
            for yon in YONLER:
                if sayac[yon][i] == 0:
                    freed.append((i, yon))
                    break
        if not freed:
            break
        for i, yon in freed:
            cikan.append((sahneler["+Z"][i].part_id, yon))
            alive.discard(i)
        for i, _ in freed:
            for yon in YONLER:
                for k in blocks.get((yon, i), []):
                    if k in alive:
                        sayac[yon][k] -= 1
    return cikan, sorted(alive)


def main():
    LOG.write_text("", encoding="utf-8")
    log("AYRILABILIRLIK PROBU — K-21 deneme4 NFV (262.5mm @0.5, +Z'de 554/588 kilit)")
    def _kuyruk_bitti():
        # "on-kosullar BITTI" ara satiri yaniltmasin: kuyrugun SON satiri
        # tam olarak "BITTI" olmali (2026-07-08 yanlis-tetiklenme dersi).
        if not BEKLE.exists():
            return False
        satirlar = [s.strip() for s in
                    BEKLE.read_text(encoding="utf-8", errors="ignore").splitlines()
                    if s.strip()]
        return bool(satirlar) and satirlar[-1] == "BITTI"

    tur = 0
    while not _kuyruk_bitti():
        if tur % 10 == 0:
            log(f"ax24 kuyrugu bekleniyor ({time.strftime('%H:%M')})")
        tur += 1
        time.sleep(300)
    log("kuyruk bitti — prob basliyor")

    # pickle GUVENLI: PKL bizim K-21 scriptimizin bu makinede urettigi artifact
    # (data/mail_stl/k21_placements_p1_n8.pkl) — dis kaynak degil.
    d = pickle.load(PKL.open("rb"))
    pls, pitch = d["placements"], float(d["pitch_mm"])
    log(f"yerlesim: {len(pls)} parca @pitch={pitch}")
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"],
        persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, pitch, n_orientations=8, margin=1)
    by_id = {p.id: p for p in parts}  # VoxelPart alani .id (part_id DEGIL — 9saat dersi)
    log(f"voxelize @{pitch} n8 margin1: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    t = time.perf_counter()
    sahneler = {yon: [] for yon in YONLER}
    for pl in pls:
        vp = by_id[pl.part_id]
        grid = vp.orientations[pl.orientation_idx].grid
        for yon in YONLER:
            sahneler[yon].append(_yonlu(pl.part_id, grid, pl.x, pl.y, pl.z, yon))
    log(f"5-yon sahne kurulumu: {time.perf_counter() - t:.0f}s")

    # SANITY: yalniz +Z ile kac kilit? (K-21 referans ~554 — grid eslesme kaniti)
    # FIX 2026-07-09: eski kurgu bos dummy sahneler kullaniyordu -> dummy'de
    # engel 0 oldugundan HERKES o yonden 'cikti' (kilit=0 artefakti). Dogrusu:
    # 5 sahnenin HEPSI +Z kopyasi = cikis ancak +Z'de mumkunse (+Z-tek semantigi).
    t = time.perf_counter()
    cikan_z, kalan_z = _sirali_sokum({y: sahneler["+Z"] for y in YONLER})
    log(f"SANITY +Z-tek: kilit={len(kalan_z)}/588 (K-21 ref 554) ({(time.perf_counter()-t)/60:.1f} dk)")

    t = time.perf_counter()
    cikan, kalan = _sirali_sokum(sahneler)
    yon_sayim = {}
    for _pid, yon in cikan:
        yon_sayim[yon] = yon_sayim.get(yon, 0) + 1
    log(f"SONUC 5-YON: kilit={len(kalan)}/588  cikan={len(cikan)}"
        f"  yon-dagilimi={yon_sayim}  ({(time.perf_counter() - t) / 60:.1f} dk)")
    if kalan:
        ids = [sahneler['+Z'][i].part_id for i in kalan[:15]]
        log("kalan kilit ornekleri: " + ", ".join(ids))
    log(f"HUKUM-VERISI: +Z-tek kilit {len(kalan_z)} -> 5-yon kilit {len(kalan)}"
        f" (fark = yan-cekmeyle kurtulan)")
    log("BITTI")


if __name__ == "__main__":
    main()
