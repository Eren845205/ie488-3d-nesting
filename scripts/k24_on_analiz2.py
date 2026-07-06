# -*- coding: utf-8 -*-
"""k24_on_analiz2.py — K-24 ADIM-1 v2: DROP-SEMANTIGIYLE kapasite (v1 duzeltmesi).

v1 (k24_on_analiz.py) [2] bolumu dikdortgen-pencere-max kullandi -> yanal
ic-ice gecen komsular (F4-A: %96) bbox penceresini "dolu" gosterdi -> 0 pencere
ARTEFAKTI. Oysa [1] mevcut layoutta 13 kokun TABANDA (z=0) oturdugunu gosterdi.

v2 uretimin GERCEK drop semantigini kullanir:
  z_drop(x0,y0) = max_{parca kolonu (i,j)} [ hm(x0+i, y0+j) - bottom(i,j) ]
  (hm = ASY'siz 526 parcanin kolon-tepe haritasi; bottom = ASY alt-profili.
   Yalniz ASY'nin DOLU kolonlari sayilir -> kavite/ic-ice dogru ele alinir;
   bu, heightmap decode'un parca oturtma formulunun kendisidir.)

Greedy ayrik kok-site secimi: global min z_drop -> site al -> o bbox'la
KESISEN tum offset'leri 4 haritada gecersizle (hm degismedigi icin kalan
degerler AYNEN gecerli = tam dogru) -> tekrarla. Sonra su-doldurma dengesi.

Kosum: python -m scripts.k24_on_analiz2   (~2-4 dk; pickle'dan, re-solve YOK)
SAF ASCII.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (k24_on_analiz.py yazdi) — dis
# kaynak pickle'i degil.
PKL = _ROOT / "data" / "mail_stl" / "k24_placements_325_264.pkl"
LOG = Path(__file__).parent / "k24_on_analiz2.log"
PLATE = 325.0
ASY = "ASY-0176446"
DUGME_TAVANI = 236.0
MAGICS_PARITE = 250.5
S_FALLBACK = 11.2  # v1 [1] olcumu: zincir z-adimi medyani


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    LOG.write_text("", encoding="utf-8")
    log("=" * 78)
    log("K-24 ADIM-1 v2 — DROP-semantikli kapasite (325 plaka, 264 layout)")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]
    grids = data["grids"]
    pitch = data["pitch"]
    H = data["height_mm"]
    N = int(round(PLATE / pitch))

    # --- ASY'siz kolon-tepe haritasi (v1 ile ayni) ---------------------------
    hm = np.zeros((N, N), dtype=np.float32)
    for p in pls:
        if p.name == ASY:
            continue
        g = grids[(p.part_id, p.orientation_idx)]
        mask = g.any(axis=2)
        top_idx = g.shape[2] - 1 - np.argmax(g[:, :, ::-1], axis=2)
        top_mm = np.where(mask, (p.z + top_idx + 1) * pitch, 0.0).astype(np.float32)
        x1 = min(p.x + g.shape[0], N)
        y1 = min(p.y + g.shape[1], N)
        sl = (slice(p.x, x1), slice(p.y, y1))
        hm[sl] = np.maximum(hm[sl], top_mm[: x1 - p.x, : y1 - p.y])
    log(f"[A] ASY'siz yuzey: max={float(hm.max()):.1f}mm  "
        f"taban-bos={float((hm == 0).mean()) * 100:.1f}%  (tavan={H:.1f})")

    # --- ASY oryantasyon gridleri (tekil, sekil bazinda) ---------------------
    asy_pls = [p for p in pls if p.name == ASY]
    ogrids = {}
    for p in asy_pls:
        oi = p.orientation_idx
        if oi not in ogrids:
            ogrids[oi] = grids[(p.part_id, oi)]
    govde = float(np.median(
        [np.flatnonzero(g.any(axis=(0, 1)))[-1] + 1 for g in ogrids.values()]
    )) * pitch
    log(f"[B] ASY oryantasyonlari: "
        f"{[(oi, g.shape[0], g.shape[1]) for oi, g in ogrids.items()]}  "
        f"govde~{govde:.1f}mm")

    # --- drop haritalari ------------------------------------------------------
    log("[C] drop haritalari (uretim formulu):")
    dmaps = {}
    for oi, g in sorted(ogrids.items()):
        t = time.perf_counter()
        mask = g.any(axis=2)
        bottom_idx = np.argmax(g, axis=2)  # ilk dolu z (mask disinda anlamsiz)
        fw, fd = g.shape[:2]
        nx, ny = N - fw + 1, N - fd + 1
        if nx <= 0 or ny <= 0:
            continue
        out = np.full((nx, ny), -np.inf, dtype=np.float32)
        cols = np.argwhere(mask)
        # kolonlari ayni bottom degerine gore grupla (dongu sayisini dusurur)
        bvals = bottom_idx[mask]
        for b in np.unique(bvals):
            sel = cols[bvals == b]
            # ayni b'li kolonlar: max_{(i,j)} hm[x0+i, y0+j]  -  b*pitch
            acc = np.full((nx, ny), -np.inf, dtype=np.float32)
            for i, j in sel:
                np.maximum(acc, hm[i:i + nx, j:j + ny], out=acc)
            np.maximum(out, acc - b * pitch, out=out)
        dmaps[oi] = out
        log(f"    oi={oi} fp={fw * pitch:.0f}x{fd * pitch:.0f}mm  "
            f"min-drop={float(out.min()):.1f}mm  "
            f"drop=0 offset sayisi={int((out <= 1e-6).sum())}  "
            f"({time.perf_counter() - t:.0f}s)")

    # --- greedy ayrik site secimi --------------------------------------------
    log("")
    log("[D] GREEDY ayrik kok-site secimi (kesisen offset gecersizleme = tam):")
    CUTOFF = MAGICS_PARITE - govde   # ilk halka bile 250.5'i asarsa site anlamsiz
    MAXSITE = 32
    sites = []
    while len(sites) < MAXSITE:
        best = None
        for oi, dm in dmaps.items():
            ij = np.unravel_index(np.argmin(dm), dm.shape)
            v = float(dm[ij])
            if best is None or v < best[0]:
                best = (v, int(ij[0]), int(ij[1]), oi)
        if best is None or best[0] > CUTOFF:
            break
        v, x0, y0, oi = best
        fw, fd = ogrids[oi].shape[:2]
        sites.append((v, x0, y0, oi, fw, fd))
        # bu bbox ile KESISEN offset'leri tum haritalarda gecersizle
        for oj, dm in dmaps.items():
            gw, gd = ogrids[oj].shape[:2]
            xa = max(0, x0 - gw + 1)
            ya = max(0, y0 - gd + 1)
            dm[xa:x0 + fw, ya:y0 + fd] = np.inf
    log(f"    site sayisi (ilk-halka-tepe<={MAGICS_PARITE}): {len(sites)}")
    for i, (v, x0, y0, oi, fw, fd) in enumerate(sites):
        log(f"      #{i + 1:>2} z_drop={v:>6.1f}  ilk-halka-tepe={v + govde:>6.1f}  "
            f"xy=({x0 * pitch:.0f},{y0 * pitch:.0f})  oi={oi} "
            f"fp={fw * pitch:.0f}x{fd * pitch:.0f}")

    # --- su-doldurma dengesi ---------------------------------------------------
    log("")
    s = S_FALLBACK
    n_rings = len(asy_pls)
    log(f"[E] DENGE — K site'a {n_rings} halka su-doldurma (z-adim={s:.1f}mm):")
    surfs = sorted(x[0] for x in sites)
    log(f"    {'K':>3} {'tavan(mm)':>10}  yorum")
    best_any = None
    for K in range(1, len(surfs) + 1):
        cnt = [0] * K
        for _ in range(n_rings):
            j = min(range(K), key=lambda i: surfs[i] + govde + cnt[i] * s)
            cnt[j] += 1
        tavan = max(surfs[i] + govde + (cnt[i] - 1) * s
                    for i in range(K) if cnt[i] > 0)
        yorum = ""
        if tavan <= DUGME_TAVANI:
            yorum = "<= 236 DUGME TAVANI (driver degisir; bin tavani ~236 olur)"
        elif tavan <= MAGICS_PARITE:
            yorum = "<= 250.5 Magics-parite"
        elif tavan < H:
            yorum = f"mevcut {H:.0f} alti"
        if best_any is None or tavan < best_any[1]:
            best_any = (K, tavan)
        log(f"    {K:>3} {tavan:>10.1f}  {yorum}")

    log("")
    log("KARAR GIRDISI (v2, drop-semantikli):")
    if not sites:
        log(f"  Site YOK -> K-24 NO-GO (v1 ile ayni hukum, artefaktsiz dogrulandi).")
    else:
        K, tavan = best_any
        etkin_bin = max(tavan, DUGME_TAVANI)
        log(f"  K={K} zincirle ASY tavani ~{tavan:.1f}mm -> etkin bin tavani "
            f"~{etkin_bin:.1f}mm (dugmeler {DUGME_TAVANI:.0f}'da).")
        log(f"  Mevcut {H:.1f} -> odul ~{H - etkin_bin:.1f}mm "
            f"({(H - etkin_bin) / H * 100:.1f}%). Magics 250.24'e kiyas: "
            f"{'ALTINA iner' if etkin_bin < 250.24 else 'ustunde kalir'}.")
        if etkin_bin < H - 4:
            log("  -> K-24 UMUTLU: sonraki adim izole zincir-ekimi prototipi "
                "(62 ASY'yi K site'a KASITLI dagitan decode; olc-once, "
                "uretime dokunmadan tam-Deneme4 replay).")
        else:
            log("  -> odul <4mm: K-24 NO-GO onerisi.")
    log("")
    log("IHTIYAT: 526 parca sabit varsayimi surer; zincir buyurken siteler arasi "
        "etkilesim (govde ustu yanal komsu) ihmal edildi; s=11.2 mevcut layout "
        "medyani. Kesin hukum Adim-2 prototip replay'inde.")
    log(f"TOPLAM SURE: {(time.perf_counter() - t_all) / 60:.1f} dk")


if __name__ == "__main__":
    main()
