# -*- coding: utf-8 -*-
"""plan1_stl.py — Plan1 legal STL uretimi (hocaya gonderim; 125.0 anchor)."""
import sys, time
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
import trimesh
from src.nesting3d.clearance import min_clearance
from src.nesting3d.accessibility import check_placements
from src.nesting3d.export_stl import placed_meshes
from scripts.eval_gate import _load_instance, _run_champion, legal_of

t = time.perf_counter()
inst = _load_instance("plan1")
n_total = sum(int(p.qty) for p in inst.parts)
r = _run_champion("plan1", inst, seed=42)
meshes = placed_meshes(r.placements, r.fine_voxel_parts, float(r.fine_pitch))
rep = min_clearance(meshes)
acc = check_placements(r.placements, r.fine_voxel_parts)
legal, reason = legal_of(float(r.height_mm), int(r.n_placed), n_total,
                         float(rep.min_mm), int(acc.n_locked))
print(f"h={float(r.height_mm):.1f} legal={legal} clear={rep.min_mm:.3f} "
      f"kilit={acc.n_locked} yerlesen={r.n_placed}/{n_total} "
      f"plaka={float(inst.container.width_mm):.1f}", flush=True)
if legal is not None:
    out = _ROOT / "results" / f"plan1_duzeltilmis_{legal:.1f}mm.stl"
    out.parent.mkdir(exist_ok=True)
    trimesh.util.concatenate(meshes).export(out)
    print(f"STL: {out}", flush=True)
print(f"BITTI {(time.perf_counter() - t) / 60:.1f} dk", flush=True)
