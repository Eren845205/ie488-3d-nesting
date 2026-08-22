"""tests/test_kafes_zincir.py — kafes uretim-kablosu birim testleri.

Kapsam (kanopi-zinciri kabul sozlesmesinin aynisi):
  - tetik yok -> ref BIREBIR + a2 HIC olculmez (sifir maliyet)
  - tetik + legal + ref'ten iyi -> KABUL (secilen=kafes, kazanc)
  - tetik + legal ama ref'ten iyi degil -> RED, ref doner
  - tetik + a2-illegal (clearance dusuk / kilit>0 / eksik) -> RED
  - kare olmayan plaka -> tetik DENENMEZ, ref doner
  - coz hatasi / a2 olcum hatasi -> ref doner (uretim dusurulmez)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.nesting3d.kafes_zincir import kafes_zinciri_uretim


@dataclass
class _FakePart:
    qty: int = 1


@dataclass
class _FakeInst:
    parts: List[_FakePart] = field(default_factory=lambda: [_FakePart(10)])


@dataclass
class _FakeRes:
    height_mm: float = 100.0
    n_placed: int = 10
    placements: tuple = ()
    fine_voxel_parts: tuple = ()
    fine_pitch: float = 2.0


def _a2_legal(res, n_total, clearance_mm):
    return {"min_clearance_mm": 2.1, "kilit_5yon": 0,
            "n_placed": res.n_placed, "legal": True}


def _a2_sayac(kayit):
    def olc(res, n_total, clearance_mm):
        kayit.append(1)
        return _a2_legal(res, n_total, clearance_mm)
    return olc


class TestTetiksiz:
    def test_ref_birebir_ve_a2_olculmez(self):
        ref = _FakeRes()
        a2_cagri = []
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": False},
            _a2=_a2_sayac(a2_cagri))
        assert res is ref
        assert tel["tetik"] is False and tel["secilen"] == "ref"
        assert a2_cagri == []


class TestKabulRed:
    def test_legal_ve_iyi_kabul(self):
        ref = _FakeRes(height_mm=100.0)
        aday = _FakeRes(height_mm=80.0)
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": True, "res": aday},
            _a2=_a2_legal)
        assert res is aday
        assert tel["secilen"] == "kafes"
        assert tel["kazanc_mm"] == 20.0

    def test_legal_ama_iyi_degil_red(self):
        ref = _FakeRes(height_mm=100.0)
        aday = _FakeRes(height_mm=100.0)  # esit = iyi DEGIL
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": True, "res": aday},
            _a2=_a2_legal)
        assert res is ref
        assert "iyi degil" in tel["red_sebep"]

    def test_illegal_red(self):
        ref = _FakeRes(height_mm=100.0)
        aday = _FakeRes(height_mm=80.0)

        def a2_kilitli(res, n_total, clearance_mm):
            return {"min_clearance_mm": 2.1, "kilit_5yon": 3,
                    "n_placed": res.n_placed, "legal": False}
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": True, "res": aday},
            _a2=a2_kilitli)
        assert res is ref
        assert tel["red_sebep"] == "a2-illegal"

    def test_ref_eff_esas(self):
        """ref_height_mm (r11-etkili) verilirse kiyas ONA yapilir."""
        ref = _FakeRes(height_mm=100.0)
        aday = _FakeRes(height_mm=95.0)
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            ref_height_mm=90.0,  # etkili ref 90 -> 95 kabul EDILMEZ
            _coz=lambda inst, **kw: {"tetik": True, "res": aday},
            _a2=_a2_legal)
        assert res is ref


class TestGuvenlik:
    def test_kare_olmayan_plaka_atlanir(self):
        ref = _FakeRes()
        cagri = []

        def coz(inst, **kw):
            cagri.append(1)
            return {"tetik": True, "res": _FakeRes(height_mm=1.0)}
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=300, ref_res=ref,
            _coz=coz, _a2=_a2_legal)
        assert res is ref and cagri == []
        assert "kare-olmayan" in tel["atlandi"]

    def test_coz_hatasi_ref_doner(self):
        ref = _FakeRes()

        def coz(inst, **kw):
            raise RuntimeError("patladi")
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=coz, _a2=_a2_legal)
        assert res is ref and "patladi" in tel["hata"]

    def test_a2_olcum_hatasi_red(self):
        ref = _FakeRes(height_mm=100.0)

        def a2_patlak(res, n_total, clearance_mm):
            raise ValueError("olculemedi")
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": True,
                                     "res": _FakeRes(height_mm=1.0)},
            _a2=a2_patlak)
        assert res is ref and "a2 olcum" in tel["hata"]

    def test_coz_hata_alani_red(self):
        ref = _FakeRes()
        res, tel = kafes_zinciri_uretim(
            _FakeInst(), plate_w_mm=335, plate_d_mm=335, ref_res=ref,
            _coz=lambda inst, **kw: {"tetik": True, "hata": "ic hata"},
            _a2=_a2_legal)
        assert res is ref and tel["hata"] == "ic hata"
