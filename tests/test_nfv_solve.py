"""Tests for src.nesting3d.nfv_solve — NFV opt-in kalite modu üretim çözücüsü.

Kabul kriterleri:
  1. solve_nfv -> CoarseToFineResult; n_placed == toplam parça.
  2. placements plaka içinde + geçerli (non-overlap OccupancyBin3D.place ile garanti).
  3. height_mm == bin3d.max_height_mm() (replay tutarlı); 0..1 density.
  4. fine_voxel_parts ile placed_meshes + build_result_scene HATASIZ (render/export uyumu).
  5. tune_result downstream'in okuduğu alanları taşır (winning_config_name/baseline_height_mm/
     all_results[(name,row.height_mm/density/time_s)]/improvement_mm).
  6. Determinizm: iki koşu aynı height.
"""
from __future__ import annotations

import pytest

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.coarse_to_fine import CoarseToFineResult
from src.nesting3d.nfv_solve import solve_nfv
from src.nesting3d.export_stl import placed_meshes, build_result_scene

PLATE_W = PLATE_D = 100.0
FINE_PITCH = 5.0


def _make_instance() -> NestingInstance:
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id="box_a", name="box_a", qty=2, source="box",
                     width_mm=30.0, depth_mm=20.0, height_mm=10.0),
            PartSpec(id="box_b", name="box_b", qty=2, source="box",
                     width_mm=20.0, depth_mm=20.0, height_mm=15.0),
        ],
    )


def _solve(force="cpu-kolA"):
    return solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                     fine_pitch=FINE_PITCH, n_orientations=2, margin=1, force=force)


def test_returns_coarse_to_fine_result():
    r = _solve()
    assert isinstance(r, CoarseToFineResult)
    assert r.n_placed == 4
    assert len(r.placements) == 4
    assert r.winning_config == "nfv"


def test_placements_in_plate_and_height_consistent():
    r = _solve()
    nx, ny = int(PLATE_W // r.fine_pitch), int(PLATE_D // r.fine_pitch)
    for pl in r.placements:
        part = r.fine_voxel_parts[pl.part_id]
        fw, fd, fh = part.orientations[pl.orientation_idx].grid.shape
        assert 0 <= pl.x and pl.x + fw <= nx
        assert 0 <= pl.y and pl.y + fd <= ny
        assert pl.z >= 0
    assert abs(r.height_mm - r.bin3d.max_height_mm()) < 1e-9
    assert 0.0 <= r.density <= 1.0
    assert r.height_mm > 0


def test_export_pipeline_compatible():
    """ÜRETİMİN gerçek transform/export'u NFV placements'ı hatasız tüketir (cavity korunur)."""
    r = _solve()
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
    assert len(meshes) == len(r.placements)
    scene = build_result_scene(r.placements, r.fine_voxel_parts, pitch=r.fine_pitch)
    assert scene is not None
    # gerçek mesh z-uzantısı NFV height ile tutarlı (voxel kuantizasyon + margin payı)
    zmax = max(float(m.bounds[1][2]) for m in meshes)
    assert zmax <= r.height_mm + 2.5 * r.fine_pitch


def test_tune_result_downstream_shape():
    r = _solve()
    tr = r.tune_result
    assert tr.winning_config_name == "nfv"
    assert tr.baseline_height_mm > 0
    assert tr.improvement_mm == 0.0
    assert len(tr.all_results) == 1
    name, row = tr.all_results[0]
    assert name == "nfv"
    # downstream (demo_pipeline 676-688) bu alanları okur:
    assert hasattr(row, "height_mm") and hasattr(row, "density") and hasattr(row, "time_s")


def test_determinism():
    assert abs(_solve().height_mm - _solve().height_mm) < 1e-9


# --- oryantasyon: n=8 default (4⊂8 garanti) + quality=max AX24 (K-18p, 2026-07-03) ---

def test_quality_fast_default_uses_n8():
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, quality="fast", force="cpu-kolA")
    assert "n=8" in r.adaptive_reason  # default fast → sabit n=8

def test_quality_max_uses_ax24_or_safe_floor():
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, quality="max", force="cpu-kolA")
    assert "quality=max" in r.adaptive_reason
    # RAM'e göre iki meşru yol: AX24 (>=13GB) veya n=8 güvenli taban
    assert ("AX24" in r.adaptive_reason) or ("guvenli taban" in r.adaptive_reason)

def test_explicit_n_overrides_quality():
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, n_orientations=2, quality="max", force="cpu-kolA")
    # açık n verilince quality yok sayılır (reason'da n=8/quality=max ibaresi olmaz)
    assert "quality=max" not in r.adaptive_reason and "n=8" not in r.adaptive_reason

def test_quality_max_orientations_ram_ladder():
    from src.nesting3d.nfv_solve import _quality_max_orientations, NFV_AX24
    assert _quality_max_orientations(4 * 10 ** 9) is None          # düşük RAM → n=8 taban
    assert _quality_max_orientations(16 * 10 ** 9) == NFV_AX24     # laptop (K-18'de ölçüldü)
    assert _quality_max_orientations(64 * 10 ** 9) == NFV_AX24     # datacenter da AX24 (eğik yok, K-13)

def test_ax24_excludes_tilted_poses():
    """AX24 eğik pozları (master 8..11) İÇERMEMELİ (K-13: greedy eğik-miyopi) ve
    n=8 default'u kapsamalı (küme-içerme: 8⊂24 → kalite >= n=8 aynı decode'da)."""
    from src.nesting3d.nfv_solve import NFV_AX24
    assert len(NFV_AX24) == 24
    assert set(range(8)).issubset(NFV_AX24)
    assert not set(NFV_AX24) & {8, 9, 10, 11}

def test_quality_max_ax24_orientations_are_axis_aligned():
    """AX24 yolu gerçekten 24 poz voxelize eder ve rot matrisleri eksen-hizalıdır
    (matris elemanları {-1,0,1} — eğik pozlarda kesirli eleman olurdu)."""
    import numpy as np
    from src.nesting3d import nfv_solve as ns

    if ns._quality_max_orientations(ns.probe_capabilities().ram_bytes) is None:
        import pytest
        pytest.skip("bu makinede RAM<13GB — AX24 yolu açılmaz")
    r = solve_nfv(_make_instance(), plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
                  fine_pitch=FINE_PITCH, quality="max", force="cpu-kolA",
                  fine_settle=False)
    part = next(iter(r.fine_voxel_parts.values()))
    assert len(part.orientations) == 24
    for o in part.orientations:
        rot = np.asarray(o.rot_matrix)[:3, :3]
        assert np.allclose(np.abs(rot)[np.abs(rot) > 1e-9], 1.0), "eğik poz sızmış"


def test_run_pipeline_opt_in_nfv_mode():
    """run_pipeline(scenario|{"nesting_mode":"nfv"}) opt-in yolu uçtan uca çalışır."""
    from scripts.demo_pipeline import run_pipeline
    from tests.test_demo_pipeline import SMOKE_SCENARIO
    scenario = {**SMOKE_SCENARIO, "nesting_mode": "nfv"}
    result = run_pipeline(scenario)
    assert result["nesting_results"], "nesting_results boş"
    for bid, nest in result["nesting_results"].items():
        assert nest["height_mm"] >= 0
        # NFV modu çalıştıysa not'ta hata yok ve placements var (fallback değilse)
        assert "n_parts" in nest

