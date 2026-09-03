# -*- coding: utf-8 -*-
"""k23_on_analiz.py — K-23 ON-ANALIZ: ASY zincir yapisi + yeniden-dengeleme tavani.

K-22/K-22b hukmu: sabit geometri doymus; kuyruk emilimi ancak yerlesim
BASTAN farkli kurulursa. K-19 v2 sirasi incelendi: ASY blogu ZATEN en onde
(sira 2..63, ROBT plakalarindan sonra) -> "kuyrugu one al" bos. Gercek soru:
62 ASY'nin olusturdugu yuvalanma ZINCIRLERI yeniden dengelenebilir mi
(daha COK paralel zincir x daha KISA boy)?

Bu analiz (dakikalar, kosu yok):
  [1] ASY->ASY ebeveyn iliskisinden zincirleri cikar (ebeveyn = tabanimin
      icine en derin gomuldugum ASY; F4-A 'inside' tanimi).
  [2] Zincir sayisi/uzunluklari/z-adimlari; en uzun zincirin tepe katkisi.
  [3] Denge tavani: mevcut K zincir ve toplam 62 halkayla, adimlar ortalama
      s ise dengeli dagitimda tavan ~ taban + ort_govde + ceil(62/K -1)*s.
      Ayrica "kac zincir olsa 250.5'e inerdik" ters hesabi.
Karar girdisi: dengeli-dagitim tavani < 282 ise K-23 kosusu UMUTLU (sira
zincir-dengesini bozuyor demektir); zincirler zaten dengeliyse K-23 NO-GO
(yeni zincir icin TABAN alani yok -> 6GB'de kabuk tavani 282 kalir).

Kosum: python -m scripts.k23_on_analiz   (~2 dk)  SAF ASCII. Rapor-only.
"""
from __future__ import annotations

import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "k23_on_analiz.log"
PITCH = 0.5
ASY = "ASY-0176446"


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("K-23 ON-ANALIZ — ASY zincir yapisi (K-19 v2 282.0mm layout)")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n=4 ({time.perf_counter() - t:.0f}s)")

    # --- ASY bbox tablosu ----------------------------------------------------
    asy = [p for p in pls if p.name == ASY]
    B = {}
    for p in asy:
        g = lookup[p.part_id].orientations[p.orientation_idx].grid
        zs = np.flatnonzero(g.any(axis=(0, 1)))
        B[p.part_id] = (p.x, p.x + g.shape[0], p.y, p.y + g.shape[1],
                        p.z, p.z + int(zs[-1]) + 1)
    log(f"ASY adedi: {len(asy)} | govde yuksekligi (poz-bazli) ornek: "
        f"{sorted({(b[5]-b[4]) * PITCH for b in B.values()})}")

    # --- ebeveyn: tabanim (z0) hangi ASY'nin [z0,z1) araliginda + xy kesisim;
    #     en derin gomuldugum sec ---------------------------------------------
    parent = {}
    for pid, b in B.items():
        best = None
        for qid, c in B.items():
            if qid == pid:
                continue
            if not (b[0] < c[1] and c[0] < b[1] and b[2] < c[3] and c[2] < b[3]):
                continue
            if c[4] < b[4] < c[5]:  # tabanim onun govdesinin icinde
                depth = c[5] - b[4]
                if best is None or depth > best[1]:
                    best = (qid, depth)
        parent[pid] = best  # None = zincir koku (plakaya/dugmeye oturan)

    roots = [pid for pid, pr in parent.items() if pr is None]
    kids = defaultdict(list)
    for pid, pr in parent.items():
        if pr is not None:
            kids[pr[0]].append(pid)

    # zincir = kokten en derine yol; halka sayisi = agactaki dugumler
    def chain_len(root):
        n, stack, deepest = 0, [root], root
        while stack:
            cur = stack.pop()
            n += 1
            for k in kids.get(cur, []):
                stack.append(k)
                if B[k][5] > B[deepest][5]:
                    deepest = k
        return n, deepest

    log("")
    log(f"[1] ZINCIR YAPISI: {len(roots)} kok (paralel zincir)")
    tops = []
    sizes = []
    steps = []
    for r in sorted(roots, key=lambda q: -B[q][5]):
        n, deepest = chain_len(r)
        sizes.append(n)
        top = B[deepest][5] * PITCH
        tops.append(top)
        base = B[r][4] * PITCH
        if n > 1:
            steps.append((top - base - (B[r][5] - B[r][4]) * PITCH) / (n - 1))
        log(f"    kok {r}: halka={n:2d}  taban={base:6.1f}  tepe={top:6.1f}mm")
    sizes_arr = np.array(sizes)
    log(f"    halka dagilimi: toplam={sizes_arr.sum()} | ort={sizes_arr.mean():.1f} "
        f"| min={sizes_arr.min()} | max={sizes_arr.max()}")
    if steps:
        log(f"    zincir z-adimi (halka basina): ort {np.mean(steps):.1f}mm "
            f"| medyan {np.median(steps):.1f}mm")

    # --- [3] denge tavani ----------------------------------------------------
    log("")
    log("[3] DENGE HESABI (analitik, kosusuz):")
    K = len(roots)
    n_tot = int(sizes_arr.sum())
    govde = float(np.median([(b[5] - b[4]) * PITCH for b in B.values()]))
    s = float(np.median(steps)) if steps else 0.0
    taban = float(np.median([B[r][4] * PITCH for r in roots]))
    dengeli_L = int(np.ceil(n_tot / K))
    dengeli_tavan = taban + govde + (dengeli_L - 1) * s
    log(f"    mevcut: K={K} zincir, en dolu={sizes_arr.max()} halka, tavan 282.0")
    log(f"    dengeli dagitim: L=ceil({n_tot}/{K})={dengeli_L} -> tahmini tavan "
        f"~ {taban:.0f} + {govde:.0f} + {dengeli_L - 1}*{s:.1f} = {dengeli_tavan:.1f}mm")
    hedef = 250.5
    if s > 0:
        L_hedef = int((hedef - taban - govde) / s) + 1
        K_hedef = int(np.ceil(n_tot / max(L_hedef, 1)))
        log(f"    250.5 hedefi icin: zincir boyu <= {L_hedef} halka -> en az "
            f"{K_hedef} zincir gerekir (mevcut {K})")
    log("")
    if dengeli_tavan < 282.0 - 1.0:
        log("KARAR GIRDISI: dengeli-dagitim tavani 282'nin ALTINDA -> zincirler "
            "DENGESIZ, K-23 sira/dengeleme kosusu UMUTLU.")
    else:
        log("KARAR GIRDISI: zincirler zaten ~dengeli -> yeni zincir icin taban "
            "alani yok; K-23 dusuk umutlu (6GB kabuk tavani ~282 yapissal).")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
