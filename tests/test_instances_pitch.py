"""tests/test_instances_pitch.py — Adaptif pitch önerisi birim testleri (R6).

Kapsam (instances/pitch.suggest_pitch):
- Determinizm: aynı instance → aynı pitch.
- Türetme: pitch = min_dim / factor (kelepçe aralığı içinde).
- Kelepçe: floor ve ceil sınırlarına dayanma.
- Çöken thin_plates/long_rods instance'larının artık voxelize edilebilir
  pitch ürettiği (regresyon — 2026-06-14 tanısı).
- Hata yolları: boş instance, floor > ceil.
"""

from __future__ import annotations

import pytest

from src.nesting3d.instances.pitch import (
    suggest_pitch,
    suggest_nfv_pitch,
    min_feature_mm,
    DEFAULT_FACTOR,
    DEFAULT_FLOOR,
    DEFAULT_CEIL,
    SAFE_FILL_RATIO,
    MIN_FILL_RATIO,
)
from src.nesting3d.instances.synthetic import (
    random_boxes,
    thin_plates,
    long_rods,
)


class TestMinFeature:
    def test_min_feature_picks_smallest_dim(self):
        inst = random_boxes(n_parts=6, min_dim=10.0, max_dim=40.0, seed=1)
        mf = min_feature_mm(inst)
        # Tüm parçaların tüm boyutları >= mf olmalı.
        for p in inst.parts:
            assert min(p.width_mm, p.depth_mm, p.height_mm) >= mf - 1e-9
        assert mf >= 10.0 - 1e-9  # min_dim alt sınırı


class TestSuggestPitch:
    def test_deterministic(self):
        inst = thin_plates(n_parts=8, seed=4)
        assert suggest_pitch(inst) == suggest_pitch(inst)

    def test_pitch_is_min_dim_over_factor_when_in_range(self):
        # min_dim ~ 10-40 aralığında random_boxes; min_dim/2.5 genelde
        # [floor, ceil] içinde kalır → tam türetme değeri beklenir.
        inst = random_boxes(n_parts=6, min_dim=10.0, max_dim=40.0, seed=2)
        mf = min_feature_mm(inst)
        expected = mf / DEFAULT_FACTOR
        if DEFAULT_FLOOR <= expected <= DEFAULT_CEIL:
            assert suggest_pitch(inst) == pytest.approx(expected)

    def test_never_below_floor(self):
        # Çıktı asla floor altına inmez (varsayılan floor ile).
        inst = thin_plates(n_parts=8, seed=4)
        assert suggest_pitch(inst) >= DEFAULT_FLOOR - 1e-9

    def test_clamped_to_floor_explicit(self):
        # Yüksek explicit floor doğal pitch'in üstündeyse clamp devreye girer.
        inst = thin_plates(n_parts=8, seed=4)
        mf = min_feature_mm(inst)
        natural = mf / DEFAULT_FACTOR
        high_floor = natural + 1.0  # doğal pitch'in garantili üstünde
        p = suggest_pitch(inst, floor=high_floor)
        assert p == pytest.approx(high_floor)

    def test_clamped_to_ceil(self):
        # Büyük parçalı instance: ceil'i düşük tutup tavanlamayı zorla.
        inst = random_boxes(n_parts=4, min_dim=100.0, max_dim=120.0, seed=3)
        p = suggest_pitch(inst, ceil=5.0)
        assert p == pytest.approx(5.0)

    def test_custom_factor(self):
        inst = random_boxes(n_parts=4, min_dim=30.0, max_dim=30.0, seed=0)
        mf = min_feature_mm(inst)
        p = suggest_pitch(inst, factor=3.0, floor=0.1, ceil=100.0)
        assert p == pytest.approx(mf / 3.0)


class TestSuggestNfvPitch:
    """NFV-farkında pitch (backlog #1, ölçüm c3_pitch_curve.py 2026-06-23).

    suggest_pitch'in TERSİ: NFV'de pitch maliyeti kübik + kalite az duyarlı → parçayı
    kaybetmeyen EN KABA pitch seçilir (hız/bellek min). + bellek pre-flight guard.
    """

    LARGE_RAM = 64 * 1024 ** 3  # bütçe bol → feasible (guard tetiklenmesin)

    def test_nfv_pitch_coarser_than_heightmap(self):
        # NFV pitch (min_feature/0.5) heightmap pitch'inden (min_feature/2.5) DAİMA kaba olmalı.
        inst = random_boxes(n_parts=6, min_dim=10.0, max_dim=40.0, seed=2)
        nfv_p, feasible, reason = suggest_nfv_pitch(
            inst, plate_w_mm=500.0, plate_d_mm=500.0, ram_bytes=self.LARGE_RAM)
        assert nfv_p > suggest_pitch(inst)  # NFV daha kaba (ters yön)
        assert feasible

    def test_nfv_pitch_derivation_safe(self):
        # Bütçe bol → güvenli (parça-garanti) pitch = min_feature / safe_ratio (=1.0).
        inst = random_boxes(n_parts=6, min_dim=10.0, max_dim=40.0, seed=2)
        mf = min_feature_mm(inst)
        nfv_p, feasible, _ = suggest_nfv_pitch(
            inst, plate_w_mm=500.0, plate_d_mm=500.0, ram_bytes=self.LARGE_RAM)
        assert feasible
        assert nfv_p == pytest.approx(mf / SAFE_FILL_RATIO)

    def test_memory_coarsens_but_feasible(self):
        # İnce parça + büyük plaka + sınırlı RAM: güvenli pitch belleği aşar → kabalaştırılır
        # (Plan2 senaryosu) ama voxelize sınırını (min_ratio) aşmadan feasible kalır.
        inst = random_boxes(n_parts=6, min_dim=2.0, max_dim=8.0, seed=2)
        mf = min_feature_mm(inst)
        pitch_safe = mf / SAFE_FILL_RATIO
        nfv_p, feasible, reason = suggest_nfv_pitch(
            inst, plate_w_mm=300.0, plate_d_mm=300.0, ram_bytes=5 * 1024 ** 3)
        assert feasible
        assert nfv_p > pitch_safe  # bellek için kabalaştırıldı
        assert nfv_p <= mf / MIN_FILL_RATIO + 1e-6  # voxelize mutlak sınırını aşmadı
        assert "kabalastirildi" in reason

    def test_memory_guard_marks_infeasible(self):
        # Çok küçük RAM bütçesi → en kaba pitch bile grid bütçesini aşar → feasible=False.
        inst = random_boxes(n_parts=6, min_dim=1.0, max_dim=4.0, seed=2)  # ince → büyük grid
        _, feasible, reason = suggest_nfv_pitch(
            inst, plate_w_mm=500.0, plate_d_mm=500.0, ram_bytes=256 * 1024 ** 2)  # 256MB
        assert feasible is False
        assert "bellek-riskli" in reason

    def test_reason_is_ascii_safe(self):
        # Windows cp1254 stdout non-ASCII'de çöker → reason ASCII olmalı (gerçek bug, 2026-06-23).
        inst = random_boxes(n_parts=4, min_dim=10.0, max_dim=20.0, seed=1)
        for ram in (self.LARGE_RAM, 64 * 1024 ** 2):  # feasible + infeasible iki yol
            _, _, reason = suggest_nfv_pitch(
                inst, plate_w_mm=500.0, plate_d_mm=500.0, ram_bytes=ram)
            reason.encode("cp1254")  # çökmemeli

    def test_never_below_floor(self):
        inst = random_boxes(n_parts=4, min_dim=10.0, max_dim=20.0, seed=1)
        nfv_p, _, _ = suggest_nfv_pitch(
            inst, plate_w_mm=500.0, plate_d_mm=500.0, ram_bytes=self.LARGE_RAM, floor=99.0)
        assert nfv_p >= 99.0 - 1e-9

    def test_plate_ratio_caps_pitch(self):
        # Büyük parça + küçük plaka: pitch plaka-oranı tavanına çekilir (parça+margin sığsın).
        inst = random_boxes(n_parts=4, min_dim=20.0, max_dim=20.0, seed=0)  # 20mm küpler
        # plaka 50, margin 1: plate_ceil=(50-20)/2=15; güvenli mf/1.0=20 → pitch=min(20,15)=15
        nfv_p, feasible, _ = suggest_nfv_pitch(
            inst, plate_w_mm=50.0, plate_d_mm=50.0, ram_bytes=self.LARGE_RAM, margin=1)
        assert feasible
        assert nfv_p <= 15.0 + 1e-6  # plaka-oranı tavanına çekildi (boxy çökmesini önler)

    def test_part_larger_than_plate_infeasible(self):
        # Parça tek boyutta plakadan büyük → sığmaz → feasible=False (NFV değil hiçbir şey çözemez).
        inst = random_boxes(n_parts=4, min_dim=20.0, max_dim=20.0, seed=0)
        _, feasible, reason = suggest_nfv_pitch(
            inst, plate_w_mm=15.0, plate_d_mm=15.0, ram_bytes=self.LARGE_RAM)
        assert feasible is False
        assert "sigmaz" in reason

    def test_empty_instance_raises(self):
        from src.nesting3d.instances.format import NestingInstance, ContainerSpec
        empty = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None),
            parts=[], meta={})
        with pytest.raises(ValueError):
            suggest_nfv_pitch(empty, plate_w_mm=100.0, plate_d_mm=100.0, ram_bytes=self.LARGE_RAM)


class TestVoxelizationRegression:
    """2026-06-14 tanısı: pitch=15'te çöken instance'lar adaptif pitch ile koşar."""

    @pytest.mark.parametrize(
        "inst_factory",
        [
            lambda: thin_plates(n_parts=8, seed=0),
            lambda: thin_plates(n_parts=8, seed=4),
            lambda: long_rods(n_parts=6, seed=5),
        ],
    )
    def test_adaptive_pitch_voxelizes(self, inst_factory):
        from src.nesting3d.instances.format import to_voxel_parts

        inst = inst_factory()
        p = suggest_pitch(inst)
        # Çökmeden voxelize olmalı (eski pitch=15 ValueError atıyordu).
        parts = to_voxel_parts(inst, p, n_orientations=4)
        assert len(parts) >= 1


class TestVoxelizerFailFastGuard:
    """Voxelizer fail-fast guard: çok kaba pitch'te şifreli assert değil,
    açık aksiyon alınabilir ValueError vermeli (2026-06-14 kullanıcı şartı)."""

    def test_too_coarse_pitch_raises_clear_value_error(self):
        from src.nesting3d.instances.format import to_voxel_parts

        # thin_plates @ pitch=15: kalınlık 3-12mm < pitch/2 → eskiden çöküyordu.
        inst = thin_plates(n_parts=8, seed=4)
        with pytest.raises(ValueError) as excinfo:
            to_voxel_parts(inst, 15.0, n_orientations=4)
        msg = str(excinfo.value)
        # Mesaj pitch'i ve adaptif pitch yönlendirmesini içermeli.
        assert "pitch" in msg.lower()
        assert "suggest_pitch" in msg


class TestErrorPaths:
    def test_floor_gt_ceil_raises(self):
        inst = random_boxes(n_parts=3, seed=0)
        with pytest.raises(ValueError):
            suggest_pitch(inst, floor=10.0, ceil=5.0)

    def test_empty_instance_raises(self):
        from src.nesting3d.instances.format import NestingInstance, ContainerSpec

        empty = NestingInstance(
            container=ContainerSpec(width_mm=100.0, depth_mm=100.0, height_mm=None),
            parts=[],
            meta={},
        )
        with pytest.raises(ValueError):
            suggest_pitch(empty)
