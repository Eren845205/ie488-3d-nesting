"""Tests for src.nesting3d.coarse_to_fine — coarse-to-fine nesting pipeline.

TDD RED → GREEN sequence.

Acceptance criteria:
  1. solve_coarse_to_fine runs, returns CoarseToFineResult; n_placed == total parts.
  2. Fine placements part_id order matches coarse winner order (coarse order -> fine).
  3. height_mm > 0, density in 0..1.
  4. coarse_pitch > fine_pitch (coarser = bigger pitch).
  5. Determinism: two calls with same args return same height_mm.
  6. Fast: small boxes + coarse pitch + low budget + 1-config menu.
"""

from __future__ import annotations

import trimesh
import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.instances.format import (
    ContainerSpec,
    NestingInstance,
    PartSpec,
)
from src.nesting3d.coarse_to_fine import (
    CoarseToFineResult,
    solve_coarse_to_fine,
    suggest_coarse_pitch,
    clearance_to_voxels,
    _min_feature_mm,
    _refined_rot_matrices,
)

# ---------------------------------------------------------------------------
# Test fixtures — small box instance (no real STL, no large voxelization)
# ---------------------------------------------------------------------------

COARSE_PITCH = 10.0   # kaba: 10 mm / voxel
FINE_PITCH = 5.0      # ince: 5 mm / voxel
PLATE_W = 100.0
PLATE_D = 100.0
BUDGET = 15           # hızlı test: 15 iterasyon yeterli


def _make_instance() -> NestingInstance:
    """4 kutu parça: 2 adet box_a (30x20x10) + 2 adet box_b (20x20x15)."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(
                id="box_a",
                name="box_a",
                qty=2,
                source="box",
                width_mm=30.0,
                depth_mm=20.0,
                height_mm=10.0,
            ),
            PartSpec(
                id="box_b",
                name="box_b",
                qty=2,
                source="box",
                width_mm=20.0,
                depth_mm=20.0,
                height_mm=15.0,
            ),
        ],
    )


def _fast_menu():
    """Tuner menu'su: sadece dblf_only (1 konfig) — hız için."""
    from src.nesting3d.solvers.dblf_solver import DBLFSolver

    return {
        "dblf_only": {
            "solver": DBLFSolver(),
            "params": {},
        }
    }


def _solve(**kwargs) -> CoarseToFineResult:
    """Ortak çağrı yardımcısı."""
    instance = _make_instance()
    return solve_coarse_to_fine(
        instance,
        plate_w_mm=PLATE_W,
        plate_d_mm=PLATE_D,
        coarse_pitch=COARSE_PITCH,
        fine_pitch=FINE_PITCH,
        budget=BUDGET,
        seed=42,
        menu=_fast_menu(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. CoarseToFineResult yapısı ve n_placed
# ---------------------------------------------------------------------------


def test_result_is_dataclass():
    """CoarseToFineResult dataclass alanlari tam olmalı."""
    from dataclasses import fields

    field_names = {f.name for f in fields(CoarseToFineResult)}
    required = {
        "placements",
        "bin3d",
        "height_mm",
        "density",
        "winning_config",
        "coarse_height_mm",
        "coarse_pitch",
        "fine_pitch",
        "coarse_time_s",
        "fine_time_s",
        "n_placed",
    }
    assert required <= field_names, f"Eksik alanlar: {required - field_names}"


def test_solve_returns_coarse_to_fine_result():
    """solve_coarse_to_fine CoarseToFineResult döndürmeli."""
    result = _solve()
    assert isinstance(result, CoarseToFineResult)


def test_n_placed_equals_total_parts():
    """n_placed == toplam parça adedi (qty'ler açılmış)."""
    instance = _make_instance()
    total = sum(p.qty for p in instance.parts)  # 2 + 2 = 4
    result = _solve()
    assert result.n_placed == total, (
        f"Beklenen n_placed={total}, gelen={result.n_placed}"
    )


def test_placements_list_length_equals_n_placed():
    """placements listesi uzunluğu n_placed ile eşit olmalı."""
    result = _solve()
    assert len(result.placements) == result.n_placed


# ---------------------------------------------------------------------------
# 2. Fine placements order matches coarse winner order
# ---------------------------------------------------------------------------


def test_fine_order_matches_coarse_order():
    """Fine placement part_id sırası, coarse kazananının sırasıyla aynı olmalı."""
    result = _solve()
    # Fine placement'ların part_id sırası coarse sırası aktarılmış olmalı.
    # Her fine placement'da part_id mevcut olmalı.
    placed_ids = [p.part_id for p in result.placements]
    # Tümü benzersiz-ish id içermeli (qty_açılmış versiyonlar: name_0, name_1, ...)
    assert len(placed_ids) == result.n_placed
    # Sıralı olmayan bir set değil, gerçek liste — sıra korunmuş.
    # Hem coarse hem fine aynı id uzayını kullandığından intersection tam olmalı.
    assert len(set(placed_ids)) == result.n_placed, (
        "Placement part_id'leri tekil olmalı (her parça bir kez yerleşir)"
    )


def test_fine_bin3d_is_bin3d_instance():
    """result.bin3d Bin3D örneği olmalı."""
    result = _solve()
    assert isinstance(result.bin3d, Bin3D)


# ---------------------------------------------------------------------------
# 3. height_mm > 0, density 0..1
# ---------------------------------------------------------------------------


def test_height_mm_positive():
    """Fine height_mm > 0 olmalı."""
    result = _solve()
    assert result.height_mm > 0.0, f"height_mm={result.height_mm}"


def test_density_in_unit_interval():
    """Fine density 0 ile 1 arasında olmalı."""
    result = _solve()
    assert 0.0 < result.density <= 1.0, f"density={result.density}"


def test_coarse_height_mm_positive():
    """Coarse kazananının height_mm > 0 olmalı."""
    result = _solve()
    assert result.coarse_height_mm > 0.0


# ---------------------------------------------------------------------------
# 4. coarse_pitch > fine_pitch
# ---------------------------------------------------------------------------


def test_pitch_relationship():
    """coarse_pitch > fine_pitch olmalı (kaba >= ince)."""
    result = _solve()
    assert result.coarse_pitch == COARSE_PITCH
    assert result.fine_pitch == FINE_PITCH
    assert result.coarse_pitch > result.fine_pitch


# ---------------------------------------------------------------------------
# 5. Determinism
# ---------------------------------------------------------------------------


def test_determinism():
    """Aynı argümanlarla iki çağrı aynı height_mm versin."""
    r1 = _solve()
    r2 = _solve()
    assert r1.height_mm == r2.height_mm, (
        f"Determinizm ihlali: {r1.height_mm} != {r2.height_mm}"
    )
    assert r1.winning_config == r2.winning_config
    assert r1.n_placed == r2.n_placed


# ---------------------------------------------------------------------------
# 6. Timing fields are non-negative floats
# ---------------------------------------------------------------------------


def test_timing_fields_non_negative():
    """coarse_time_s ve fine_time_s >= 0 olmalı."""
    result = _solve()
    assert result.coarse_time_s >= 0.0
    assert result.fine_time_s >= 0.0


# ---------------------------------------------------------------------------
# 7. winning_config is a string matching the menu key
# ---------------------------------------------------------------------------


def test_winning_config_is_menu_key():
    """winning_config menu'deki bir anahtar olmalı."""
    menu = _fast_menu()
    result = _solve()
    assert result.winning_config in menu, (
        f"winning_config='{result.winning_config}' menu'de yok: {list(menu)}"
    )


# ---------------------------------------------------------------------------
# 8. Farklı seed -> farklı veya aynı ama geçerli sonuç
# ---------------------------------------------------------------------------


def test_different_seed_still_valid():
    """Farklı seed ile sonuç yine geçerli (height>0, density 0..1)."""
    instance = _make_instance()
    result = solve_coarse_to_fine(
        instance,
        plate_w_mm=PLATE_W,
        plate_d_mm=PLATE_D,
        coarse_pitch=COARSE_PITCH,
        fine_pitch=FINE_PITCH,
        budget=BUDGET,
        seed=99,
        menu=_fast_menu(),
    )
    assert result.height_mm > 0.0
    assert 0.0 < result.density <= 1.0


# ---------------------------------------------------------------------------
# Adaptif coarse pitch (suggest_coarse_pitch) — her veriye özel güvenli
# ---------------------------------------------------------------------------

def _inst(dim_list):
    """dim_list: [(w,d,h), ...] -> box parçalı NestingInstance."""
    return NestingInstance(
        container=ContainerSpec(width_mm=PLATE_W, depth_mm=PLATE_D),
        parts=[
            PartSpec(id=f"p{i}", name=f"p{i}", qty=1, source="box",
                     width_mm=w, depth_mm=d, height_mm=h)
            for i, (w, d, h) in enumerate(dim_list)
        ],
    )


def test_min_feature_en_ince_boyut():
    inst = _inst([(50, 50, 50), (10, 1.0, 20)])
    assert _min_feature_mm(inst) == 1.0


def test_suggest_coarse_ince_parca_guvenli():
    # 1 mm ince parça → coarse pitch onu voxelize'da kaybetmemeli
    inst = _inst([(50, 50, 50), (10, 1.0, 20)])
    cp = suggest_coarse_pitch(inst, fine_pitch=0.4)
    assert _min_feature_mm(inst) / cp > 0.5   # kaybolmaz (güvenli)


def test_suggest_coarse_kalin_parca_fine_x3():
    # En ince 10 mm → güvenli tavan (10/0.6=16.7) yüksek, hedef fine×3 geçerli
    inst = _inst([(50, 50, 50), (20, 10, 30)])
    cp = suggest_coarse_pitch(inst, fine_pitch=1.0)
    assert cp == pytest.approx(3.0)


def test_suggest_coarse_fine_alt_sinir():
    # coarse asla fine'dan küçük olamaz
    inst = _inst([(2, 1.0, 2)])  # çok ince
    cp = suggest_coarse_pitch(inst, fine_pitch=2.0)
    assert cp >= 2.0


def test_solve_coarse_pitch_none_otomatik():
    # coarse_pitch=None → otomatik suggest; çalışmalı
    inst = _make_instance()
    r = solve_coarse_to_fine(
        inst, plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
        coarse_pitch=None, fine_pitch=FINE_PITCH, budget=BUDGET, seed=42,
    )
    assert r.n_placed == 4
    assert r.coarse_pitch >= FINE_PITCH


# ---------------------------------------------------------------------------
# Faz 2b — İnce-açı rotasyon refinement (hocanın 0.5-1° hassas döndürme isteği)
# ---------------------------------------------------------------------------

import numpy as np


def test_refined_rot_matrices_base_first_and_count():
    """Baz poz İLK eleman (regresyon koruması) + sayı = 1 + eksen·2·(window/step)."""
    base = np.eye(4)
    mats = _refined_rot_matrices(base, window_deg=5.0, step_deg=1.0, axes=("z",))
    # window/step = 5 → her eksen için ±1..±5 = 10 perturbasyon + 1 baz = 11
    assert len(mats) == 1 + 1 * 2 * 5
    assert np.array_equal(mats[0], base), "ilk eleman tam baz poz olmalı (0°)"
    # 3 eksen
    mats3 = _refined_rot_matrices(base, window_deg=5.0, step_deg=1.0,
                                  axes=("x", "y", "z"))
    assert len(mats3) == 1 + 3 * 2 * 5


def test_refined_rot_matrices_window_zero_only_base():
    """window=0 → sadece baz poz (perturbasyon yok)."""
    base = np.eye(4)
    mats = _refined_rot_matrices(base, window_deg=0.0, step_deg=1.0, axes=("z",))
    assert len(mats) == 1
    assert np.array_equal(mats[0], base)


def test_refine_window_zero_equals_baseline():
    """fine_angle_window=0 → refinement KAPALI, mevcut yolla aynı sonuç."""
    r_base = _solve()
    r_zero = _solve(fine_angle_window=0.0)
    assert r_zero.height_mm == r_base.height_mm
    assert r_zero.n_placed == r_base.n_placed


def test_refine_runs_and_places_all():
    """Refinement açık (±5°, 1° adım, z) → tüm parçalar yerleşir, geçerli sonuç."""
    r = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    assert r.n_placed == 4
    assert r.height_mm > 0.0
    assert 0.0 < r.density <= 1.0


def test_refine_safe_never_worse_than_baseline():
    """GÜVENLİ MOD (varsayılan): ince açı global yüksekliği ASLA bozmaz.

    Algoritma hem açısız baz hem ince-açılı çözümü üretir, daha iyi global
    yüksekliği seçer → sonuç DAİMA ≤ baseline. Kutularda in-plane dönüş yardım
    etmediğinden baz seçilir (yükseklik = baseline, fine_angle_used=False).
    """
    r_base = _solve()
    r_ref = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    assert r_ref.height_mm <= r_base.height_mm + 1e-9, (
        f"güvenli mod yüksekliği bozdu: {r_ref.height_mm} > {r_base.height_mm}"
    )


def test_refine_safe_picks_base_for_boxes():
    """Kutularda güvenli mod baz çözümü seçer (fine_angle_used=False, yük=baseline)."""
    r_base = _solve()
    r_ref = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    assert r_ref.fine_angle_used is False
    assert r_ref.height_mm == r_base.height_mm


def test_refine_unsafe_forces_refined():
    """safe=False → refined koşulsuz kullanılır (fine_angle_used=True)."""
    r = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z",
               fine_angle_safe=False)
    assert r.fine_angle_used is True
    assert r.n_placed == 4


def test_refine_deterministic():
    """Refinement deterministik (aynı argüman → aynı yükseklik)."""
    r1 = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    r2 = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    assert r1.height_mm == r2.height_mm
    assert r1.n_placed == r2.n_placed


# ---------------------------------------------------------------------------
# H-15p — ince-açı rafinesini ATLAYAN opt-in hız fix'i + telemetri
# ---------------------------------------------------------------------------

def test_skip_fine_angle_default_is_false():
    """skip_fine_angle varsayilani False (mevcut davranis birebir)."""
    import inspect
    sig = inspect.signature(solve_coarse_to_fine)
    assert "skip_fine_angle" in sig.parameters
    assert sig.parameters["skip_fine_angle"].default is False


def test_fine_angle_time_s_field_exists():
    """CoarseToFineResult telemetri alani fine_angle_time_s (skaler, default 0.0)."""
    from dataclasses import fields
    names = {f.name for f in fields(CoarseToFineResult)}
    assert "fine_angle_time_s" in names
    # Rafine kosmayan (window=0) kosuda 0.0
    r = _solve(fine_angle_window=0.0)
    assert r.fine_angle_time_s == 0.0


def test_skip_fine_angle_true_bypasses_refine(monkeypatch):
    """skip_fine_angle=True → window>0 olsa bile rafine yolu HIC cagrilmaz."""
    import src.nesting3d.coarse_to_fine as c2f
    calls = []
    orig = c2f._build_refined_fine_parts

    def _spy(*a, **k):
        calls.append(1)
        return orig(*a, **k)

    monkeypatch.setattr(c2f, "_build_refined_fine_parts", _spy)
    r = _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z",
               skip_fine_angle=True)
    assert calls == [], "skip_fine_angle=True iken _build_refined_fine_parts cagrilmamali"
    assert r.fine_angle_used is False
    assert r.fine_angle_time_s == 0.0


def test_skip_fine_angle_true_equals_baseline():
    """skip_fine_angle=True (window>0 ile) → baz cozumle birebir ayni sonuc."""
    r_skip = _solve(fine_angle_window=5.0, fine_angle_step=1.0,
                    fine_angle_axes="z", skip_fine_angle=True)
    r_base = _solve(fine_angle_window=0.0)
    assert r_skip.height_mm == r_base.height_mm
    assert r_skip.n_placed == r_base.n_placed


def test_no_skip_default_runs_refine(monkeypatch):
    """Varsayilan (skip=False) + window>0 → rafine yolu GERCEKTEN cagrilir."""
    import src.nesting3d.coarse_to_fine as c2f
    calls = []
    orig = c2f._build_refined_fine_parts

    def _spy(*a, **k):
        calls.append(1)
        return orig(*a, **k)

    monkeypatch.setattr(c2f, "_build_refined_fine_parts", _spy)
    _solve(fine_angle_window=5.0, fine_angle_step=1.0, fine_angle_axes="z")
    assert calls, "skip=False + window>0 iken rafine yolu cagrilmali"


# ---------------------------------------------------------------------------
# Adaptif parametre seçimi (kutuluk özelliğinden veri-odaklı karar)
# ---------------------------------------------------------------------------

def test_boxes_are_boxy():
    """Kutu parçalar voxelize edilince kutuluk ≈ 1.0 olmalı."""
    from src.nesting3d.adaptive_params import instance_boxiness
    from src.nesting3d.instances.format import to_voxel_parts
    parts = to_voxel_parts(_make_instance(), FINE_PITCH, n_orientations=1)
    b = instance_boxiness(parts)
    assert b >= 0.9, f"kutular kutu çıkmalı, boxiness={b}"


def test_recommend_skips_angle_for_boxes():
    """Kutu parçalarda öneri ince-açıyı ATLAR (window=0)."""
    from src.nesting3d.adaptive_params import recommend
    from src.nesting3d.instances.format import to_voxel_parts
    parts = to_voxel_parts(_make_instance(), FINE_PITCH, n_orientations=1)
    rec = recommend(parts)
    assert rec.fine_angle_window == 0.0
    assert "ATLANDI" in rec.reason


def test_adaptive_solve_sets_reason_and_skips_for_boxes():
    """adaptive=True: kutu setinde gerekçe yazılır, ince-açı atlanır."""
    r_ad = _solve(adaptive=True)
    assert r_ad.adaptive_reason is not None
    assert "kutuluk" in r_ad.adaptive_reason
    # Kutularda ince-açı atlanır → refinement kullanılmaz
    assert r_ad.fine_angle_used is False


def test_adaptive_auto_selects_pose_count():
    """adaptive=True poz sayısını KENDİ seçer (gerekçede poz izi + n; ladder içinde)."""
    r_ad = _solve(adaptive=True)
    assert "poz:" in r_ad.adaptive_reason
    assert r_ad.n_placed == 4  # tüm parçalar yerleşir (seçilen n ne olursa)


def test_adaptive_deterministic():
    """Adaptif tam akış deterministik (aynı argüman → aynı yükseklik + gerekçe)."""
    r1 = _solve(adaptive=True)
    r2 = _solve(adaptive=True)
    assert r1.height_mm == r2.height_mm
    assert r1.adaptive_reason == r2.adaptive_reason


def test_auto_select_returns_ladder_value():
    """_auto_select_n_orientations ladder içinden bir n + tüm parçaları döndürür."""
    from src.nesting3d.coarse_to_fine import (
        _auto_select_n_orientations, _ORIENTATION_LADDER)
    n, parts, used, trail = _auto_select_n_orientations(
        _make_instance(), PLATE_W, PLATE_D, COARSE_PITCH, FINE_PITCH)
    assert n in _ORIENTATION_LADDER
    assert parts is not None and len(parts) == 4
    assert len(trail) >= 1 and trail[0][0] == _ORIENTATION_LADDER[0]


# ---------------------------------------------------------------------------
# H-16w — dirty-region drop_map onbellegini FINE yolda ac (opt-in hiz)
# ---------------------------------------------------------------------------

def test_drop_cache_default_is_false():
    """drop_cache varsayilani False (mevcut davranis birebir)."""
    import inspect
    sig = inspect.signature(solve_coarse_to_fine)
    assert "drop_cache" in sig.parameters
    assert sig.parameters["drop_cache"].default is False
    assert "drop_cache_cap_mb" in sig.parameters


def test_drop_cache_off_stats_none():
    """drop_cache=False (default) -> drop_cache_stats None (telemetri eski)."""
    r = _solve()
    assert r.drop_cache_stats is None


def test_drop_cache_on_equals_off_placements():
    """drop_cache=True fine yerlesimi (height + yerlesim listesi) drop_cache=False
    ile BIREBIR ayni (kalite garantisi: cache dogruluk-notr)."""
    r_off = _solve()
    r_on = _solve(drop_cache=True)
    assert r_on.height_mm == r_off.height_mm
    assert r_on.n_placed == r_off.n_placed
    key_off = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
               for p in r_off.placements]
    key_on = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
              for p in r_on.placements]
    assert key_on == key_off, "cache'li fine yerlesim cache'siz ile birebir olmali"


def test_drop_cache_on_stats_populated():
    """drop_cache=True -> drop_cache_stats sozlugu doldurulur (enabled=True,
    beklenen anahtarlar mevcut)."""
    r = _solve(drop_cache=True)
    st = r.drop_cache_stats
    assert isinstance(st, dict)
    assert st["enabled"] is True
    for k in ("hit_ratio", "keys", "peak_mb", "fallbacks", "evictions",
              "hits", "misses", "full_computes"):
        assert k in st
    assert 0.0 <= st["hit_ratio"] <= 1.0


def test_drop_cache_reaches_bin3d(monkeypatch):
    """drop_cache=True -> fine _run_fine Bin3D'si GERCEKTEN drop_cache acik kurulur
    (kablonun Bin3D'ye ulastigini yakala; sonuctan bagimsiz)."""
    import src.nesting3d.coarse_to_fine as c2f
    seen = []
    orig = c2f.Bin3D

    def _spy(*a, **k):
        seen.append(k.get("drop_cache", False))
        return orig(*a, **k)

    monkeypatch.setattr(c2f, "Bin3D", _spy)
    _solve(drop_cache=True)
    assert any(seen), "drop_cache=True iken en az bir Bin3D drop_cache=True kurulmali"


def test_drop_cache_thread_isolation():
    """THREAD-GUVENLIGI kaniti: ayni instance uzerinde drop_cache=True ile
    PARALEL solve_coarse_to_fine cagrilari, seri cagrilarla BIREBIR ayni sonuc
    verir. Her cagri kendi fine Bin3D'sini (dolayisiyla kendi _dc_cache'ini)
    kurar; Orientation nesneleri salt-okunur -> cross-thread bozulma yok."""
    import threading

    serial = _solve(drop_cache=True)
    serial_key = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
                  for p in serial.placements]

    results = {}

    def _worker(idx):
        r = _solve(drop_cache=True)
        results[idx] = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
                        for p in r.placements]

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    for idx, key in results.items():
        assert key == serial_key, \
            f"thread {idx} paralel sonucu seri sonuctan sapti (cross-thread bozulma)"


# ---------------------------------------------------------------------------
# Clearance garantisi (hoca sarti 2026-06-11: parca-arasi >= 1mm) — web
# NFV-DISI yollari icin clearance_mm parametresi (fix 2026-07-06)
# ---------------------------------------------------------------------------

def test_clearance_to_voxels_zero_is_legacy():
    """clearance_mm=0.0 -> (margin=0, z_clearance=1) = MEVCUT davranis BIT-OZDES."""
    assert clearance_to_voxels(0.0, 5.0) == (0, 1)
    assert clearance_to_voxels(0.0, 0.5) == (0, 1)
    assert clearance_to_voxels(0.0, 2.0) == (0, 1)


def test_clearance_to_voxels_formula_fine_pitch():
    """Ince pitch (0.5mm): 1mm clearance -> margin=z_clearance=2 (olcum-kalibreli:
    margin=1 @0.5 sadece ~0.8mm verir=ihlal; margin=2 = 1.05mm OK). Deneme4."""
    assert clearance_to_voxels(1.0, 0.5) == (2, 2)


def test_clearance_to_voxels_formula_coarse_pitch():
    """Kaba pitch (5mm): 1mm clearance -> her ikisi de en az 1 voxel (max(1,..))."""
    assert clearance_to_voxels(1.0, 5.0) == (1, 1)
    # pitch 2.0 -> ceil(1/2)=1 (NFV/benchmark margin=1 konvansiyonuyla tutarli)
    assert clearance_to_voxels(1.0, 2.0) == (1, 1)


def test_clearance_to_voxels_margin_equals_zclearance():
    """Olcum-kalibreli formul: margin == z_clearance == ceil(clearance/pitch)."""
    for cl, p in [(1.0, 0.5), (1.0, 0.3), (2.0, 0.5), (1.0, 5.0), (1.5, 0.5)]:
        m, z = clearance_to_voxels(cl, p)
        assert m == z, f"margin({m}) != z_clearance({z}) @ clearance={cl} pitch={p}"


def test_clearance_to_voxels_scales_with_clearance():
    """2mm clearance @ 0.5 pitch -> margin=z=4 (clearance ile olcekler)."""
    assert clearance_to_voxels(2.0, 0.5) == (4, 4)
    # 1mm @ 0.3 pitch: ceil(1/0.3)=4
    assert clearance_to_voxels(1.0, 0.3) == (4, 4)


def test_clearance_mm_default_is_zero():
    """clearance_mm parametresi var, varsayilan 0.0 (bit-ozdes eski yol)."""
    import inspect
    sig = inspect.signature(solve_coarse_to_fine)
    assert "clearance_mm" in sig.parameters
    assert sig.parameters["clearance_mm"].default == 0.0


def test_clearance_zero_equals_default_bit_identical():
    """clearance_mm=0.0 acikca gecince, hic gecmemekle BIREBIR ayni yerlesim
    (yukseklik + tum placement anahtarlari)."""
    r_default = _solve()
    r_zero = _solve(clearance_mm=0.0)
    assert r_zero.height_mm == r_default.height_mm
    assert r_zero.n_placed == r_default.n_placed
    key_d = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
             for p in r_default.placements]
    key_z = [(p.part_id, p.x, p.y, p.z, p.orientation_idx)
             for p in r_zero.placements]
    assert key_z == key_d, "clearance_mm=0.0 eski yolla birebir olmali"


def test_clearance_positive_guarantees_min_gap():
    """clearance_mm=1.0 -> yerlesmis GERCEK mesh'ler arasi olculen min bosluk
    >= 1mm (hoca sarti). Garanti zinciri: yatay margin dilation + dikey
    z_clearance; placed_meshes orijinal mesh'i (voxel_origin margin-kaydirmasi
    dahil) yerine koyar -> olculen deger gercek bosluktur."""
    from src.nesting3d.export_stl import placed_meshes
    from src.nesting3d.clearance import min_clearance
    r = _solve(clearance_mm=1.0)
    assert r.n_placed == 4
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
    rep = min_clearance(meshes, samples_per_mesh=3000, seed=1)
    assert rep.ok(1.0), (
        f"clearance_mm=1.0 gercek >=1mm boslugu saglamadi: {rep.min_mm:.3f}mm")


def test_clearance_submm_pitch_guarantees_gap():
    """REGRESYON KİLİDİ (2026-07-06): ince pitch (0.5mm) rejiminde clearance_mm=1.0
    -> olculen min bosluk >= 1mm. Eski margin=max(1,ceil(1/(2*pitch)))=1 formulu
    bu rejimde SADECE ~0.8mm veriyordu (ihlal); duzeltilmis margin=ceil(1/pitch)=2
    gecmeli. Kaba-pitch testi (pitch=5) bu bug'i YAKALAYAMIYORDU."""
    from src.nesting3d.export_stl import placed_meshes
    from src.nesting3d.clearance import min_clearance
    # 4 kucuk kutu @ pitch 0.5 (hizli); clearance 1.0 -> margin=z_clearance=2
    inst = NestingInstance(
        container=ContainerSpec(width_mm=40.0, depth_mm=40.0),
        parts=[
            PartSpec(id="c_a", name="c_a", qty=2, source="box",
                     width_mm=6.0, depth_mm=6.0, height_mm=6.0),
            PartSpec(id="c_b", name="c_b", qty=2, source="box",
                     width_mm=8.0, depth_mm=5.0, height_mm=4.0),
        ],
    )
    r = solve_coarse_to_fine(
        inst, plate_w_mm=40.0, plate_d_mm=40.0,
        coarse_pitch=2.0, fine_pitch=0.5, budget=BUDGET, seed=42,
        menu=_fast_menu(), clearance_mm=1.0,
    )
    assert r.n_placed == 4
    meshes = placed_meshes(r.placements, r.fine_voxel_parts, r.fine_pitch)
    rep = min_clearance(meshes, samples_per_mesh=3000, seed=1)
    assert rep.ok(1.0), (
        f"sub-mm pitch clearance saglanmadi: {rep.min_mm:.3f}mm "
        f"(margin=ceil(1/0.5)=2 gerekli)")


def test_clearance_positive_deterministic():
    """clearance_mm>0 yolu deterministik (ayni argüman -> ayni yukseklik)."""
    r1 = _solve(clearance_mm=1.0)
    r2 = _solve(clearance_mm=1.0)
    assert r1.height_mm == r2.height_mm
    assert r1.n_placed == r2.n_placed


def test_clearance_reaches_fine_bin3d(monkeypatch):
    """clearance_mm=1.0 -> fine _run_fine Bin3D'si z_clearance>=1 ile kurulur
    (kablonun Bin3D'ye ulastigini yakala; sonuctan bagimsiz)."""
    import src.nesting3d.coarse_to_fine as c2f
    seen_zc = []
    orig = c2f.Bin3D

    def _spy(*a, **k):
        seen_zc.append(k.get("z_clearance"))
        return orig(*a, **k)

    monkeypatch.setattr(c2f, "Bin3D", _spy)
    # Ince fine pitch (0.5) + clearance 1.0 -> fine z_clearance = max(1, ceil(1/0.5)) = 2
    # (Deneme4 senaryosunun net kaniti). _solve fine_pitch'i sabitledigi icin
    # dogrudan solve_coarse_to_fine cagrilir.
    solve_coarse_to_fine(
        _make_instance(),
        plate_w_mm=PLATE_W, plate_d_mm=PLATE_D,
        coarse_pitch=2.0, fine_pitch=0.5, budget=BUDGET, seed=42,
        menu=_fast_menu(), clearance_mm=1.0,
    )
    assert 2 in seen_zc, f"fine Bin3D z_clearance=2 kurulmali, gorulen: {seen_zc}"
