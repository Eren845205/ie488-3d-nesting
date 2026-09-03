# -*- coding: utf-8 -*-
"""f4a_ayrisim.py — F4-A: K-19 v2 yerlesiminden 95mm kazancin anatomisi (probe).

Girdi: data/mail_stl/k19v2_placements_B001.pkl ({placements, pitch_mm=0.5,
height_mm=282.0}; 588 Placement3D — K-19 v2 uretim kosusunun fine yerlesimi).

Yontem: parcalar coarse_to_fine fine asamasinin AYNI cagrisiyla yeniden
voxelize edilir: to_voxel_parts(instance, 0.5, n_orientations=4)  [margin=0,
method="slice" default]. rotation_matrices prefix-stable oldugundan idx 0-3
her n>=4'te ayni poza denk gelir; DOGRULAMA KAPISI yine de zorunlu:
yerlesim yeniden-oynatilinca max yukseklik TAM 282.0mm (564 voxel) cikmali
ve hicbir voxel cifte-dolu olmamali. Kapi gecmezse analiz YAZDIRILMAZ.

Analizler (rapor-only, uretime dokunmaz):
  [1] cift-bazli z-ic-icelik  — bbox z-araligi ortusen + xy-ayakizi kesisen
      ciftler (telescoping payi) + tip->tip yuvalanma matrisi
  [2] z-dilim yanal doluluk    — 10mm bantlarda dolu-voxel / plaka-alani
  [3] tepe-yuzey kompozisyonu  — son 30mm'de hangi tipler (tavani kim kuruyor)

SAF ASCII cikti (cp1254 guvenli). Kullanim: python -m scripts.f4a_ayrisim
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

PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "f4a_ayrisim.log"
PITCH = 0.5
TOP_BAND_MM = 30.0


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log("F4-A AYRISIM ANALIZI — K-19 v2 (282.0mm) yerlesim anatomisi")
    log("=" * 78)

    # GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2 oturumu, repo ici kalici
    # kopya) — dis/guvenilmez kaynak degil; pickle.load bu dosya icin kabul.
    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]
    exp_h = float(data["height_mm"])
    assert float(data["pitch_mm"]) == PITCH, f"pitch uyusmuyor: {data['pitch_mm']}"
    log(f"pickle: {len(pls)} placement, beklenen yukseklik {exp_h}mm @ {PITCH}mm")

    # --- Instance + voxelize (coarse_to_fine fine cagrisiyla BIREBIR) --------
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    cont = res.instance.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)
    log(f"plaka (auto): {pw:.1f} x {pd:.1f} mm -> grid {nx} x {ny} @ {PITCH}mm")

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
    lookup = {p.id: p for p in parts}
    log(f"voxelize: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    missing = [p.part_id for p in pls if p.part_id not in lookup]
    assert not missing, f"eslesmeyen part_id: {missing[:5]} (+{len(missing)} adet)"

    # --- Yerlesim tablosu: her placement icin oryante grid + bbox ------------
    # rec: (placement, grid(bool nxp,nyp,nzp), x, y, z)
    recs = []
    for p in pls:
        g = lookup[p.part_id].orientations[p.orientation_idx].grid
        recs.append((p, g, p.x, p.y, p.z))
    nz = max(r[4] + r[1].shape[2] for r in recs)

    # --- DOGRULAMA KAPISI: 3D isgal grid'i (cakisma + yukseklik) -------------
    t = time.perf_counter()
    occ = np.zeros((nx, ny, nz), dtype=np.uint8)
    top_v = 0
    for p, g, x, y, z in recs:
        gx, gy, gz = g.shape
        occ[x:x + gx, y:y + gy, z:z + gz] += g.astype(np.uint8)
        # gercek dolu tepe (bbox degil): en ustteki dolu dilim
        zs = np.flatnonzero(g.any(axis=(0, 1)))
        top_v = max(top_v, z + int(zs[-1]) + 1)
    n_overlap = int((occ > 1).sum())
    got_h = top_v * PITCH
    log(f"KAPI: yukseklik {got_h:.1f}mm (beklenen {exp_h}), "
        f"cifte-dolu voxel = {n_overlap}  ({time.perf_counter() - t:.0f}s)")
    if n_overlap != 0 or abs(got_h - exp_h) > 1e-6:
        log("KAPI GECEMEDI — oryantasyon/param eslesmesi bozuk, analiz iptal.")
        sys.exit(1)
    log("KAPI GECTI — rekonstruksiyon birebir; analiz basliyor.")
    log("")

    # ==========================================================================
    # [1] CIFT-BAZLI Z-IC-ICELIK (telescoping) + tip->tip yuvalanma matrisi
    # ==========================================================================
    # bbox dizileri (voxel): x0,x1,y0,y1,z0,z1  (z1 = gercek dolu tepe, bbox'la
    # ayni cunku margin=0 crop grid'i siki keser; yine de grid.shape kullanilir)
    n = len(recs)
    B = np.zeros((n, 6), dtype=np.int64)
    names = []
    for i, (p, g, x, y, z) in enumerate(recs):
        B[i] = (x, x + g.shape[0], y, y + g.shape[1], z, z + g.shape[2])
        names.append(p.name)
    names = np.array(names)

    # vektorize cift testi: xy-bbox kesisimi VE z-araligi ortusmesi
    x0, x1, y0, y1, z0, z1 = (B[:, k] for k in range(6))
    XY = ((np.minimum(x1[:, None], x1[None, :]) > np.maximum(x0[:, None], x0[None, :]))
          & (np.minimum(y1[:, None], y1[None, :]) > np.maximum(y0[:, None], y0[None, :])))
    ZOV = (np.minimum(z1[:, None], z1[None, :])
           - np.maximum(z0[:, None], z0[None, :]))  # >0 = z-ortusme (voxel)
    np.fill_diagonal(XY, False)
    pair_mask = XY & (ZOV > 0)

    # tek yonlu say (i<j)
    iu = np.triu(pair_mask)
    pi, pj = np.nonzero(iu)
    ov_mm = ZOV[pi, pj] * PITCH
    log("[1] CIFT-BAZLI Z-IC-ICELIK (bbox duzeyi; xy-kesisen + z-ortusen ciftler)")
    log(f"    ic-ice cift sayisi : {len(pi)}  (588 parca, {n*(n-1)//2} olasi cift)")
    if len(pi):
        log(f"    z-ortusme mm       : toplam {ov_mm.sum():.0f} | ort {ov_mm.mean():.1f} "
            f"| medyan {np.median(ov_mm):.1f} | max {ov_mm.max():.1f}")

    # parca-basi yuvalanma derinligi: tabanim baska parcanin bbox'unun icinde mi?
    # depth_i = max_j( z1_j - z0_i ) , j: xy-kesisen ve z0_j < z0_i < z1_j
    inside = XY & (z0[None, :] < z0[:, None]) & (z0[:, None] < z1[None, :])
    depth_v = np.where(inside, z1[None, :] - z0[:, None], 0).max(axis=1)
    nested = depth_v > 0
    log(f"    tabani baska parcanin bbox'una gomulu parca: {int(nested.sum())}/{n} "
        f"(%{100.0 * nested.sum() / n:.0f})")
    log(f"    gomulme derinligi mm: ort {depth_v[nested].mean() * PITCH:.1f} | "
        f"medyan {np.median(depth_v[nested]) * PITCH:.1f} | "
        f"max {depth_v.max() * PITCH:.1f}" if nested.any() else "    (gomulu parca yok)")

    # tip->tip yuvalanma matrisi: alt(tip A) icine giren ust(tip B) sayisi.
    # "iceri girme" = B'nin tabani A'nin bbox z-araliginin icinde + xy kesisim.
    log("")
    log("    TIP->TIP YUVALANMA (satir=ALT parca tipi, sutun icine giren UST adedi)")
    mat: dict = defaultdict(lambda: defaultdict(int))
    li, lj = np.nonzero(inside)  # i = ust (giren), j = alt (kabul eden)
    for ii, jj in zip(li, lj):
        mat[names[jj]][names[ii]] += 1
    order = sorted({*names}, key=lambda s: s)
    kis = {nm: f"T{k:02d}" for k, nm in enumerate(order)}
    for nm in order:
        log(f"      {kis[nm]} = {nm}")
    hdr = "      ALT\\UST " + " ".join(f"{kis[nm]:>5s}" for nm in order)
    log(hdr)
    for a in order:
        row = mat.get(a, {})
        cells = " ".join(f"{row.get(b, 0):>5d}" for b in order)
        log(f"      {kis[a]:>8s} {cells}")

    # ==========================================================================
    # [2] Z-DILIM YANAL DOLULUK (10mm bantlar)
    # ==========================================================================
    log("")
    log("[2] Z-DILIM YANAL DOLULUK (dolu voxel / plaka hucresi, 10mm bant ort.)")
    slice_fill = occ.sum(axis=(0, 1)).astype(np.float64) / float(nx * ny)
    band = int(round(10.0 / PITCH))  # 20 dilim = 10mm
    for b0 in range(0, nz, band):
        b1 = min(b0 + band, nz)
        f = slice_fill[b0:b1].mean()
        bar = "#" * int(round(f * 60))
        log(f"    {b0 * PITCH:6.1f}-{b1 * PITCH:6.1f}mm  %{100 * f:5.1f}  {bar}")

    # ==========================================================================
    # [3] TEPE-YUZEY KOMPOZISYONU (son 30mm)
    # ==========================================================================
    log("")
    log(f"[3] TEPE-YUZEY KOMPOZISYONU (son {TOP_BAND_MM:.0f}mm = "
        f"{exp_h - TOP_BAND_MM:.0f}..{exp_h:.0f}mm)")
    zcut = int(round((exp_h - TOP_BAND_MM) / PITCH))
    band_vox: dict = defaultdict(int)
    band_parts: dict = defaultdict(int)
    type_top: dict = defaultdict(float)
    for p, g, x, y, z in recs:
        gz = g.shape[2]
        zs = np.flatnonzero(g.any(axis=(0, 1)))
        top_mm = (z + int(zs[-1]) + 1) * PITCH
        type_top[p.name] = max(type_top[p.name], top_mm)
        if z + gz > zcut:
            k0 = max(zcut - z, 0)
            band_vox[p.name] += int(g[:, :, k0:].sum())
            if top_mm > exp_h - TOP_BAND_MM:
                band_parts[p.name] += 1
    log("    tip | bant-voxel | bant-icinde-tepesi-olan parca | tipin max tepesi")
    for nm in sorted(type_top, key=lambda s: -band_vox.get(s, 0)):
        log(f"    {kis[nm]} {nm[:44]:44s} {band_vox.get(nm, 0):>9d} "
            f"{band_parts.get(nm, 0):>4d}  {type_top[nm]:7.1f}mm")

    log("")
    log(f"TOPLAM SURE: {time.perf_counter() - t_all:.0f}s")
    log("NOT: [1] bbox-duzeyi olcum (gercek voxel-yuvalanmasi degil) — 'ic-ice'")
    log("     etiketi kanitli CAKISMASIZ (kapi: 0 cifte-dolu voxel) bbox ortusmesi.")


if __name__ == "__main__":
    main()
