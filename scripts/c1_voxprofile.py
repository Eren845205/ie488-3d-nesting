"""c1_voxprofile.py — C1: buyuk-parca voxelize suresinin AYRISTIRILMASI (teshis).

Meta-ders #11: stratejiden ONCE darbogazi olc. coarse_to_fine FINE adimi buyuk
parcayi 0.5mm'de ~159s/parca voxelize ediyor (H-13 notu). Bu script tek buyuk
parcada (Plan2 P155308, 178x299x356mm) voxelize_part'in iki bilesenini asama
asama zamanlar:

  _slice_voxelize : section_multiplane (kesit) + contains_xy (ici-test)
  _surface_cells  : barycentric pts uretimi + _mark (hucre isaretleme)

Uretim fonksiyonlariyla BIREBIR ayni grid urettigi dogrulanir (birebirlik
kapisi) — instrumented kopyalar sadece timer ekler, mantik ayni.

Kullanim: python scripts/c1_voxprofile.py [stl_yolu] [pitch1,pitch2,...]
Default : Plan2 P155308, pitch 2.0,1.0,0.5
"""
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from nesting3d.voxelize import _slice_voxelize, _surface_cells  # noqa: E402
from shapely import contains_xy  # noqa: E402

DEFAULT_STL = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2\PO-TR155308-17705.stl")


# ---------------------------------------------------------------------------
# Instrumented kopyalar — uretimle AYNI mantik + asama timerlari
# ---------------------------------------------------------------------------

def slice_voxelize_timed(mesh, pitch):
    t = {}
    t0 = time.perf_counter()
    ext = mesh.extents
    n = np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1)
    zs = np.minimum((np.arange(n[2]) + 0.5) * pitch, ext[2] - 1e-6)
    sections = mesh.section_multiplane(
        plane_origin=[0.0, 0.0, 0.0], plane_normal=[0.0, 0.0, 1.0], heights=zs
    )
    t["section_multiplane"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    xs = (np.arange(n[0]) + 0.5) * pitch
    ys = (np.arange(n[1]) + 0.5) * pitch
    XX, YY = np.meshgrid(xs, ys, indexing="ij")
    px, py = XX.ravel(), YY.ravel()
    grid = np.zeros((n[0], n[1], n[2]), dtype=bool)
    n_poly = 0
    for k, sec in enumerate(sections):
        if sec is None:
            continue
        mask = np.zeros(px.shape, dtype=bool)
        for poly in sec.polygons_full:
            n_poly += 1
            mask |= contains_xy(poly, px, py)
        grid[:, :, k] = mask.reshape(n[0], n[1])
    t["contains_xy_loop"] = time.perf_counter() - t0
    t["_n_slices"] = int(n[2])
    t["_n_polygons"] = n_poly
    t["_grid_shape"] = tuple(int(v) for v in n)
    return grid, t


def surface_cells_timed(mesh, pitch, shape):
    t = {"bary_pts": 0.0, "mark": 0.0}
    tri = mesh.triangles
    edge = np.linalg.norm(tri - np.roll(tri, 1, axis=1), axis=2).max(axis=1)
    k_per_tri = np.maximum(np.ceil(edge / (pitch / 2.0)).astype(int), 1)
    t["_n_tri"] = int(tri.shape[0])
    t["_k_max"] = int(k_per_tri.max())
    t["_k_mean"] = float(k_per_tri.mean())
    t["_n_unique_k"] = int(np.unique(k_per_tri).size)
    # toplam uretilen nokta sayisi: her ucgen icin (k+1)(k+2)/2
    t["_total_pts"] = int(((k_per_tri + 1) * (k_per_tri + 2) // 2).sum())

    grid = np.zeros(shape, dtype=bool)
    shape_arr = np.asarray(shape)

    _PTS_CHUNK_ELEMS = 8_000_000
    for k in np.unique(k_per_tri):
        sub = tri[k_per_tri == k]
        ii, jj = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (ii + jj) <= k
        u = (ii[keep] / k)[None, :, None]
        v = (jj[keep] / k)[None, :, None]
        n_bary = int(keep.sum())
        chunk_mk = max(1, _PTS_CHUNK_ELEMS // max(1, n_bary * 3))
        for s0 in range(0, sub.shape[0], chunk_mk):
            chunk = sub[s0:s0 + chunk_mk]
            t0 = time.perf_counter()
            pts = (chunk[:, 0:1, :] * (1.0 - u - v)
                   + chunk[:, 1:2, :] * u
                   + chunk[:, 2:3, :] * v)
            pts = pts.reshape(-1, 3)
            t["bary_pts"] += time.perf_counter() - t0
            t0 = time.perf_counter()
            idx = np.floor(pts / pitch).astype(int)
            np.clip(idx, 0, shape_arr - 1, out=idx)
            grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
            t["mark"] += time.perf_counter() - t0
    return grid, t


def main():
    stl = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_STL
    pitches = ([float(p) for p in sys.argv[2].split(",")]
               if len(sys.argv) > 2 else [2.0, 1.0, 0.5])

    print(f"STL: {stl.name}")
    t0 = time.perf_counter()
    mesh = trimesh.load(str(stl), force="mesh")
    print(f"yukleme: {time.perf_counter()-t0:.2f}s  ucgen={len(mesh.faces)}  "
          f"bbox={np.round(mesh.extents, 1)}")

    for pitch in pitches:
        m = mesh.copy()
        m.apply_translation(-m.bounds[0])
        print(f"\n=== pitch {pitch} mm ===")

        g_slice, ts = slice_voxelize_timed(m, pitch)
        t_slice = ts["section_multiplane"] + ts["contains_xy_loop"]
        print(f"  _slice_voxelize toplam {t_slice:7.2f}s  "
              f"grid={ts['_grid_shape']}  dilim={ts['_n_slices']}  poligon={ts['_n_polygons']}")
        print(f"    section_multiplane   {ts['section_multiplane']:7.2f}s")
        print(f"    contains_xy dongusu  {ts['contains_xy_loop']:7.2f}s")

        g_surf, tu = surface_cells_timed(m, pitch, g_slice.shape)
        t_surf = tu["bary_pts"] + tu["mark"]
        print(f"  _surface_cells  toplam {t_surf:7.2f}s  "
              f"ucgen={tu['_n_tri']}  k_max={tu['_k_max']}  k_ort={tu['_k_mean']:.1f}  "
              f"unique_k={tu['_n_unique_k']}  nokta={tu['_total_pts']:,}")
        print(f"    barycentric pts      {tu['bary_pts']:7.2f}s")
        print(f"    _mark (isaretleme)   {tu['mark']:7.2f}s")

        # ---- birebirlik kapisi: instrumented == uretim ----
        t0 = time.perf_counter()
        ref_slice = _slice_voxelize(m, pitch)
        ref_surf = _surface_cells(m, pitch, ref_slice.shape)
        t_prod = time.perf_counter() - t0
        ok_s = bool(np.array_equal(g_slice, ref_slice))
        ok_u = bool(np.array_equal(g_surf, ref_surf))
        print(f"  uretim (referans)      {t_prod:7.2f}s  "
              f"birebir: slice={'OK' if ok_s else 'FARK!'} surface={'OK' if ok_u else 'FARK!'}")
        pay_slice = 100.0 * t_slice / max(t_slice + t_surf, 1e-9)
        print(f"  PAY: slice %{pay_slice:.0f} / surface %{100-pay_slice:.0f}   "
              f"(toplam {t_slice+t_surf:.2f}s / oryantasyon)")


if __name__ == "__main__":
    main()
