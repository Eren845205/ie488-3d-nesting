"""c1_voxspeed.py — C1 hiz prototipi: _surface_cells + _slice_voxelize (BIREBIR).

Profil (c1_voxprofile, P155308 @0.5mm, 150s/oryantasyon):
  _surface_cells %84 (bary_pts 84s + mark 41.5s, 915M nokta)
  _slice_voxelize %16 (contains_xy 20s, section 4s)

Iki aday — ikisi de MATEMATIKSEL OZDES (ayni islem sirasi / ayni maske):
  S1: _surface_cells eksen-bazli hesap + out= buffer reuse + int32 indeks.
      Eleman basina ayni carpim/toplam SIRASI (IEEE cift-duyarlik deterministik)
      -> bit-duzeyi ayni floor/clip/indeks. Kazanc: taze S-boyutlu tahsisler
      (page-fault) + int64 indeks trafigi + reshape kopyalari kalkar; chunk
      boyutu 3x buyur (eksen basina bellek S/3).
  S2: contains_xy bbox-kirpma — poligon bbox'i disindaki hucre merkezi zaten
      strictly-outside -> contains False; test etmemek maskeyi DEGISTIRMEZ.
      searchsorted(left/right) bbox SINIRINDAKI noktalari dahil eder (konservatif).

Kapi: np.array_equal(eski_grid, yeni_grid) — gecmeyen aday RED.
Kullanim: python scripts/c1_voxspeed.py [quick|full]
  quick: sadece 2.0/1.0mm (hizli dogrulama)   full: +0.5mm buyuk olcum
"""
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from nesting3d.voxelize import _slice_voxelize, _surface_cells  # eski (referans)
from shapely import contains_xy

PLAN2_DIR = Path(r"C:\Users\erenk\OneDrive\Masaüstü\Veriler\Plan2\Plan2")
MAIL_DIRS = [_ROOT / "data" / "mail_stl" / "mail_stl_4F427959",
             _ROOT / "data" / "mail_stl" / "mail_stl_CADD13C2"]


# ---------------------------------------------------------------------------
# S1 — _surface_cells yeni (eksen-bazli, buffer-reuse, int32)
# ---------------------------------------------------------------------------

def surface_cells_new(mesh: trimesh.Trimesh, pitch: float, shape) -> np.ndarray:
    tri = mesh.triangles  # (m, 3, 3)
    edge = np.linalg.norm(tri - np.roll(tri, 1, axis=1), axis=2).max(axis=1)
    k_per_tri = np.maximum(np.ceil(edge / (pitch / 2.0)).astype(int), 1)

    grid = np.zeros(shape, dtype=bool)
    lims = [np.int32(int(s) - 1) for s in shape]

    # Eksen-bazli bellek = eski pts'in 1/3'u -> ayni bellek tavaniyla 3x chunk.
    _ELEMS = 24_000_000  # (chunk_mk * n_bary) ust siniri (~0.19 GB float64)
    for k in np.unique(k_per_tri):
        sub = tri[k_per_tri == k]  # (mk, 3, 3)
        ii, jj = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing="ij")
        keep = (ii + jj) <= k
        u1 = ii[keep] / k          # (n_bary,) — eski u ile ayni degerler
        v1 = jj[keep] / k
        w1 = (1.0 - u1) - v1       # eski (1.0 - u - v) ile ayni eleman-sirasi
        n_bary = int(u1.size)
        chunk_mk = max(1, _ELEMS // max(1, n_bary))

        buf = np.empty((min(chunk_mk, sub.shape[0]), n_bary), dtype=np.float64)
        tmp = np.empty_like(buf)
        idx = [np.empty(buf.shape, dtype=np.int32) for _ in range(3)]

        for s0 in range(0, sub.shape[0], chunk_mk):
            chunk = sub[s0:s0 + chunk_mk]
            mk = chunk.shape[0]
            b, t = buf[:mk], tmp[:mk]
            for c in range(3):
                # eski: chunk[:,0:1,c]*w + chunk[:,1:2,c]*u + chunk[:,2:3,c]*v
                # eleman basina AYNI carpim ve AYNI toplama sirasi -> bit-ozdes
                np.multiply(chunk[:, 0, c, None], w1[None, :], out=b)
                np.multiply(chunk[:, 1, c, None], u1[None, :], out=t)
                np.add(b, t, out=b)
                np.multiply(chunk[:, 2, c, None], v1[None, :], out=t)
                np.add(b, t, out=b)
                np.divide(b, pitch, out=b)
                np.floor(b, out=b)
                ic = idx[c][:mk]
                ic[...] = b                      # integral float -> int32 (ozdes)
                np.clip(ic, np.int32(0), lims[c], out=ic)
            grid[idx[0][:mk], idx[1][:mk], idx[2][:mk]] = True
    return grid


# ---------------------------------------------------------------------------
# S2 — _slice_voxelize yeni (poligon bbox-kirpma)
# ---------------------------------------------------------------------------

def slice_voxelize_new(mesh: trimesh.Trimesh, pitch: float) -> np.ndarray:
    ext = mesh.extents
    n = np.maximum(np.ceil(ext / pitch - 1e-9).astype(int), 1)
    zs = np.minimum((np.arange(n[2]) + 0.5) * pitch, ext[2] - 1e-6)
    sections = mesh.section_multiplane(
        plane_origin=[0.0, 0.0, 0.0], plane_normal=[0.0, 0.0, 1.0], heights=zs
    )
    xs = (np.arange(n[0]) + 0.5) * pitch
    ys = (np.arange(n[1]) + 0.5) * pitch

    grid = np.zeros((n[0], n[1], n[2]), dtype=bool)
    for k, sec in enumerate(sections):
        if sec is None:
            continue
        for poly in sec.polygons_full:
            minx, miny, maxx, maxy = poly.bounds
            # bbox disindaki merkez strictly-outside -> contains False (ozdes).
            # left/right secimi sinirdaki (==) merkezleri DAHIL eder.
            i0 = int(np.searchsorted(xs, minx, side="left"))
            i1 = int(np.searchsorted(xs, maxx, side="right"))
            j0 = int(np.searchsorted(ys, miny, side="left"))
            j1 = int(np.searchsorted(ys, maxy, side="right"))
            if i0 >= i1 or j0 >= j1:
                continue
            sxx, syy = np.meshgrid(xs[i0:i1], ys[j0:j1], indexing="ij")
            m = contains_xy(poly, sxx.ravel(), syy.ravel())
            grid[i0:i1, j0:j1, k] |= m.reshape(i1 - i0, j1 - j0)
    if not grid.any():
        raise ValueError("bos grid (yeni yol)")  # eski yol da ValueError atar
    return grid


# ---------------------------------------------------------------------------

def bench_part(stl: Path, pitch: float, heavy: bool):
    mesh = trimesh.load(str(stl), force="mesh")
    m = mesh.copy()
    m.apply_translation(-m.bounds[0])

    t0 = time.perf_counter(); g_old_s = _slice_voxelize(m, pitch); t_old_s = time.perf_counter() - t0
    t0 = time.perf_counter(); g_new_s = slice_voxelize_new(m, pitch); t_new_s = time.perf_counter() - t0
    ok_s = np.array_equal(g_old_s, g_new_s)

    t0 = time.perf_counter(); g_old_u = _surface_cells(m, pitch, g_old_s.shape); t_old_u = time.perf_counter() - t0
    t0 = time.perf_counter(); g_new_u = surface_cells_new(m, pitch, g_old_s.shape); t_new_u = time.perf_counter() - t0
    ok_u = np.array_equal(g_old_u, g_new_u)

    tag = "OK " if (ok_s and ok_u) else "FARK!!!"
    print(f"  {stl.name[:34]:34s} p={pitch:4.1f}  "
          f"slice {t_old_s:6.2f}->{t_new_s:6.2f}s ({t_old_s/max(t_new_s,1e-9):4.1f}x) "
          f"surf {t_old_u:7.2f}->{t_new_u:7.2f}s ({t_old_u/max(t_new_u,1e-9):4.1f}x)  "
          f"birebir:{tag}")
    return ok_s and ok_u, (t_old_s + t_old_u), (t_new_s + t_new_u)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"
    all_ok, tot_old, tot_new = True, 0.0, 0.0

    # cross-dataset kapisi: Plan2 (2 parca) + mail setleri (Plan1/Plan3 kaynagi)
    cases = []
    p2 = sorted(PLAN2_DIR.glob("*.stl"))
    if p2:
        cases.append((PLAN2_DIR / "PO-TR155308-17705.stl", 2.0))
        cases.append((p2[0], 2.0))
        cases.append((p2[len(p2) // 2], 1.0))
    for d in MAIL_DIRS:
        stls = sorted(d.glob("*.stl")) if d.exists() else []
        for s in stls[:2]:
            cases.append((s, 1.0))
    if mode == "full":
        cases.append((PLAN2_DIR / "PO-TR155308-17705.stl", 1.0))
        cases.append((PLAN2_DIR / "PO-TR155308-17705.stl", 0.5))

    print(f"{len(cases)} olcum (mode={mode})")
    for stl, pitch in cases:
        if not stl.exists():
            print(f"  ATLA (yok): {stl}")
            continue
        ok, t_old, t_new = bench_part(stl, pitch, heavy=pitch <= 0.5)
        all_ok &= ok
        tot_old += t_old; tot_new += t_new

    print(f"\nTOPLAM {tot_old:.1f}s -> {tot_new:.1f}s = {tot_old/max(tot_new,1e-9):.2f}x   "
          f"BIREBIR KAPISI: {'GECTI' if all_ok else 'KALDI — MERGE YOK'}")


if __name__ == "__main__":
    main()
