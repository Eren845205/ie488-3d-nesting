"""generate_models.py — Procedurally build the 3 demo STL models (PLAN_3D.md §2.2).

Creates data/models/{chair,bracket,ring}.stl using trimesh primitives only.
No boolean union is performed (PLAN_3D.md risk note): composite models are
plain concatenations of overlapping watertight primitives.  Voxelization with
fill() handles overlapping solids correctly, so the union step is unnecessary.

Run:  python scripts/generate_models.py
Idempotent: overwrites existing files (models are deterministic, no RNG).
"""

from pathlib import Path

import numpy as np
import trimesh

MODELS_DIR = Path(__file__).resolve().parent.parent / "data" / "models"


def _box(extents, translate):
    """Axis-aligned box with its centre moved to `translate`."""
    b = trimesh.creation.box(extents=extents)
    b.apply_translation(translate)
    return b


def make_chair() -> trimesh.Trimesh:
    """Chair (hocanın çizdiği örnek): 4 legs + seat + backrest, ~40x40x80 units.

    Concave from every side view — a deliberately non-prismatic test shape.
    """
    leg_xy = 6.0
    leg_h = 36.0
    seat = 40.0
    seat_t = 6.0
    back_h = 38.0
    back_t = 6.0

    parts = []
    off = seat / 2 - leg_xy / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(
                _box((leg_xy, leg_xy, leg_h), (sx * off, sy * off, leg_h / 2))
            )
    parts.append(_box((seat, seat, seat_t), (0, 0, leg_h + seat_t / 2)))
    parts.append(
        _box(
            (seat, back_t, back_h),
            (0, -(seat / 2 - back_t / 2), leg_h + seat_t + back_h / 2),
        )
    )
    return trimesh.util.concatenate(parts)


def make_bracket() -> trimesh.Trimesh:
    """Asymmetric L-bracket: base plate + upright wall + stiffening rib."""
    parts = [
        _box((50.0, 30.0, 8.0), (25.0, 15.0, 4.0)),     # base plate
        _box((8.0, 30.0, 40.0), (4.0, 15.0, 20.0)),     # upright wall
        _box((20.0, 6.0, 20.0), (14.0, 15.0, 14.0)),    # diagonal-ish rib (box)
    ]
    return trimesh.util.concatenate(parts)


def make_ring() -> trimesh.Trimesh:
    """Ring: annulus (cylinder with a hole) — watertight, hole built in."""
    return trimesh.creation.annulus(r_min=12.0, r_max=20.0, height=12.0)


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for name, builder in (
        ("chair", make_chair),
        ("bracket", make_bracket),
        ("ring", make_ring),
    ):
        mesh = builder()
        out = MODELS_DIR / f"{name}.stl"
        mesh.export(out)
        ext = np.round(mesh.extents, 1)
        print(f"{out.name}: extents={ext.tolist()} faces={len(mesh.faces)}")


if __name__ == "__main__":
    main()
