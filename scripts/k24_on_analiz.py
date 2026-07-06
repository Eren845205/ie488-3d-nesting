# -*- coding: utf-8 -*-
"""k24_on_analiz.py — K-24 ADIM-1: gercek plakada (325) zincir-ekimi KAPASITE olcumu.

Baglam (YONTEM_HARITASI K-23 + 2026-07-06 oturum):
  - 264mm tavanini TAMAMEN 62 ASY-0176446 cani kuruyor; dugmeler 236'da tavanli.
  - K-23 teshisi (ESKI 301.6 plaka, 282 layout): 62 ASY -> 10 kok, dagilim ucurum
    (30-halkali kule), halka z-adimi ~10.7mm; analitik denge tavani ~152 ama
    o plakada YENI zincir icin TABAN ALANI YOKTU -> tavan yapisaldi.
  - Gercek plaka 325x325 (+%16 alan) sansi ARTIRDI: canlari dugme-tavani 236
    altina yayabilme imkani dogmus olabilir. K-24 (kasitli zincir-ekimi
    planlayicisi) prototipinden ONCE bu kapasiteyi OLC (meta-ders: olc-once).

Bu script (uretime DOKUNMAZ, scripts/ only):
  [0] 264-config kosusunu AYNEN tekrar uret (c3_height_driver_deneme4 ile ayni:
      wall_aware yol, fine m2/z2, coarse (1,1), clearance_mm=1.0, seed=42,
      plate=325) ve yerlesimleri PICKLE'a kaydet (sonraki K-24 adimlari
      re-solve etmesin). Kapi: tavan 264.0 bekleniyor; sapma = config drift.
  [1] MEVCUT zincir yapisi (264 layout): ASY->ASY ebeveyn agaci (K-23 mantigi)
      -> kac kok, halka dagilimi, z-adim, kok tabanlari + XY dagilimi.
  [2] KAPASITE: 62 ASY sokulur, kalan 526 parcanin yuzey haritasi cikarilir;
      ASY taban-penceresi (yerlesen oryantasyon footprint'leri) icin AYRIK
      dusuk-yuzey pencereleri greedy toplanir -> "kac ek zincir tabani var".
  [3] DENGE: K pencereye 62 halka su-doldurma ile atanir -> ulasabilir min
      tavan egrisi (K=1..N). Esikler: 236 (dugme tavani = yeni driver),
      250.5 (Magics-parite), 264 (mevcut).

KISITLAR/IHTIYAT: pencere-max yuzey yaklasik (kolon-tepe haritasi; gercek drop
tam 3D profil oturtur); diger 526 parca SABIT varsayilir (gercek yeniden-plan
farkli dolar). Bu bir GO/NO-GO teshisi, kesin sonuc degil.

Kosum: python -m scripts.k24_on_analiz   (~10-25 dk, cogu solve)  SAF ASCII.
"""
from __future__ import annotations

import os
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import numpy as np  # noqa: E402
from numpy.lib.stride_tricks import sliding_window_view  # noqa: E402

import src.nesting3d.coarse_to_fine as c2f  # noqa: E402
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine  # noqa: E402
from src.nesting3d.tuner import build_menu  # noqa: E402
from scripts.clearance_decompose import make_deneme4  # noqa: E402

PLATE = 325.0
FINE = 0.5
SEED = 42
BUDGET = 25
ASY = "ASY-0176446"
BEKLENEN_TAVAN = 264.0
DUGME_TAVANI = 236.0      # h_driver teshisi: ASY-disi en yuksek tip
MAGICS_PARITE = 250.5     # K-22 altin bulgu: 9-ASY'siz taban
# GUVENLIK: pickle KENDI kosumuzun ciktisi (bu script yazar, bu script okur;
# k19v2/k23 ile ayni desen) — dis kaynak pickle'i ASLA yuklenmez.
PKL = _ROOT / "data" / "mail_stl" / "k24_placements_325_264.pkl"
LOG = Path(__file__).parent / "k24_on_analiz.log"

_orig_ctv = c2f.clearance_to_voxels


def _patched(clearance_mm, pitch):
    # 264-config (c3_height_driver_deneme4 ile BIREBIR): fine m2/z2, coarse (1,1)
    if pitch <= 0.75:
        return 2, 2
    return 1, 1


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def win_max(a: np.ndarray, wx: int, wy: int) -> np.ndarray:
    """Dikdortgen pencere maksimumu (ayrisabilir 2-gecis)."""
    m = sliding_window_view(a, wx, axis=0).max(axis=-1)
    return sliding_window_view(m, wy, axis=1).max(axis=-1)


def solve_veya_yukle():
    if PKL.exists():
        log(f"[0] PICKLE bulundu, solve ATLANDI: {PKL.name}")
        with PKL.open("rb") as fh:
            return pickle.load(fh)
    inst = make_deneme4()
    menu = {"dblf_only": build_menu()["dblf_only"]}
    t = time.perf_counter()
    c2f.clearance_to_voxels = _patched
    try:
        r = solve_coarse_to_fine(
            inst, plate_w_mm=PLATE, plate_d_mm=PLATE,
            coarse_pitch=None, fine_pitch=FINE, budget=BUDGET, seed=SEED,
            menu=menu, skip_fine_angle=True, drop_cache=True, clearance_mm=1.0,
        )
    finally:
        c2f.clearance_to_voxels = _orig_ctv
    log(f"[0] solve bitti: tavan={r.height_mm:.1f}mm  yerlesen={r.n_placed}/588  "
        f"({(time.perf_counter() - t) / 60:.1f} dk)")
    if abs(r.height_mm - BEKLENEN_TAVAN) > 0.6:
        log(f"    !!! UYARI: beklenen {BEKLENEN_TAVAN} idi — config drift olabilir; "
            f"analiz yine de bu layout uzerinden.")
    data = {
        "placements": r.placements,
        "pitch": r.fine_pitch,
        "height_mm": r.height_mm,
        "plate_mm": PLATE,
        "config": "wall_aware dblf_only skip_fine_angle m2/z2 coarse(1,1) clearance1.0 seed42",
    }
    # grid'leri ham numpy olarak sakla (VoxelPart nesnesi buyuk/surumlu olmasin)
    grids = {}
    for p in r.placements:
        key = (p.part_id, p.orientation_idx)
        if key not in grids:
            grids[key] = np.asarray(
                r.fine_voxel_parts[p.part_id].orientations[p.orientation_idx].grid,
                dtype=bool)
    data["grids"] = grids
    PKL.parent.mkdir(parents=True, exist_ok=True)
    with PKL.open("wb") as fh:
        pickle.dump(data, fh, protocol=4)
    log(f"    yerlesimler kaydedildi: {PKL} ({PKL.stat().st_size / 1e6:.1f} MB)")
    return data


def main() -> None:
    t_all = time.perf_counter()
    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("K-24 ADIM-1 — gercek plakada (325) zincir-ekimi KAPASITE olcumu")
    log("=" * 78)

    data = solve_veya_yukle()
    pls = data["placements"]
    grids = data["grids"]
    pitch = data["pitch"]
    H = data["height_mm"]
    N = int(round(PLATE / pitch))

    # ---------------- [1] mevcut zincir yapisi + XY dagilimi -----------------
    asy = [p for p in pls if p.name == ASY]
    B = {}
    for p in asy:
        g = grids[(p.part_id, p.orientation_idx)]
        zs = np.flatnonzero(g.any(axis=(0, 1)))
        B[p.part_id] = (p.x, p.x + g.shape[0], p.y, p.y + g.shape[1],
                        p.z, p.z + int(zs[-1]) + 1)
    govde = float(np.median([(b[5] - b[4]) * pitch for b in B.values()]))
    log("")
    log(f"[1] MEVCUT ZINCIR YAPISI (tavan={H:.1f}, ASY={len(asy)}, "
        f"govde={govde:.1f}mm)")

    parent = {}
    for pid, b in B.items():
        best = None
        for qid, c in B.items():
            if qid == pid:
                continue
            if not (b[0] < c[1] and c[0] < b[1] and b[2] < c[3] and c[2] < b[3]):
                continue
            if c[4] < b[4] < c[5]:
                depth = c[5] - b[4]
                if best is None or depth > best[1]:
                    best = (qid, depth)
        parent[pid] = best

    roots = [pid for pid, pr in parent.items() if pr is None]
    kids = defaultdict(list)
    for pid, pr in parent.items():
        if pr is not None:
            kids[pr[0]].append(pid)

    def chain_stats(root):
        n, stack, deepest = 0, [root], root
        while stack:
            cur = stack.pop()
            n += 1
            for k in kids.get(cur, []):
                stack.append(k)
                if B[k][5] > B[deepest][5]:
                    deepest = k
        return n, deepest

    steps = []
    sizes = []
    log(f"    kok sayisi (paralel zincir): {len(roots)}")
    log(f"    {'kok-pid':>8} {'halka':>5} {'taban':>7} {'tepe':>7} "
        f"{'xy-merkez(mm)':>16}")
    for r_ in sorted(roots, key=lambda q: -chain_stats(q)[0]):
        n, deepest = chain_stats(r_)
        sizes.append(n)
        b = B[r_]
        top = B[deepest][5] * pitch
        base = b[4] * pitch
        cx = (b[0] + b[1]) / 2 * pitch
        cy = (b[2] + b[3]) / 2 * pitch
        if n > 1:
            steps.append((top - base - (b[5] - b[4]) * pitch) / (n - 1))
        log(f"    {r_:>8} {n:>5} {base:>7.1f} {B[deepest][5] * pitch:>7.1f} "
            f"{f'({cx:.0f},{cy:.0f})':>16}")
    sizes_arr = np.array(sizes)
    s = float(np.median(steps)) if steps else 10.7
    log(f"    halka: toplam={sizes_arr.sum()} ort={sizes_arr.mean():.1f} "
        f"min={sizes_arr.min()} max={sizes_arr.max()} | z-adim medyan={s:.1f}mm")

    # ---------------- [2] kapasite: ASY'siz yuzey + pencere taramasi ---------
    log("")
    log("[2] KAPASITE — 62 ASY sokuldu, kalan 526 parcanin yuzeyi:")
    hm = np.zeros((N, N), dtype=np.float32)
    for p in pls:
        if p.name == ASY:
            continue
        g = grids[(p.part_id, p.orientation_idx)]
        mask = g.any(axis=2)
        # kolon-tepe (bos kolon 0 kalir)
        top_idx = g.shape[2] - 1 - np.argmax(g[:, :, ::-1], axis=2)
        top_mm = np.where(mask, (p.z + top_idx + 1) * pitch, 0.0).astype(np.float32)
        x1 = min(p.x + g.shape[0], N)
        y1 = min(p.y + g.shape[1], N)
        sl = (slice(p.x, x1), slice(p.y, y1))
        hm[sl] = np.maximum(hm[sl], top_mm[: x1 - p.x, : y1 - p.y])
    kalan_max = float(hm.max())
    log(f"    ASY'siz yuzey max={kalan_max:.1f}mm (beklenen ~{DUGME_TAVANI:.0f}) | "
        f"taban-bos hucre orani={float((hm == 0).mean()) * 100:.1f}%")

    # yerlesen ASY oryantasyonlarinin footprint'leri (tekil)
    fps = sorted({grids[(p.part_id, p.orientation_idx)].shape[:2] for p in asy})
    log(f"    ASY footprint adaylari (hucre {pitch}mm): "
        f"{[(fw, fd, f'{fw * pitch:.0f}x{fd * pitch:.0f}mm') for fw, fd in fps]}")

    CUTOFF = MAGICS_PARITE - govde  # ilk halkasi bile 250.5 ustune cikan pencere ise yaramaz
    MAXWIN = 24
    windows = []
    work = hm.copy()
    while len(windows) < MAXWIN:
        best = None
        for fw, fd in fps:
            if fw > N or fd > N:
                continue
            wm = win_max(work, fw, fd)
            ij = np.unravel_index(np.argmin(wm), wm.shape)
            v = float(wm[ij])
            if best is None or v < best[0]:
                best = (v, int(ij[0]), int(ij[1]), fw, fd)
        if best is None or best[0] > CUTOFF:
            break
        v, x0, y0, fw, fd = best
        windows.append(best)
        work[x0:x0 + fw, y0:y0 + fd] = 1e9
    log(f"    AYRIK dusuk-yuzey pencere sayisi (yuzey+govde<={MAGICS_PARITE:.1f}): "
        f"{len(windows)}")
    for i, (v, x0, y0, fw, fd) in enumerate(windows):
        log(f"      #{i + 1:>2} yuzey={v:>6.1f}mm  ilk-halka-tepe={v + govde:>6.1f}  "
            f"xy=({x0 * pitch:.0f},{y0 * pitch:.0f})  fp={fw * pitch:.0f}x{fd * pitch:.0f}")

    # ---------------- [3] denge: su-doldurma egrisi --------------------------
    log("")
    log(f"[3] DENGE — K pencereye 62 halka su-doldurma (z-adim={s:.1f}mm):")
    n_rings = len(asy)
    surfs = sorted(w[0] for w in windows)
    log(f"    {'K':>3} {'tavan(mm)':>10}  yorum")
    best_any = None
    for K in range(1, len(surfs) + 1):
        cnt = [0] * K

        def top(i):
            return surfs[i] + govde + max(cnt[i] - 1, 0) * s

        for _ in range(n_rings):
            j = min(range(K), key=lambda i: surfs[i] + govde + cnt[i] * s)
            cnt[j] += 1
        tavan = max(top(i) for i in range(K) if cnt[i] > 0)
        yorum = ""
        if tavan <= DUGME_TAVANI:
            yorum = "<= 236 DUGME TAVANI — driver degisir!"
        elif tavan <= MAGICS_PARITE:
            yorum = "<= 250.5 Magics-parite"
        elif tavan < H:
            yorum = f"mevcut {H:.0f}'in altinda"
        if best_any is None or tavan < best_any[1]:
            best_any = (K, tavan)
        log(f"    {K:>3} {tavan:>10.1f}  {yorum}")

    log("")
    log("KARAR GIRDISI:")
    if not windows:
        log(f"  Pencere YOK (yuzey+govde hep >{MAGICS_PARITE:.1f}) -> gercek plakada da "
            f"zincir tabani icin yer yok; K-24 NO-GO, tavan {H:.0f} yapisal kalir.")
    else:
        K, tavan = best_any
        log(f"  En iyi: K={K} zincirle ulasilabilir tavan ~{tavan:.1f}mm "
            f"(mevcut {H:.1f}; dugme tavani {DUGME_TAVANI:.0f}).")
        if tavan <= DUGME_TAVANI + 2:
            log("  -> K-24 UMUTLU: canlar dugme-tavani bandina inebilir; kazanc "
            f"~{H - max(tavan, DUGME_TAVANI):.0f}mm. Sonraki adim: izole 62-can "
            "mini-instance'ta zincir-ekimi prototipi (olc-once).")
        elif tavan < H - 4:
            log(f"  -> KISMEN umutlu: ~{H - tavan:.0f}mm odul var ama dugme tavanina "
                "inilemiyor; prototip maliyet/odul karariyla.")
        else:
            log("  -> K-24 DUSUK umutlu: pencere yuzeyleri yuksek, odul <4mm; "
                "NO-GO onerisi.")
    log("")
    log("IHTIYAT: yuzey haritasi kolon-tepe yaklasimi + 526 parca sabit varsayimi; "
        "gercek zincir-ekimi decode'u farkli dolabilir. Bu bir on-teshis.")
    log(f"TOPLAM SURE: {(time.perf_counter() - t_all) / 60:.1f} dk")


if __name__ == "__main__":
    main()
