# -*- coding: utf-8 -*-
"""f2v2_prototip.py — F2-v2 prototip: NFV decode + yerlestirme-anI +Z-sokulebilirlik kIsItI.

AMAC (BAGLAM: YONTEM_HARITASI [EVAL-1]/[K-21]/[K-22b], SS5 F2-v2):
  NFV kalite modu PLAN ailesinde de A2-ILLEGAL (plan1 81 / plan3 87 kilit, clearance <1mm).
  Unlu ~%20-28 NFV kazanci = kapali-kaviteye gomme (sokulemez yigin). F2-v2: decode aninda
  "gok koridoru" kIsItI -> her parca YERLESTIGI anda +Z'ye cekilebilir olsun.

KISIT (gok koridoru, ileri-yon):
  Bir aday (x,y,z,orient) kabul edilmeden once parcanin DOLU footprint kolonlarinda, parcanin
  ust profilinin USTUNDE kalan tum hucreler O ANKI occupancy'de BOS olmali. Formulasyon:
      dolu kolonlarda  column_top[x+i,y+j] <= z + bottom_local[i,j]
  yani parcanin kendi kolonlarindaki mevcut occupancy TAMAMEN parcanin altinda kalir.
  KANIT: her parca yerlestigi an ust-bos ise, ters-yerlestirme sirasi GECERLI bir sokum
  sirasidir (tumevarIm) -> 0 kilit GARANTI (ileri-yon tek basina yeter; K-22b'nin post-hoc
  legal-insert'inden farkli). Empty kolonlar (parcanin kavitesi) yok sayilir -> yanal ic-ice
  nesting KORUNUR (komsu daha yuksek olabilir, parcanin kendi kolonu ustu bos oldukca legal).

  Kanit-sonu: yine de accessibility.check_placements ile DOGRULA (fine_settle/clearance-dilation
  gibi post-pass'lar bozabilir mi diye) + kilit kalirsa anatomi + 2. iterasyon (ban+tekrar).

YAKLASIM (uretim src'ye DOKUNMADAN): solve_nfv makinesini (pitch secimi, clearance voxelize,
  replay, fine_settle, raporlama) AYNEN kullan; yalniz decode cekirdegini monkeypatch ile
  gok-koridorlu drop-decode ile degistir. clearance_mm=1.0 (dikey bosluk fix'i commit'li).

  Gok-koridorlu en-dusuk z == drop pozisyonu (parca footprint'inin USTUNE oturur) oldugu icin
  (matematik: ust-bos sarti en-dusuk z'yi drop'a esitler) decode = konkav-farkinda drop packer +
  NFV secim-anahtari (max(z_top,cur_max), z_top, z, y, x, oi). FFT'nin bulacagi tek EK poz
  overhang-alti (=kilit) olurdu; onu KISIT zaten reddeder -> drop'u dogrudan hesaplamak esdeger.

Kosum: python -m scripts.f2v2_prototip     SAF ASCII. Log: scripts/f2v2_prototip.log.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import src.nesting3d.nfv_solve as nfv_solve  # noqa: E402
from src.nesting3d.nfv_solve import solve_nfv  # noqa: E402
from src.nesting3d.parallel_decode import _nz_limit, _eligible_orients  # noqa: E402
from src.nesting3d.extreme_point import OccupancyBin3D  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from scripts.eval_gate import _load_instance  # noqa: E402

LOG = Path(__file__).parent / "f2v2_prototip.log"
NEG = np.iinfo(np.int64).min // 4

# HEDEF referanslar (task): plan3 legal heightmap=701, Magics=593, eski ILLEGAL NFV 755-844.
REF_HEIGHTMAP = 701.0
REF_MAGICS = 593.0


def log(msg=""):
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


# ---------------------------------------------------------------------------
# Gok-koridorlu drop-decode (ileri-yon +Z-sokulebilirlik kIsItI)
# ---------------------------------------------------------------------------

def _orient_drop(ct, orient, cur_max):
    """Bu oryantasyon icin tum (x,y) origin'lerinde gok-koridorlu drop pozisyonu.

    ct: (nx,ny) column_top. orient.bottom=colmin (lokal en-dusuk dolu z), orient.filled.
    drop_z(x,y) = max_{dolu kolon} (ct[x+i,y+j] - bottom[i,j])  -> parca footprint USTUNE oturur
    (kendi dolu kolonlarinda mevcut occupancy tamamen altta -> +Z ust-bos). Empty kolonlar NEG
    ile yok sayilir -> yanal nesting korunur. Doner: en-iyi (eff,z_top,z,y,x) NFV-anahtar tuple'i.
    """
    g = orient.grid
    fw, fd, fh = g.shape
    win = sliding_window_view(ct, (fw, fd))                 # (X, Y, fw, fd)
    need = np.where(orient.filled, -orient.bottom.astype(np.int64), NEG)
    drop_z = (win + need[None, None, :, :]).max(axis=(2, 3))  # (X, Y)
    np.maximum(drop_z, 0, out=drop_z)
    z_top = drop_z + fh
    eff = np.maximum(z_top, cur_max)
    X, Y = drop_z.shape
    xs, ys = np.meshgrid(np.arange(X), np.arange(Y), indexing="ij")
    # lexsort: son anahtar birincil -> (eff, z_top, drop_z, y, x) minimize
    order = np.lexsort((xs.ravel(), ys.ravel(), drop_z.ravel(),
                        z_top.ravel(), eff.ravel()))
    i = order[0]
    return (int(eff.ravel()[i]), int(z_top.ravel()[i]), int(drop_z.ravel()[i]),
            int(ys.ravel()[i]), int(xs.ravel()[i]))


def _sky_decode(parts, nx, ny, pitch, banned=None):
    """Gok-koridorlu drop decode. banned: {part_id: set((x,y,oi))} 2.iter icin poz yasagi.
    Doner: (height_mm, [(pid,oi,x,y,z)], n_placed)."""
    banned = banned or {}
    ob = OccupancyBin3D(nx, ny, nz_limit=_nz_limit(pitch), pitch=pitch)
    raw = []
    n_placed = 0
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        ct = ob.column_top
        best_key = None
        best = None
        for oi, orient in _eligible_orients(part, nx, ny):
            eff, z_top, z, y, x = _orient_drop(ct, orient, cur_max)
            if (x, y, oi) in banned.get(part.id, ()):  # 2.iter yasakli poz
                continue
            key = (eff, z_top, z, y, x, oi)
            if best_key is None or key < best_key:
                best_key = key
                best = (oi, x, y, z)
        if best is None:              # tum pozlar yasakli -> strict-top bbox drop
            oi0, or0 = _eligible_orients(part, nx, ny)[0]
            zt = int(ob.column_top.max()) if ob.max_height_voxels() else 0
            best = (oi0, 0, 0, zt)
        oi, x, y, z = best
        orient = part.orientations[oi]
        # konkav-guvenlik: kolon-profil drop mid-yukseklikte carpisirsa yukari zipla
        while not ob.is_feasible(orient, x, y, z):
            z += 1
        ob.place(orient, x, y, z)
        raw.append((part.id, oi, x, y, z))
        n_placed += 1
    return ob.height_mm(), raw, n_placed


def make_sky_best_decode(banned=None):
    """solve_nfv'nin cagirdigi best_decode(parts,nx,ny,pitch,force,time_budget_sec) imzasina
    uyan monkeypatch. Butce yok sayilir (drop ucuz). strategy string F2-v2 izi tasir."""
    def sky_best_decode(parts, nx, ny, pitch=2.0, *, force=None, verbose=False,
                        time_budget_sec=None):
        h, raw, n = _sky_decode(parts, nx, ny, pitch, banned=banned)
        return h, raw, f"f2v2-sky-corridor (n_decoded={n})"
    return sky_best_decode


# ---------------------------------------------------------------------------
# Olcum
# ---------------------------------------------------------------------------

def _measure(tag, inst, pw, pd, n_total, *, fine_settle, banned=None):
    orig = nfv_solve.best_decode
    nfv_solve.best_decode = make_sky_best_decode(banned)
    t = time.perf_counter()
    try:
        r = solve_nfv(inst, plate_w_mm=pw, plate_d_mm=pd, seed=42,
                      quality="fast", clearance_mm=1.0, fine_settle=fine_settle)
    finally:
        nfv_solve.best_decode = orig
    dt = time.perf_counter() - t
    pitch = float(r.fine_pitch)
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, pitch)
    rep = min_clearance(meshes)
    acc = check_placements(r.placements, r.fine_voxel_parts)
    legal = (r.n_placed == n_total and rep.min_mm >= 1.0 and acc.n_locked == 0)
    log("")
    log(f"[{tag}] yukseklik={float(r.height_mm):.1f}mm  yerlesen={r.n_placed}/{n_total}  "
        f"pitch={pitch:.3f}  fine_settle={fine_settle}  ({dt:.0f}s)")
    log(f"       min_clearance={rep.min_mm:.3f}mm  "
        f"{'OK>=1' if rep.min_mm >= 1.0 else '!!! IHLAL'}")
    log(f"       kilit={acc.n_locked}/{acc.n_parts}  grup={len(acc.locked_groups)}"
        + (f"  boylar={sorted((len(g) for g in acc.locked_groups), reverse=True)[:8]}"
           if acc.locked_groups else ""))
    log(f"       LEGAL_HEIGHT: "
        + (f"{float(r.height_mm):.1f}mm  (heightmap {REF_HEIGHTMAP:.0f} / Magics {REF_MAGICS:.0f})"
           if legal else "INVALID (kalan sebep yukarida)"))
    if legal:
        d_hm = float(r.height_mm) - REF_HEIGHTMAP
        d_mg = float(r.height_mm) - REF_MAGICS
        log(f"       vs heightmap: {d_hm:+.1f}mm ({d_hm / REF_HEIGHTMAP * 100:+.1f}%)  "
            f"vs Magics: {d_mg:+.1f}mm ({d_mg / REF_MAGICS * 100:+.1f}%)")
    return r, rep, acc, legal


def main():
    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("F2-v2 PROTOTIP — NFV decode + yerlestirme-ani +Z gok-koridoru kIsIti  (plan3)")
    log("=" * 78)
    inst = _load_instance("plan3")
    pw = float(inst.container.width_mm)
    pd = float(inst.container.depth_mm)
    n_total = sum(int(p.qty) for p in inst.parts)
    log(f"plan3: plaka={pw:.2f}x{pd:.2f}mm  parca_sayisi={n_total}")

    # ITER-1: gok-koridorlu decode, fine_settle=False (temiz legal izole)
    r1, rep1, acc1, legal1 = _measure("ITER1 settleOFF", inst, pw, pd, n_total,
                                      fine_settle=False)

    # fine_settle=True (uretim NFV default) — settle legalligi bozuyor mu?
    r2, rep2, acc2, legal2 = _measure("ITER1 settleON", inst, pw, pd, n_total,
                                      fine_settle=True)

    # ITER-2 (yalniz gerekirse): kilitli gruplardaki parcalarin pozlarini yasakla, tekrar koir.
    base = r1 if acc1.n_locked <= acc2.n_locked else r2
    base_acc = acc1 if acc1.n_locked <= acc2.n_locked else acc2
    if base_acc.n_locked > 0:
        log("")
        log(f"ITER-2 tetiklendi (kalan kilit={base_acc.n_locked}) — kilitli poz yasagi + tekrar")
        locked_ids = {pid for g in base_acc.locked_groups for pid in g}
        banned = {}
        for pl in base.placements:
            if pl.part_id in locked_ids:
                banned.setdefault(pl.part_id, set()).add((pl.x, pl.y, pl.orientation_idx))
        _measure("ITER2 settleOFF ban", inst, pw, pd, n_total,
                 fine_settle=False, banned=banned)
    else:
        log("")
        log("ITER-2 GEREKMEDI: iter-1 zaten 0 kilit (ileri-yon gok-koridoru tumevarim garantisi).")

    log("")
    log("BITTI")


if __name__ == "__main__":
    main()
