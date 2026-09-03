"""c3_coord_tilt.py — KOORDINELI ORTAK-TILT probe (Yol A, OLC-ONCE).

SORU (2026-06-26): C24 kanitladi ki greedy'ye SERBEST surekli rotasyon menusu vermek
BOZUYOR (522->550) cunku greedy egik pozu miyopca kapip footprint buyutuyor. Peki
KOORDINELI rotasyon (parcalar BIRLIKTE ayni acida) kazanir mi? = "ekmek rafi" mekanizmasi.

HIPOTEZ: kazandiran "rotasyon" degil "KOORDINE rotasyon". Greedy'nin per-parca serbest
secimi zarar; uzun/plaka parcalarin PAYLASILAN ortak tilt acisi fayda (paralel egik
plakalar raf gibi sik dizilir: her biri ~ L*sin(a)+t*cos(a)).

TASARIM (greedy serbest secemesin -> KOORDINASYON ZORLA):
  - Uzun/plaka parca (en-boy orani >= ELONG_THRESH, GEOMETRIDEN turetilir, isimden DEGIL):
    SADECE ortak rack acisi `a`'daki pozlar (4 z-spin) -> greedy tilt'i atlayamaz.
  - Kompakt parca: n=8 eksen-hizali (tilt'e zorlanmaz).
  - `a`'yi TARA. Her a icin global yukseklik vs baz 522.
OVERFIT NOTU: bu bir TESHIS (a sweep edilir). Kazanirsa uretim surumu a'yi parca
geometrisinden (L,t -> kapali-form optimal) turetir + cross-dataset kapisi. K-06 emsali.

URETIME DOKUNMAZ — scripts/ only. [[feedback-windows-stdout-ascii]] ASCII.
Kullanim: python scripts/c3_coord_tilt.py [plan2|plan3|plan1]
"""
from __future__ import annotations
import sys, math, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh

from src.nesting3d.voxelize import rotation_matrices, voxelize_part, VoxelPart
from src.nesting3d.instances.format import _make_mesh
from src.nesting3d.instances.stl_order_loader import build_instance_from_order
from src.nesting3d.parallel_decode import best_decode
from src.nesting3d.capabilities import probe_capabilities
from scripts.c3_continuous_rot import DATASETS, PITCH, MARGIN, MAGICS

ELONG_THRESH = 2.0  # en-boy orani >= bu -> "uzun/plaka" (geometri-turevli siniflama)
RACK_ANGLES = (90, 75, 60, 45, 30)  # Rx tilt derece; 90=yan-yatik (eksen-hizali), <90=rack
SPINS = (0, 90, 180, 270)


def _rz(deg):
    return trimesh.transformations.rotation_matrix(math.radians(deg), (0, 0, 1))


def rack_poses(a_deg):
    """Ortak rack acisi a'daki pozlar: yan-yatir (Rx a) + 4 z-spin. a=90 -> tam yan."""
    rx = trimesh.transformations.rotation_matrix(math.radians(a_deg), (1, 0, 0))
    return [_rz(s) @ rx for s in SPINS]


def rack_suitable(mesh, plate_min):
    """Rack adayi = UZUN (en-boy>=ELONG_THRESH) VE konteyner'e gore YETERINCE KUCUK.
    Buyuk plaka egilince z-boyu domine eder (bread-rack 'cok sayida orta parca' icindir);
    plate_min'in 0.6 kati ust sinir = konteyner-turevli (Plan2-uydurmasi DEGIL)."""
    ext = sorted(float(x) for x in mesh.extents)
    elong = (ext[2] / max(ext[0], 1e-9)) >= ELONG_THRESH
    small_enough = ext[2] <= 0.6 * plate_min
    return elong and small_enough


def build_parts_coord(instance, a_deg, plate_min):
    """Rack-uygun parca -> SADECE rack(a) pozlari (koordinasyon zorla); digerleri -> n=8.
    Poz-bazinda dayanikli (ince poz ValueError -> atla)."""
    n8 = list(rotation_matrices(8))
    name_to_qty, name_to_mesh = {}, {}
    for p in instance.parts:
        if p.name not in name_to_mesh:
            name_to_mesh[p.name] = _make_mesh(p)
        name_to_qty[p.name] = name_to_qty.get(p.name, 0) + p.qty
    parts, n_elong = [], 0
    for name, mesh in name_to_mesh.items():
        elong = rack_suitable(mesh, plate_min)
        mats = rack_poses(a_deg) if elong else n8
        if elong:
            n_elong += 1
        orients = []
        for rot in mats:
            try:
                vp1 = voxelize_part(name, mesh, PITCH, rot_matrices=[rot],
                                    margin=MARGIN, method="slice")
            except ValueError:
                continue
            orients.extend(vp1.orientations)
        if not orients:  # rack tumuyle ince -> n8 fallback (parcayi kaybetme)
            for rot in n8:
                try:
                    orients.extend(voxelize_part(name, mesh, PITCH, rot_matrices=[rot],
                                                 margin=MARGIN, method="slice").orientations)
                except ValueError:
                    continue
        qty = name_to_qty[name]
        w = max(2, len(str(qty)))
        for k in range(1, qty + 1):
            parts.append(VoxelPart(
                id=f"{name}_{k:0{w}d}", name=name, mesh=mesh,
                orientations=orients, volume_voxels=orients[0].voxel_count,
                qty_of_model=qty, display_mesh=None))
    return parts, n_elong


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else "plan2"
    caps = probe_capabilities()
    cfg = DATASETS[ds]
    mg = MAGICS.get(ds)

    print("=" * 78)
    print(f"KOORDINELI ORTAK-TILT (Yol A) — dataset={ds} pitch={PITCH}mm — {caps.summary()}")
    print(f"  hipotez: uzun parcalar PAYLASILAN tilt acisinda raf gibi dizilir mi? "
          f"(baz n=8=522, Magics={mg})")
    print("=" * 78, flush=True)

    stl_map = {f.stem: f.read_bytes() for f in sorted(cfg["stl_dir"].glob("*.stl"))}
    kwargs = {"persist_dir": _ROOT / "data" / "mail_stl" / f"crot_{ds}"}
    if cfg["plate"] is not None:
        kwargs["container_w_mm"], kwargs["container_d_mm"] = cfg["plate"]
    res = build_instance_from_order(stl_map, cfg["qty"], **kwargs)
    inst = res.instance
    cont = inst.container
    pw, pd = float(cont.width_mm), float(cont.depth_mm)
    nx, ny = int(pw // PITCH), int(pd // PITCH)

    plate_min = min(pw, pd)
    # kac model rack-uygun? (bilgi)
    names = {p.name for p in inst.parts}
    n_models = len(names)
    n_elong = sum(1 for name in names
                  if rack_suitable(_make_mesh(next(p for p in inst.parts if p.name == name)),
                                   plate_min))
    print(f"  plaka {pw:.0f}x{pd:.0f}mm ({nx}x{ny}); {n_models} model, "
          f"{n_elong} rack-uygun (uzun & <= {0.6*plate_min:.0f}mm) koordine edilecek", flush=True)
    print(f"  {'rack_aci':>9} {'NFV':>8} {'vs-baz522':>10} {'vs-Magics':>10} {'sure':>7}")
    print("-" * 78, flush=True)

    BAZ = 522.0
    best = (BAZ, "baz n=8")
    for a in RACK_ANGLES:
        t = time.perf_counter()
        try:
            parts, ne = build_parts_coord(inst, a, plate_min)
            h, _, _ = best_decode(parts, nx, ny, pitch=PITCH)
            vb = (BAZ - h) / BAZ * 100
            vm = f"{(h - mg) / mg * 100:+.1f}%" if mg else "-"
            tag = "  <-- KOORDINASYON KAZANIR" if h < BAZ - 1 else ""
            if h < best[0]:
                best = (h, f"rack={a}")
            print(f"  {a:>8}d {h:>8.1f} {vb:>+9.1f}% {vm:>10} {time.perf_counter()-t:>6.0f}s{tag}",
                  flush=True)
        except Exception as e:
            nm = type(e).__name__
            print(f"  {a:>8}d {nm[:8]:>8} {'-':>10} {'-':>10} {time.perf_counter()-t:>6.0f}s",
                  flush=True)

    print("-" * 78)
    print(f"  EN IYI: {best[0]:.1f}mm ({best[1]}) | baz 522")
    if best[0] < BAZ - 1:
        print("  -> KOORDINE rotasyon KAZANIR (greedy-serbest C24=550 BOZUYORDU). "
              "Sonraki: a'yi geometriden turet + cross-dataset (plan1/3/boxy).")
    else:
        print("  -> koordine tilt de bu veride kazanmadi -> rack firsati zayif / "
              "A1 (tam NLP) beklentisi duser. Onemli negatif bilgi.")
    print("=" * 78)


if __name__ == "__main__":
    main()
