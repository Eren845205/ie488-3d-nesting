"""K-17 fine-settle post-pass testleri (2026-07-03).

Sözleşmeler:
  * Yükseklik TEK TARAFLI: settle kabul edilirse h_fine < h_coarse; edilmezse None.
  * Non-penetrasyon: settle çıktısındaki fine grid'ler çakışmaz.
  * Graceful skip: bellek bütçesi yetmezse None (coarse korunur).
  * solve_nfv entegrasyonu: fine_settle=True yüksekliği asla artırmaz; kabul
    edilirse result.fine_pitch küçülür ve export zinciri (placed_meshes) çalışır.
"""

import numpy as np
import pytest
import trimesh

from src.nesting3d.fine_settle import fine_settle_raw
from src.nesting3d.voxelize import voxelize_part

PITCH = 2.0


def _box_part(name, w, d, h, margin=0):
    b = trimesh.creation.box(extents=(w, d, h))
    b.apply_translation(-b.bounds[0])
    return voxelize_part(name, b, PITCH, n_orientations=1, margin=margin,
                         method="slice")


def test_stacked_boxes_recover_quantization_tax():
    """10.6mm kutu coarse'ta 6 hücre (12mm) kaplar; iki kutu istifi coarse'ta
    24mm, gerçekte 21.2mm — settle @0.5 bunu ~21.5mm'e indirmeli."""
    a = _box_part("a", 30.0, 30.0, 10.6)
    b = _box_part("b", 30.0, 30.0, 10.6)
    parts = {"a": a, "b": b}
    raw = [("a", 0, 0, 0, 0), ("b", 0, 0, 0, 6)]  # b, a'nın hücre-tavanına oturmuş
    h_coarse = 12 * PITCH  # 2 kutu x 6 hücre

    s = fine_settle_raw(raw, parts, plate_w_mm=60.0, plate_d_mm=60.0,
                        pitch=PITCH, margin=0, h_coarse_mm=h_coarse)
    assert s is not None
    assert s.height_mm < h_coarse
    # fine=0.5: kutu 22 hücre (11mm); istif 44 hücre = 22.0mm bekleriz
    assert s.height_mm == pytest.approx(22.0, abs=0.51)


def test_no_gain_returns_none():
    """Pitch'e tam hizalı kutuda (12.0mm = 6 hücre) vergi yok → None (coarse korunur)."""
    a = _box_part("a", 20.0, 20.0, 12.0)
    parts = {"a": a}
    raw = [("a", 0, 0, 0, 0)]
    s = fine_settle_raw(raw, parts, plate_w_mm=40.0, plate_d_mm=40.0,
                        pitch=PITCH, margin=0, h_coarse_mm=6 * PITCH)
    assert s is None


def test_memory_budget_skip():
    a = _box_part("a", 30.0, 30.0, 10.6)
    raw = [("a", 0, 0, 0, 0)]
    s = fine_settle_raw(raw, {"a": a}, plate_w_mm=60.0, plate_d_mm=60.0,
                        pitch=PITCH, margin=0, h_coarse_mm=12 * PITCH,
                        mem_budget_bytes=10)  # kasıtlı imkânsız bütçe
    assert s is None


def test_settled_grids_do_not_overlap():
    """Settle çıktısı yeniden simüle edilir: hiçbir çift çakışmamalı."""
    parts = {f"p{i}": _box_part(f"p{i}", 24.0, 24.0, 7.3) for i in range(4)}
    raw = [(f"p{i}", 0, 0, 0, i * 4) for i in range(4)]  # 4'lü istif, 4 hücre adım
    h_coarse = (3 * 4 + 4) * PITCH
    s = fine_settle_raw(raw, parts, plate_w_mm=50.0, plate_d_mm=50.0,
                        pitch=PITCH, margin=0, h_coarse_mm=h_coarse)
    assert s is not None
    occ = None
    for pid, oi, x, y, z in s.raw_fine:
        g = s.fine_parts[pid].orientations[oi].grid
        if occ is None:
            nx = max(px + s.fine_parts[p].orientations[o].grid.shape[0]
                     for p, o, px, _, _ in s.raw_fine)
            ny = max(py + s.fine_parts[p].orientations[o].grid.shape[1]
                     for p, o, _, py, _ in s.raw_fine)
            nz = max(pz + s.fine_parts[p].orientations[o].grid.shape[2]
                     for p, o, _, _, pz in s.raw_fine)
            occ = np.zeros((nx, ny, nz), dtype=bool)
        sub = occ[x:x + g.shape[0], y:y + g.shape[1], z:z + g.shape[2]]
        assert not np.logical_and(sub, g).any(), f"{pid} çakıştı"
        sub |= g


def test_margin_preserved_in_mm():
    """margin=1 coarse (2mm yanal dilation) → fine'da margin*scale: grid mm-genişliği korunur."""
    a = _box_part("a", 20.0, 20.0, 10.6, margin=1)
    raw = [("a", 0, 0, 0, 0)]
    s = fine_settle_raw(raw, {"a": a}, plate_w_mm=60.0, plate_d_mm=60.0,
                        pitch=PITCH, margin=1, h_coarse_mm=6 * PITCH)
    assert s is not None
    g = s.fine_parts["a"].orientations[0].grid
    fine = s.fine_pitch
    coarse_w_mm = a.orientations[0].grid.shape[0] * PITCH
    fine_w_mm = g.shape[0] * fine
    assert fine_w_mm == pytest.approx(coarse_w_mm, abs=PITCH)  # mm-eşdeğer dilation


# ---------------------------------------------------------------------------
# solve_nfv entegrasyonu
# ---------------------------------------------------------------------------

def _mini_instance():
    from src.nesting3d.instances.format import NestingInstance, PartSpec, ContainerSpec

    parts = [
        PartSpec(id="ka", name="kutu_a", qty=2, source="box", width_mm=24.0,
                 depth_mm=24.0, height_mm=10.6),
        PartSpec(id="kb", name="kutu_b", qty=2, source="box", width_mm=18.0,
                 depth_mm=18.0, height_mm=7.3),
    ]
    return NestingInstance(
        container=ContainerSpec(width_mm=60.0, depth_mm=60.0, height_mm=400.0),
        parts=parts,
    )


def test_solve_nfv_settle_never_worse_and_export_works():
    from src.nesting3d.nfv_solve import solve_nfv
    from src.nesting3d.export_stl import placed_meshes

    inst = _mini_instance()
    base = solve_nfv(inst, plate_w_mm=60.0, plate_d_mm=60.0, fine_pitch=PITCH,
                     fine_settle=False)
    settled = solve_nfv(inst, plate_w_mm=60.0, plate_d_mm=60.0, fine_pitch=PITCH,
                        fine_settle=True)
    assert settled.height_mm <= base.height_mm + 1e-9
    if settled.fine_pitch < base.fine_pitch:  # settle kabul edildi
        assert "settle" in settled.adaptive_reason
        assert settled.height_mm < base.height_mm
    # export zinciri settle çıktısıyla çalışmalı (padded orientations + fine pitch)
    meshes = placed_meshes(settled.placements, settled.fine_voxel_parts,
                           settled.fine_pitch)
    assert len(meshes) == len(settled.placements)
    # yerleşmiş mesh'lerin tavanı rapor edilen yükseklikle uyumlu (konservatif sarma payı)
    top = max(float(m.bounds[1][2]) for m in meshes)
    assert top <= settled.height_mm + 1e-6


def test_solve_nfv_settle_off_is_unchanged_shape():
    from src.nesting3d.nfv_solve import solve_nfv

    inst = _mini_instance()
    r = solve_nfv(inst, plate_w_mm=60.0, plate_d_mm=60.0, fine_pitch=PITCH,
                  fine_settle=False)
    assert r.fine_pitch == PITCH
    assert "settle" not in r.adaptive_reason
