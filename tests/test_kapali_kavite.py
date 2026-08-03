"""test_kapali_kavite.py — kapali kavite (SLM toz hapsi) analizi TDD.

DENETIM_RAPORU_2026-07-03.md #21, FAZ-1: bu testler SADECE
`kapali_kavite_analizi` / `occ_grid_from_placements` fonksiyonlarinin
DOGRULUGUNU dogrular. Ciktinin legal/INVALID kararina baglanmadigi ayri bir
disiplin maddesidir (bkz. src/nesting3d/cavity.py modul basligi).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.cavity import kapali_kavite_analizi, occ_grid_from_placements


def _hollow_box(n: int = 5, hole: tuple | None = None) -> np.ndarray:
    """n x n x n kutu: duvarlar dolu, ic (n-2)^3 bos. `hole` verilirse o
    duvar hucresi de BOS yapilir (kaviteyi disariya acar)."""
    occ = np.ones((n, n, n), dtype=bool)
    occ[1:-1, 1:-1, 1:-1] = False
    if hole is not None:
        occ[hole] = False
    return occ


class TestKapaliKaviteAnalizi:
    def test_kapali_kutu_kaviteyi_bulur(self):
        occ = _hollow_box(5)
        pitch = 2.0
        rap = kapali_kavite_analizi(occ, pitch)
        assert rap["n_bolge"] == 1
        beklenen_voxel = 3 ** 3  # ic 3x3x3 bos
        assert rap["hacim_mm3"] == pytest.approx(beklenen_voxel * pitch ** 3)
        assert rap["en_buyuk_mm3"] == pytest.approx(beklenen_voxel * pitch ** 3)
        assert rap["sure_s"] >= 0.0

    def test_delikli_kutuda_kavite_yok(self):
        # duvarin ortasinda bir hucre bos -> ic bosluk disariyla baglanir
        occ = _hollow_box(5, hole=(0, 2, 2))
        rap = kapali_kavite_analizi(occ, 2.0)
        assert rap["n_bolge"] == 0
        assert rap["hacim_mm3"] == 0.0
        assert rap["en_buyuk_mm3"] == 0.0

    def test_tamamen_dolu_grid_sifir(self):
        occ = np.ones((4, 4, 4), dtype=bool)
        rap = kapali_kavite_analizi(occ, 1.5)
        assert rap == {"hacim_mm3": 0.0, "n_bolge": 0, "en_buyuk_mm3": 0.0,
                       "sure_s": rap["sure_s"]}
        assert rap["hacim_mm3"] == 0.0 and rap["n_bolge"] == 0

    def test_bos_grid_sifir(self):
        occ = np.zeros((4, 4, 4), dtype=bool)
        rap = kapali_kavite_analizi(occ, 1.5)
        assert rap["hacim_mm3"] == 0.0
        assert rap["n_bolge"] == 0
        assert rap["en_buyuk_mm3"] == 0.0

    def test_iki_ayri_kapali_kavite(self):
        # 9x5x5: iki ayri 5x5x5 kapali kutu yan yana (araları dolu duvar)
        occ = np.ones((9, 5, 5), dtype=bool)
        occ[1:4, 1:-1, 1:-1] = False   # kavite-1
        occ[5:8, 1:-1, 1:-1] = False   # kavite-2
        rap = kapali_kavite_analizi(occ, 1.0)
        assert rap["n_bolge"] == 2
        assert rap["hacim_mm3"] == pytest.approx(2 * 27.0)

    def test_uint8_girdi_kabul_edilir(self):
        occ = _hollow_box(5).astype(np.uint8)
        rap = kapali_kavite_analizi(occ, 1.0)
        assert rap["n_bolge"] == 1


class TestOccGridFromPlacements:
    def test_iki_parca_orleniyor(self):
        from types import SimpleNamespace

        g1 = np.zeros((2, 2, 2), dtype=bool)
        g1[:, :, 0] = True
        g2 = np.zeros((2, 2, 2), dtype=bool)
        g2[:, :, 0] = True

        class _Orient:
            def __init__(self, grid):
                self.grid = grid

        class _Part:
            def __init__(self, grid):
                self.orientations = [_Orient(grid)]

        parts = {"p1": _Part(g1), "p2": _Part(g2)}
        placements = [
            SimpleNamespace(part_id="p1", x=0, y=0, z=0, orientation_idx=0),
            SimpleNamespace(part_id="p2", x=2, y=0, z=0, orientation_idx=0),
        ]
        occ = occ_grid_from_placements(placements, parts, nx=4, ny=2)
        assert occ.shape == (4, 2, 2)
        assert occ[:, :, 0].all()
        assert not occ[:, :, 1].any()

    def test_bin_disina_tasan_pay_kirpilir(self):
        from types import SimpleNamespace

        grid = np.ones((3, 3, 3), dtype=bool)

        class _Orient:
            def __init__(self, grid):
                self.grid = grid

        class _Part:
            def __init__(self, grid):
                self.orientations = [_Orient(grid)]

        parts = {"p1": _Part(grid)}
        placements = [
            SimpleNamespace(part_id="p1", x=2, y=2, z=0, orientation_idx=0),
        ]
        # nx=ny=3 -> parca (x=2..5) disariya tasar, kirpilmali (hata FIRLAMAZ)
        occ = occ_grid_from_placements(placements, parts, nx=3, ny=3, nz=3)
        assert occ.shape == (3, 3, 3)
        assert occ[2, 2, 0]
