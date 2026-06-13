"""test_regression_numune.py — Faz 0.1 regresyon emniyet agi (PLAN_DEMO1.md).

DBLF baseline (SA'siz) deterministik altin deger testi.
Altin deger: 214.5 mm — ilk kosuda olculerek sabitlenen deger
(2026-06-12, pitch 1.5, plate 335, margin 1, orient hybrid, slice method).

Konfigurasyon (tum motor degisikliklerinden once bu testi yaz, sonra motorlara dokunma):
  - senaryo  : numune (48 gercek parca)
  - pitch    : 1.5 mm
  - plate    : 335.0 mm (hoca makinesi tabani, 2026-06-11)
  - margin   : 1 voxel (garantili >= 1 mm gercek mesafe)
  - method   : slice (yuksek yuz sayili STL'ler icin hacim-dogru yol)
  - orient   : hybrid (NUMUNE_ORIENTATIONS_HYBRID)
  - algo     : dblf (SA YOK — deterministik, seed bagimsiz)

Kabul kriteri: +-0 sapma (tam esitlik; DBLF deterministik).

@pytest.mark.slow: slice voxelization gercek numune STL'leri icin dakikalar surер.
Default pytest kosusunda bu test ATLANIR (`pytest.ini: addopts = -m "not slow"`).
Tam kosus: `pytest -m slow`
"""

import pytest

from src.nesting3d.bin3d import Bin3D
from src.nesting3d.dblf import dblf
from src.nesting3d.models import (
    NUMUNE_DIR,
    NUMUNE_ORIENTATIONS_HYBRID,
    model_set,
)
from src.nesting3d.voxelize import expand_quantities

# Altin deger — 2026-06-12 ilk kosuda olculdu, elle degistirme yasak.
# Motor degisikligi bu degeri bozarsa: once benchmark'ta gerilemеyi belgele,
# sonra bu sabiti guncelle (PLAN_DEMO1.md tek-konfig kurali §4.4).
DBLF_BASELINE_GOLDEN_MM = 214.5

# Rekor konfigurasyon parametreleri (compare_numune.py + ILERLEME_2026-06-11)
PITCH = 1.5
PLATE = 335.0
MARGIN = 1
N_ORIENTATIONS = 8  # expand_quantities'e: 8-poz master set (0-7); tilt harici


@pytest.mark.slow
@pytest.mark.skipif(not NUMUNE_DIR.exists(), reason="Numuneler/ klasoru yok")
def test_dblf_baseline_numune_golden():
    """DBLF baseline yuksekligi altin degerden sapmasin (+-0, deterministik).

    Bu test hizli degil: 48 gercek STL parcayi slice yontemiyle voxelize eder,
    dakikalar surebilir.  `pytest -m slow` ile kosturun.
    """
    parts = expand_quantities(
        model_set("numune"),
        PITCH,
        n_orientations=N_ORIENTATIONS,
        margin=MARGIN,
        method="slice",
        orientation_overrides=NUMUNE_ORIENTATIONS_HYBRID,
    )
    assert len(parts) == 48, f"Beklenen 48 parca, bulundu: {len(parts)}"

    bin_factory = lambda: Bin3D(PLATE, PLATE, PITCH, z_clearance=MARGIN)
    _placements, bin3d = dblf(parts, bin_factory)

    height = bin3d.max_height_mm()
    assert height == pytest.approx(DBLF_BASELINE_GOLDEN_MM, abs=0.0), (
        f"DBLF baseline regresyonu: beklenen {DBLF_BASELINE_GOLDEN_MM} mm, "
        f"bulundu {height:.1f} mm — motor degisikligi baseline'i bozmus olabilir."
    )
