# -*- coding: utf-8 -*-
"""plan1_aci_kurtarma.py — ACI-KURTARMA prototipi: eksen-hizali sigmayan parcaya
z-acisi tara (Plan1 baseplate @335+NOGO — Magics'in acili bastigi vaka).

Mekanizma: to_voxel_parts n8 pozlari; plaka gridine hicbir pozu sigmayan parca
icin Rz(5..85, adim 5) pozlari voxelize edilir, SIGANLAR o parcanin oryantasyon
listesi olur. Cozum: dblf (uretim heightmap mantigi) + no-go muhur + legal olcum.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import trimesh
from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.voxelize import voxelize_part
from src.nesting3d.instances.format import to_voxel_parts
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import _load_instance, legal_of

LOG = Path(__file__).parent / "plan1_aci_kurtarma.log"
PLATE = (335.0, 335.0)
NOGO = ((185.1, 0.2), (215.2, 45.3))
PITCH = 1.0
MARGIN = 1          # clearance_to_voxels(1.0, 1.0) = (1,1)
ZC = 1


def log(m=""):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(m + "\n")


def main():
    LOG.write_text("", encoding="utf-8")
    log("PLAN1 ACI-KURTARMA — 335+NOGO (Magics 110.41)")
    inst = _load_instance("plan1")
    n_total = sum(int(p.qty) for p in inst.parts)
    nx, ny = int(PLATE[0] // PITCH), int(PLATE[1] // PITCH)
    t = time.perf_counter()
    parts = to_voxel_parts(inst, PITCH, n_orientations=8, margin=MARGIN)
    log(f"voxelize n8: {len(parts)} parca ({time.perf_counter() - t:.0f}s)")

    kurtarilan = 0
    for p in parts:
        fits = [o for o in p.orientations
                if o.grid.shape[0] <= nx and o.grid.shape[1] <= ny]
        if fits:
            p.orientations = fits
            continue
        # ACI-KURTARMA: z-acilarini tara, siganlari poz yap
        ok = []
        for ang in range(5, 90, 5):
            R = trimesh.transformations.rotation_matrix(
                np.deg2rad(ang), [0, 0, 1])
            try:
                vp = voxelize_part(p.name, p.mesh, PITCH, rot_matrices=[R],
                                   method="slice", margin=MARGIN)
            except Exception:
                continue
            g = vp.orientations[0].grid
            if g.shape[0] <= nx and g.shape[1] <= ny:
                ok.append(vp.orientations[0])
        if ok:
            p.orientations = ok
            kurtarilan += 1
            log(f"  KURTARILDI: {p.name[:40]} -> {len(ok)} acili poz "
                f"(ilk fp: {ok[0].grid.shape[0]}x{ok[0].grid.shape[1]})")
        else:
            log(f"  KURTARILAMADI: {p.name[:40]} — hicbir acida sigmiyor")

    mask = Bin3D.no_go_mask_from_bounds(NOGO, PLATE[0], PLATE[1], PITCH)
    t = time.perf_counter()
    _, b = dblf(parts, lambda: Bin3D(PLATE[0], PLATE[1], PITCH,
                                     z_clearance=ZC, no_go_mask=mask))
    h = b.max_height_mm()
    log(f"dblf bitti: h={h:.1f}  yerlesen={len(b.placements)}/{n_total} "
        f"({(time.perf_counter() - t) / 60:.1f} dk)  kurtarilan_parca={kurtarilan}")
    if h > 10000:
        log("IMKANSIZ kaldi (sentinel)")
        return
    pbid = {p.id: p for p in parts}
    meshes = placed_meshes(b.placements, pbid, PITCH)
    rep = min_clearance(meshes)
    acc = check_placements(b.placements, pbid)
    legal, reason = legal_of(h, len(b.placements), n_total,
                             float(rep.min_mm), int(acc.n_locked))
    log(f"SONUC: h={h:.1f}  legal="
        f"{legal if legal is not None else 'INVALID(' + str(reason) + ')'}"
        f"  clear={rep.min_mm:.3f}  kilit={acc.n_locked}")
    if legal is not None:
        out = _ROOT / "results" / f"plan1_nogo335_aci_{legal:.1f}mm.stl"
        trimesh.util.concatenate(meshes).export(out)
        log(f"STL: {out}")
    log("BITTI")


if __name__ == "__main__":
    main()
