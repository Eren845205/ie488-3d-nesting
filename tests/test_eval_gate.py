# -*- coding: utf-8 -*-
"""eval_gate saf fonksiyon testleri (legal_of + compare_verdict â€” ANAYASA A2/B2).

Solve KOSMAZ â€” yalniz metrik/verdict mantigi. Kosum: pytest tests/test_eval_gate.py
"""
from scripts.eval_gate import legal_of, compare_verdict


# ---------------------------------------------------------------------------
# legal_of â€” A2: yerlesen==N ve clearance>=1 ve 0 kilit, aksi INVALID(sebep)
# ---------------------------------------------------------------------------

def test_legal_of_gecerli():
    lh, reason = legal_of(264.0, 588, 588, 2.023, 0)  # A2: req=2.0 (Sprint-3)
    assert lh == 264.0 and reason is None


def test_legal_of_clearance_ihlali():
    lh, reason = legal_of(282.0, 588, 588, 0.084, 0)
    assert lh is None and "clearance" in reason


def test_legal_of_kilit():
    lh, reason = legal_of(262.5, 588, 588, 1.1, 554)
    assert lh is None and "554 kilit" in reason


def test_legal_of_eksik_yerlesim():
    lh, reason = legal_of(193.0, 193, 588, 1.5, 0)
    assert lh is None and "193/588" in reason


def test_legal_of_coklu_sebep_hepsi_raporlanir():
    lh, reason = legal_of(100.0, 500, 588, 0.5, 3)
    assert lh is None
    assert "500/588" in reason and "clearance" in reason and "3 kilit" in reason


def test_legal_of_clearance_olculemedi_invalid():
    # kanitsizlik gecer not degildir (live-runtime kurali)
    lh, reason = legal_of(264.0, 588, 588, None, 0)
    assert lh is None and "olculemedi" in reason


# ---------------------------------------------------------------------------
# compare_verdict â€” B2 esikleri: >%2 kotu veya INVALID=FAIL; +-%0.5 gurultu;
# kotulesme yoksa ve >=1 iyilesme varsa PASS; arasi INSAN-KARARI.
# ---------------------------------------------------------------------------

def test_verdict_pass_iyilesme():
    overall, per = compare_verdict({"a": 250.0, "b": 500.0},
                                   {"a": 264.0, "b": 500.0})
    assert overall == "PASS"
    assert per["a"][1] == "iyilesme"


def test_verdict_noop_gurultu_bandi():
    overall, _ = compare_verdict({"a": 264.5}, {"a": 264.0})  # +0.19% < 0.5
    assert overall == "NOOP"


def test_verdict_fail_buyuk_kotulesme():
    overall, _ = compare_verdict({"a": 270.0}, {"a": 264.0})  # +2.27% > 2
    assert overall == "FAIL"


def test_verdict_fail_invalid_set():
    overall, per = compare_verdict({"a": None, "b": 490.0},
                                   {"a": 264.0, "b": 500.0})
    assert overall == "FAIL"          # INVALID her seyi FAIL yapar (iyilesmeye ragmen)
    assert "INVALID" in per["a"][1]


def test_verdict_insan_karari_tradeoff():
    # bir sette gurultu-ustu ama <%2 kotulesme + digerinde iyilesme -> insan karari
    overall, _ = compare_verdict({"a": 266.0, "b": 480.0},
                                 {"a": 264.0, "b": 500.0})  # a: +0.76%
    assert overall == "INSAN-KARARI"


def test_verdict_baseline_invalid_simdi_gecerli_iyilesmedir():
    overall, per = compare_verdict({"a": 264.0}, {"a": None})
    assert overall == "PASS" and "iyilesme" in per["a"][1]


def test_verdict_baseline_yok():
    overall, _ = compare_verdict({"a": 264.0}, None)
    assert overall == "BASELINE-YOK"


def test_verdict_sinir_tam_fail_esiginde_fail_degil():
    # tam +%2.0 -> FAIL degil (esik "asilirsa"); INSAN-KARARI bandi
    overall, _ = compare_verdict({"a": 102.0}, {"a": 100.0})
    assert overall == "INSAN-KARARI"


# ---------------------------------------------------------------------------
# Sprint-3 v2 sozlesmesi: sampiyon-yolu paritesi (NFV dali + no-go + 2mm)
# ---------------------------------------------------------------------------

def _mini_inst():
    from src.nesting3d.instances.format import ContainerSpec, NestingInstance, PartSpec
    return NestingInstance(
        container=ContainerSpec(width_mm=335.0, depth_mm=335.0),
        parts=[PartSpec(id="k", name="k", qty=2, source="box",
                        width_mm=30.0, depth_mm=30.0, height_mm=20.0)])


def test_clearance_req_iki_mm():
    from scripts.eval_gate import CLEARANCE_REQ_MM, legal_of
    assert CLEARANCE_REQ_MM == 2.0
    lh, reason = legal_of(100.0, 5, 5, 1.5, 0)
    assert lh is None and "clearance 1.500<2.0" in reason


def test_run_champion_nfv_dali_uretim_paritesi(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_kalite(inst, **kw):
        yakalanan.update(kw)
        return "NFV_SONUC", {"secilen": "ham"}

    class _Dec:
        mode = "nfv"
        wall_aware = False

    import src.nesting3d.nfv_solve as nfv_mod
    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(nfv_mod, "solve_nfv_kalite", sahte_kalite)
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    r = eg._run_champion("t", _mini_inst(), 42)
    assert r == "NFV_SONUC"
    assert yakalanan["clearance_mm"] == 2.0
    assert yakalanan["quality"] == "fast"          # uretim DEFAULT'u
    assert yakalanan["no_go_bounds"] == eg.NOGO_STD
    assert yakalanan["r11"] is False               # kapi CPU israfi yapmaz


def test_run_champion_heightmap_dali_nogo_tasir(monkeypatch):
    import scripts.eval_gate as eg
    yakalanan = {}

    def sahte_c2f(inst, **kw):
        yakalanan.update(kw)
        return "HM_SONUC"

    class _Dec:
        mode = "heightmap"
        wall_aware = False

    import src.nesting3d.adaptive_params as ap_mod
    monkeypatch.setattr(ap_mod, "predict_nfv_benefit", lambda inst, **k: _Dec())
    monkeypatch.setattr(eg, "solve_coarse_to_fine", sahte_c2f)
    r = eg._run_champion("t", _mini_inst(), 42)
    assert r == "HM_SONUC"
    assert yakalanan["no_go_bounds"] == eg.NOGO_STD
    assert yakalanan["clearance_mm"] == 2.0
