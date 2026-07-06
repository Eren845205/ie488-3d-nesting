# -*- coding: utf-8 -*-
"""eval_gate saf fonksiyon testleri (legal_of + compare_verdict — ANAYASA A2/B2).

Solve KOSMAZ — yalniz metrik/verdict mantigi. Kosum: pytest tests/test_eval_gate.py
"""
from scripts.eval_gate import legal_of, compare_verdict


# ---------------------------------------------------------------------------
# legal_of — A2: yerlesen==N ve clearance>=1 ve 0 kilit, aksi INVALID(sebep)
# ---------------------------------------------------------------------------

def test_legal_of_gecerli():
    lh, reason = legal_of(264.0, 588, 588, 1.023, 0)
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
# compare_verdict — B2 esikleri: >%2 kotu veya INVALID=FAIL; +-%0.5 gurultu;
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
