"""c3_generality.py — GENELLİK KAPISI: NFV cavity Plan2-overfit mi, GENEL mi?

KULLANICI SORUSU: Bu yöntem bütün verilerde algoritmayı iyileştirir mi, yoksa
sadece bu plan üzerinde mi çalışan, overfit riski olan bir yöntem mi?

CEVAP STRATEJİSİ = doluluk SPEKTRUMUNDA NFV-greedy vs heightmap.
  Algoritma GENEL (Plan2'ye ayarlı sabit YOK — saf geometrik fftconvolve + BLB + largest-first).
  Ama KAZANÇ doluluğa bağlı olmalı:
    düşük doluluk (oyuklu)  -> NFV KAZANIR  (parçalar birbirinin oyuğuna girer)
    yüksek doluluk (kutu)   -> NFV ~heightmap (oyuk yok -> kazanç yok)
  KRİTİK SORU: kutu-benzeri veride NFV REGRESYONA giriyor mu?
    girmiyorsa  -> yöntem GENEL, güvenle bağlanır
    giriyorsa   -> overfit DEĞİL ama körlemesine bağlanamaz -> adaptif/best-of-both ŞART

Dataset arg: plan1 | plan2 | plan3 | deneme4 | boxy
Çıktı: parça sayısı, kutuluk (ort doluluk), heightmap(dblf), NFV(decode_fast), delta%.

ÜRETİME DOKUNMAZ — sadece scripts/, src/ salt-okunur. Kaba pitch (hızlı, adil kıyas).
"""
from __future__ import annotations
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import scipy.fft as _sfft
from scipy.signal import fftconvolve

_sfft.set_workers(max(1, (__import__("os").cpu_count() or 2)))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback

VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
PITCH, N_OR, MARGIN = 2.0, 4, 1

# --- Dataset config'leri (plate=None -> otomatik plaka, kıyas NFV vs heightmap aynı plakada) ---
DATASETS = {
    "plan1": {  # orta doluluk (braket / bobbin / gauge — daha katı parçalar)
        "stl_dir": VERILER / "Plan1" / "Plan1", "plate": None,
        "qty": {
            "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
            "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6,
            "811791-1": 19, "pyramid_with_doors": 5, "MTShoe": 1,
            "M18_toShopVac_Adapter": 2, "part262835": 2, "baseplate_v2": 1,
        },
    },
    "plan2": {  # ÇAPA — oyuklu (kutuluk ~0.07, parçalar %93 boş); bilinen 556 vs 740
        "stl_dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19),
        "qty": {
            "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
            "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
            "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
            "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
            "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
            "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
            "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
            "PO-TR155890-17789": 1, "PO-TR155308-17705": 1,
        },
    },
    "plan3": {  # kullanıcı adetleri (2026-06-23)
        "stl_dir": VERILER / "Plan3" / "Plan3", "plate": None,
        "qty": {
            "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
            "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
            "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
            "152000218": 7, "171600022": 4, "152000217": 7,
        },
    },
    "deneme4": {  # ilk dış-müşteri seti (2026-07-03, FSM) — ince-cidarlı kabuk ailesi
        # (0.8-1.35mm çan-düğme + 2 dev ROBT plakası). Magics referansı 250.24mm
        # (plaka bilinmiyor -> otomatik; hoca plaka cevabı gelince "plate" doldurulacak).
        # STL'ler repo içinde KALICI; adetler mail gövdesi "Ad - Sayı" + 588 checksum kanıtlı.
        "stl_dir": _ROOT / "data" / "mail_stl" / "mail_stl_AD786DF3", "plate": None,
        "qty": {
            "ASY-0176446": 62, "ASY-0176446-1": 126,
            "part239392_ROBT UST v27": 1, "part239391_ROBT ALT v27": 1,
            "01_202201790014_00-K179 Dugme Aksesuari": 12,
            "02_202201790002_T00-K179 Dugme Cift Fonksiyonlu": 12,
            "02_T00-K179 Dugme Cift Fonksiyonlu-25pcs": 26,  # gerçek adet 26 (mail+checksum; "-25pcs" dosya adı yanıltıcı)
            "03_00-K179 Dugme Tek Fonksiyonlu": 200,
            "04_T00-K179 Dugme Fonksiyonsuz": 56,
            "05_00-K179 WBT Dugme": 20,
            "09_00-K179 Dugme Kilidi": 27,
            "10_T00-K179 Kilitli Dugme": 25,
            "17_00-K179 SSB Dugme": 20,
        },
    },
}


def _boxy_stl_map_and_qty():
    """Saf kutu sentetik (doluluk ~1.0 — bbox'ı tam dolduran katı kutular).
    NFV'nin oyuk-fırsatı OLMAYAN veride regresyona girip girmediğini ölçer (stres testi)."""
    import trimesh
    specs = {  # (genişlik, derinlik, yükseklik mm) — çeşitli oranlar
        "box_60x40x30": (60, 40, 30), "box_50x50x50": (50, 50, 50),
        "box_80x30x20": (80, 30, 20), "box_45x45x70": (45, 45, 70),
        "box_35x90x25": (35, 90, 25),
    }
    qty = {"box_60x40x30": 20, "box_50x50x50": 14, "box_80x30x20": 16,
           "box_45x45x70": 10, "box_35x90x25": 12}
    stl_map = {}
    for name, ext in specs.items():
        m = trimesh.creation.box(extents=list(ext))
        data = m.export(file_type="stl")
        stl_map[name] = data if isinstance(data, (bytes, bytearray)) else data.encode()
    return stl_map, qty


def _blb(mask):
    z_any = mask.any(axis=(0, 1))
    if not z_any.any():
        return None
    zstar = int(np.argmax(z_any))
    sl = mask[:, :, zstar]
    ystar = int(np.argmax(sl.any(axis=0)))
    xstar = int(np.argmax(sl[:, ystar]))
    return xstar, ystar, zstar


def _blb_nfv_fast(ob, orient):
    """KADEMELİ z-dilim (c3_speed.py Faz4 — kalite-koruma birebir). Küçük dilimle başla,
    feasible bulununca dur; BLB min-z aradığından sonuç tam dilimle BİREBİR aynı."""
    fw, fd, fh = orient.grid.shape
    nz = ob.occupancy.shape[2]
    z_cap = fh + 4
    while True:
        z_lim = min(nz, z_cap)
        C = fftconvolve(ob.occupancy[:, :, :z_lim].astype(np.float64),
                        orient.grid[::-1, ::-1, ::-1].astype(np.float64), mode="valid")
        o = _blb(C < 0.5)
        if o is not None:
            return o
        if z_lim >= nz:
            return None
        z_cap *= 2


def decode_nfv(parts, nx, ny):
    """NFV-greedy decode (largest-first, cavity guard max(zt,cur_max)). c3_speed.decode_fast ile aynı."""
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None; best = None
        for oi, orient in enumerate(part.orientations):
            fw, fd, fh = orient.grid.shape
            if fw > nx or fd > ny:
                continue
            o = _blb_nfv_fast(ob, orient)
            if o is None:
                continue
            key = (max(o[2] + fh, cur_max), o[2] + fh, o[2], o[1], o[0], oi)
            if best_key is None or key < best_key:
                best_key, best = key, (oi, o[0], o[1], o[2])
        if best is None:
            (x, y, z), oi = _drop_fallback(ob, part)
            best = (oi, x, y, z)
        oi, x, y, z = best
        ob.place(part.orientations[oi], x, y, z)
    return ob.height_mm()


def kutuluk(parts):
    """Ortalama doluluk = volume_voxels / bbox_voxels (orientation 0). Hacim-ağırlıklı değil, parça-başı."""
    rs = []
    for p in parts:
        g = p.orientations[0].grid
        bbox = int(g.shape[0] * g.shape[1] * g.shape[2])
        if bbox:
            rs.append(p.volume_voxels / bbox)
    return float(np.mean(rs)) if rs else 0.0


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "boxy"
    print("=" * 70)
    print(f"C3 GENELLİK KAPISI — dataset={ds}  (pitch={PITCH}, n_or={N_OR})")
    print("=" * 70, flush=True)

    if ds == "boxy":
        stl_map, qty = _boxy_stl_map_and_qty()
        plate = None
    else:
        cfg = DATASETS[ds]
        stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
        qty = cfg["qty"]
        plate = cfg["plate"]
        eksik = set(k.lower() for k in qty) - set(k.lower() for k in stl_map)
        if eksik:
            print(f"  [UYARI] STL bulunamadı: {sorted(eksik)}", flush=True)

    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"gen_{ds}"}
    if plate is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = plate
    t = time.perf_counter()
    res = build_instance_from_order(stl_map, qty, **kwargs)
    parts = to_voxel_parts(res.instance, PITCH, n_orientations=N_OR, margin=MARGIN)
    cont = res.instance.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)
    ku = kutuluk(parts)
    print(f"voxelize: {len(parts)} parça, plaka {pw:.0f}x{pd:.0f}mm ({nx}x{ny} voxel), "
          f"kutuluk(ort doluluk)={ku:.3f}  ({time.perf_counter()-t:.0f}s)", flush=True)

    # [1] HEIGHTMAP baseline (dblf — bizim üretim yolu mantığı, kaba)
    t = time.perf_counter()
    _, hb = dblf(parts, lambda: Bin3D(pw, pd, PITCH, z_clearance=MARGIN))
    hm = hb.max_height_mm()
    print(f"[1] HEIGHTMAP : {hm:7.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    # [2] NFV-greedy (decode_fast)
    t = time.perf_counter()
    nfv = decode_nfv(parts, nx, ny)
    print(f"[2] NFV-greedy: {nfv:7.1f} mm  ({time.perf_counter()-t:.0f}s)", flush=True)

    delta = (hm - nfv) / hm * 100 if hm else 0.0
    print("-" * 70)
    print(f"  kutuluk={ku:.3f} | heightmap={hm:.1f} | NFV={nfv:.1f} | delta={delta:+.1f}% "
          f"({'NFV İYİ' if delta > 0.5 else 'NFV KÖTÜ' if delta < -0.5 else 'BERABERE'})")
    # Yorum
    if ku < 0.20:
        verdict = "BEKLENEN: NFV kazanmali (oyuklu)" + (" [OK]" if delta > 2 else " [FAIL] KAZANAMADI")
    elif ku > 0.55:
        verdict = "BEKLENEN: NFV ~heightmap, regresyon YOK" + \
                  (" [OK]" if delta > -2 else " [FAIL] REGRESYON -> adaptif-guard sart")
    else:
        verdict = "orta doluluk: NFV kazanabilir veya berabere (regresyon olmamali)" + \
                  (" [FAIL] REGRESYON" if delta < -2 else " [OK]")
    print(f"  -> {verdict}")
    print("=" * 70)


if __name__ == "__main__":
    main()
