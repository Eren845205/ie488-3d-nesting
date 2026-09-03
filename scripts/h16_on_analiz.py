# -*- coding: utf-8 -*-
"""h16_on_analiz.py — H-16 ON-ANALIZ: dirty-region drop_map onbellegi MALIYET MODELI.

HIPOTEZ (H-16): fine dblf geciste her yerlestirmeden sonra drop_map'in TAMAMI
yeniden hesaplaniyor. Oysa place() heightmap'i YALNIZ yerlesen parcanin xy-bbox
penceresinde degistirir. Bir aday (x,y) icin drop_map ciktisi Z[x,y] yalniz
H[x:x+fw, y:y+fh] penceresine bagli -> yalniz KIRLI bolgeyle kesisen adaylar
degisir. Dirty-region onbellegi ile fine 514s -> ~100-150s bandina inebilir mi?

KARAR VERMEDEN once maliyet modeli OLCULUR (tahmin degil). Uretim koduna
DOKUNULMAZ — yalniz olcum.

Olculenler:
  1) drop_map cagri envanteri (fine dblf, deneme4 @0.5, wall_aware grid):
     cagri sayisi, cagri basi ort/median sure, grid nx*ny, footprint pencere
     dagilimi, fast-path payi.
  2) Kirlilik: her yerlestirmeden sonra DEGISEN hucrelerin xy-bbox alani /
     grid alani -> median/p90/max. Ayni-tip ardisik bloklarda footprint sabit.
  3) Dirty-pencere SIZINTI kontrolu: ardisik iki drop_map ciktisi diff'lenir;
     degisen bolge beklenen dirty-pencere (changed-bbox + (fw-1,fh-1)) icinde
     mi? Sizinti varsa hipotez CURUR.
  4) Bit-ozdeslik: N ornekte full drop_map(H_new) == (Z_prev + dirty-pencere
     yerel yeniden-hesap) mi (np.array_equal)?
  5) Maliyet modeli: dirty_oran * drop_toplam + ek yuk -> yeni fine bandi;
     Amdahl -> toplam kosu tavani.

Kosum: python -m scripts.h16_on_analiz [STRIDE=25] [N_BIT=20]   SAF ASCII.
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np  # noqa: E402

from src.nesting3d.bin3d import Bin3D  # noqa: E402
from src.nesting3d.instances.stl_order_loader import build_instance_from_order  # noqa: E402
from src.nesting3d.instances.format import to_voxel_parts  # noqa: E402
from scripts.c3_generality import DATASETS  # noqa: E402

# GUVENLIK: pickle KENDI kosumuzun ciktisi (K-19 v2, repo ici kalici kopya).
PKL = _ROOT / "data" / "mail_stl" / "k19v2_placements_B001.pkl"
LOG = Path(__file__).parent / "h16_on_analiz.log"
PITCH = 0.5
STRIDE = int(sys.argv[1]) if len(sys.argv) > 1 else 25
N_BIT = int(sys.argv[2]) if len(sys.argv) > 2 else 20
GERCEK_FINE_S = 514.0   # uretim kosusu fine dblf payi (553s toplamin %93'u)
GERCEK_TOTAL_S = 553.0  # kabuk yolu uretim toplam


def log(msg: str = "") -> None:
    print(msg, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def drop_region(H: np.ndarray, orient, x0: int, x1: int, y0: int, y1: int,
                z_clear: int) -> np.ndarray:
    """Aday alt-dikdortgen [x0:x1, y0:y1] icin YEREL drop hesabi.

    _drop_map_loop ile ayni tamsayi max-reduksiyonu (dolu kolonlar uzerinde),
    yalniz aday indeks penceresi kaydirilarak. max birlesmeli/tamsayi ->
    full drop_map ile BIRE BIR ayni sonuc (yalniz yerel bolge). Uretim
    disindaki bagimsiz referans hesap.
    """
    filled = orient.filled
    ci, cj = np.nonzero(filled)
    bot = orient.bottom
    Z = np.zeros((x1 - x0, y1 - y0), dtype=np.int32)
    for i, j in zip(ci.tolist(), cj.tolist()):
        b = int(bot[i, j])
        sub = H[x0 + i:x1 + i, y0 + j:y1 + j].astype(np.int32) - b
        np.maximum(Z, sub, out=Z)
    np.maximum(Z, 0, out=Z)
    if z_clear:
        Z[Z > 0] += z_clear
    return Z


def dirty_window(changed_bbox, fw: int, fh: int, npx: int, npy: int):
    """Degisen H bbox'i (r0,r1,c0,c1) + aday footprint (fw,fh) -> dirty aday
    indeks penceresi [wx0:wx1, wy0:wy1] (clamp'li). Bos changed -> None."""
    if changed_bbox is None:
        return None
    r0, r1, c0, c1 = changed_bbox
    wx0 = max(0, r0 - fw + 1)
    wx1 = min(npx, r1)
    wy0 = max(0, c0 - fh + 1)
    wy1 = min(npy, c1)
    if wx0 >= wx1 or wy0 >= wy1:
        return None
    return wx0, wx1, wy0, wy1


def main() -> None:
    t_all = time.perf_counter()
    log("=" * 78)
    log(f"H-16 ON-ANALIZ — dirty-region drop_map maliyet modeli "
        f"(stride={STRIDE}, N_bit={N_BIT})")
    log("=" * 78)

    with PKL.open("rb") as fh:
        data = pickle.load(fh)
    pls = data["placements"]
    log(f"K-19 v2 replay: {len(pls)} yerlestirme, height={data['height_mm']}mm, "
        f"pitch={data['pitch_mm']}")

    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    res = build_instance_from_order(
        stl_map, cfg["qty"], persist_dir=_ROOT / "data" / "mail_stl" / "gen_deneme4")
    pw = float(res.instance.container.width_mm)
    pd = float(res.instance.container.depth_mm)

    t = time.perf_counter()
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=4)
    lookup = {p.id: p for p in parts}
    log(f"voxelize @0.5 n=4 ({time.perf_counter() - t:.0f}s)")

    b = Bin3D(pw, pd, PITCH, z_clearance=1)
    grid_area = b.nx * b.ny
    log(f"grid: nx={b.nx} ny={b.ny} (alan={grid_area} hucre, "
        f"plaka {pw:.1f}x{pd:.1f}mm @ {PITCH}mm)")

    # copy ek-yuk olcumu (dirty-cache basina Z_prev.copy())
    _z = np.empty((b.nx, b.ny), dtype=np.int32)
    tc = time.perf_counter()
    for _ in range(50):
        _ = _z.copy()
    copy_s = (time.perf_counter() - tc) / 50.0
    log(f"grid copy ek-yuk: {copy_s * 1e3:.3f} ms/cagri")
    log("")

    # -- PASS: replay + olcumler ------------------------------------------
    call_t = []          # (1) olculen full drop_map sureleri (stride'da)
    call_fast = []       # fast-path bayragi
    call_fw = []         # footprint fw
    call_fh = []         # footprint fh
    call_npxy = []       # aday sayisi npx*npy
    dirty_frac = []      # (2) her yerlestirme: changed-bbox alan / grid alan
    changed_cells = []   # degisen hucre sayisi
    win_frac = []        # (2b) aday dirty-pencere alan / grid alan (ayni orient)

    # (3)+(4) icin ornek indisleri
    n = len(pls)
    bit_idx = set(np.linspace(0, n - 1, min(N_BIT, n)).astype(int).tolist())
    leak_total = 0
    leak_cases = 0
    bit_ok = 0
    bit_run = 0

    for k, p in enumerate(pls):
        part = lookup[p.part_id]
        orient = part.orientations[p.orientation_idx]
        fw, fh = orient.filled.shape
        npx, npy = b.nx - fw + 1, b.ny - fh + 1

        measure = (k % STRIDE == 0 or k < 2)
        do_bit = k in bit_idx

        # --- (1) full drop_map sure olcumu (stride'da) ---
        if measure and npx > 0 and npy > 0:
            t0 = time.perf_counter()
            Zm = b.drop_map(orient)
            dt = time.perf_counter() - t0
            fast = b._drop_map_fast(orient, npx, npy) is not None
            call_t.append(dt)
            call_fast.append(fast)
            call_fw.append(fw)
            call_fh.append(fh)
            call_npxy.append(npx * npy)

        # --- (3)+(4) sizinti + bit-ozdeslik: Z_prev (place ONCESI) ---
        Zprev = None
        if do_bit and npx > 0 and npy > 0:
            Zprev = b.drop_map(orient).copy()
            Hprev = b.height.copy()

        # --- degisen hucre bbox'i (place oncesi/sonrasi) ---
        sub_before = b.height[p.x:p.x + fw, p.y:p.y + fh].copy()
        b.place(part, p.orientation_idx, p.x, p.y, p.z)
        sub_after = b.height[p.x:p.x + fw, p.y:p.y + fh]
        chg = sub_after != sub_before
        ncell = int(chg.sum())
        changed_cells.append(ncell)
        if ncell:
            ri, cj = np.nonzero(chg)
            r0, r1 = p.x + int(ri.min()), p.x + int(ri.max()) + 1
            c0, c1 = p.y + int(cj.min()), p.y + int(cj.max()) + 1
            bbox = (r0, r1, c0, c1)
            dirty_frac.append((r1 - r0) * (c1 - c0) / grid_area)
            win = dirty_window(bbox, fw, fh, npx, npy)
            if win is not None:
                wx0, wx1, wy0, wy1 = win
                win_frac.append((wx1 - wx0) * (wy1 - wy0) / grid_area)
        else:
            bbox = None
            dirty_frac.append(0.0)

        # --- (3)+(4) sizinti + bit ozdeslik degerlendirme ---
        if Zprev is not None:
            Zfull = b.drop_map(orient)   # place SONRASI full
            diff = Zfull != Zprev
            win = dirty_window(bbox, fw, fh, npx, npy)
            bit_run += 1
            if win is None:
                # H hic degismedi (parca plakaya sifir katki?) -> beklenen: diff bos
                leak = int(diff.sum())
                leak_total += leak
                if leak:
                    leak_cases += 1
                if not diff.any():
                    bit_ok += 1
                continue
            wx0, wx1, wy0, wy1 = win
            # sizinti: pencere DISINDA degisen var mi?
            mask = np.zeros_like(diff)
            mask[wx0:wx1, wy0:wy1] = True
            leak = int((diff & ~mask).sum())
            leak_total += leak
            if leak:
                leak_cases += 1
            # bit-ozdeslik: Zprev + yerel yeniden-hesap == Zfull ?
            Zinc = Zprev.copy()
            Zinc[wx0:wx1, wy0:wy1] = drop_region(
                b.height, orient, wx0, wx1, wy0, wy1, b.z_clearance)
            if np.array_equal(Zinc, Zfull):
                bit_ok += 1

    assert abs(b.max_height_mm() - float(data["height_mm"])) < 1e-6, "replay bozuk"
    log(f"replay dogru (282.0) | olculen full drop_map cagri: {len(call_t)}")
    log("")

    # -- (a) CAGRI ENVANTERI ----------------------------------------------
    ct = np.array(call_t)
    log("(a) DROP_MAP CAGRI ENVANTERI  [KANITLI: olculen ornekler]")
    log(f"  olculen cagri = {len(ct)} (stride={STRIDE}); dblf toplam cagri "
        f"= {n} parca x oryantasyon-sayisi [her parca TUM aci denenir]")
    log(f"  cagri basi sure: ort={ct.mean() * 1e3:.1f} ms  "
        f"median={np.median(ct) * 1e3:.1f} ms  "
        f"p90={np.percentile(ct, 90) * 1e3:.1f} ms  max={ct.max() * 1e3:.1f} ms")
    log(f"  fast-path payi: %{100 * np.mean(call_fast):.0f} "
        f"(konkav/degisken-taban -> genel yol)")
    fwh = np.array([call_fw, call_fh]).T
    log(f"  footprint (fw x fh): median={int(np.median(call_fw))}x"
        f"{int(np.median(call_fh))}  "
        f"min={int(np.min(call_fw))}x{int(np.min(call_fh))}  "
        f"max={int(np.max(call_fw))}x{int(np.max(call_fh))}")
    log(f"  aday sayisi (npx*npy): median={int(np.median(call_npxy))}  "
        f"grid alani={grid_area}")
    log("")

    # -- (b) KIRLILIK DAGILIMI --------------------------------------------
    df = np.array(dirty_frac)
    cc = np.array(changed_cells)
    wf = np.array(win_frac) if win_frac else np.array([0.0])
    log("(b) KIRLILIK DAGILIMI  [KANITLI: 588 yerlestirmenin tamami olculdu]")
    log(f"  degisen-hucre bbox alani / grid alani:")
    log(f"    median=%{100 * np.median(df):.3f}  p90=%{100 * np.percentile(df, 90):.3f}"
        f"  max=%{100 * df.max():.3f}  ort=%{100 * df.mean():.3f}")
    log(f"  degisen hucre sayisi: median={int(np.median(cc))}  "
        f"p90={int(np.percentile(cc, 90))}  max={int(cc.max())}")
    log(f"  ADAY dirty-pencere alani / grid alani (footprint (fw,fh) genisletmeli):")
    log(f"    median=%{100 * np.median(wf):.2f}  p90=%{100 * np.percentile(wf, 90):.2f}"
        f"  max=%{100 * wf.max():.2f}  ort=%{100 * wf.mean():.2f}")
    log(f"    => bir yerlestirmenin ETKILEDIGI aday orani ~%{100 * wf.mean():.1f} "
        f"(gerisi = onbellekten AYNEN korunur)")
    log("")

    # -- (c) SIZINTI KONTROLU ---------------------------------------------
    log("(c) DIRTY-PENCERE SIZINTI KONTROLU  [KANITLI: {} ornek]".format(bit_run))
    log(f"  pencere DISINDA degisen hucre toplami: {leak_total}  "
        f"(sizintili vaka: {leak_cases}/{bit_run})")
    if leak_total == 0:
        log("  SONUC: SIZINTI YOK -> full drop_map ile onceki-cikti farki TAM olarak")
        log("         beklenen dirty-pencere icinde. HIPOTEZ (H-16) DOGRULANDI.")
    else:
        log("  SONUC: SIZINTI VAR -> degisim dirty-pencere disina tasti. "
            "HIPOTEZ CURUDU (yerel yeniden-hesap yetmez).")
    log("")

    # -- (d) BIT-OZDESLIK -------------------------------------------------
    log("(d) BIT-OZDESLIK KONTROLU  [KANITLI]")
    log(f"  full drop_map(H_new) == (Z_prev + yerel yeniden-hesap): "
        f"{bit_ok}/{bit_run}")
    if bit_ok == bit_run:
        log("  SONUC: yerel yeniden-hesap full ile BIRE BIR ozdes (tamsayi max-")
        log("         reduksiyon -> kalite garantisi korunur, yukseklik degismez).")
    else:
        log("  SONUC: ozdeslik SAGLANMADI -> dirty-cache kalite-notr DEGIL. RISK.")
    log("")

    # -- (e) MALIYET MODELI -----------------------------------------------
    log("(e) MALIYET MODELI + TAVAN")
    drop_frac_of_fine = GERCEK_FINE_S / GERCEK_TOTAL_S  # ~0.93 (fine payi)
    log(f"  [KANITLI-ATIF] fine dblf = {GERCEK_FINE_S:.0f}s / toplam "
        f"{GERCEK_TOTAL_S:.0f}s (fine payi %{100 * drop_frac_of_fine:.0f})")
    # drop_map fine surenin ~tamami (h15: drop dongusu baskin). Ek: settle/sort.
    # Yeni maliyet ~ dirty_oran * full_maliyet + copy ek-yuk (cagri basi).
    d_med = float(np.mean(wf))    # ort etkilenen aday orani (dogrusal maliyet)
    d_p90 = float(np.percentile(wf, 90))
    # cagri sayisi tahmini: her parca ort. oryantasyon denemesi
    # (KANITLI degil -> ekstrapolasyon). Muhafazakar: dirty oran x fine.
    new_low = d_med * GERCEK_FINE_S
    new_high = d_p90 * GERCEK_FINE_S
    # copy ek-yuk: cagri basi copy; toplam cagri ~ full drop cagrilari. Ust
    # sinir: fine sure / ort-cagri-sure kadar cagri.
    est_calls = GERCEK_FINE_S / max(ct.mean(), 1e-9)
    copy_overhead = est_calls * copy_s
    log(f"  [KANITLI] etkilenen aday orani: ort=%{100 * d_med:.1f} "
        f"p90=%{100 * d_p90:.1f}")
    log(f"  [KANITLI] copy ek-yuk/cagri={copy_s * 1e3:.3f}ms; tahmini cagri "
        f"~{est_calls:.0f} -> copy toplam ~{copy_overhead:.1f}s [EKSTRAPOLE]")
    log(f"  [EKSTRAPOLE] yeni fine bandi ~ dirty_oran x {GERCEK_FINE_S:.0f}s + copy:")
    log(f"    alt  ~{new_low + copy_overhead:.0f}s (ort kirlilik)")
    log(f"    ust  ~{new_high + copy_overhead:.0f}s (p90 kirlilik)")
    # Amdahl: fine disi sabit
    fixed = GERCEK_TOTAL_S - GERCEK_FINE_S
    tot_low = fixed + new_low + copy_overhead
    tot_high = fixed + new_high + copy_overhead
    log(f"  [EKSTRAPOLE] Amdahl: fine-disi sabit ={fixed:.0f}s "
        f"(coarse+settle+voxelize+sort)")
    log(f"    toplam kosu tavani bandi: ~{tot_low:.0f}s .. ~{tot_high:.0f}s "
        f"(uretim {GERCEK_TOTAL_S:.0f}s'den "
        f"{GERCEK_TOTAL_S / tot_high:.1f}x .. {GERCEK_TOTAL_S / tot_low:.1f}x)")
    log("")

    # -- (f) GO / NO-GO ---------------------------------------------------
    log("(f) GO / NO-GO ONERISI")
    hyp_ok = (leak_total == 0) and (bit_ok == bit_run)
    if hyp_ok and d_med < 0.20:
        log("  ONERI: GO (kesif/prototip). Hipotez dogrulandi (sizinti yok + "
            "bit-ozdes), etkilenen aday orani dusuk -> teorik kazanc buyuk.")
    elif hyp_ok:
        log("  ONERI: TEMKINLI GO. Ozdeslik+sizintisiz ama etkilenen aday orani "
            "yuksek -> kazanc sinirli, olcum-once.")
    else:
        log("  ONERI: NO-GO / DUR. Sizinti veya bit-ozdeslik ihlali -> kalite "
            "riski. Once kok neden.")
    log("  RISKLER:")
    log("   - Z_prev'i oryantasyon BASINA saklamak gerekir (aday sayisi kadar")
    log("     grid; RAM: aday-orient x nx*ny int32). Bellek tavani olculmeli.")
    log("   - Sira bagimliligi: farkli parca yerlesince footprint (fw,fh) degisir")
    log("     -> dirty-pencere aday-footprint'e GENISLER; ort orani bunu icerir.")
    log("   - Ilk cagri (bos bin) tam hesap; kazanc ikinci cagridan itibaren.")
    log("   - est_calls/copy ekstrapolasyonu KANITLI degil; gercek entegrasyon")
    log("     olcumu GO sonrasi ilk adim olmali.")
    log("")
    log(f"TOPLAM PROB SURESI: {time.perf_counter() - t_all:.0f}s")


if __name__ == "__main__":
    main()
