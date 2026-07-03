"""test_instances_synthetic_shells.py — shell_bells / hollow_tubes üreticileri."""

from __future__ import annotations

import trimesh

from src.nesting3d.instances.format import ContainerSpec, NestingInstance
from src.nesting3d.instances.synthetic import (
    _bell_shell_mesh,
    hollow_tubes,
    shell_bells,
)


class TestShellBells:
    def test_part_count(self):
        inst = shell_bells(n_parts=5, seed=0)
        assert len(inst.parts) == 5

    def test_returns_nesting_instance(self):
        assert isinstance(shell_bells(n_parts=3, seed=0), NestingInstance)

    def test_all_box_source(self):
        inst = shell_bells(n_parts=4, seed=0)
        assert all(p.source == "box" for p in inst.parts)

    def test_parts_carry_wall_and_true_fill(self):
        inst = shell_bells(n_parts=4, seed=0)
        for p in inst.parts:
            assert p.wall_mm is not None and p.wall_mm > 0.0
            assert p.true_fill is not None and p.true_fill < 0.5

    def test_meta_family(self):
        assert shell_bells(seed=0).meta["family"] == "shell_bells"

    def test_deterministic(self):
        a = shell_bells(n_parts=4, seed=3)
        b = shell_bells(n_parts=4, seed=3)
        assert [p.wall_mm for p in a.parts] == [p.wall_mm for p in b.parts]
        assert [p.true_fill for p in a.parts] == [p.true_fill for p in b.parts]

    def test_zero_parts_does_not_raise(self):
        inst = shell_bells(n_parts=0, seed=0)
        assert len(inst.parts) == 0

    def test_custom_container(self):
        cnt = ContainerSpec(width_mm=500.0, depth_mm=400.0, height_mm=300.0)
        assert shell_bells(container=cnt, seed=0).container.width_mm == 500.0


class TestHollowTubes:
    def test_part_count(self):
        inst = hollow_tubes(n_parts=6, seed=0)
        assert len(inst.parts) == 6

    def test_all_box_source(self):
        inst = hollow_tubes(n_parts=4, seed=0)
        assert all(p.source == "box" for p in inst.parts)

    def test_parts_carry_wall_and_true_fill(self):
        inst = hollow_tubes(n_parts=4, seed=0)
        for p in inst.parts:
            assert p.wall_mm is not None and p.wall_mm > 0.0
            assert p.true_fill is not None and p.true_fill < 0.5

    def test_tubes_are_elongated(self):
        inst = hollow_tubes(n_parts=6, r_min=8.0, r_max=14.0,
                            length_min=100.0, length_max=160.0, seed=0)
        for p in inst.parts:
            dims = sorted([p.width_mm, p.depth_mm, p.height_mm])
            elong = dims[2] / dims[1]
            assert elong > 3.0

    def test_meta_family(self):
        assert hollow_tubes(seed=0).meta["family"] == "hollow_tubes"

    def test_deterministic(self):
        a = hollow_tubes(n_parts=4, seed=5)
        b = hollow_tubes(n_parts=4, seed=5)
        assert [p.height_mm for p in a.parts] == [p.height_mm for p in b.parts]

    def test_zero_parts_does_not_raise(self):
        assert len(hollow_tubes(n_parts=0, seed=0).parts) == 0


class TestMeshContract:
    """L2 sözleşme-kilidi: jeneratör mesh'leri watertight + wall ~ nominal."""

    def test_bell_mesh_watertight_and_wall_near_nominal(self):
        for r, wall in [(30.0, 0.8), (45.0, 1.2), (60.0, 1.6)]:
            mesh = _bell_shell_mesh(r, wall)
            assert mesh.is_watertight, f"bell r={r} wall={wall} watertight degil"
            measured = 2.0 * abs(float(mesh.volume)) / float(mesh.area)
            assert abs(measured - wall) / wall < 0.05, (
                f"bell wall olcumu sapti: nominal={wall} olculen={measured:.4f}"
            )

    def test_tube_mesh_watertight_and_wall_near_nominal(self):
        for r, wall, length in [(10.0, 1.0, 120.0), (14.0, 2.0, 150.0)]:
            mesh = trimesh.creation.annulus(r_min=r - wall, r_max=r, height=length)
            assert mesh.is_watertight, f"tube r={r} wall={wall} watertight degil"
            measured = 2.0 * abs(float(mesh.volume)) / float(mesh.area)
            assert abs(measured - wall) / wall < 0.05, (
                f"tube wall olcumu sapti: nominal={wall} olculen={measured:.4f}"
            )
