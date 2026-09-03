"""c1_fine_zcompact.py — K-17 PROBU: pozisyon-koruyan FINE z-kompaksiyon (kuantizasyon vergisi).

HIPOTEZ: Plan2 522mm tavani 2.0mm hucre kuantizasyonunda olculuyor; istif
arayuzlerinde (tavan = ~20 buyuk levha USTUSTE, K-14) iki kayip birikir:
  (a) parca gercek ust yuzeyi hucre ortasinda bitse de ustteki parca bir
      sonraki 2mm sinirindan baslar;
  (b) konservatif yuzey-sarma 2.0mm'de parcayi z'de ~1 hucreye kadar sisirir
      (0.5mm'de sadece ~0.5mm).
~8-10 istif katmani x 1-2mm = 10-20mm potansiyel.

YONTEM (FFT YOK -> H-11 bellek duvarina TAKILMAZ; H-14 sonrasi fine voxelize 3x ucuz):
  1. Baz: NFV-greedy decode @2.0mm n=8 (c3_generality ile birebir) -> (name,oi,x,y,z) listesi.
  2. Kullanilan her (tip, oi) 0.5mm'de TEK oryantasyon yeniden voxelize
     (margin mm-esdeger: 1 hucre@2.0 = 4 hucre@0.5 -> yanal bosluk ayni).
  3. Parcalar ORIJINAL z-sirasiyla fine grid'e yerlestirilir: ayni (x,y)
     (x4 olcek, mm-birebir), z orijinalden asagi TEMASA kadar alcaltilir
     (feasible degilse yukari ilk feasible'a). Tunelleme yok, sira korunur.
  4. Rapor: baz yukseklik vs kompakt yukseklik + parca-basi bosluk histogrami.

K-11 monotoniklik teoremiyle CELISMEZ: parca sokup yeniden yerlestirmiyoruz
(o olu); ayni yerlesimi daha ince olcekte 'oturtuyoruz' — kuantizasyon bosalimi.

URETIME DOKUNMAZ — scripts/ only. ASCII cikti.
Kullanim: python scripts/c1_fine_zcompact.py [plan2|plan3|plan1] [fine_pitch=0.5] [n8|n24] [probe|prod]
  n24 = 24 eksen-hizali poz (master 0..7 + 12..27, Ry ailesi dahil; egik 8..11 HARIC —
  K-13: egik pozlar greedy'de miyop). K-13 A24 kontrolu plan2'de 520 olcmustu (baz 522);
  yeni bilgi = n24 + settle TOPLAMI.
  prod = coarse decode uretimdeki best_decode ile (GPU-resident -> CPU fallback;
  H-04/H-05 birebir-invariant kanitli, ~3-5x hizli). Default probe = eski CPU greedy.
"""
from __future__ import annotations
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.instances.format import to_voxel_parts, _make_mesh
from src.nesting3d.extreme_point import OccupancyBin3D, _drop_fallback
from src.nesting3d.voxelize import voxelize_part, rotation_matrices
from scripts.c3_generality import _blb_nfv_fast, DATASETS, PITCH, MARGIN


def decode_with_placements(parts, nx, ny):
    """c3_height_driver.decode_record ile ayni greedy; tam (part,oi,x,y,z) kaydi."""
    ob = OccupancyBin3D(nx, ny, nz_limit=600, pitch=PITCH)
    placements = []
    for part in sorted(parts, key=lambda vp: -vp.volume_voxels):
        cur_max = ob.max_height_voxels()
        best_key = None
        best = None
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
        placements.append((part, oi, x, y, z))
    return ob.height_mm(), placements


AX24 = tuple(range(8)) + tuple(range(12, 28))  # 24 eksen-hizali (egik 8..11 haric)


def decode_prod(parts, nx, ny):
    """Uretim best_decode ile coarse decode (GPU-resident -> cpu-kolA -> seri fallback).
    H-04/H-05: stratejiler birebir ayni layout uretir; probe greedy ile ayni BLB mantigi."""
    from src.nesting3d.parallel_decode import best_decode
    by_id = {p.id: p for p in parts}
    _, raw, strategy = best_decode(parts, nx, ny, pitch=PITCH)
    placements = [(by_id[pid], oi, x, y, z) for (pid, oi, x, y, z) in raw]
    h = max(z + p.orientations[oi].grid.shape[2]
            for p, oi, _x, _y, z in placements) * PITCH
    print(f"  decode stratejisi: {strategy}")
    return h, placements


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    fine = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    omode = sys.argv[3] if len(sys.argv) > 3 else "n8"
    dmode = sys.argv[4] if len(sys.argv) > 4 else "probe"
    scale = PITCH / fine
    if abs(scale - round(scale)) > 1e-9:
        raise SystemExit(f"PITCH/fine tam sayi olmali (simdi {scale})")
    scale = int(round(scale))
    fine_margin = MARGIN * scale  # mm-esdeger yanal bosluk

    cfg = DATASETS[ds]
    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"zc_{ds}"}
    if cfg["plate"] is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    res = build_instance_from_order(stl_map, cfg["qty"], **kwargs)
    inst = res.instance
    pw, pd = float(inst.container.width_mm), float(inst.container.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)

    print(f"[{ds}] plaka {pw:.1f}x{pd:.1f}  coarse={PITCH}  fine={fine}  scale={scale}  omode={omode}")
    t0 = time.perf_counter()
    if omode == "n24":
        # to_voxel_parts orientation_overrides gecmiyor -> expand_quantities direkt
        from src.nesting3d.voxelize import expand_quantities
        name_to_qty, name_to_mesh = {}, {}
        for p in inst.parts:
            if p.name not in name_to_mesh:
                name_to_mesh[p.name] = _make_mesh(p)
            name_to_qty[p.name] = name_to_qty.get(p.name, 0) + p.qty
        combined = [(n, name_to_mesh[n], name_to_qty[n]) for n in name_to_mesh]
        parts = expand_quantities(combined, PITCH, margin=MARGIN, method="slice",
                                  orientation_overrides={n: AX24 for n in name_to_mesh})
    else:
        parts = to_voxel_parts(inst, PITCH, n_orientations=8, margin=MARGIN, method="slice")
    print(f"coarse voxelize: {time.perf_counter()-t0:.1f}s  ({len(parts)} parca)")

    # coarse decode pahali (~9dk CPU) ve deterministik -> diske cache
    # (prod decode ayri cache: tie-break farklari olabilir, karistirma)
    suffix = ("" if omode == "n8" else f"_{omode}") + ("_prod" if dmode == "prod" else "")
    cache_f = _ROOT / "data" / "mail_stl" / f"zc_{ds}" / f"coarse_decode{suffix}.npz"
    by_id = {p.id: p for p in parts}
    if cache_f.exists():
        # pickle YOK: str + int array'ler (kendi urettigimiz cache olsa da guvenli taraf)
        d = np.load(cache_f)
        h_base = float(d["h"])
        placements = [(by_id[str(pid)], int(r[0]), int(r[1]), int(r[2]), int(r[3]))
                      for pid, r in zip(d["ids"], d["oixyz"])]
        print(f"BAZ decode @2.0mm n=8: {h_base:.1f}mm  (CACHE)")
    else:
        t0 = time.perf_counter()
        if dmode == "prod":
            h_base, placements = decode_prod(parts, nx, ny)
        else:
            h_base, placements = decode_with_placements(parts, nx, ny)
        print(f"BAZ decode @2.0mm ({omode},{dmode}): {h_base:.1f}mm  "
              f"({time.perf_counter()-t0:.1f}s)")
        cache_f.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_f, h=np.float64(h_base),
                 ids=np.array([p.id for p, *_ in placements]),
                 oixyz=np.array([(oi, x, y, z) for _p, oi, x, y, z in placements],
                                dtype=np.int64))

    # ---- kullanilan (tip, oi) ciftlerini fine'da tek-oryantasyon voxelize ----
    # rot matrisi coarse parcanin kendi orientation'indan alinir -> n8/n24 ayni yol
    t0 = time.perf_counter()
    fine_cache = {}
    for part, oi, _x, _y, _z in placements:
        key = (part.name, oi)
        if key in fine_cache:
            continue
        vp = voxelize_part(part.name, part.mesh, fine,
                           rot_matrices=[part.orientations[oi].rot_matrix],
                           margin=fine_margin, method="slice")
        fine_cache[key] = vp.orientations[0].grid
    print(f"fine voxelize ({len(fine_cache)} tip-oi): {time.perf_counter()-t0:.1f}s")

    # ---- fine grid'e z-kompaksiyonlu replay (orijinal z-sirasi) ----
    nxf, nyf = int(pw // fine), int(pd // fine)
    nzf = int(h_base / fine * 1.2) + 64
    occ = np.zeros((nxf, nyf, nzf), dtype=bool)

    def feasible(g, x, y, z):
        fw, fd, fh = g.shape
        if x < 0 or y < 0 or z < 0 or x + fw > nxf or y + fd > nyf or z + fh > nzf:
            return False
        return not np.logical_and(occ[x:x + fw, y:y + fd, z:z + fh], g).any()

    def lowest_z(g, x, y, z_start, z_bound=0):
        """z_start'tan asagi ilk temas; feasible degilse None."""
        if not feasible(g, x, y, z_start):
            return None
        z = z_start
        while z > z_bound and feasible(g, x, y, z - 1):
            z -= 1
        return z

    def place(g, x, y, z):
        occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]] |= g

    def unplace(g, x, y, z):
        occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]] &= ~g

    # --- 1. geciş: HERKES ORIJINAL z'sine (ALCALTMA YOK — kritik!).
    #     Ilk surumde burada aninda alcaltiliyordu; oyuk-zengin plan3'te
    #     ic-ice gecmis parcalarda (per-kolon komsuluk != min-z sirasi) once
    #     islenen parca alcalinca henuz yerlesmemis komsunun yerini isgal
    #     ediyordu -> 66 yukari-kacis, -123mm. Alcaltma SADECE settle
    #     dongusunde (herkes yerlesikken carpisma kontrolu dogru).
    #     Sigmayanlara (fine ornekleme coarse'un kacirdigi yuzeyi
    #     isaretleyebilir) hucre-ici xy-jitter, son care yukari.
    t0 = time.perf_counter()
    jit = [(dx, dy) for r in range(1, scale)
           for dx in range(-r, r + 1) for dy in range(-r, r + 1)
           if max(abs(dx), abs(dy)) == r]
    state = {}   # i -> (xf, yf, zf)
    up_fixes = jit_fixes = 0
    order = sorted(range(len(placements)), key=lambda i: (placements[i][4], i))
    for i in order:
        part, oi, x, y, z = placements[i]
        g = fine_cache[(part.name, oi)]
        xf, yf, zf = x * scale, y * scale, z * scale
        fw, fd, _fh = g.shape
        xf = min(xf, max(0, nxf - fw))
        yf = min(yf, max(0, nyf - fd))
        if not feasible(g, xf, yf, zf):
            fixed = False
            for dx, dy in jit:
                if feasible(g, xf + dx, yf + dy, zf):
                    xf, yf = xf + dx, yf + dy
                    jit_fixes += 1
                    fixed = True
                    break
            if not fixed:
                up_fixes += 1
                while not feasible(g, xf, yf, zf):
                    zf += 1
                    if zf >= nzf:
                        raise SystemExit(f"yer bulunamadi: {part.id}")
        place(g, xf, yf, zf)
        state[i] = (xf, yf, zf)
    t_pass1 = time.perf_counter() - t0

    # --- 2..n gecis: yakinsayana kadar yeniden-oturt (alttakiler oturunca
    #     usttekiler tekrar oturabilir). Tavana yakin parcalara xy-jitter de dene.
    t0 = time.perf_counter()
    n_pass = 1
    while True:
        n_pass += 1
        moved = 0
        h_now = max((state[i][2] + fine_cache[(placements[i][0].name,
                                               placements[i][1])].shape[2])
                    for i in state) * fine
        for i in sorted(state, key=lambda j: state[j][2]):
            part, oi, _x, _y, _z = placements[i]
            g = fine_cache[(part.name, oi)]
            xf, yf, zf = state[i]
            near_ceiling = (zf + g.shape[2]) * fine >= h_now - 25.0
            unplace(g, xf, yf, zf)
            zb = lowest_z(g, xf, yf, zf)
            best = (xf, yf, zb if zb is not None else zf)
            if near_ceiling:
                for dx, dy in jit:
                    if best[2] == 0:
                        break
                    zb2 = lowest_z(g, xf + dx, yf + dy, best[2] - 1)
                    if zb2 is not None and zb2 < best[2]:
                        best = (xf + dx, yf + dy, zb2)
            place(g, *best)
            if best[2] < zf:
                moved += 1
            state[i] = best
        if moved == 0 or n_pass >= 20:
            break
    t_settle = time.perf_counter() - t0

    slacks = np.array([(placements[i][4] * scale - state[i][2]) * fine
                       for i in range(len(placements))])
    tops = np.array([(state[i][2] + fine_cache[(placements[i][0].name,
                                                placements[i][1])].shape[2]) * fine
                     for i in range(len(placements))])
    h_fine = float(tops.max())

    print(f"replay: 1.gecis {t_pass1:.1f}s (jitter-fix {jit_fixes}, yukari {up_fixes})"
          f" + settle {n_pass-1} gecis {t_settle:.1f}s")
    print("=" * 64)
    print(f"  BAZ    @{PITCH}mm : {h_base:8.1f} mm")
    print(f"  KOMPAKT@{fine}mm : {h_fine:8.1f} mm")
    kaz = h_base - h_fine
    print(f"  KAZANC          : {kaz:8.1f} mm  (%{100.0*kaz/h_base:.1f})")
    print(f"  parca-basi alcalma: ort {slacks.mean():.2f}  medyan {np.median(slacks):.2f}"
          f"  max {slacks.max():.2f}  (mm); alcalan parca {int((slacks>0).sum())}/{len(slacks)}")
    # fine tavani ne belirliyor? (K-14 height-driver'in fine karsiligi)
    idx = np.argsort(-tops)[:8]
    print("  fine tavan surucULERI:")
    for i in idx:
        p, oi, *_ = placements[i]
        print(f"    top={tops[i]:6.1f}  oi={oi}  {p.name[:36]}")
    print("=" * 64)


if __name__ == "__main__":
    main()
