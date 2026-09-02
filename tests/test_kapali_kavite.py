"""test_kapali_kavite.py — kapali kavite (SLM toz hapsi) analizi TDD.

DENETIM_RAPORU_2026-07-03.md #21, FAZ-1: bu testler SADECE
`kapali_kavite_analizi` / `occ_grid_from_placements` fonksiyonlarinin
DOGRULUGUNU dogrular. Ciktinin legal/INVALID kararina baglanmadigi ayri bir
disiplin maddesidir (bkz. src/nesting3d/cavity.py modul basligi).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.nesting3d.cavity import (kaba_havuz, kapali_kavite_analizi,
                                  occ_grid_from_placements)


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


class TestKabaHavuz:
    """2026-09-02 p3-max dersi: buyuk gridde telemetri kaba pitch'te."""

    def test_f1_aynen_doner(self):
        occ = _hollow_box(5)
        assert kaba_havuz(occ, 1) is occ

    def test_any_havuz_ve_pad(self):
        occ = np.zeros((5, 4, 3), dtype=bool)
        occ[4, 0, 0] = True   # pad'e dusen kenar blogu
        occ[0, 3, 2] = True
        k = kaba_havuz(occ, 2)
        assert k.shape == (3, 2, 2)
        assert k[2, 0, 0] and k[0, 1, 1]
        assert int(k.sum()) == 2

    def test_kaba_grid_kapali_kutuyu_korur(self):
        # 10^3 kutu, duvar 2 voxel, ic 6^3 bos -> f=2'de 5^3 kutu, ic 3^3
        occ = np.ones((10, 10, 10), dtype=bool)
        occ[2:-2, 2:-2, 2:-2] = False
        rap = kapali_kavite_analizi(kaba_havuz(occ, 2), 2.0)
        assert rap["n_bolge"] == 1
        assert rap["hacim_mm3"] == pytest.approx(27 * 8.0)


class TestKapaliKaviteGateButce:
    """demo_pipeline._kapali_kavite_gate voxel butcesi (telemetri; uretim
    cozumu degismez)."""

    def _kur(self):
        from types import SimpleNamespace

        class _Orient:
            def __init__(self, grid):
                self.grid = grid

        class _Part:
            def __init__(self, grid):
                self.orientations = [_Orient(grid)]

        grid = np.ones((4, 4, 4), dtype=bool)
        grid[1:-1, 1:-1, 1:-1] = False
        parts = {"p1": _Part(grid)}
        pls = [SimpleNamespace(part_id="p1", x=0, y=0, z=0,
                               orientation_idx=0)]
        return pls, parts

    def test_butce_icinde_ince_olcum(self, monkeypatch):
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "KAVITE_VOXEL_BUTCE", 10 ** 9)
        pls, parts = self._kur()
        instr = {}
        dp._kapali_kavite_gate(pls, parts, 8.0, 8.0, 1.0, instr)
        rap = instr["kapali_kavite"]
        assert rap["kaba_faktor"] == 1 and rap["pitch_mm"] == 1.0
        assert rap["n_bolge"] == 1 and rap["hacim_mm3"] == pytest.approx(8.0)
        assert rap["n_voxel_ince"] == 8 * 8 * 4

    def test_butce_asilinca_kaba_faktor(self, monkeypatch):
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "KAVITE_VOXEL_BUTCE", 40)   # 256 voxel > 40
        pls, parts = self._kur()
        instr = {}
        dp._kapali_kavite_gate(pls, parts, 8.0, 8.0, 1.0, instr)
        rap = instr["kapali_kavite"]
        assert rap["kaba_faktor"] == 2 and rap["pitch_mm"] == 2.0
        assert "n_bolge" in rap and "atlandi" not in rap

    def test_tavan_asilinca_atlanir(self, monkeypatch):
        import scripts.demo_pipeline as dp
        monkeypatch.setattr(dp, "KAVITE_VOXEL_TAVAN", 100)
        pls, parts = self._kur()
        instr = {}
        dp._kapali_kavite_gate(pls, parts, 8.0, 8.0, 1.0, instr)
        rap = instr["kapali_kavite"]
        assert rap["atlandi"] == "voxel tavani" and rap["n_voxel"] == 256
