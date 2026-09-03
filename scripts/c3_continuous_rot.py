"""c3_continuous_rot.py — SUREKLI ROTASYON @ KABA PITCH (A1 on-fizibilite, OLC-ONCE).

KULLANICI SORUSU (2026-06-26): "Dusuk voxelization'da calismasi lazim. Pitch inceltmek
OOM veriyor; kazanc ince cozunurlugun eseri olmamali, SUREKLI ROTASYON'un eseri olmali."

HIPOTEZ (literatur Tur 03, A1): Magics'in sirri pitch DEGIL surekli rotasyon. Diskret
eksen-hizali oryantasyonlar (n=8/12/24) doygun (veritabani K-05); ama off-axis SUREKLI
aci parcalarin oyuga girmesini KABA pitch'te de acabilir.

KRITIK: OOM'a sokan PITCH inceltmek; oryantasyon SAYISI degil (FFT grid'i buyutmez, sadece
daha cok decode = lineer yavaslama). Yani bu deney 6GB'de YAPILABILIR.

TASARIM (diskret katki ile surekli katkiyi IZOLE et):
  L0  = n=8 eksen-hizali (uretim default, baz; Plan2 beklenen 522)
  A24 = 24 eksen-hizali (KONTROL: "daha cok DISKRET aci" — K-05 doygun diyor)
  Cxx = n=8 + SUREKLI egik acilar (ASIL hipotez: off-axis surekli rotasyon)
Her surekli/kontrol set n=8'i ICERIR -> kume-icerme: sonuc ASLA baz'dan kotu olamaz
(K-05 mantigi: greedy daha cok secenekle her adimda <=). Tek soru: ekstra pozlar DUSURUR mu?

URETIME DOKUNMAZ — sadece scripts/, src/ salt-okunur. [[feedback-windows-stdout-ascii]] ASCII.
Kullanim: python scripts/c3_continuous_rot.py [plan2|plan3|plan1]  [hizli|tam]
"""
from __future__ import annotations
import sys, math, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

from src.nesting3d.voxelize import rotation_matrices, voxelize_part, VoxelPart
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import _make_mesh
from src.nesting3d.parallel_decode import best_decode
from src.nesting3d.capabilities import probe_capabilities

# Plan2/Plan3/Plan1 dataset config (c3_generality.py ile AYNI — tek dogruluk kaynagi)
VERILER = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler")
PITCH, MARGIN = 2.0, 1
MAGICS = {"plan2": 492.0, "plan3": None, "plan1": None}

DATASETS = {
    "plan1": {"stl_dir": VERILER / "Plan1" / "Plan1", "plate": None, "qty": {
        "ENG-500053_L-Bracket": 22, "811793-1": 20, "TAPER-GAUGE-1": 10,
        "bobbin_1_v2": 12, "bobbin_2_v2": 12, "bobbin_3_v2": 6, "811791-1": 19,
        "pyramid_with_doors": 5, "MTShoe": 1, "M18_toShopVac_Adapter": 2,
        "part262835": 2, "baseplate_v2": 1}},
    "plan2": {"stl_dir": VERILER / "Plan2" / "Plan2", "plate": (328.74, 328.19), "qty": {
        "P00000002586": 20, "part284676_06B23B8_model_r_0": 15,
        "part282114_07D4114_model_r_0": 9, "PARCA_NYLON-12_KABLO_KORUMA": 93,
        "PO-TR154979-17747_P282334": 5, "PO-TR154979-17747_P282335": 5,
        "PO-TR154979-17747_P282336": 5, "PO-TR154979-17747_P282337": 5,
        "PO-TR154989-17667_P282407": 20, "PO-TR154989-17667_P282410": 12,
        "PO-TR156122-17810_P284641": 17, "part282115_07D4113": 9,
        "PO-TR155318-17709": 5, "PO-TR156398-17851": 4,
        "PO-TR155890-17789": 1, "PO-TR155308-17705": 1}},
    "plan3": {"stl_dir": VERILER / "Plan3" / "Plan3", "plate": None, "qty": {
        "171600020": 4, "171600021": 4, "155000224": 16, "155000223": 16,
        "194301273": 1, "153000507": 5, "153000508": 11, "171600003": 11,
        "124601728": 5, "152900295": 4, "152900079": 10, "153004449": 4,
        "152000218": 7, "171600022": 4, "152000217": 7}},
}


def _tilt(angle_deg, axis):
    return trimesh.transformations.rotation_matrix(math.radians(angle_deg), axis)


def axis24():
    """Kupun 24 eksen-hizali simetrisi = master indeks 0..7 + 12..27 (egik 8..11 haric)."""
    m = rotation_matrices(28)
    return [m[i] for i in (list(range(8)) + list(range(12, 28)))]


def continuous_rots(tilt_degs, n_azimuth, n_spin):
    """n=8 baz (kume-icerme garantisi) + SUREKLI off-axis egik pozlar.

    Her (tilt, azimuth) z-eksenini yatay duzlemde azimuth yonune `tilt` derece egiyor;
    her egik poz n_spin tane duzlem-ici spin ile kombine -> master sette OLMAYAN keyfi acilar.
    """
    mats = list(rotation_matrices(8))  # baz: asla baz'dan kotu olamaz
    for td in tilt_degs:
        for ai in range(n_azimuth):
            az = 2.0 * math.pi * ai / n_azimuth
            axis = (math.cos(az), math.sin(az), 0.0)
            t = _tilt(td, axis)
            for si in range(n_spin):
                spin = trimesh.transformations.rotation_matrix(
                    2.0 * math.pi * si / n_spin, (0, 0, 1))
                mats.append(t @ spin)
    return mats


def build_parts(instance, rot_mats):
    """expand_quantities'i AYNEN replike et ama her modele AÇIK rot_matrices besle
    (to_voxel_parts/expand_quantities rot_matrices'i expose etmiyor).

    POZ-BAZINDA DAYANIKLI: bir egik poz kaba pitch'te parcayi voxelize edilemeyecek
    kadar inceltiyorsa (ValueError 'bos grid') O POZU ATLA, parcaya kalan pozlari ver.
    n=8 baz pozlari (eksen-hizali) HER ZAMAN voxelize olur -> kume-icerme korunur
    (her parca >= n=8 secenek). Atlanan poz = kaba pitch'te zaten kaybolacak dejenere poz."""
    name_to_qty, name_to_mesh = {}, {}
    for p in instance.parts:
        if p.name not in name_to_mesh:
            name_to_mesh[p.name] = _make_mesh(p)
        name_to_qty[p.name] = name_to_qty.get(p.name, 0) + p.qty
    parts = []
    skipped = 0
    for name, mesh in name_to_mesh.items():
        orients = []
        for rot in rot_mats:
            try:
                vp1 = voxelize_part(name, mesh, PITCH, rot_matrices=[rot],
                                    margin=MARGIN, method="slice")
            except ValueError:
                skipped += 1
                continue
            orients.extend(vp1.orientations)
        if not orients:
            raise ValueError(f"{name}: hicbir oryantasyon voxelize edilemedi")
        qty = name_to_qty[name]
        w = max(2, len(str(qty)))
        for k in range(1, qty + 1):
            parts.append(VoxelPart(
                id=f"{name}_{k:0{w}d}", name=name, mesh=mesh,
                orientations=orients, volume_voxels=orients[0].voxel_count,
                qty_of_model=qty, display_mesh=None))
    if skipped:
        print(f"  [not] {skipped} egik poz kaba pitch'te cok ince -> atlandi "
              f"(baz n=8 korundu)", flush=True)
    return parts


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    mode = sys.argv[2] if len(sys.argv) > 2 else "hizli"
    caps = probe_capabilities()

    # Oryantasyon setleri (label, matris-listesi)
    if mode == "cont":
        # A24 (kontrol) zaten kosuldu -> sadece baz teyit + surekli seviyeler
        levels = [
            ("L0  n=8 (baz)", list(rotation_matrices(8))),
            ("C24 n=8+surekli(t20/40 a4 s2)", continuous_rots([20, 40], 4, 2)),
            ("C44 n=8+surekli(t15/30/45 a6 s2)", continuous_rots([15, 30, 45], 6, 2)),
        ]
    else:
        levels = [
            ("L0  n=8 (baz)", list(rotation_matrices(8))),
            ("A24 eksen-24 (KONTROL)", axis24()),
            ("C24 n=8+surekli(t20/40 a4 s2)", continuous_rots([20, 40], 4, 2)),
        ]
        if mode == "tam":
            levels.append(("C44 n=8+surekli(t15/30/45 a6 s2)",
                           continuous_rots([15, 30, 45], 6, 2)))

    print("=" * 78)
    print(f"SUREKLI ROTASYON @ KABA PITCH={PITCH}mm — dataset={ds} — {caps.summary()}")
    mg = MAGICS.get(ds)
    print(f"  hipotez: off-axis surekli aci KABA cozunurlukte cavity acar mi? "
          f"(Magics={mg if mg else '-'})")
    print("=" * 78, flush=True)

    cfg = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"crot_{ds}"}
    if cfg["plate"] is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    res = build_instance_from_order(stl_map, cfg["qty"], **kwargs)
    inst = res.instance
    cont = inst.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)
    print(f"  plaka {pw:.0f}x{pd:.0f}mm ({nx}x{ny} voxel)", flush=True)
    print(f"  {'set':<34} {'n_or':>5} {'NFV':>8} {'vs-baz':>8} {'vs-Magics':>10} {'sure':>7}")
    print("-" * 78, flush=True)

    baz = None
    for label, mats in levels:
        t = time.perf_counter()
        try:
            parts = build_parts(inst, mats)
            h, _, strat = best_decode(parts, nx, ny, pitch=PITCH)
            dt = time.perf_counter() - t
            if baz is None:
                baz = h
            vb = (baz - h) / baz * 100
            vm = f"{(h - mg) / mg * 100:+.1f}%" if mg else "-"
            print(f"  {label:<34} {len(mats):>5} {h:>8.1f} {vb:>+7.1f}% {vm:>10} "
                  f"{dt:>6.0f}s", flush=True)
        except Exception as e:
            nm = type(e).__name__
            durum = "OOM" if "Memory" in nm or "alloc" in str(e).lower() else nm[:12]
            print(f"  {label:<34} {len(mats):>5} {durum:>8} {'-':>8} {'-':>10} "
                  f"{time.perf_counter()-t:>6.0f}s", flush=True)

    print("-" * 78)
    print("  YORUM: A24 ~ L0 ise diskret doygun (K-05 dogrulanir). "
          "Cxx < L0 ise SUREKLI rotasyon KAZANIR -> A1 super-bilgisayar degerli.")
    print("=" * 78)


if __name__ == "__main__":
    main()
