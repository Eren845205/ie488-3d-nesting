# -*- coding: utf-8 -*-
"""k24_adim2_prototip.py — K-24 ADIM-2: dengeli zincir-routing decode prototipi.

Baglam (YONTEM_HARITASI §3.1 K-24/Adim-1, K-23, K-22, K-25):
  - Gercek plaka (325) 264-config'te 62 ASY-0176446 cani tavani KURUYOR: greedy
    _best_position 13 kok acti ama DENGESIZ yigdi (36-halkali tek kule 264'u
    kuruyor; 7 can tabanda tek). Analitik denge tavani ~132 -> bin ~236 (dugme
    guduml). Odul ~28mm AMA spekulatif: dengeli routing'de teleskop-ofset XY'si
    komsu koklerce BLOKE olabilir (Adim-1'in acik sorusu — bu script OLCER).
  - Adim-1 post-hoc kapasite = 0 (iki yontemle): heightmap'te SIRA-ICI olmayan
    site analizi yapisal imkansiz. Bu yuzden Adim-2 GERCEK solve icinde,
    yerlestirme aninda ASY'leri koklere KISITLI drop ile dagitir.

YAKLASIM (a) — round-robin kok-site penceresine kisitli drop:
  - Uretim decode'u BIREBIR (make_deneme4 + solve_coarse_to_fine, 264-config:
    wall_aware dblf_only, skip_fine_angle, fine m2/z2, coarse (1,1), clearance 1.0,
    seed 42, plate 325). SIRA DEGISMEZ (ROBT'lar ASY'den once kalir).
  - TEK degisiklik: FINE asamada (pitch<=0.75) ASY-0176446 parcalari icin
    dblf._best_position monkeypatch'lenir. Her ASY, id-sirasina gore round-robin
    atanmis bir kok-site'in XY penceresine (merkez +/- R mm) KISITLANIR; o
    pencere icinde uretimle AYNI leksikografik (z_top,z,y,x) argmin secilir
    (teleskop drop korunur, yalniz XY sinirlanir). Pencere uygun degilse
    kisitsiz orijinale duser (parca DAIMA yerlesir; olcum legal/tam kalir).
  - Kok-site'lar Adim-1 log'undaki 13 mevcut zincir XY-merkezi.

OLCUM (uc sart hepsi gerekli, yoksa INVALID):
  - bin yuksekligi (max_height_mm) + n_placed==588
  - min_clearance (clearance.min_clearance, >=1.0mm sart)
  - kilit sayisi (accessibility.check_placements, 0 sart)
Kiyas: uretim 264.0mm (0 kilit, clearance 1.023). Hedef bandi ~236 (dugme tavani).

Kosum: python -m scripts.k24_adim2_prototip   (konfig basina ~6-10 dk)
URETIME DOKUNMAZ (scripts/ only, monkeypatch). SAF ASCII (cp1254 guvenli).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import numpy as np  # noqa: E402

import src.nesting3d.coarse_to_fine as c2f  # noqa: E402
import src.nesting3d.dblf as dblf  # noqa: E402
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.tuner import build_menu  # noqa: E402
from src.nesting3d.export_stl import placed_meshes  # noqa: E402
from src.nesting3d.clearance import min_clearance  # noqa: E402
from src.nesting3d.accessibility import check_placements  # noqa: E402
from scripts.clearance_decompose import make_deneme4  # noqa: E402

PLATE = 325.0
FINE = 0.5
SEED = 42
BUDGET = 25
ASY = "ASY-0176446"
URETIM_TAVAN = 264.0
DUGME_TAVANI = 236.0
MAGICS = 250.24
LOG = Path(__file__).parent / "k24_adim2.log"

# Adim-1 log'undaki 13 mevcut zincir XY-merkezi (mm) — round-robin kok-site'lar.
SITES = [
    (213.0, 254.0), (268.0, 98.0), (299.0, 67.0), (26.0, 45.0),
    (87.0, 224.0), (140.0, 100.0), (214.0, 232.0), (86.0, 246.0),
    (85.0, 268.0), (212.0, 276.0), (252.0, 105.0), (84.0, 289.0),
    (211.0, 297.0),
]

# Konfig sweep. mode="window" (yaklasim a): (etiket, "window", R_mm, K).
#              mode="penalty" (yaklasim b): (etiket, "penalty", LAM, None).
# Yaklasim (a) [window] ILK KOSUDA olculdu (rr13_R12=925mm, rr13_R25=637mm =
# felaket: balance saglandi ama yanal cavity-nesting ozgurlugu yok edilince
# kuleler patladi). Bu kosu yaklasim (b)'yi olcer (append; (a) log korunur).
CONFIGS = [
    ("penalty_L0.5", "penalty", 0.5, None),
    ("penalty_L2.0", "penalty", 2.0, None),
]

_orig_ctv = c2f.clearance_to_voxels
_orig_bp = dblf._best_position

# Aktif routing konfigurasyonu (solve oncesi set edilir)
_R_MM = 0.0
_SITES: list = []
_MODE = "window"
_LAM = 0.0


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _patched_ctv(clearance_mm, pitch):
    # 264-config: fine margin=2/z2, coarse (1,1) — c3_height_driver_deneme4 birebir.
    if pitch <= 0.75:
        return 2, 2
    return 1, 1


def _asy_index(part) -> "int | None":
    """ASY-0176446_NN -> NN (int); ASY degilse None."""
    if getattr(part, "name", None) != ASY:
        return None
    pid = part.id
    tail = pid.rsplit("_", 1)[-1]
    try:
        return int(tail)
    except ValueError:
        return None


def _constrained_best(bin3d, part, orientation_indices, cx_mm, cy_mm, r_mm):
    """Uretim _best_position ile AYNI leksikografik argmin AMA offset penceresi
    parca-merkezini (cx,cy) +/- r_mm ile sinirlanir. Pencere bos -> None."""
    pitch = bin3d.pitch
    best = None
    for oi in orientation_indices:
        orient = part.orientations[oi]
        Z = bin3d.drop_map(orient)
        if Z is None:
            continue
        fw, fh = orient.filled.shape
        npx, npy = Z.shape
        # offset x0 araligi: merkez ((x0+fw/2)*pitch) in [cx-r, cx+r]
        x_lo = int(np.ceil((cx_mm - r_mm) / pitch - fw / 2.0))
        x_hi = int(np.floor((cx_mm + r_mm) / pitch - fw / 2.0))
        y_lo = int(np.ceil((cy_mm - r_mm) / pitch - fh / 2.0))
        y_hi = int(np.floor((cy_mm + r_mm) / pitch - fh / 2.0))
        x_lo = max(0, x_lo)
        x_hi = min(npx - 1, x_hi)
        y_lo = max(0, y_lo)
        y_hi = min(npy - 1, y_hi)
        if x_lo > x_hi or y_lo > y_hi:
            continue
        sub = Z[x_lo:x_hi + 1, y_lo:y_hi + 1]
        z_top = sub + orient.grid.shape[2]
        cand_top = int(z_top.min())
        lxs, lys = np.nonzero(z_top == cand_top)
        zs = sub[lxs, lys]
        gxs = lxs + x_lo
        gys = lys + y_lo
        k = int(np.lexsort((gxs, gys, zs))[0])  # birincil zs, sonra gys, gxs
        cand = (cand_top, int(zs[k]), int(gys[k]), int(gxs[k]), oi)
        if best is None or cand < best:
            best = cand
    return best


def _penalty_best(bin3d, part, orientation_indices, lam):
    """Yaklasim (b): TAM XY ozgurlugu korunur ama ASY skoru zincir-yukseklik
    dengesizligiyle cezalanir. eff = z_top + lam * z_drop -> yuksek oturmayi
    (uzun zinciri uzatmayi) caydirir, dusuk/bos alani (denge) tesvik eder.
    Uretim _best_position (lam=0) ile leksikografik tie-break AYNI."""
    best = None  # (eff, z_top, z, y, x, oi)
    for oi in orientation_indices:
        orient = part.orientations[oi]
        Z = bin3d.drop_map(orient)
        if Z is None:
            continue
        gz = orient.grid.shape[2]
        z_top = Z + gz
        eff = z_top.astype(np.float64) + lam * Z.astype(np.float64)
        cand_eff = float(eff.min())
        xs, ys = np.nonzero(eff == cand_eff)
        zs = Z[xs, ys]
        zt = zs + gz
        # leksikografik tie-break: (z_top, z, y, x) — uretimle ayni sira
        k = int(np.lexsort((xs, ys, zs, zt))[0])
        cand = (cand_eff, int(zt[k]), int(zs[k]), int(ys[k]), int(xs[k]), oi)
        if best is None or cand < best:
            best = cand
    if best is None:
        return None
    _, zt, z, y, x, oi = best
    return (zt, z, y, x, oi)   # dblf._Best formati (z_top, z, y, x, oi)


def _patched_bp(bin3d, part, orientation_indices):
    """FINE asamada ASY'ye routing uygula (mode'a gore); digerleri orjinal."""
    if bin3d.pitch > 0.75:                       # coarse asama -> uretim birebir
        return _orig_bp(bin3d, part, orientation_indices)
    idx = _asy_index(part)
    if idx is None:                              # ASY disi (ROBT/dugme) -> orjinal
        return _orig_bp(bin3d, part, orientation_indices)
    if _MODE == "penalty":
        best = _penalty_best(bin3d, part, orientation_indices, _LAM)
    else:
        cx, cy = _SITES[(idx - 1) % len(_SITES)]  # round-robin kok-site
        best = _constrained_best(bin3d, part, orientation_indices, cx, cy, _R_MM)
    if best is None:                             # uygun degil -> kisitsiz orjinal
        return _orig_bp(bin3d, part, orientation_indices)
    return best


def _solve_routed():
    inst = make_deneme4()
    menu = {"dblf_only": build_menu()["dblf_only"]}
    c2f.clearance_to_voxels = _patched_ctv
    dblf._best_position = _patched_bp
    try:
        r = solve_coarse_to_fine(
            inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
            coarse_pitch=None, fine_pitch=FINE, budget=BUDGET, seed=SEED,
            menu=menu, skip_fine_angle=True, drop_cache=True, clearance_mm=1.0,
        )
    finally:
        c2f.clearance_to_voxels = _orig_ctv
        dblf._best_position = _orig_bp
    return r


def _asy_top_mm(part, oi, z, pitch):
    g = part.orientations[oi].grid
    zs = np.flatnonzero(g.any(axis=(0, 1)))
    return (z + int(zs[-1]) + 1) * pitch


def _chain_report(r):
    """ASY yerlesimlerini atanmis site'a gore grupla; site basi adet + max-tepe."""
    pitch = r.fine_pitch
    vp = r.fine_voxel_parts
    per_site = {}
    asy_tops = []
    for p in r.placements:
        if p.name != ASY:
            continue
        idx = None
        tail = p.part_id.rsplit("_", 1)[-1]
        try:
            idx = int(tail)
        except ValueError:
            pass
        site = (idx - 1) % len(_SITES) if idx is not None else -1
        top = _asy_top_mm(vp[p.part_id], p.orientation_idx, p.z, pitch)
        asy_tops.append(top)
        d = per_site.setdefault(site, {"n": 0, "max_top": 0.0})
        d["n"] += 1
        d["max_top"] = max(d["max_top"], top)
    return per_site, (max(asy_tops) if asy_tops else 0.0), len(asy_tops)


def _validate(r):
    """(height, n_placed, min_clear, n_locked, valid, reason)."""
    h = r.height_mm
    n = r.n_placed
    t = time.perf_counter()
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
    rep = min_clearance(meshes, samples_per_mesh=3000, seed=1)
    clr = rep.min_mm
    log(f"    clearance olcumu: {clr:.3f}mm  ({time.perf_counter() - t:.0f}s)")
    t = time.perf_counter()
    acc = check_placements(r.placements, r.fine_voxel_parts)
    locked = acc.n_locked
    log(f"    erisilebilirlik: kilitli={locked}/{acc.n_parts}  "
        f"({time.perf_counter() - t:.0f}s)")
    reasons = []
    if n != 588:
        reasons.append(f"n_placed={n}!=588")
    if clr < 1.0:
        reasons.append(f"clearance={clr:.3f}<1.0")
    if locked > 0:
        reasons.append(f"kilit={locked}>0")
    return h, n, clr, locked, (not reasons), "; ".join(reasons)


def _run_config(label, mode, p1, p2):
    global _R_MM, _SITES, _MODE, _LAM
    _MODE = mode
    _SITES = SITES[: (p2 or len(SITES))]
    log("")
    log("-" * 78)
    if mode == "penalty":
        _LAM = p1
        log(f"KONFIG {label} [b/penalty]: TAM XY ozgurlugu + zincir-ceza "
            f"eff=z_top+{p1:.1f}*z_drop")
    else:
        _R_MM = p1
        log(f"KONFIG {label} [a/window]: round-robin {p2} kok-site, "
            f"pencere R=+/-{p1:.0f}mm")
    log("-" * 78)
    t = time.perf_counter()
    r = _solve_routed()
    dt = (time.perf_counter() - t) / 60
    per_site, asy_max, n_asy = _chain_report(r)
    log(f"  solve: tavan={r.height_mm:.1f}mm  yerlesen={r.n_placed}/588  "
        f"ASY={n_asy} ASY-max-tepe={asy_max:.1f}mm  ({dt:.1f} dk)")
    log(f"  {'site':>5} {'xy(mm)':>14} {'adet':>5} {'max-tepe(mm)':>13}")
    for s in sorted(per_site):
        xy = _SITES[s] if 0 <= s < len(_SITES) else ("-", "-")
        d = per_site[s]
        log(f"  {s:>5} {f'({xy[0]:.0f},{xy[1]:.0f})':>14} {d['n']:>5} "
            f"{d['max_top']:>13.1f}")
    return label, r


def main():
    t_all = time.perf_counter()
    # append: yaklasim (a) log'u (ayni dosyada) KORUNUR
    log("")
    log("#" * 78)
    log("K-24 ADIM-2 — YAKLASIM (b): zincir-yukseklik-cezali skorlama")
    log("#" * 78)
    log(f"uretim referans: {URETIM_TAVAN:.1f}mm (0 kilit, clearance 1.023) | "
        f"hedef ~{DUGME_TAVANI:.0f} (dugme tavani) | Magics {MAGICS}")
    log("(a/window ONCEKI kosuda: rr13_R12=925mm, rr13_R25=637mm = felaket)")

    results = []
    for label, mode, p1, p2 in CONFIGS:
        results.append(_run_config(label, mode, p1, p2))

    # gecerli-yukseklik'e gore en iyi konfigi tam-dogrula
    best = min(results, key=lambda lr: lr[1].height_mm)
    label, r = best
    log("")
    log("=" * 78)
    log(f"EN IYI KONFIG (tavana gore): {label}  tavan={r.height_mm:.1f}mm")
    log("=" * 78)
    h, n, clr, locked, valid, reason = _validate(r)

    log("")
    log("SONUC:")
    log(f"  tavan       = {h:.1f}mm   yerlesen={n}/588")
    log(f"  min_clear   = {clr:.3f}mm  ({'OK>=1' if clr >= 1.0 else 'IHLAL<1'})")
    log(f"  kilit       = {locked}    ({'OK' if locked == 0 else 'ILLEGAL'})")
    if valid:
        d264 = URETIM_TAVAN - h
        d236 = h - DUGME_TAVANI
        log(f"  GECERLI. uretim {URETIM_TAVAN:.0f}'a kiyas: "
            f"{'-' if d264 >= 0 else '+'}{abs(d264):.1f}mm "
            f"({d264 / URETIM_TAVAN * 100:+.1f}%).")
        log(f"  hedef {DUGME_TAVANI:.0f} bandina: {d236:+.1f}mm "
            f"({'bandda/alti' if d236 <= 2 else 'ustunde'}).")
        log(f"  Magics {MAGICS}'e kiyas: "
            f"{'ALTINA iner' if h < MAGICS else 'ustunde kalir'}.")
        if h <= URETIM_TAVAN - 4:
            log(f"  -> GO SINYALI: dengeli routing tavani {URETIM_TAVAN - h:.1f}mm "
                "indirdi, legal (0 kilit + clearance OK).")
        else:
            log(f"  -> NO-GO: odul {URETIM_TAVAN - h:.1f}mm (<4mm) — routing "
                "kaydadeger kazanc vermedi; greedy zaten yapisal tavana yakin.")
    else:
        log(f"  INVALID({reason}).")
        log(f"  -> NO-GO: dengeli routing gecerli-legal layout uretmedi "
            f"(sebep: {reason}). Adim-1 spekulasyonu (teleskop-ofset komsu "
            "koklerce bloke) bu olcumle desteklenir/reddedilir — detay yukarida.")

    log("")
    log("IHTIYAT: yaklasim (a) sabit kok-site penceresi kullanir; site'lar "
        "mevcut 264-layout zincir merkezleridir (bazilari yanal ic-ice = "
        "ortusen pencereler). Blokaj gorulurse (b) zincir-yukseklik-cezali "
        "skorlama denenebilir. Bu bir prototip olcumdur.")
    log(f"TOPLAM SURE: {(time.perf_counter() - t_all) / 60:.1f} dk")


if __name__ == "__main__":
    main()
