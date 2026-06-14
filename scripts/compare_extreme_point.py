"""compare_extreme_point.py — Extreme-point vs heightmap DBLF comparison.

Runs several synthetic instances and reports:
  - max height (voxels and mm) for both methods
  - wall-clock time for each
  - overhang scenario: instance where EP beats heightmap structurally

Usage:
    python scripts/compare_extreme_point.py

Notes:
  - Real numune STL parts are NOT included (too slow at 3D occupancy scale).
  - All instances are small synthetic boxes; instances are parameterized
    so the report is reproducible.
  - Times are honest: 3D occupancy is more expensive than heightmap.
"""

import sys
import time
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
import trimesh

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.extreme_point import OccupancyBin3D, place_extreme_point
from src.nesting3d.voxelize import voxelize_part, VoxelPart


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _box_part(pid: str, w_mm: float, d_mm: float, h_mm: float,
              pitch: float) -> VoxelPart:
    mesh = trimesh.creation.box(extents=(w_mm - 0.01, d_mm - 0.01, h_mm - 0.01))
    mesh.apply_translation(-mesh.bounds[0])
    vp = voxelize_part(pid, mesh, pitch, n_orientations=1)
    vp.id = pid
    return vp


def _dblf_height(parts: List[VoxelPart], base_mm: float,
                 pitch: float) -> Tuple[float, float]:
    """Return (max_height_mm, elapsed_s) for heightmap DBLF."""
    def factory():
        return Bin3D(base_mm, base_mm, pitch)
    t0 = time.perf_counter()
    _, b = dblf(parts, factory)
    elapsed = time.perf_counter() - t0
    return b.max_height_mm(), elapsed


def _ep_height(parts: List[VoxelPart], nx: int, ny: int,
               pitch: float) -> Tuple[float, float]:
    """Return (max_height_mm, elapsed_s) for extreme-point packer."""
    def factory():
        return OccupancyBin3D(nx, ny, nz_limit=nx * ny * 10, pitch=pitch)
    t0 = time.perf_counter()
    _, b = place_extreme_point(parts, factory)
    elapsed = time.perf_counter() - t0
    return b.height_mm(), elapsed


def _sep(title: str = "") -> None:
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    else:
        print("-" * 60)


# ---------------------------------------------------------------------------
# Instance definitions
# ---------------------------------------------------------------------------

INSTANCES = [
    # (label, pitch_mm, base_voxels, box_w_mm, box_d_mm, box_h_mm, qty)
    ("Tiny  (5×5 bin, 4 cubes)",      5.0, 5,  10.0, 10.0, 10.0, 4),
    ("Small (8×8 bin, 9 boxes)",      5.0, 8,  10.0, 10.0, 15.0, 9),
    ("Medium (10×10 bin, 12 boxes)",  5.0, 10, 10.0, 10.0, 20.0, 12),
    ("Mixed (12×12 bin, 16 mixed)",   5.0, 12, 10.0, 10.0, 15.0, 16),
]

# Wider+deeper boxes for the mixed instance to give EP more room to exploit
MIXED_BOXES = [
    (10.0, 10.0, 15.0),
    (10.0, 20.0, 10.0),
    (20.0, 10.0, 10.0),
    (15.0, 15.0, 10.0),
]


def _make_parts_uniform(pitch, base_vox, w, d, h, qty) -> List[VoxelPart]:
    return [_box_part(f"p{i:02d}", w, d, h, pitch) for i in range(qty)]


def _make_parts_mixed(pitch, base_vox, qty) -> List[VoxelPart]:
    parts = []
    for i in range(qty):
        w, d, h = MIXED_BOXES[i % len(MIXED_BOXES)]
        parts.append(_box_part(f"m{i:02d}", w, d, h, pitch))
    return parts


# ---------------------------------------------------------------------------
# Overhang scenario
# ---------------------------------------------------------------------------

def run_overhang_demo(pitch: float = 5.0) -> None:
    """Demonstrate structural gain: EP places a block under an arch overhang.

    Architecture (in voxel coordinates, pitch=5mm):
      Bin: 10 wide x 6 deep x 40 tall
      Arch structure (manually constructed in occupancy):
        Left pillar:  x=0, y=0..5, z=0..5   (1 wide, 6 deep, 6 tall)
        Right pillar: x=6, y=0..5, z=0..5   (1 wide, 6 deep, 6 tall)
        Roof:         x=0..6, y=0..5, z=5   (covers top — SINGLE layer)
        Cavity:       x=1..5, y=0..5, z=0..4 — 5 wide x 6 deep x 5 tall = EMPTY

      Filler block voxelized from 14.99 mm cube → 4x4x4 voxels.
        Fits at x=1, y=0, z=0 inside the cavity (4 <= 5 wide, 4 <= 6 deep, 4 <= 5 tall).

    Heightmap perspective:
      H[1..5, 0..5] = 6  (roof top at z=5 → top=6 vox above floor).
      drop-z for filler at (x=1, y=0) = max(H[1..4, 0..3] - 0) = 6.
      Filler top = 6 + 4 = 10 vox = 50 mm.

    Extreme-point perspective:
      Cavity at x=1..4, y=0..3, z=0..3 is empty → filler fits at z=0.
      Filler top = 4 vox (does not raise above existing arch roof = 6).
      Effective max height = max(arch=6, filler_top=4) = 6 vox = 30 mm.

    Height gain: 50 mm (heightmap) vs 30 mm (extreme-point) = 20 mm saved.
    """
    _sep("OVERHANG SCENARIO (structural proof)")
    print("  Arch: pillars at x=0 and x=6, roof at z=5 (1 vox thick).")
    print("  Cavity: x=1..5, y=0..5, z=0..4 — 5 wide x 6 deep x 5 tall.")
    print("  Filler: 14.99mm cube -> 4x4x4 voxels at pitch=5mm.\n")

    nx, ny, nz = 10, 6, 40

    # --- Build arch in EP occupancy ---
    b_ep = OccupancyBin3D(nx, ny, nz, pitch=pitch)
    # Left pillar: x=0, z=0..5
    for z in range(6):
        for y in range(ny):
            b_ep.occupancy[0, y, z] = True
    # Right pillar: x=6, z=0..5
    for z in range(6):
        for y in range(ny):
            b_ep.occupancy[6, y, z] = True
    # Roof: x=0..6, z=5 (single voxel layer)
    for x in range(7):
        for y in range(ny):
            b_ep.occupancy[x, y, 5] = True
    b_ep._max_z_used = 6  # roof top = z=5+1=6 voxels
    b_ep._rebuild_extreme_points()

    # Filler: 14.99mm cube → 4x4x4 voxels
    filler_mesh = trimesh.creation.box(extents=(14.99, 14.99, 14.99))
    filler_mesh.apply_translation(-filler_mesh.bounds[0])
    filler_vp = voxelize_part("filler", filler_mesh, pitch, n_orientations=1)
    filler_orient = filler_vp.orientations[0]
    fw, fd, fh = filler_orient.grid.shape
    print(f"  Filler voxelized grid shape: {fw}x{fd}x{fh} voxels")

    # Verify cavity feasibility
    can_fit_z0 = b_ep.is_feasible(filler_orient, 1, 0, 0)
    print(f"  EP is_feasible at cavity origin (x=1, y=0, z=0): {can_fit_z0}")

    if can_fit_z0:
        b_ep.place(filler_orient, 1, 0, 0)
        ep_top_vox = b_ep.max_height_voxels()  # should still be 6 (arch > filler)
        ep_height_mm = b_ep.height_mm()
        ep_place_z = 0
    else:
        # filler larger than expected cavity — place above arch
        ep_place_z = 6
        b_ep.place(filler_orient, 1, 0, ep_place_z)
        ep_top_vox = b_ep.max_height_voxels()
        ep_height_mm = b_ep.height_mm()

    # --- Heightmap perspective ---
    # Build equivalent arch in Bin3D
    b_hm = Bin3D(nx * pitch, ny * pitch, pitch)
    for y in range(ny):
        b_hm.height[0, y] = 6   # left pillar + roof top
        b_hm.height[6, y] = 6   # right pillar + roof top
    for x in range(1, 6):       # span under roof — roof top = 6
        for y in range(ny):
            b_hm.height[x, y] = 6

    Z = b_hm.drop_map(filler_orient)
    if Z is not None and Z.shape[0] > 1 and Z.shape[1] > 0:
        hm_drop_z = int(Z[1, 0])
    else:
        hm_drop_z = 6  # manual: H=6 - bottom(0) = 6
    hm_top = hm_drop_z + fh
    hm_height_mm = hm_top * pitch

    print(f"\n  HEIGHTMAP: filler drop-z = {hm_drop_z} vox,  top = {hm_top} vox,"
          f"  height = {hm_height_mm:.1f} mm")
    print(f"  EXTREME-PT: filler at z = {ep_place_z} (cavity),  "
          f"max height = {ep_top_vox} vox = {ep_height_mm:.1f} mm")

    gain_mm = hm_height_mm - ep_height_mm
    print(f"\n  HEIGHT GAIN: {gain_mm:.1f} mm")
    if gain_mm > 0:
        print("  [STRUCTURAL PROOF PASSED] EP exploits cavity; heightmap stacks above.")
    elif gain_mm == 0:
        print("  [NOTE] Both methods achieve same height (filler top <= arch top).")
    else:
        print("  [NOTE] EP placed above arch due to geometry mismatch (see shape above).")


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run_comparison() -> None:
    _sep("Extreme-Point vs Heightmap DBLF — Synthetic Instance Comparison")
    print(f"  {'Instance':<35}  {'DBLF-h mm':>10}  {'EP-h mm':>10}  "
          f"{'Diff mm':>8}  {'DBLF-t ms':>10}  {'EP-t ms':>10}  {'Slowdown':>9}")
    _sep()

    for label, pitch, base_vox, w, d, h, qty in INSTANCES:
        base_mm = base_vox * pitch
        nx = ny = base_vox

        if "mixed" in label.lower():
            parts_dblf = _make_parts_mixed(pitch, base_vox, qty)
            parts_ep = _make_parts_mixed(pitch, base_vox, qty)
        else:
            parts_dblf = _make_parts_uniform(pitch, base_vox, w, d, h, qty)
            parts_ep = _make_parts_uniform(pitch, base_vox, w, d, h, qty)

        hm_h, hm_t = _dblf_height(parts_dblf, base_mm, pitch)
        ep_h, ep_t = _ep_height(parts_ep, nx, ny, pitch)

        diff = hm_h - ep_h
        slowdown = ep_t / hm_t if hm_t > 0 else float("nan")
        sign = "" if abs(diff) < 0.01 else (" EP-BETTER" if diff > 0 else " HM-BETTER")

        print(
            f"  {label:<35}  {hm_h:>10.1f}  {ep_h:>10.1f}  "
            f"{diff:>+8.1f}  {hm_t*1000:>10.1f}  {ep_t*1000:>10.1f}  "
            f"{slowdown:>8.1f}x{sign}"
        )

    run_overhang_demo(pitch=5.0)

    _sep()
    print("\nNotes:")
    print("  - Height difference for box-only instances may be 0 (no overhangs in boxes).")
    print("  - Overhang demo above shows structural gain with a crafted cavity scenario.")
    print("  - EP slowdown is expected: 3D voxel AND checks vs 2D heightmap sliding max.")
    print("  - For numune-scale (~220mm / pitch 1.5 mm -> ~147^3 grid): EP is very slow.")
    print("    Do NOT use EP as a drop-in SA decode; use as a one-shot constructive")
    print("    baseline for structural analysis or future GPU-accelerated variants.")


if __name__ == "__main__":
    run_comparison()
