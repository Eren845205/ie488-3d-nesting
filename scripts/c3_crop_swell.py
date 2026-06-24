"""c3_crop_swell.py — (A) NO-GO kok-neden DOGRULAMA: ortak-crop GERCEKTEN sisiyor mu?

HIPOTEZ (7b'de varsayildi, OLCULMEDI): plan3 yavasladi cunku parcalar anizotropik -> ortak crop
max-kernel'e gore sisiyor -> her oryant gereginden buyuk occ-FFT. plan1 izotropik -> az sisme.

BU SCRIPT hipotezi OLCER (implementasyondan ONCE): gercek decode sirasinda her parca-adiminda
  - baseline maliyet = SUM_oryant FFTcost(crop_o)        (her oryant kendi crop'u, occ-FFT ayri)
  - shared  maliyet = FFTcost(ortak_crop) + SUM kernelFFT (occ-FFT 1 kez, ortak buyuk crop)
FFTcost(n) ~ n*log2(n) (FFT karmasikligi; sabit carpan iptal -> oran anlamli). occ-FFT genelde
baskin (crop >> kernel). Eger shared/baseline plan1'de <1 (kazanc) ama plan3'te >1 (kayip) ->
HIPOTEZ DOGRU + maliyet-tabanli parca-bazli karar (ucuz olani sec) plan3'u baseline'a dondururdu.
Eger oran iki veride de benzerse -> baska kok-neden, maliyet-modeli COZMEZ.

Gercek decode_gpu yolunu calistirir; her parcada occ-bbox'tan baseline+ortak crop boyutlarini cikarir
(FFT YAPMAZ, sadece BOYUT -> maliyet; hizli + GPU OOM yok). URETIME DOKUNMAZ — scripts/.
Kullanim: python scripts/c3_crop_swell.py [plan1|plan3|all] [n]
"""
from __future__ import annotations
import sys, math
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.instances.pitch import suggest_nfv_pitch
from src.nesting3d.capabilities import probe_capabilities
from src.nesting3d.extreme_point import OccupancyBin3D
from src.nesting3d.fft_backend import get_backend, blb_xybbox
from src.nesting3d.parallel_decode import _eligible_orients, _nz_limit

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
MARGIN = 1
DATASETS = {
    "plan1": {"dir": VERILER / "Plan1" / "Plan1", "wd": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan3": {"dir": VERILER / "Plan3" / "Plan3", "wd": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def _fftcost(shape, ker):
    """occ-FFT maliyeti ~ full*log2(full), full = crop + kernel - 1 (rfftn boyutu)."""
    full = [s + k - 1 for s, k in zip(shape, ker)]
    n = 1
    for v in full:
        n *= v
    return n * math.log2(max(n, 2))


def _load(ds):
    c = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(c["dir"].glob("*.stl"))}
    kwargs = {}
    if c["wd"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = c["wd"]
    res = build_instance_from_order(stl_map, c["qty"],
                                    persist_dir=_ROOT / "data" / "mail_stl" / f"swell_{ds}", **kwargs)
    return res.instance


def run_one(ds, caps, n_or):
    print(f"\n{'=' * 74}\n[{ds}] n={n_or}", flush=True)
    inst = _load(ds)
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    pitch, _, _ = suggest_nfv_pitch(inst, plate_w_mm=pw, plate_d_mm=pd, ram_bytes=caps.ram_bytes)
    parts = to_voxel_parts(inst, pitch, n_orientations=n_or, margin=MARGIN)
    nx, ny = int(pw // pitch), int(pd // pitch)
    print(f"  pitch={pitch:.2f} | {len(parts)} parca {nx}x{ny}vox", flush=True)

    # gercek decode (CPU scipy, BIREBIR yerlesim) — occ ilerletmek icin; her parcada maliyet cikar
    fm, _ = get_backend("scipy")
    ob = OccupancyBin3D(nx, ny, nz_limit=_nz_limit(pitch), pitch=pitch)

    tot_base = 0.0; tot_shared = 0.0
    swell_ratios = []        # ortak-crop hacmi / ort. baseline-crop hacmi
    aniso = []               # parca-ici max-kernel-hacmi / min-kernel-hacmi
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        elig = _eligible_orients(part, nx, ny)
        if not elig:
            continue
        occ = ob.occupancy
        # occ dolu-xy-bbox (ortak, kernel-bagimsiz)
        if occ.any():
            xs = np.where(occ.any(axis=(1, 2)))[0]
            ys = np.where(occ.any(axis=(0, 2)))[0]
            x0, x1 = int(xs[0]), int(xs[-1]) + 1
            y0, y1 = int(ys[0]), int(ys[-1]) + 1
            zspan = int(occ.any(axis=(0, 1)).sum())
        else:
            x0 = y0 = 0; x1 = y1 = 1; zspan = 1
        kers = [o.grid.shape for _, o in elig]
        max_fw = max(k[0] for k in kers); max_fd = max(k[1] for k in kers)
        max_fh = max(k[2] for k in kers)
        kvol = [k[0] * k[1] * k[2] for k in kers]
        aniso.append(max(kvol) / max(min(kvol), 1))

        # baseline: her oryant KENDI crop'u + KENDI full'unda 3 transform (occ-FFT + kernel-FFT + irfftn)
        n_k = len(kers)
        base_cost = 0.0; base_crop_vol = 0.0
        for (fw, fd, fh) in kers:
            cw = min(nx, x1 + (fw - 1)) - max(0, x0 - (fw - 1))
            cd = min(ny, y1 + (fd - 1)) - max(0, y0 - (fd - 1))
            cz = min(_nz_limit(pitch), fh + 4)
            base_cost += 3.0 * _fftcost((cw, cd, cz), (fw, fd, fh))  # occ + kernel + ters, kendi boyutu
            base_crop_vol += cw * cd * cz
        # shared: ortak crop (occ-bbox + MAX kernel). occ-FFT 1 KEZ ortak boyutta; AMA her oryant
        # kernel-FFT + irfftn'i de ORTAK BUYUK boyutta yapar (prototipteki gercek davranis).
        sw = min(nx, x1 + (max_fw - 1)) - max(0, x0 - (max_fw - 1))
        sd = min(ny, y1 + (max_fd - 1)) - max(0, y0 - (max_fd - 1))
        sz = min(_nz_limit(pitch), max_fh + 4)
        cost_one = _fftcost((sw, sd, sz), (max_fw, max_fd, max_fh))  # ortak full bir transform
        shared_cost = cost_one * (1 + 2 * n_k)  # 1 occ-FFT + n kernel-FFT + n irfftn (hepsi ortak boyut)
        tot_base += base_cost; tot_shared += shared_cost
        avg_base_crop = base_crop_vol / len(kers)
        swell_ratios.append((sw * sd * sz) / max(avg_base_crop, 1))

        # occ ilerlet (gercek BLB yerlesim — birebir occ evrimi)
        cur_max = ob.max_height_voxels()
        best = None; best_key = None
        for oi, orient in elig:
            o = blb_xybbox(occ, orient.grid, fm)
            if o is None:
                continue
            fh = orient.grid.shape[2]
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            continue
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)

    ratio = tot_shared / tot_base if tot_base else 0
    print(f"  parca-ici anizotropi (max/min kernel-hacim): ort {np.mean(aniso):.1f}x "
          f"(medyan {np.median(aniso):.1f}x)", flush=True)
    print(f"  ortak-crop SISME (shared crop / ort. baseline crop): ort {np.mean(swell_ratios):.2f}x "
          f"(medyan {np.median(swell_ratios):.2f}x)", flush=True)
    print(f"  TAHMINI FFT maliyet orani (shared/baseline): {ratio:.2f}  "
          f"-> {'KAZANC (paylas)' if ratio < 1 else 'KAYIP (sisme baskin)'}", flush=True)
    return ds, float(np.mean(aniso)), float(np.mean(swell_ratios)), ratio


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    n_or = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    caps = probe_capabilities()
    print("=" * 74)
    print(f"(A) KOK-NEDEN: ortak-crop sisme hipotezi DOGRULAMA — {caps.summary()}")
    print("=" * 74, flush=True)
    todo = ["plan1", "plan3"] if arg == "all" else [arg]
    rows = []
    for ds in todo:
        try:
            rows.append(run_one(ds, caps, n_or))
        except Exception as e:
            import traceback
            print(f"\n[{ds}] HATA: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()

    print(f"\n{'=' * 74}\nOZET — hipotez: plan3 sisme>1 (kayip), plan1 ~1 veya <1 (kazanc)?")
    print(f"{'veri':>7} | {'anizotropi':>10} | {'crop-sisme':>10} | {'FFT-oran':>8} | {'beklenen':>14}")
    for ds, an, sw, r in rows:
        exp = "KAZANC" if r < 1 else "KAYIP"
        print(f"{ds:>7} | {an:9.1f}x | {sw:9.2f}x | {r:8.2f} | {exp:>14}", flush=True)
    print("\nHIPOTEZ DOGRU ise: plan1 dusuk-anizotropi/dusuk-sisme/oran<1, plan3 yuksek/yuksek/oran>1.")
    print("-> O zaman MALIYET-TABANLI parca-bazli karar (oran<1 ise paylas, degilse baseline) GENEL")
    print("   cozum: her parca kendi geometrisinden karar verir, asla baseline'dan kotu olmaz.")
    print("HIPOTEZ YANLIS ise (oranlar benzer): baska kok-neden, maliyet-modeli COZMEZ -> dur.")
    print("=" * 74)


if __name__ == "__main__":
    main()
