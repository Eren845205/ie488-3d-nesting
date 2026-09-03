"""TDD tests for parallel expand_quantities (voxelize.py).

Tests:
  1. Parallel (above-threshold) and serial (below-threshold) paths yield
     identical VoxelPart id lists and grid shapes — deterministic.
  2. ValueError from voxelize_part propagates out of expand_quantities
     (must not be swallowed by the thread executor).
  3. Small instances (below threshold) stay on the serial path — observed
     behaviour matches the original serial-only implementation.
  4. Two calls with the same input produce the same id order (determinism).

All boxes are small, pitch is coarse — tests run fast (< 3 s total).
"""

from __future__ import annotations

import math
from typing import List
from unittest.mock import patch

import numpy as np
import pytest
import trimesh

from src.nesting3d.voxelize import (
    PARALLEL_MIN_TYPES,
    PARALLEL_MIN_VOXELS,
    VoxelPart,
    expand_quantities,
    voxelize_part,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PITCH = 10.0  # coarse — voxelization is fast


def _box(w: float = 30.0, d: float = 20.0, h: float = 20.0) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return b


def _model_set(n_types: int, qty: int = 2) -> List[tuple]:
    """Build a model_set with *n_types* distinct boxes, *qty* copies each."""
    return [
        (f"type_{i:02d}", _box(w=20.0 + i * 5, d=20.0, h=20.0), qty)
        for i in range(n_types)
    ]


def _ids(parts: List[VoxelPart]) -> List[str]:
    return [p.id for p in parts]


# ---------------------------------------------------------------------------
# Constants are importable and sane
# ---------------------------------------------------------------------------


def test_parallel_constants_importable_and_positive():
    """PARALLEL_MIN_TYPES and PARALLEL_MIN_VOXELS must be positive integers."""
    assert isinstance(PARALLEL_MIN_TYPES, int) and PARALLEL_MIN_TYPES > 0
    assert isinstance(PARALLEL_MIN_VOXELS, (int, float)) and PARALLEL_MIN_VOXELS > 0


# ---------------------------------------------------------------------------
# Test 1 — parallel path == serial path (id list + shapes + grid equality)
# ---------------------------------------------------------------------------


def test_parallel_result_equals_serial():
    """Above-threshold instance: parallel output is identical to serial."""
    # Build a model set large enough to trigger parallelism:
    # use PARALLEL_MIN_TYPES types to guarantee the threshold is crossed.
    n = max(PARALLEL_MIN_TYPES, 6)
    model_set = _model_set(n_types=n, qty=1)

    # Force serial path by patching threshold to an impossibly high value.
    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 10_000):
        serial = expand_quantities(model_set, PITCH, n_orientations=1)

    # Force parallel path by patching threshold to 1.
    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 1), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_VOXELS", 1):
        parallel = expand_quantities(model_set, PITCH, n_orientations=1)

    assert _ids(serial) == _ids(parallel), (
        "ID order differs between serial and parallel paths"
    )
    assert len(serial) == len(parallel)
    for s, p in zip(serial, parallel):
        assert s.name == p.name
        assert len(s.orientations) == len(p.orientations)
        for o_s, o_p in zip(s.orientations, p.orientations):
            assert o_s.shape == o_p.shape, (
                f"Grid shape mismatch for part {s.id}: {o_s.shape} vs {o_p.shape}"
            )
            assert np.array_equal(o_s.grid, o_p.grid), (
                f"Grid content mismatch for part {s.id}"
            )


# ---------------------------------------------------------------------------
# Test 2 — ValueError from voxelize_part propagates through executor
# ---------------------------------------------------------------------------


def test_valueerror_propagates_from_parallel():
    """If voxelize_part raises ValueError, expand_quantities must re-raise it."""
    model_set = _model_set(n_types=2, qty=1)

    def _exploding_voxelize(*args, **kwargs):
        raise ValueError("boş grid: pitch çok kaba")

    with patch("src.nesting3d.voxelize.voxelize_part", side_effect=_exploding_voxelize), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 1), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_VOXELS", 1):
        with pytest.raises(ValueError, match="boş grid"):
            expand_quantities(model_set, PITCH, n_orientations=1)


def test_valueerror_propagates_from_serial():
    """ValueError must propagate on the serial path too (regression guard)."""
    model_set = _model_set(n_types=1, qty=1)

    def _exploding_voxelize(*args, **kwargs):
        raise ValueError("boş grid: pitch çok kaba")

    with patch("src.nesting3d.voxelize.voxelize_part", side_effect=_exploding_voxelize), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 10_000):
        with pytest.raises(ValueError, match="boş grid"):
            expand_quantities(model_set, PITCH, n_orientations=1)


# ---------------------------------------------------------------------------
# Test 3 — small instance stays on serial path (no parallelism overhead)
# ---------------------------------------------------------------------------


def test_small_instance_uses_serial_path():
    """Below-threshold input: ThreadPoolExecutor must NOT be invoked."""
    # One type — well below any reasonable PARALLEL_MIN_TYPES threshold.
    model_set = _model_set(n_types=1, qty=3)

    with patch("src.nesting3d.voxelize.ThreadPoolExecutor") as mock_tpe:
        parts = expand_quantities(model_set, PITCH, n_orientations=1)

    mock_tpe.assert_not_called()
    assert len(parts) == 3
    assert all(p.name == "type_00" for p in parts)


# ---------------------------------------------------------------------------
# Test 4 — determinism: two calls produce identical id order
# ---------------------------------------------------------------------------


def test_expand_quantities_is_deterministic():
    """Same input -> same id list, both with serial and parallel paths."""
    n = max(PARALLEL_MIN_TYPES, 6)
    model_set = _model_set(n_types=n, qty=2)

    # Serial
    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 10_000):
        run_a = _ids(expand_quantities(model_set, PITCH, n_orientations=1))
        run_b = _ids(expand_quantities(model_set, PITCH, n_orientations=1))
    assert run_a == run_b, "Serial path is not deterministic"

    # Parallel
    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 1), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_VOXELS", 1):
        run_c = _ids(expand_quantities(model_set, PITCH, n_orientations=1))
        run_d = _ids(expand_quantities(model_set, PITCH, n_orientations=1))
    assert run_c == run_d, "Parallel path is not deterministic"
    assert run_a == run_c, "Serial and parallel produce different id orders"


# ---------------------------------------------------------------------------
# Test 5 — qty expansion is correct after parallelisation
# ---------------------------------------------------------------------------


def test_qty_expansion_correct_in_parallel():
    """Qty copies of each type must be present with correct suffixed ids."""
    n = max(PARALLEL_MIN_TYPES, 6)
    qty = 3
    model_set = _model_set(n_types=n, qty=qty)

    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 1), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_VOXELS", 1):
        parts = expand_quantities(model_set, PITCH, n_orientations=1)

    assert len(parts) == n * qty
    for i in range(n):
        type_parts = [p for p in parts if p.name == f"type_{i:02d}"]
        assert len(type_parts) == qty
        # All instances of the same type share orientation data (read-only sharing)
        assert type_parts[0].orientations is type_parts[1].orientations


# ---------------------------------------------------------------------------
# Test 6 — orientation sharing preserved in parallel path
# ---------------------------------------------------------------------------


def test_orientation_sharing_in_parallel():
    """Parallel path must maintain orientation data sharing (one voxelize per type)."""
    n = max(PARALLEL_MIN_TYPES, 6)
    model_set = _model_set(n_types=n, qty=4)

    with patch("src.nesting3d.voxelize.PARALLEL_MIN_TYPES", 1), \
         patch("src.nesting3d.voxelize.PARALLEL_MIN_VOXELS", 1):
        parts = expand_quantities(model_set, PITCH, n_orientations=1)

    # Group by name; all instances of a name must share the same orientations object
    by_name: dict = {}
    for p in parts:
        by_name.setdefault(p.name, []).append(p)

    for name, group in by_name.items():
        ref = group[0].orientations
        for p in group[1:]:
            assert p.orientations is ref, (
                f"Orientation data not shared for '{name}' — "
                "voxelize_part called more than once per type?"
            )
