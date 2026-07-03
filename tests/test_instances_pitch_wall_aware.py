"""tests/test_instances_pitch_wall_aware.py — Cidar-duyarli (wall-aware) OPT-IN pitch.

K-19 (YONTEM_HARITASI §3.1) uretime baglama (F3), OPT-IN. Kabuk ailesinde
(thin_shell/tube) ORTAK pitch cidar kalinligindan (PartSpec.wall_mm = 2V/A)
turer; bbox-min yerine cidar kullanildiginda pitch cok daha ince olur
(Deneme4: min_feature 7.26->0.81 -> pitch 2.9 yerine 0.5mm).

Tetik SARTLARI (hepsi birden):
  (a) cagiran wall_aware=True gecmis (DEFAULT False = mevcut davranis BIT-OZDES),
  (b) classify_prelim family in {thin_shell, tube},
  (c) family guveni >= esik (default WALL_AWARE_CONF_THRESHOLD),
  (d) min_feature kaynagi = PartSpec.wall_mm (None ise bbox-min ile katilir);
      sonuc TEK ORTAK pitch (H-06 per-part pitch NO-GO).

Esik turetimi (gercek-veri family guvenleri; K-19 olcum + F3 brief). Iki tablo
olculdu (qty-agirlik family oylamasini kaydirir); ikisi de raporlanir:

  URETIM qty-agirlikli (ASIL KAPI, siparis adetleri dahil):
    deneme4 = 0.87  -> TETIKLER
    plan2   = 0.58 ; plan3 = 0.56 ; plan1 = 0.53 (mixed_scale)
    numune  = 0.59 (mixed_scale) ; boxy = 0.69 (solid_bulk)
    -> esige headroom ~0.17 (en yakin non-tetik = boxy 0.69, family kapisi zaten reddeder).
  Dry-run qty=1 (bilgi amacli, f3_dryrun; adetsiz oylama):
    deneme4 = 0.89 ; plan2 = 0.66 ; plan1 = 0.64 ; numune = 0.65
    plan3   = 0.52 ; boxy = 0.67
    -> esige headroom yalniz ~0.09 (en yakin non-tetik = plan2 0.66).

Esik (max non-tetik, deneme4] araliginda olmali. Default 0.75. Guvenlik payi
MUHAFAZAKAR okunur: qty=1 tablosunda min headroom ~0.09 (deneme4 tarafinda
0.89-0.75=0.14). boxy her iki tabloda solid_bulk (family kapisi reddeder;
guven kapisi ikinci savunma). Sihirli-sayi DEGIL: wall_conf_threshold
parametresiyle ezilebilir; dar qty=1 payi ilerideki setlerde yeniden olcum
gerektirebilir.
"""

from __future__ import annotations

import pytest

from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
from src.nesting3d.instances.pitch import (
    DEFAULT_FACTOR,
    DEFAULT_FLOOR,
    SAFE_FILL_RATIO,
    WALL_AWARE_CONF_THRESHOLD,
    min_feature_mm,
    suggest_nfv_pitch,
    suggest_pitch,
    wall_feature_mm,
)
from src.nesting3d.instances.family import THIN_SHELL, TUBE, classify_prelim


# ---------------------------------------------------------------------------
# Fixture kuruculari — dogrudan PartSpec (hizli, STL yok)
# ---------------------------------------------------------------------------

def _container() -> ContainerSpec:
    return ContainerSpec(width_mm=300.0, depth_mm=250.0, height_mm=None)


def _shell_part(pid: str, *, w, d, h, wall, true_fill, qty=1) -> PartSpec:
    """Ince-cidarli kabuk parcasi (stl kaynak, wall_mm + dusuk true_fill)."""
    return PartSpec(
        id=pid, name=pid, qty=qty, source="stl", stl_path=f"/x/{pid}.stl",
        width_mm=w, depth_mm=d, height_mm=h, wall_mm=wall, true_fill=true_fill,
    )


def _box_part(pid: str, *, w, d, h, qty=1) -> PartSpec:
    return PartSpec(id=pid, name=pid, qty=qty, source="box",
                    width_mm=w, depth_mm=d, height_mm=h)


def high_conf_shell_instance() -> NestingInstance:
    """Yuksek-guven kabuk (deneme4 benzeri): wall_mm dolu, true_fill dusuk."""
    parts = [
        _shell_part("s1", w=50.0, d=40.0, h=30.0, wall=1.5, true_fill=0.05, qty=2),
        _shell_part("s2", w=60.0, d=45.0, h=35.0, wall=2.0, true_fill=0.08, qty=2),
    ]
    return NestingInstance(container=_container(), parts=parts)


def low_conf_shell_instance() -> NestingInstance:
    """Dusuk-guven kabuk (plan2/plan3 benzeri): family=thin_shell ama guven<esik.

    wall_mm dolu (cidar var) ama true_fill 0.5'e cok yakin -> _fill_conf dusuk (~0.71).
    """
    parts = [
        _shell_part("l1", w=50.0, d=40.0, h=30.0, wall=1.0, true_fill=0.48, qty=2),
        _shell_part("l2", w=55.0, d=42.0, h=32.0, wall=1.2, true_fill=0.49, qty=2),
    ]
    return NestingInstance(container=_container(), parts=parts)


def solid_bulk_instance() -> NestingInstance:
    """Boxy: kati kup blok -> solid_bulk (family kapisi reddeder)."""
    parts = [
        _box_part("b1", w=60.0, d=60.0, h=55.0, qty=3),
        _box_part("b2", w=70.0, d=65.0, h=60.0, qty=2),
    ]
    return NestingInstance(container=_container(), parts=parts)


def mixed_wall_instance() -> NestingInstance:
    """Bazi parcalar wall_mm dolu, bazilari None -> ortak pitch min hepsi uzerinden."""
    parts = [
        _shell_part("m1", w=50.0, d=40.0, h=30.0, wall=1.5, true_fill=0.05, qty=2),
        # wall_mm None ama true_fill dusuk -> yine kabuk; wall_feature bbox-min ile katilir
        _shell_part("m2", w=45.0, d=20.0, h=25.0, wall=None, true_fill=0.05, qty=2),
    ]
    return NestingInstance(container=_container(), parts=parts)


# ---------------------------------------------------------------------------
# Esik + fixture on-dogrulama (kapilarin gercekten ayirdigini garanti et)
# ---------------------------------------------------------------------------

class TestFixtureConfidenceGates:
    def test_default_threshold_between_real_labels(self):
        # Esik (0.58, 0.87] araliginda; plan2/plan3'un ustunde, deneme4'un altinda.
        assert 0.58 < WALL_AWARE_CONF_THRESHOLD <= 0.87
        assert WALL_AWARE_CONF_THRESHOLD > 0.69  # boxy defans-derinligi

    def test_high_conf_shell_classifies_above_threshold(self):
        fam, conf = classify_prelim(high_conf_shell_instance())
        assert fam in (THIN_SHELL, TUBE)
        assert conf >= WALL_AWARE_CONF_THRESHOLD

    def test_low_conf_shell_is_shell_but_below_threshold(self):
        fam, conf = classify_prelim(low_conf_shell_instance())
        assert fam in (THIN_SHELL, TUBE)          # aile dogru
        assert conf < WALL_AWARE_CONF_THRESHOLD    # ama guven esik altinda

    def test_solid_bulk_family_rejected(self):
        fam, _ = classify_prelim(solid_bulk_instance())
        assert fam not in (THIN_SHELL, TUBE)


# ---------------------------------------------------------------------------
# wall_feature_mm — cidar-turevli en kucuk ozellik
# ---------------------------------------------------------------------------

class TestWallFeature:
    def test_uses_wall_mm_when_present(self):
        inst = high_conf_shell_instance()
        wf = wall_feature_mm(inst)
        assert wf == pytest.approx(1.5)  # en ince cidar
        assert wf < min_feature_mm(inst)  # bbox-min'den cok daha ince

    def test_falls_back_to_bbox_min_when_wall_none(self):
        # m2 wall_mm=None -> bbox-min=20 katilir; m1 wall=1.5 -> min(1.5,20)=1.5
        inst = mixed_wall_instance()
        assert wall_feature_mm(inst) == pytest.approx(1.5)

    def test_all_wall_none_equals_min_feature(self):
        inst = solid_bulk_instance()
        assert wall_feature_mm(inst) == pytest.approx(min_feature_mm(inst))


# ---------------------------------------------------------------------------
# suggest_pitch — OPT-IN cidar dali (heightmap yolu)
# ---------------------------------------------------------------------------

class TestSuggestPitchWallAware:
    def test_default_off_is_bit_identical(self):
        # wall_aware DEFAULT False: cikti eski davranisla BIT-OZDES olmali.
        for inst in (high_conf_shell_instance(), low_conf_shell_instance(),
                     solid_bulk_instance(), mixed_wall_instance()):
            assert suggest_pitch(inst, wall_aware=False) == suggest_pitch(inst)

    def test_high_conf_shell_triggers_wall_pitch(self):
        inst = high_conf_shell_instance()
        normal = suggest_pitch(inst)  # bbox-min turevli
        wall = suggest_pitch(inst, wall_aware=True)
        assert wall < normal  # cidar-turevli daha ince
        expected = max(DEFAULT_FLOOR, wall_feature_mm(inst) / DEFAULT_FACTOR)
        assert wall == pytest.approx(expected)

    def test_low_conf_shell_does_not_trigger(self):
        # Aile thin_shell AMA guven<esik -> tetiklenmez; pitch bbox-turevli kalir.
        inst = low_conf_shell_instance()
        assert suggest_pitch(inst, wall_aware=True) == pytest.approx(suggest_pitch(inst))

    def test_solid_bulk_does_not_trigger(self):
        # Family kapisi: solid_bulk -> tetiklenmez (yuksek guven olsa bile).
        inst = solid_bulk_instance()
        assert suggest_pitch(inst, wall_aware=True) == pytest.approx(suggest_pitch(inst))

    def test_threshold_override_can_force_trigger(self):
        # Dusuk-guven kabuk normalde tetiklemez; esik dusurulunce tetikler.
        inst = low_conf_shell_instance()
        base = suggest_pitch(inst)
        forced = suggest_pitch(inst, wall_aware=True, wall_conf_threshold=0.5)
        assert forced < base  # esik dususu ile cidar dali acildi

    def test_common_pitch_single_value(self):
        # H-06: sonuc tek skaler (per-part degil).
        inst = mixed_wall_instance()
        p = suggest_pitch(inst, wall_aware=True)
        assert isinstance(p, float)


# ---------------------------------------------------------------------------
# suggest_nfv_pitch — OPT-IN cidar dali (plaka-boyut kosullu, H-11 korunur)
# ---------------------------------------------------------------------------

class TestSuggestNfvPitchWallAware:
    LARGE_RAM = 64 * 1024 ** 3

    def test_default_off_is_bit_identical(self):
        inst = high_conf_shell_instance()
        a = suggest_nfv_pitch(inst, plate_w_mm=300.0, plate_d_mm=250.0,
                              ram_bytes=self.LARGE_RAM)
        b = suggest_nfv_pitch(inst, plate_w_mm=300.0, plate_d_mm=250.0,
                              ram_bytes=self.LARGE_RAM, wall_aware=False)
        assert a[0] == pytest.approx(b[0])
        assert a[1] == b[1]

    def test_wall_aware_finer_on_small_plate(self):
        # Kucuk plaka + bol RAM: cidar dali grid butceye sigar -> daha ince pitch.
        inst = high_conf_shell_instance()
        base, _, _ = suggest_nfv_pitch(
            inst, plate_w_mm=200.0, plate_d_mm=150.0, ram_bytes=self.LARGE_RAM)
        wall, feasible, reason = suggest_nfv_pitch(
            inst, plate_w_mm=200.0, plate_d_mm=150.0, ram_bytes=self.LARGE_RAM,
            wall_aware=True)
        assert feasible
        assert wall < base  # cidar-duyarli daha ince NFV pitch
        assert "cidar-duyarli" in reason

    def test_wall_branch_skipped_on_large_plate_h11(self):
        # H-11 FFT bellek duvari: cok buyuk plaka + sinirli RAM -> cidar pitch grid'i
        # butceyi asar -> cidar ATLANIR, min_feature davranisi korunur (OOM'dan kacin).
        inst = high_conf_shell_instance()
        small_ram = 2 * 1024 ** 3
        base, _, _ = suggest_nfv_pitch(
            inst, plate_w_mm=2000.0, plate_d_mm=2000.0, ram_bytes=small_ram)
        wall, _, reason = suggest_nfv_pitch(
            inst, plate_w_mm=2000.0, plate_d_mm=2000.0, ram_bytes=small_ram,
            wall_aware=True)
        assert wall == pytest.approx(base)  # cidar atlandi -> ayni sonuc
        assert "cidar-atlandi" in reason

    def test_solid_bulk_no_trigger(self):
        inst = solid_bulk_instance()
        base = suggest_nfv_pitch(inst, plate_w_mm=300.0, plate_d_mm=250.0,
                                 ram_bytes=self.LARGE_RAM)
        wall = suggest_nfv_pitch(inst, plate_w_mm=300.0, plate_d_mm=250.0,
                                 ram_bytes=self.LARGE_RAM, wall_aware=True)
        assert wall[0] == pytest.approx(base[0])

    def test_reason_is_ascii_safe(self):
        inst = high_conf_shell_instance()
        for plate in (200.0, 2000.0):
            _, _, reason = suggest_nfv_pitch(
                inst, plate_w_mm=plate, plate_d_mm=plate,
                ram_bytes=2 * 1024 ** 3, wall_aware=True)
            reason.encode("cp1254")  # cokmemeli
