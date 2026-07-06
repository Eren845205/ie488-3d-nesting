"""+47mm AYRISTIRMA (282->329) — Deneme4 fine-pitch (0.5) wall_aware yolu.

Soru (a/b karari): 282->329mm bedeli ne kadari GERCEK 1mm-clearance maliyeti,
ne kadari dilation'in KUANTIZASYON vergisi (margin tamsayi -> margin=1.4 yapilamiyor)?

Uretim clearance_to_voxels margin==z_clearance'i BIRLIKTE degistirir. Ayristirma
icin ikisini BAGIMSIZ surmek gerek -> clearance_to_voxels'i RUNTIME monkeypatch
ederiz (uretim dosyalarina DOKUNMAZ; Stream A ile izole). Fine pitch (<=0.75) ->
deneysel (m,z); coarse pitch -> uretim (1,1).

Grid (m_fine, z_fine) @ fine 0.5:
  (0,1) SANITY  -> ~282 beklenir (uretim baseline; seed/plate dogru mu?)
  (2,1) yatay-only -> yatay dilation maliyeti = h - 282
  (0,2) dikey-only -> dikey z_clearance maliyeti = h - 282
  (2,2) SANITY  -> ~329 beklenir (uretim clearance-1mm)
  (1,1) tek yatay adim -> kuantizasyon egrisi
Mevcut log capalari: (1,2)=296  (2,2)=329.

Toplam maliyet ~ yatay + dikey mi (toplanabilir mi)? (2,2)-(0,1) =? [(2,1)-(0,1)]+[(0,2)-(0,1)]
"""
import os
import sys
sys.path.insert(0, os.getcwd())

import src.nesting3d.coarse_to_fine as c2f
from src.nesting3d.coarse_to_fine import solve_coarse_to_fine
from src.nesting3d.export_stl import placed_meshes
from src.nesting3d.clearance import min_clearance
from src.nesting3d.tuner import build_menu
from scripts.c3_generality import DATASETS
from src.nesting3d.instances.stl_order_loader import build_instance_from_order

SEED = 42
FINE = 0.5
BUDGET = 25  # demo COARSE_BUDGET

# HOCA CEVABI (2026-07-06 mail): fiziksel plaka 335x335x600 mm, kenar payi 5mm
# -> kullanilabilir paketleme alani = 335 - 2*5 = 325x325 mm. (Onceki auto-plaka
# 301.6 YANLISTI; hoca gercek makine plakasini verdi -> +%16 alan, yukseklik duser.)
PLATE = 325.0

# KARAR-KRITIK hucreler ONCE (kismi olum halinde bile headline + kuantizasyon):
#   (2,2) clearance-1mm HEADLINE (gercek plakadaki asil sayi)
#   (1,2) yatay kuantizasyon probu (m1 vs m2, dikey yeterli iken)
#   (0,1) baseline · (2,1) yatay-only · (0,2) dikey-only (decomposition)
CELLS = [(2, 2), (1, 2), (0, 1), (2, 1), (0, 2)]

_orig_ctv = c2f.clearance_to_voxels


def _patched(m_fine, z_fine):
    def f(clearance_mm, pitch):
        if pitch <= 0.75:          # FINE asama -> deneysel
            return m_fine, z_fine
        return (1, 1)              # COARSE asama -> uretim (ceil(1/2)=1)
    return f


def make_deneme4():
    cfg = DATASETS["deneme4"]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": os.path.join(os.getcwd(), "data", "mail_stl", "feat_deneme4")}
    if cfg["plate"]:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    return build_instance_from_order(stl_map, cfg["qty"], **kwargs).instance


def main():
    print("=" * 70, flush=True)
    print("DENEME4 +47mm AYRISTIRMA (margin/z_clearance BAGIMSIZ)", flush=True)
    print("=" * 70, flush=True)
    inst = make_deneme4()
    plate_w = PLATE
    plate_d = PLATE
    auto_w = float(inst.container.width_mm)
    n_types = len(inst.parts)
    n_total = sum(p.qty for p in inst.parts)
    print(f"plaka(HOCA 335-5mm kenar)={plate_w:.1f}x{plate_d:.1f}mm  "
          f"(eski auto={auto_w:.1f})  fine_pitch={FINE}  "
          f"tip={n_types}  toplam_parca={n_total}  seed={SEED}", flush=True)
    menu = {"dblf_only": build_menu()["dblf_only"]}

    import time
    results = {}
    for (m, z) in CELLS:
        c2f.clearance_to_voxels = _patched(m, z)
        t0 = time.perf_counter()
        try:
            r = solve_coarse_to_fine(
                inst, plate_w_mm=plate_w, plate_d_mm=plate_d,
                coarse_pitch=None, fine_pitch=FINE, budget=BUDGET, seed=SEED,
                menu=menu, skip_fine_angle=True, drop_cache=True,
                clearance_mm=1.0,
            )
            dt = time.perf_counter() - t0
            meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
            rep = min_clearance(meshes, samples_per_mesh=3000, seed=1)
            results[(m, z)] = (r.height_mm, rep.min_mm, r.n_placed)
            ok = "OK>=1mm" if rep.min_mm >= 1.0 else "IHLAL<1mm"
            print(f"\n--- (margin={m}, z_clearance={z}) ---", flush=True)
            print(f"  yukseklik = {r.height_mm:.1f} mm   yerlesen={r.n_placed}/{n_total}   ({dt:.0f}s)", flush=True)
            print(f"  min_bosluk = {rep.min_mm:.3f} mm   {ok}", flush=True)
        except Exception as exc:
            print(f"\n--- (margin={m}, z_clearance={z}) HATA: {exc} ---", flush=True)
            results[(m, z)] = None
        finally:
            c2f.clearance_to_voxels = _orig_ctv

    # Ayristirma ozeti
    print("\n" + "=" * 70, flush=True)
    print("AYRISTIRMA", flush=True)
    base = results.get((0, 1))
    if base:
        h_base = base[0]
        print(f"  baseline (0,1) = {h_base:.1f} mm  (bosluk {base[1]:.3f})", flush=True)
        if results.get((2, 1)):
            print(f"  yatay-only (2,1): +{results[(2,1)][0]-h_base:.1f} mm  "
                  f"(bosluk {results[(2,1)][1]:.3f})", flush=True)
        if results.get((0, 2)):
            print(f"  dikey-only (0,2): +{results[(0,2)][0]-h_base:.1f} mm  "
                  f"(bosluk {results[(0,2)][1]:.3f})", flush=True)
        if results.get((2, 2)):
            print(f"  toplam    (2,2): +{results[(2,2)][0]-h_base:.1f} mm  "
                  f"(bosluk {results[(2,2)][1]:.3f})", flush=True)
        if results.get((1, 2)):
            print(f"  yatay-1@z2 (1,2): +{results[(1,2)][0]-h_base:.1f} mm  "
                  f"(bosluk {results[(1,2)][1]:.3f})", flush=True)
        if results.get((2, 1)) and results.get((0, 2)) and results.get((2, 2)):
            toplanabilir = (results[(2,1)][0]-h_base) + (results[(0,2)][0]-h_base)
            gercek = results[(2,2)][0]-h_base
            print(f"\n  TOPLANABILIRLIK: yatay+dikey={toplanabilir:.1f} vs gercek(2,2)={gercek:.1f} mm", flush=True)
        # KUANTIZASYON VERGISI: m1->m2 son tamsayi adimi (dikey yeterli z2 iken).
        # m1 bosluk<1 (yetersiz), m2 bosluk>=1 (hafif asim) -> aradaki yukseklik
        # farki, margin=1.x yapamadigimiz icin odenen vergi. (b)'nin tavan odulu.
        if results.get((1, 2)) and results.get((2, 2)):
            vergi = results[(2,2)][0] - results[(1,2)][0]
            print(f"  KUANTIZASYON VERGISI (m1->m2 @z2): {vergi:.1f} mm  "
                  f"[m1 bosluk {results[(1,2)][1]:.3f}<1 yetersiz -> m2 {results[(2,2)][1]:.3f}]", flush=True)
    print("=" * 70, flush=True)
    print("BITTI", flush=True)


if __name__ == "__main__":
    main()
